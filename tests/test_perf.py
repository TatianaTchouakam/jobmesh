"""Performance guard on a 600k-row index.

Builds a synthetic 600,000-posting database once and asserts the hot read
paths stay fast: keyword search under 500 ms, country pages and the /changes
cursor under 1 s. Runs at the storage layer (no HTTP serialisation), which is
what the FTS index and the filter indexes are there to make fast.
"""
import random
import time

import pytest

from jobmesh import storage

N = 600_000

_TITLE_WORDS = ["Data", "Software", "Senior", "Junior", "Machine", "Learning",
                "Engineer", "Analyst", "Scientist", "Backend", "Frontend",
                "Platform", "Cloud", "DevOps", "Product", "Manager", "Designer"]
_COMPANIES = [f"Company {c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWX"]
_PLACES = [("Berlin, Germany", "DE"), ("Munich, Germany", "DE"),
           ("Paris, France", "FR"), ("London, UK", "GB"),
           ("New York, NY, USA", "US"), ("Amsterdam, Netherlands", "NL"),
           ("Madrid, Spain", "ES"), ("Remote", None)]


@pytest.fixture(scope="module")
def big_db(tmp_path_factory):
    db = str(tmp_path_factory.mktemp("perf") / "big.db")
    rnd = random.Random(42)
    # Bulk-insert directly (the FTS triggers populate the index as we go).
    with storage.session(db) as conn:
        rows = []
        for i in range(N):
            w = rnd.sample(_TITLE_WORDS, 3)
            title = " ".join(w) + f" #{i % 9999}"
            comp = rnd.choice(_COMPANIES)
            loc, country = rnd.choice(_PLACES)
            day = 1 + (i % 28)
            changed = f"2026-11-{day:02d}T0{i % 9}:00:00Z"
            rows.append((
                f"gh:board{i % 1000}:{i}", "greenhouse", f"board{i % 1000}",
                str(i), title, comp, loc, None, f"https://x/{i}", f"https://x/{i}",
                None, None, None, None, None, 0, changed[:10], f"r{i % 5000}",
                changed, changed, changed, country, 1 if i % 7 else 0,
            ))
            if len(rows) >= 10000:
                conn.executemany(
                    "INSERT INTO jobs(uid,source_platform,source_board,source_job_id,"
                    "title,company,location,description,source_url,apply_url,salary,"
                    "employment_type,workplace_type,category,level,remote,posted_at,"
                    "dedup_key,first_seen,last_checked,last_changed,country,is_open) "
                    "VALUES (" + ",".join("?" * 23) + ")", rows)
                rows = []
        if rows:
            conn.executemany(
                "INSERT INTO jobs(uid,source_platform,source_board,source_job_id,"
                "title,company,location,description,source_url,apply_url,salary,"
                "employment_type,workplace_type,category,level,remote,posted_at,"
                "dedup_key,first_seen,last_checked,last_changed,country,is_open) "
                "VALUES (" + ",".join("?" * 23) + ")", rows)
        conn.commit()
        conn.execute("ANALYZE")          # same stats refresh we run at cycle end
        storage.refresh_stats_cache(conn)
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        nf = conn.execute("SELECT COUNT(*) FROM jobs_fts").fetchone()[0]
    assert n == N and nf == N      # FTS kept in sync by the triggers
    return db


def _ms(fn):
    t = time.perf_counter()
    out = fn()
    return (time.perf_counter() - t) * 1000, out


def test_keyword_search_under_500ms(big_db):
    with storage.session(big_db) as conn:
        for term in ("data", "software engineer", "machine learning"):
            ms, rows = _ms(lambda: storage.search(conn, limit=30, keyword=term))
            assert rows, f"no rows for {term}"
            assert ms < 500, f"search {term!r} took {ms:.0f}ms"
            ms, _ = _ms(lambda: storage.count(conn, keyword=term))
            assert ms < 500, f"count {term!r} took {ms:.0f}ms"


def test_country_page_under_1s(big_db):
    with storage.session(big_db) as conn:
        ms, rows = _ms(lambda: storage.search(conn, limit=100, country="DE"))
        assert rows and ms < 1000, f"country search took {ms:.0f}ms"
        ms, _ = _ms(lambda: storage.count(conn, country="DE"))
        assert ms < 1000, f"country count took {ms:.0f}ms"


def test_changes_cursor_under_1s(big_db):
    with storage.session(big_db) as conn:
        ms, (rows, cur) = _ms(
            lambda: storage.changes_since(conn, since="2026-11-10T00:00:00Z", limit=200))
        assert rows and ms < 1000, f"changes took {ms:.0f}ms"


def test_count_is_bounded(big_db):
    with storage.session(big_db) as conn:
        # A broad term matches far more than the cap but stays fast and bounded.
        ms, n = _ms(lambda: storage.count(conn, keyword="data"))
        assert n <= storage.COUNT_CAP + 1, f"count not bounded: {n}"
        assert ms < 500, f"bounded count took {ms:.0f}ms"


def test_stats_served_from_cache_fast(big_db):
    with storage.session(big_db) as conn:
        cached = storage.stats(conn)            # cache built in the fixture
        ms, again = _ms(lambda: storage.stats(conn))
        assert ms < 100, f"/stats took {ms:.0f}ms (should read the cache)"
        assert again["open_postings"] == cached["open_postings"]
        assert again["total_postings"] == N


def test_keyword_plus_country_under_500ms(big_db):
    # A keyword combined with a country filter stays fast: the country lives in
    # the FTS index, so the match is already country-scoped (no per-row probe).
    with storage.session(big_db) as conn:
        for term in ("data", "engineer", "software"):
            ms, rows = _ms(lambda: storage.search(
                conn, limit=30, keyword=term, country="DE"))
            assert ms < 500, f"search {term!r}+DE took {ms:.0f}ms"
            ms, n = _ms(lambda: storage.count(conn, keyword=term, country="DE"))
            assert ms < 500, f"count {term!r}+DE took {ms:.0f}ms"
            assert n <= storage.COUNT_CAP + 1
