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

import sqlite3
from contextlib import contextmanager
from typing import Iterable, Iterator, Optional

from .models import Job, now_iso

DEFAULT_DB = "jobmesh.db"

# Fields compared to decide whether an existing posting has changed.
_TRACKED_FIELDS = (
    "title", "company", "location", "description", "source_url",
    "apply_url", "salary", "employment_type", "remote", "posted_at",
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
    remote          INTEGER,
    posted_at       TEXT,
    dedup_key       TEXT,
    first_seen      TEXT,
    last_checked    TEXT,
    last_changed    TEXT,
    is_open         INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_jobs_board   ON jobs(source_platform, source_board);
CREATE INDEX IF NOT EXISTS idx_jobs_dedup   ON jobs(dedup_key);
CREATE INDEX IF NOT EXISTS idx_jobs_open    ON jobs(is_open);

CREATE TABLE IF NOT EXISTS fetch_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    platform   TEXT NOT NULL,
    board      TEXT NOT NULL,
    status     TEXT NOT NULL,          -- 'success' or 'failure'
    job_count  INTEGER,
    error      TEXT,
    ran_at     TEXT NOT NULL
);
"""


def connect(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


@contextmanager
def session(db_path: str = DEFAULT_DB) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# -- writes ---------------------------------------------------------------

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
                    apply_url, salary, employment_type, remote, posted_at,
                    dedup_key, first_seen, last_checked, last_changed, is_open
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                (
                    job.uid, job.source_platform, job.source_board,
                    job.source_job_id, job.title, job.company, job.location,
                    job.description, job.source_url, job.apply_url, job.salary,
                    job.employment_type, _bool(job.remote), job.posted_at,
                    job.dedup_key, now, now, now,
                ),
            )
            new += 1
            continue

        changed = _has_changed(row, job)
        conn.execute(
            """
            UPDATE jobs SET
                title=?, company=?, location=?, description=?, source_url=?,
                apply_url=?, salary=?, employment_type=?, remote=?,
                posted_at=?, dedup_key=?, last_checked=?,
                last_changed=?, is_open=1
            WHERE uid=?
            """,
            (
                job.title, job.company, job.location, job.description,
                job.source_url, job.apply_url, job.salary, job.employment_type,
                _bool(job.remote), job.posted_at, job.dedup_key, now,
                now if changed else row["last_changed"], job.uid,
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

    to_close = [r["uid"] for r in rows if r["uid"] not in seen_uids]
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

def search(
    conn: sqlite3.Connection,
    keyword: Optional[str] = None,
    company: Optional[str] = None,
    location: Optional[str] = None,
    open_only: bool = True,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Filtered, paginated search over the index."""
    clauses, params = [], []
    if open_only:
        clauses.append("is_open = 1")
    if keyword:
        clauses.append("(title LIKE ? OR description LIKE ?)")
        params += [f"%{keyword}%", f"%{keyword}%"]
    if company:
        clauses.append("company LIKE ?")
        params.append(f"%{company}%")
    if location:
        clauses.append("location LIKE ?")
        params.append(f"%{location}%")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        f"SELECT * FROM jobs {where} "
        f"ORDER BY COALESCE(posted_at, first_seen) DESC LIMIT ? OFFSET ?"
    )
    params += [limit, offset]
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def stats(conn: sqlite3.Connection) -> dict:
    """Headline numbers about the current index."""
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    open_ = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE is_open=1"
    ).fetchone()[0]
    boards = conn.execute(
        "SELECT COUNT(DISTINCT source_platform || ':' || source_board) "
        "FROM jobs"
    ).fetchone()[0]
    dupes = conn.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT dedup_key) FROM jobs "
        "WHERE is_open=1 AND dedup_key IS NOT NULL"
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
        "duplicate_open_postings": dupes,
        "open_by_platform": by_platform,
    }


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
