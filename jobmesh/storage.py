"""SQLite storage for the job index.

Responsibilities:
  * keep one row per posting (keyed by its uid),
  * track first_seen / last_checked,
  * detect when a posting changes,
  * mark postings closed when they disappear from a *successful* fetch,
  * log every fetch (success or failure) so a failed request is never
    mistaken for "all jobs closed".

SQLite keeps the project dependency-light and trivial to run locally; the
same schema maps cleanly onto Postgres later.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time as _time
from contextlib import contextmanager
from typing import Iterable, Iterator, Optional

from .models import Job, now_iso

log = logging.getLogger(__name__)

# DB location is env-configurable so a deploy can point it at a
# persistent disk (e.g. Render: JOBMESH_DB=/var/data/jobmesh.db).
DEFAULT_DB = os.getenv("JOBMESH_DB", "jobmesh.db")

# Fields compared to decide whether an existing posting has changed.
_TRACKED_FIELDS = (
    "title", "company", "location", "description", "source_url",
    "apply_url", "salary", "employment_type", "workplace_type",
    "category", "level", "remote", "posted_at",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uid             TEXT PRIMARY KEY,
    source_platform TEXT NOT NULL,
    source_board    TEXT NOT NULL,
    source_job_id   TEXT NOT NULL,
    title           TEXT,
    company         TEXT,
    location        TEXT,
    description     TEXT,
    source_url      TEXT,
    apply_url       TEXT,
    salary          TEXT,
    employment_type TEXT,
    workplace_type  TEXT,
    category        TEXT,
    level           TEXT,
    remote          INTEGER,
    posted_at       TEXT,
    dedup_key       TEXT,
    first_seen      TEXT,
    last_checked    TEXT,
    last_changed    TEXT,
    country         TEXT,
    is_open         INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_jobs_board   ON jobs(source_platform, source_board);
CREATE INDEX IF NOT EXISTS idx_jobs_dedup   ON jobs(dedup_key);
CREATE INDEX IF NOT EXISTS idx_jobs_open    ON jobs(is_open);
CREATE INDEX IF NOT EXISTS idx_jobs_sortdate ON jobs(is_open, COALESCE(posted_at, first_seen) DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_platform ON jobs(source_platform, is_open);
CREATE INDEX IF NOT EXISTS idx_jobs_posted   ON jobs(posted_at);
CREATE INDEX IF NOT EXISTS idx_jobs_changed  ON jobs(last_changed, uid);
CREATE INDEX IF NOT EXISTS idx_jobs_lastseen ON jobs(last_checked);
CREATE INDEX IF NOT EXISTS idx_jobs_firstseen ON jobs(first_seen);

CREATE TABLE IF NOT EXISTS fetch_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    platform   TEXT NOT NULL,
    board      TEXT NOT NULL,
    status     TEXT NOT NULL,          -- 'success' or 'failure'
    job_count  INTEGER,
    error      TEXT,
    ran_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT,
    message    TEXT NOT NULL,
    lang       TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# --- optional Turso / libSQL embedded-replica backend --------------------
# When JOBMESH_DB_URL is set, the local SQLite file becomes an embedded replica
# of a Turso database: pulled on a cold start and pushed after writes, so the
# index survives redeploys on an ephemeral host. Every query still runs against
# the local file; a thin wrapper keeps sqlite3.Row-style access (row["col"],
# dict(row), iteration, lastrowid) working, so no app query code changes.

_WRITE_PREFIXES = ("insert", "update", "delete", "replace", "create", "alter", "drop")


class _Row:
    """sqlite3.Row-like view over a tuple, with name and index access."""
    __slots__ = ("_idx", "_vals")

    def __init__(self, idx: dict, vals):
        self._idx = idx
        self._vals = tuple(vals)

    def __getitem__(self, key):
        return self._vals[self._idx[key]] if isinstance(key, str) else self._vals[key]

    def keys(self):
        return list(self._idx)

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


class _Cursor:
    def __init__(self, cur):
        self._cur = cur
        self._idx = None

    def _index(self):
        if self._idx is None:
            self._idx = {d[0]: i for i, d in enumerate(self._cur.description or ())}
        return self._idx

    def _wrap(self, row):
        return None if row is None else _Row(self._index(), row)

    def fetchone(self):
        return self._wrap(self._cur.fetchone())

    def fetchall(self):
        return [self._wrap(r) for r in self._cur.fetchall()]

    def __iter__(self):
        for r in self._cur.fetchall():
            yield self._wrap(r)

    @property
    def lastrowid(self):
        return self._cur.lastrowid


class _LibsqlConn:
    """Minimal sqlite3-compatible facade over a libSQL embedded-replica conn."""

    def __init__(self, raw):
        self._raw = raw
        self._dirty = False

    def execute(self, sql, params=()):
        if sql.lstrip().lower().startswith(_WRITE_PREFIXES):
            self._dirty = True
        return _Cursor(self._raw.execute(sql, params))

    def executemany(self, sql, seq_of_params):
        self._dirty = True
        self._raw.executemany(sql, list(seq_of_params))

    def executescript(self, script: str):
        self._dirty = True
        for stmt in script.split(";"):
            if stmt.strip():
                self._raw.execute(stmt)

    def commit(self):
        self._raw.commit()

    def sync(self):
        self._raw.sync()

    def close(self):
        try:
            if self._dirty:
                self._raw.commit()
                self._raw.sync()
        finally:
            closer = getattr(self._raw, "close", None)
            if callable(closer):
                closer()


def _connect_libsql(db_path: str, url: str):
    import libsql_experimental as libsql  # imported only when the backend is on

    token = os.getenv("JOBMESH_DB_TOKEN")
    cold = (not os.path.exists(db_path)) or os.path.getsize(db_path) == 0
    raw = libsql.connect(db_path, sync_url=url, auth_token=token)
    if cold:
        raw.sync()  # pull the whole database from Turso on a cold start
    conn = _LibsqlConn(raw)
    conn.executescript(_SCHEMA)  # idempotent (CREATE ... IF NOT EXISTS)
    _migrate(conn)
    migrate_heavy(conn)
    conn._raw.commit()
    conn._raw.sync()  # push the schema / migrations on first deploy
    conn._dirty = False
    return conn


def connect(db_path: str = DEFAULT_DB):
    url = os.getenv("JOBMESH_DB_URL")
    if url:
        try:
            return _connect_libsql(db_path, url)
        except Exception as exc:  # keep the site alive if Turso is unreachable
            log.warning("Turso/libSQL backend unavailable (%s); using local SQLite", exc)
    # timeout: wait (don't error) if another connection holds the write lock.
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    # Wait (don't error) when another connection holds the write lock.
    conn.execute("PRAGMA busy_timeout=30000")
    # WAL lets readers and a single writer coexist without corrupting the file
    # (e.g. the web server reading while `ingest` writes). Some filesystems
    # (certain network/overlay mounts) reject WAL with a disk I/O error, so
    # fall back silently to the default rollback journal there.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.OperationalError:
        pass
    # Migrate once per process per database: the schema/FTS persist on disk, so
    # later connections in the same process skip the (count-checking) migration.
    if db_path not in _MIGRATED:
        conn.executescript(_SCHEMA)
        _migrate(conn)                 # fast DDL only
        _MIGRATED.add(db_path)
        if not DEFER_HEAVY_MIGRATION:  # tests / CLI / local: do the heavy part now
            migrate_heavy(conn)
    return conn


# FTS5 full-text index over the short, high-signal fields (title, company,
# location). Kept in sync by triggers; the UPDATE trigger fires only when one
# of those fields actually changes, so re-opening a posting or stamping
# last_checked each cycle never re-indexes it.
_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts
    USING fts5(title, company, location, country, tokenize='unicode61');

CREATE TRIGGER IF NOT EXISTS jobs_fts_ai AFTER INSERT ON jobs BEGIN
    INSERT INTO jobs_fts(rowid, title, company, location, country)
    VALUES (new.rowid, new.title, new.company, new.location, new.country);
END;
CREATE TRIGGER IF NOT EXISTS jobs_fts_ad AFTER DELETE ON jobs BEGIN
    DELETE FROM jobs_fts WHERE rowid = old.rowid;
END;
CREATE TRIGGER IF NOT EXISTS jobs_fts_au
    AFTER UPDATE OF title, company, location, country ON jobs
    WHEN new.title IS NOT old.title OR new.company IS NOT old.company
         OR new.location IS NOT old.location OR new.country IS NOT old.country
BEGIN
    DELETE FROM jobs_fts WHERE rowid = old.rowid;
    INSERT INTO jobs_fts(rowid, title, company, location, country)
    VALUES (new.rowid, new.title, new.company, new.location, new.country);
END;
"""


