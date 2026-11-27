"""Offline tests for storage: upsert, change detection, closing, failures."""

from jobmesh import storage
from jobmesh.models import Job


def _job(job_id="1", title="Data Engineer", location="Berlin", **kw):
    data = dict(
        source_platform="greenhouse",
        source_board="acme",
        source_job_id=job_id,
        title=title,
        company="Acme",
        location=location,
    )
    data.update(kw)
    return Job(**data)


def test_insert_then_update_and_close(tmp_path):
    db = str(tmp_path / "t.db")
    with storage.session(db) as conn:
        # First run: two jobs, both new.
        res = storage.upsert_jobs(conn, [_job("1"), _job("2")])
        assert res["new"] == 2

        # Second run: job 1 changed title, job 2 gone.
        res = storage.upsert_jobs(conn, [_job("1", title="Senior Data Engineer")])
        assert res["updated"] == 1
        closed = storage.close_absent(conn, "greenhouse", "acme", {"greenhouse:acme:1"})
        assert closed == 1

        open_rows = storage.search(conn, open_only=True)
        assert len(open_rows) == 1
        assert open_rows[0]["title"] == "Senior Data Engineer"


def test_unchanged_is_not_flagged_as_updated(tmp_path):
    db = str(tmp_path / "t.db")
    with storage.session(db) as conn:
        storage.upsert_jobs(conn, [_job("1")])
        res = storage.upsert_jobs(conn, [_job("1")])
        assert res["unchanged"] == 1
        assert res["updated"] == 0


def test_failed_fetch_does_not_close(tmp_path):
    db = str(tmp_path / "t.db")
    with storage.session(db) as conn:
        storage.upsert_jobs(conn, [_job("1"), _job("2")])
        storage.log_fetch(conn, "greenhouse", "acme", "failure", error="timeout")
        # No close_absent call on failure -> both stay open.
        assert len(storage.search(conn, open_only=True)) == 2


def test_incomplete_fetch_does_not_mass_close(tmp_path):
    """A throttled fetch returning far fewer than are open must NOT close the
    rest (guards against false mass-closures like MinaJobs 399 -> 73)."""
    db = str(tmp_path / "t.db")
    with storage.session(db) as conn:
        # Seed 30 open postings for one board.
        storage.upsert_jobs(conn, [_job(str(i)) for i in range(30)])
        assert storage.count(conn, open_only=True) == 30

        # Next run sees only 5 of them (throttled). Guard should skip closing.
        seen = {f"greenhouse:acme:{i}" for i in range(5)}
        closed = storage.close_absent(conn, "greenhouse", "acme", seen)
        assert closed == 0
        assert storage.count(conn, open_only=True) == 30


def test_normal_shrink_still_closes(tmp_path):
    """A healthy fetch that still returns most postings closes the few absent
    ones (guard only trips on a drastic, throttling-sized drop)."""
    db = str(tmp_path / "t.db")
    with storage.session(db) as conn:
        storage.upsert_jobs(conn, [_job(str(i)) for i in range(30)])
        # Next run sees 28 of 30 -> 2 genuinely gone, well above the 50% floor.
        seen = {f"greenhouse:acme:{i}" for i in range(28)}
        closed = storage.close_absent(conn, "greenhouse", "acme", seen)
        assert closed == 2
        assert storage.count(conn, open_only=True) == 28


def test_search_dedups_by_role_and_reports_sources(tmp_path):
    """Two sources of the same role (shared dedup_key) collapse to one result
    carrying group_size and the other source's URL."""
    from jobmesh import storage
    from jobmesh.models import Job
    db = str(tmp_path / "dedup.db")
    jobs = [
        Job("greenhouse", "acme", "1", "Data Engineer", "Acme", "Berlin, Germany",
            source_url="https://boards.greenhouse.io/acme/1", dedup_key="role-de"),
        Job("lever", "acme", "9", "Data Engineer", "Acme", "Berlin, Germany",
            source_url="https://jobs.lever.co/acme/9", dedup_key="role-de"),
        Job("ashby", "beta", "2", "Data Analyst", "Beta", "Paris, France",
            source_url="https://jobs.ashbyhq.com/beta/2", dedup_key="role-da"),
    ]
    with storage.session(db) as conn:
        storage.upsert_jobs(conn, jobs)
        conn.commit()
        # keyword path (FTS)
        res = storage.search(conn, limit=20, keyword="data")
        titles = [r["title"] for r in res]
        assert titles.count("Data Engineer") == 1          # collapsed
        de = next(r for r in res if r["title"] == "Data Engineer")
        assert de["group_size"] == 2
        assert len(de["other_source_urls"]) == 1
        assert de["source_url"] not in de["other_source_urls"]
        # plain listing path (no keyword)
        res2 = storage.search(conn, limit=20)
        assert [r["title"] for r in res2].count("Data Engineer") == 1
