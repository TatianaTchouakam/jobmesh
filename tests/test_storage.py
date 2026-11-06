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