def _ensure_fts(conn: sqlite3.Connection) -> bool:
    """Create the FTS5 table + sync triggers and backfill when out of sync.

    Returns False (degrading to LIKE search) if FTS5 is unavailable in this
    SQLite build. rowids are stable here (the app never VACUUMs), so a plain
    count mismatch is enough to trigger a one-off rebuild (e.g. first deploy
    on an existing database)."""
    try:
        # An older index has only (title, company, location). Rebuild it to add
        # the country column (so a country filter runs inside the FTS match).
        cols = [r[1] for r in conn.execute("PRAGMA table_info(jobs_fts)")]
        if cols and "country" not in cols:
            conn.execute("DROP TABLE IF EXISTS jobs_fts")
            for trig in ("jobs_fts_ai", "jobs_fts_ad", "jobs_fts_au"):
                conn.execute(f"DROP TRIGGER IF EXISTS {trig}")
        conn.executescript(_FTS_SCHEMA)
        n_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        n_fts = conn.execute("SELECT COUNT(*) FROM jobs_fts").fetchone()[0]
        if n_jobs and n_fts != n_jobs:
            conn.execute("DELETE FROM jobs_fts")
            conn.execute("INSERT INTO jobs_fts(rowid, title, company, location, country) "
                         "SELECT rowid, title, company, location, country FROM jobs")
            conn.commit()
        return True
    except sqlite3.OperationalError as exc:  # no FTS5 in this build
        log.warning("FTS5 unavailable (%s); keyword search falls back to LIKE", exc)
        return False


def _backfill_country(conn: sqlite3.Connection) -> None:
    """Populate the country column for rows that don't have it yet (one-off).

    Batched with a per-distinct-location cache so a 400k-row backfill is a few
    seconds, not one UPDATE per row."""
    from .geo import resolve_country
    cache: dict[str, Optional[str]] = {}
    batch: list[tuple] = []
    rows = conn.execute(
        "SELECT rowid, location FROM jobs WHERE country IS NULL AND location IS NOT NULL"
    ).fetchall()
    for rid, loc in rows:
        if loc in cache:
            c = cache[loc]
        else:
            c = resolve_country(loc)
            cache[loc] = c
        if c:
            batch.append((c, rid))
            if len(batch) >= 5000:
                conn.executemany("UPDATE jobs SET country=? WHERE rowid=?", batch)
                batch = []
    if batch:
        conn.executemany("UPDATE jobs SET country=? WHERE rowid=?", batch)
    conn.commit()


_MIGRATED: set = set()   # db paths whose fast schema this process has ensured
_HEAVY_DONE: set = set()  # db paths whose heavy migration (backfill/FTS rebuild) is done
_HEAVY_LOCK = threading.Lock()
# The deployed server sets this True so startup stays fast: the heavy migration
# (country backfill, FTS rebuild) then runs in a background thread and keyword
# search falls back to LIKE until it finishes. Off for tests/CLI/local, where
# the heavy migration runs synchronously on first connect (as before).
DEFER_HEAVY_MIGRATION = False


def _fts_available() -> bool:
    """Whether the FTS index is ready to serve. During a deferred heavy
    migration it may be missing or the wrong shape, so search uses LIKE."""
    return (not DEFER_HEAVY_MIGRATION) or bool(_HEAVY_DONE)


def _migrate(conn: sqlite3.Connection) -> None:
    """Fast, synchronous schema shape: add any missing columns and create the
    indexes and the FTS table + triggers. No row backfills and no FTS rebuild --
    those are the heavy part (``migrate_heavy``), deferred on the server so
    startup answers in seconds."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for col in ("workplace_type", "category", "level"):
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")
    if "country" not in existing:
        conn.execute("ALTER TABLE jobs ADD COLUMN country TEXT")
    conn.commit()
    # Indexes/FTS from _SCHEMA may post-date the table: re-apply idempotently.
    conn.executescript(_SCHEMA)
    conn.execute('CREATE INDEX IF NOT EXISTS idx_jobs_country ON jobs(country, is_open)')
    # Create the FTS table + triggers if absent (fast). An existing index of the
    # wrong shape is left as-is here and rebuilt by migrate_heavy().
    try:
        conn.executescript(_FTS_SCHEMA)
    except sqlite3.OperationalError:
        pass   # FTS5 not available in this build -> LIKE search
    conn.commit()


def migrate_heavy(conn: sqlite3.Connection) -> None:
    """Slow data migrations: backfill the country column and rebuild the FTS
    index when its columns or row count are out of date. Safe to run in the
    background -- keyword search falls back to LIKE until it finishes."""
    _backfill_country(conn)   # only touches rows with country IS NULL (no-op once done)
    _ensure_fts(conn)         # rebuilds (drop + reindex) if columns/count differ
    conn.commit()


def run_heavy_migration(db_path: str = DEFAULT_DB) -> float:
    """Run migrate_heavy once per db_path, under a lock. Returns seconds taken.
    Used by the server's background thread after a fast startup."""
    if db_path in _HEAVY_DONE:
        return 0.0
    with _HEAVY_LOCK:
        if db_path in _HEAVY_DONE:
            return 0.0
        t = _time.time()
        with session(db_path) as conn:
            migrate_heavy(conn)
            # Fresh FTS has no query-planner stats until the next cycle-end
            # optimize (~hours away), which makes search pick poor plans right
            # after a deploy. Refresh stats now, as soon as the index is rebuilt.
            try:
                conn.execute("PRAGMA optimize")
            except Exception:
                pass
        _HEAVY_DONE.add(db_path)
        took = _time.time() - t
        log.info("heavy migration complete for %s in %.1fs", db_path, took)
        return took


@contextmanager
def session(db_path: str = DEFAULT_DB) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# -- writes ---------------------------------------------------------------

def _country_of(location):
    """ISO-2 country code for a location string (cached), or None."""
    if not location:
        return None
    from .geo import resolve_country
    return resolve_country(location)


def upsert_jobs(conn: sqlite3.Connection, jobs: Iterable[Job]) -> dict:
    """Insert new postings and update existing ones.

    Returns counts: {"new": n, "updated": n, "unchanged": n}.
    An update refreshes last_checked, reopens a previously-closed posting,
    and stamps last_changed only when a tracked field actually changed.
    """
    now = now_iso()
    new = updated = unchanged = 0

    for job in jobs:
        row = conn.execute(
            "SELECT * FROM jobs WHERE uid = ?", (job.uid,)
        ).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT INTO jobs (
                    uid, source_platform, source_board, source_job_id,
                    title, company, location, description, source_url,
                    apply_url, salary, employment_type, workplace_type,
                    category, level, remote, posted_at, dedup_key, first_seen,
                    last_checked, last_changed, country, is_open
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                (
                    job.uid, job.source_platform, job.source_board,
                    job.source_job_id, job.title, job.company, job.location,
                    job.description, job.source_url, job.apply_url, job.salary,
                    job.employment_type, job.workplace_type, job.category,
                    job.level, _bool(job.remote), job.posted_at, job.dedup_key,
                    now, now, now, _country_of(job.location),
                ),
            )
            new += 1
            continue

        changed = _has_changed(row, job)
        conn.execute(
            """
            UPDATE jobs SET
                title=?, company=?, location=?, description=?, source_url=?,
                apply_url=?, salary=?, employment_type=?, workplace_type=?,
                category=?, level=?, remote=?, posted_at=?, dedup_key=?, last_checked=?,
                last_changed=?, country=?, is_open=1
            WHERE uid=?
            """,
            (
                job.title, job.company, job.location, job.description,
                job.source_url, job.apply_url, job.salary, job.employment_type,
                job.workplace_type, job.category, job.level, _bool(job.remote),
                job.posted_at, job.dedup_key, now,
                now if changed else row["last_changed"],
                _country_of(job.location), job.uid,
            ),
        )
        if changed:
            updated += 1
        else:
            unchanged += 1

    return {"new": new, "updated": updated, "unchanged": unchanged}


def close_absent(
    conn: sqlite3.Connection,
    platform: str,
    board: str,
    seen_uids: set[str],
) -> int:
    """Mark postings of this board closed if they weren't in the fetch.

    Call this ONLY after a successful fetch. Returns the number closed.
    """
    now = now_iso()
    rows = conn.execute(
        "SELECT uid FROM jobs WHERE source_platform=? AND source_board=? "
        "AND is_open=1",
        (platform, board),
    ).fetchall()

    open_before = len(rows)
    to_close = [r["uid"] for r in rows if r["uid"] not in seen_uids]

    # Guard against false mass-closures from an incomplete/throttled fetch.
    # If a board that currently has many open postings suddenly returns far
    # fewer than half of them, the fetch was almost certainly rate-limited or
    # cut short (not a genuine mass-expiry), so keep the existing postings open
    # rather than closing real jobs. A later healthy fetch closes any that are
    # truly gone.
    if open_before >= 20 and len(seen_uids) < open_before * 0.5:
        log.warning(
            "close_absent: incomplete fetch for %s/%s (%d seen vs %d open) \u2014 "
            "skipping close of %d postings to avoid false closures",
            platform, board, len(seen_uids), open_before, len(to_close),
        )
        return 0

    for uid in to_close:
        conn.execute(
            "UPDATE jobs SET is_open=0, last_checked=?, last_changed=? "
            "WHERE uid=?",
            (now, now, uid),
        )
    return len(to_close)


def log_fetch(
    conn: sqlite3.Connection,
    platform: str,
    board: str,
    status: str,
    job_count: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO fetch_log (platform, board, status, job_count, error, "
        "ran_at) VALUES (?,?,?,?,?,?)",
        (platform, board, status, job_count, error, now_iso()),
    )


# -- reads ----------------------------------------------------------------

def _filter_clauses(f: dict, exclude=None, alias: str = ""):
    """(clauses, params) for a filter dict. `alias` (e.g. "j.") qualifies the
    columns so the same builder works in a plain query and in an FTS join.
    `exclude` is a field name or a set of field names to skip."""
    a = alias
    ex = (exclude if isinstance(exclude, (set, frozenset, list, tuple))
          else ({exclude} if exclude else set()))
    clauses, params = [], []
    if f.get("open_only", True):
        clauses.append(f"{a}is_open = 1")
    if f.get("keyword") and "keyword" not in ex:
        for tok in str(f["keyword"]).split():
            clauses.append(f"({a}title LIKE ? OR {a}description LIKE ?)")
            params += [f"%{tok}%", f"%{tok}%"]
    if f.get("company") and "company" not in ex:
        clauses.append(f"{a}company LIKE ?"); params.append(f"%{f['company']}%")
    if f.get("location") and "location" not in ex:
        clauses.append(f"{a}location LIKE ?"); params.append(f"%{f['location']}%")
    if f.get("platform") and "platform" not in ex:
        clauses.append(f"{a}source_platform = ?"); params.append(f["platform"])
    if f.get("workplace_type") and "workplace_type" not in ex:
        clauses.append(f"{a}workplace_type = ?"); params.append(f["workplace_type"])
    if f.get("employment_type") and "employment_type" not in ex:
        clauses.append(f"{a}employment_type = ?"); params.append(f["employment_type"])
    if f.get("category") and "category" not in ex:
        clauses.append(f"{a}category = ?"); params.append(f["category"])
    if f.get("level") and "level" not in ex:
        clauses.append(f"{a}level = ?"); params.append(f["level"])
    if f.get("country") and "country" not in ex:
        # Indexed country column (populated at ingest). Fall back to a name
        # match only for a value the column can't carry (shouldn't happen).
        code = str(f["country"]).upper()
        clauses.append(f"{a}country = ?"); params.append(code)
    if f.get("since") and "since" not in ex:
        try:
            _days = int(f["since"])
        except (TypeError, ValueError):
            _days = 0
        if _days > 0:
            from datetime import datetime, timezone, timedelta
            _cut = (datetime.now(timezone.utc) - timedelta(days=_days)).strftime("%Y-%m-%d")
            clauses.append(f"substr(COALESCE({a}posted_at, {a}first_seen),1,10) >= ?")
            params.append(_cut)
    if f.get("posted_after") and "posted_after" not in ex:
        clauses.append(f"substr(COALESCE({a}posted_at, {a}first_seen),1,10) >= ?")
        params.append(str(f["posted_after"])[:10])
    if f.get("seen_within") and "seen_within" not in ex:
        try:
            _sw = int(f["seen_within"])
        except (TypeError, ValueError):
            _sw = 0
        if _sw > 0:
            from datetime import datetime, timezone, timedelta
            _swc = (datetime.now(timezone.utc) - timedelta(days=_sw)).strftime("%Y-%m-%d")
            clauses.append(f"substr({a}first_seen,1,10) >= ?")
            params.append(_swc)
    if f.get("has_salary") and "has_salary" not in ex:
        clauses.append(f"{a}salary IS NOT NULL AND TRIM({a}salary) != ''")
    return clauses, params


def _build_where(f: dict, exclude: Optional[str] = None):
    clauses, params = _filter_clauses(f, exclude=exclude, alias="")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


_FTS_RANK_CAP = int(os.getenv("FTS_RANK_CAP", "1000"))
# Keyword result counts are bounded: beyond this the UI shows "N+".
COUNT_CAP = int(os.getenv("SEARCH_COUNT_CAP", "10000"))


_FTS_TEXT_COLS = "title company location"


def _fts_match(tokens: list[str], country: str | None = None) -> str:
    """FTS5 MATCH expression. The query tokens (every one required) are scoped
    to the text columns so a term that happens to equal a country code can't
    match the country column; an optional country filter is applied inside the
    index via the country column, so a country filter needs no per-row probe."""
    safe = ['"' + t.replace('"', '') + '"' for t in tokens if t.strip()]
    expr = "{" + _FTS_TEXT_COLS + "} : (" + " ".join(safe) + ")" if safe else ""
    if country:
        cc = str(country).lower().replace('"', '')
        tag = 'country : ("' + cc + '")'
        expr = (expr + " AND " + tag) if expr else tag
    return expr


# One row per role: the same posting indexed from several sources shares a
# dedup_key, so search collapses a group to its best representative and reports
# the other sources. A NULL/empty dedup_key is its own group (its uid).
def _enrich_groups(conn: sqlite3.Connection, rows: list[dict]) -> list[dict]:
    """Attach group_size and other_source_urls (the duplicate postings of the
    same role on other sources) to each representative row."""
    keys = sorted({r["dedup_key"] for r in rows
                   if r.get("dedup_key")})
    agg: dict = {}
    if keys:
        ph = ",".join("?" * len(keys))
        for k, n, urls in conn.execute(
            f"SELECT dedup_key, COUNT(*) AS n, "
            f"GROUP_CONCAT(source_url, char(10)) AS urls "
            # +is_open disables the is_open index so the selective dedup_key
            # index drives the lookup (otherwise SQLite scans all open rows).
            f"FROM jobs WHERE dedup_key IN ({ph}) AND +is_open = 1 "
            f"GROUP BY dedup_key", keys):
            agg[k] = (n, (urls or "").split("\n"))
    for r in rows:
        r.pop("_r", None); r.pop("_d", None)
        k = r.get("dedup_key")
        n, urls = agg.get(k, (1, []))
        r["group_size"] = n
        r["other_source_urls"] = [u for u in urls if u and u != r.get("source_url")]
    return rows


def search(conn: sqlite3.Connection, limit: int = 20, offset: int = 0,
           **filters) -> list[dict]:
    """Filtered, paginated search.

    A keyword goes through the FTS5 index (title/company/location) ranked by
    bm25 with the title weighted highest; there the same role indexed from
    several sources (one dedup_key) collapses to one representative, with the
    other sources reported on it. Non-keyword listings stay a plain indexed
    query. Everything is de-duplicated for display either way: keyword results
    collapse in SQL (bounded by the FTS top-k), and the plain path is
    collapsed in Python over the page."""
    tokens = str(filters.get("keyword") or "").split()
    if tokens and _fts_available():
        clauses, params = _filter_clauses(
            filters, exclude={"keyword", "country"}, alias="j2.")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        # The country filter rides inside the FTS match (country column), so the
        # top-k is already country-restricted -- no per-row country probe.
        match = _fts_match(tokens, filters.get("country"))
        sql = (
            "SELECT j.* FROM ("
            " SELECT j2.rowid AS rid, MIN(m.rank) AS r, "
            "        COALESCE(j2.posted_at, j2.first_seen) AS d"
            "  FROM (SELECT rowid, bm25(jobs_fts, 10.0, 3.0, 1.0, 0.0) AS rank"
            "        FROM jobs_fts WHERE jobs_fts MATCH ? ORDER BY rank LIMIT ?) m"
            "  CROSS JOIN jobs j2 ON j2.rowid = m.rowid"
            f"{where}"
            "  GROUP BY COALESCE(NULLIF(j2.dedup_key, ''), j2.uid)"
            "  ORDER BY r, d DESC LIMIT ? OFFSET ?"
            ") g JOIN jobs j ON j.rowid = g.rid ORDER BY g.r, g.d DESC"
        )
        try:
            rows = [dict(r) for r in conn.execute(
                sql, [match, _FTS_RANK_CAP] + params
                + [limit, offset]).fetchall()]
            return _enrich_groups(conn, rows)
        except sqlite3.OperationalError:
            pass  # FTS5 not available in this build -> LIKE fallback below
    # Plain path: fast indexed query, then collapse same-role duplicates within
    # the returned page (cheap; a broad listing stays index-fast).
    where, params = _build_where(filters)
    date_order = "COALESCE(posted_at, first_seen) DESC"
    over = max(limit * 3, limit + 20)   # fetch a little extra to refill after collapse
    if tokens:
        score = " + ".join("(CASE WHEN title LIKE ? THEN 1 ELSE 0 END)" for _ in tokens)
        sql = (f"SELECT * FROM jobs {where} "
               f"ORDER BY ({score}) DESC, {date_order} LIMIT ? OFFSET ?")
        order_params = [f"%{t}%" for t in tokens]
        raw = [dict(r) for r in conn.execute(
            sql, params + order_params + [over, offset]).fetchall()]
    else:
        sql = f"SELECT * FROM jobs {where} ORDER BY {date_order} LIMIT ? OFFSET ?"
        raw = [dict(r) for r in conn.execute(
            sql, params + [over, offset]).fetchall()]
    seen: set = set()
    rows = []
    for row in raw:
        key = row.get("dedup_key") or row.get("uid")
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        if len(rows) >= limit:
            break
    return _enrich_groups(conn, rows)


def count(conn: sqlite3.Connection, cap: int | None = None, **filters) -> int:
    """Postings matching the filters. Keyword counts are bounded at `cap`
    (default COUNT_CAP): the query stops once it has seen cap+1 rows, so a
    broad term stays fast and the UI shows e.g. "10,000+". Results are
    de-duplicated for display; the count is of raw matches."""
    tokens = str(filters.get("keyword") or "").split()
    if tokens and _fts_available():
        cap = COUNT_CAP if cap is None else cap
        clauses, params = _filter_clauses(
            filters, exclude={"keyword", "country"}, alias="j.")
        # Country rides inside the FTS match (country column); only the remaining
        # filters (if any) still need a per-row probe.
        match = _fts_match(tokens, filters.get("country"))
        extra_clauses = [c for c in clauses if "is_open" not in c]
        lim = f" LIMIT {cap + 1}" if cap else ""
        # "Selective" = a country or another filter narrows the match. Then the
        # candidate set coming out of the FTS index is small (country is indexed
        # inside the match), so we can afford the per-row is_open/other probe and
        # return an exact open count. A broad term with no such filter would
        # instead probe up to cap rows, so there we count straight from the FTS
        # index (a few ms; the open/closed skew is bounded and the UI caps at N+).
        selective = bool(filters.get("country")) or bool(extra_clauses)
        try:
            if not selective:
                return conn.execute(
                    "SELECT COUNT(*) FROM "
                    f"(SELECT 1 FROM jobs_fts WHERE jobs_fts MATCH ?{lim})",
                    [match]).fetchone()[0]
            # CROSS JOIN forces the FTS index to drive the scan (SQLite would
            # otherwise pick the is_open index and probe FTS per row -> slow).
            extra = (" AND " + " AND ".join(clauses)) if clauses else ""
            return conn.execute(
                "SELECT COUNT(*) FROM (SELECT 1 "
                "FROM jobs_fts f CROSS JOIN jobs j ON j.rowid = f.rowid "
                f"WHERE jobs_fts MATCH ?{extra}{lim})",
                [match] + params).fetchone()[0]
        except sqlite3.OperationalError:
            pass
    where, params = _build_where(filters)
    return conn.execute(f"SELECT COUNT(*) FROM jobs {where}", params).fetchone()[0]


def facets(conn: sqlite3.Connection, **filters) -> dict:
    """Return the total plus value counts for each filterable field.

    Each field's counts ignore that field's own current selection, so the
    dropdowns show how many jobs each option would yield.
    """
    out = {"total": count(conn, **filters)}
    # (column, filter-key) — the platform column and its filter key differ.
    for field, key in (
        ("workplace_type", "workplace_type"),
        ("employment_type", "employment_type"),
        ("level", "level"),
        ("category", "category"),
        ("source_platform", "platform"),
    ):
        where, params = _build_where(filters, exclude=key)
        where = (where + f" AND {field} IS NOT NULL") if where \
            else f"WHERE {field} IS NOT NULL"
        rows = conn.execute(
            f"SELECT {field} AS v, COUNT(*) AS n FROM jobs {where} "
            f"GROUP BY {field} ORDER BY n DESC",
            params,
        ).fetchall()
        out[field] = {r["v"]: r["n"] for r in rows}
    return out


def add_feedback(conn: sqlite3.Connection, message: str,
                 name: Optional[str] = None, lang: Optional[str] = None) -> dict:
    """Store one visitor feedback entry and return it."""
    msg = (message or "").strip()[:2000]
    nm = (name or "").strip()[:80] or None
    now = now_iso()
    cur = conn.execute(
        "INSERT INTO feedback (name, message, lang, created_at) "
        "VALUES (?,?,?,?)", (nm, msg, lang, now))
    return {"id": cur.lastrowid, "name": nm, "message": msg,
            "lang": lang, "created_at": now}


def list_feedback(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    """Most recent feedback entries."""
    rows = conn.execute(
        "SELECT id, name, message, lang, created_at FROM feedback "
        "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def location_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Open-posting counts grouped by raw location string."""
    rows = conn.execute(
        "SELECT location AS loc, COUNT(*) AS n FROM jobs "
        "WHERE is_open=1 AND location IS NOT NULL AND location <> '' "
        "GROUP BY location"
    ).fetchall()
    return {r["loc"]: r["n"] for r in rows}


def set_meta(conn: sqlite3.Connection, key: str, value) -> None:
    """Store a small key/value fact about the index (e.g. last ingest time)."""
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, None if value is None else str(value)),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default=None):
    """Read a meta value, or `default` if the key was never set."""
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row and row[0] is not None else default


def record_ingest_run(conn: sqlite3.Connection, results, started_ts: float,
                      finished_ts: float) -> None:
    """Persist a one-line summary of an ingest run (for the status page and the
    "last updated" display). `results` is a list of objects with .status,
    .platform and .board. A board that failed to fetch is recorded as a fetch
    failure, never as proof its jobs closed."""
    import json
    from datetime import datetime, timezone

    def _iso(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")

    failed = [f"{r.platform}/{r.board}" for r in results
              if getattr(r, "status", None) == "failure"]
    ok = [r for r in results if getattr(r, "status", None) == "success"]
    set_meta(conn, "last_ingest_started", _iso(started_ts))
    set_meta(conn, "last_ingest_finished", _iso(finished_ts))
    set_meta(conn, "last_ingest_seconds",
             f"{max(0.0, finished_ts - started_ts):.1f}")
    set_meta(conn, "last_ingest_boards", str(len(results)))
    set_meta(conn, "last_ingest_ok", str(len(ok)))
    set_meta(conn, "last_ingest_failed", str(len(failed)))
    set_meta(conn, "last_ingest_failed_sources", json.dumps(failed))


def _rotation_info(conn) -> dict | None:
    """Parsed ``rotation_info`` meta (platforms fetched on a rotating schedule),
    or None when nothing is rotating."""
    raw = get_meta(conn, "rotation_info")
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return info or None


def compute_stats_aggregates(conn: sqlite3.Connection) -> dict:
    """The expensive headline aggregates (full COUNT/DISTINCT/GROUP BY).

    Run once at the end of a cycle and cached in meta; never on a request."""
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    open_ = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_open=1").fetchone()[0]
    boards = conn.execute(
        "SELECT COUNT(DISTINCT source_platform || ':' || source_board) FROM jobs"
    ).fetchone()[0]
    dupes = conn.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT dedup_key) FROM jobs "
        "WHERE is_open=1 AND dedup_key IS NOT NULL"
    ).fetchone()[0]
    companies = conn.execute(
        "SELECT COUNT(DISTINCT company) FROM jobs "
        "WHERE is_open=1 AND company IS NOT NULL AND company <> ''"
    ).fetchone()[0]
    platforms = conn.execute(
        "SELECT COUNT(DISTINCT source_platform) FROM jobs WHERE is_open=1"
    ).fetchone()[0]
    by_platform = {
        r["source_platform"]: r["n"]
        for r in conn.execute(
            "SELECT source_platform, COUNT(*) AS n FROM jobs "
            "WHERE is_open=1 GROUP BY source_platform"
        ).fetchall()
    }
    return {
        "total_postings": total,
        "open_postings": open_,
        "closed_postings": total - open_,
        "boards_indexed": boards,
        "platforms": platforms,
        "companies": companies,
        "duplicate_open_postings": dupes,
        "open_by_platform": by_platform,
    }


def refresh_stats_cache(conn: sqlite3.Connection) -> dict:
    """Recompute the headline aggregates and cache them in meta (JSON)."""
    agg = compute_stats_aggregates(conn)
    set_meta(conn, "stats_cache", json.dumps(agg))
    return agg


def stats(conn: sqlite3.Connection) -> dict:
    """Headline numbers about the current index.

    The heavy aggregates come from the per-cycle cache in meta (served in a few
    ms); only cheap live meta is read per request. The cache is backfilled on
    first use if a cycle hasn't populated it yet."""
    raw = get_meta(conn, "stats_cache")
    agg = None
    if raw:
        try:
            agg = json.loads(raw)
        except (ValueError, TypeError):
            agg = None
    if agg is None:
        agg = refresh_stats_cache(conn)      # one-off backfill, then cached
    return {
        **agg,
        "last_updated": get_meta(conn, "last_ingest_finished"),
        "last_ingest_seconds": (
            float(get_meta(conn, "last_ingest_seconds"))
            if get_meta(conn, "last_ingest_seconds") else None),
        "last_ingest_boards": (
            int(get_meta(conn, "last_ingest_boards"))
            if get_meta(conn, "last_ingest_boards") else None),
        "sources_failed_last_run": (
            int(get_meta(conn, "last_ingest_failed"))
            if get_meta(conn, "last_ingest_failed") else 0),
        "ingesting": get_meta(conn, "ingesting") == "1",
        "refresh_interval_hours": (
            float(os.getenv("INGEST_INTERVAL_HOURS"))
            if os.getenv("INGEST_INTERVAL_HOURS") else None),
        "rotation": _rotation_info(conn),
    }


def open_counts_by_board(conn: sqlite3.Connection) -> dict:
    """Open-posting counts keyed by (source_platform, source_board).

    Lets the status page attribute per-platform totals for connectors that
    serve several required platforms from one engine (e.g. the shared feed
    parser), by summing a platform's own boards — each board counted once.
    """
    rows = conn.execute(
        "SELECT source_platform AS p, source_board AS b, COUNT(*) AS n "
        "FROM jobs WHERE is_open=1 GROUP BY source_platform, source_board"
    ).fetchall()
    return {(r["p"], r["b"]): r["n"] for r in rows}


def coverage(conn: sqlite3.Connection) -> dict:
    """Per-platform coverage: open jobs, boards and last-fetch health.

    Powers a transparent "status page": which source platforms are live,
    how many open roles each carries, and whether the last refresh of each
    succeeded (from fetch_log). Every number traces back to a real fetch.
    """
    rows = conn.execute(
        "SELECT source_platform AS platform, COUNT(*) AS open_jobs, "
        "COUNT(DISTINCT source_board) AS boards "
        "FROM jobs WHERE is_open=1 GROUP BY source_platform "
        "ORDER BY open_jobs DESC"
    ).fetchall()
    last = {
        r["platform"]: {"status": r["status"], "ran_at": r["ran_at"]}
        for r in conn.execute(
            "SELECT platform, status, ran_at FROM fetch_log "
            "WHERE id IN (SELECT MAX(id) FROM fetch_log GROUP BY platform)"
        ).fetchall()
    }
    platforms = []
    for r in rows:
        p = r["platform"]
        platforms.append({
            "platform": p,
            "open_jobs": r["open_jobs"],
            "boards": r["boards"],
            "last_run": last.get(p, {}).get("ran_at"),
            "last_status": last.get(p, {}).get("status"),
        })
    return {"platforms_live": len(platforms), "platforms": platforms}


# -- helpers --------------------------------------------------------------

def _bool(value: Optional[bool]) -> Optional[int]:
    return None if value is None else int(bool(value))


def _has_changed(row: sqlite3.Row, job: Job) -> bool:
    for field in _TRACKED_FIELDS:
        old = row[field]
        new = getattr(job, field)
        if field == "remote":
            new = _bool(new)
        if (old or None) != (new or None):
            return True
    return False


# --- Read helpers for the public API (jobs by id/url, companies, facets,
#     suggestions, change feed) --------------------------------------------

def get_job(conn: sqlite3.Connection, uid: str):
    """One posting by its uid (primary key), or None."""
    r = conn.execute("SELECT * FROM jobs WHERE uid = ?", (uid,)).fetchone()
    return dict(r) if r else None


def get_job_by_url(conn: sqlite3.Connection, url: str):
    """One posting by its source_url or apply_url (open preferred), or None."""
    if not url:
        return None
    r = conn.execute(
        "SELECT * FROM jobs WHERE source_url = ? OR apply_url = ? "
        "ORDER BY is_open DESC LIMIT 1", (url, url)).fetchone()
    return dict(r) if r else None


def list_companies(conn: sqlite3.Connection, limit: int = 100, offset: int = 0,
                   q: str | None = None, open_only: bool = True):
    """(total, rows) of companies with their open-job counts, most first."""
    cond = "WHERE is_open = 1" if open_only else "WHERE 1 = 1"
    cond += " AND company IS NOT NULL AND TRIM(company) != ''"
    params: list = []
    if q:
        cond += " AND company LIKE ?"
        params.append(f"%{q}%")
    total = conn.execute(
        f"SELECT COUNT(DISTINCT company) FROM jobs {cond}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT company, COUNT(*) AS n FROM jobs {cond} "
        f"GROUP BY company ORDER BY n DESC, company ASC LIMIT ? OFFSET ?",
        params + [limit, offset]).fetchall()
    return total, [{"company": r["company"], "open_jobs": r["n"]} for r in rows]


def filter_values(conn: sqlite3.Connection, open_only: bool = True) -> dict:
    """Distinct values (with counts) for each filterable field."""
    cond = "WHERE is_open = 1" if open_only else "WHERE 1 = 1"

    def vals(col: str):
        rows = conn.execute(
            f"SELECT {col} AS v, COUNT(*) AS n FROM jobs {cond} "
            f"AND {col} IS NOT NULL AND TRIM({col}) != '' "
            f"GROUP BY {col} ORDER BY n DESC LIMIT 200").fetchall()
        return [{"value": r["v"], "count": r["n"]} for r in rows]

    return {
        "platform": vals("source_platform"),
        "category": vals("category"),
        "level": vals("level"),
        "employment_type": vals("employment_type"),
        "workplace_type": vals("workplace_type"),
    }


def suggest(conn: sqlite3.Connection, q: str, limit: int = 10):
    """Prefix-first title and company suggestions for a short query."""
    if not q or not q.strip():
        return []
    q = q.strip()
    like, pre = f"%{q}%", f"{q}%"
    out, seen = [], set()
    for col, kind in (("title", "title"), ("company", "company")):
        rows = conn.execute(
            f"SELECT {col} AS v, COUNT(*) AS n FROM jobs "
            f"WHERE is_open = 1 AND {col} LIKE ? AND TRIM({col}) != '' "
            f"GROUP BY {col} "
            f"ORDER BY (CASE WHEN {col} LIKE ? THEN 0 ELSE 1 END), n DESC "
            f"LIMIT ?", (like, pre, limit)).fetchall()
        for r in rows:
            key = (kind, (r["v"] or "").lower())
            if key in seen:
                continue
            seen.add(key)
            out.append({"value": r["v"], "type": kind, "count": r["n"]})
    out.sort(key=lambda x: -x["count"])
    return out[:limit]


def changes_since(conn: sqlite3.Connection, since: str | None = None,
                  limit: int = 200):
    """Postings whose last_changed is after `since` (ISO cursor), oldest first,
    closed ones included. Returns (rows, next_cursor)."""
    where = "WHERE last_changed IS NOT NULL"
    params: list = []
    if since:
        where += " AND last_changed > ?"
        params.append(since)
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM jobs {where} ORDER BY last_changed ASC, uid ASC LIMIT ?",
        params + [limit]).fetchall()]
    next_cursor = rows[-1]["last_changed"] if rows else since
    return rows, next_cursor


def change_type(row: dict) -> str:
    """Classify a change feed row: closed / new / modified."""
    if not row.get("is_open"):
        return "closed"
    if row.get("first_seen") and row.get("first_seen") == row.get("last_changed"):
        return "new"
    return "modified"


def last_fetch_by_platform(conn: sqlite3.Connection, status: str = "success"):
    """{platform: last successful ran_at} from fetch_log, for the /sources
    "last read X h ago" display."""
    rows = conn.execute(
        "SELECT platform, MAX(ran_at) AS last FROM fetch_log "
        "WHERE status = ? GROUP BY platform", (status,)).fetchall()
    return {r["platform"]: r["last"] for r in rows if r["last"]}
