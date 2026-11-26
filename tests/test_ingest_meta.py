"""Tests for ingest-run metadata, the "last updated" surface, and the lock."""

from types import SimpleNamespace

from jobmesh import storage
from jobmesh.locks import ingest_lock


def _result(platform, board, status):
    return SimpleNamespace(platform=platform, board=board, status=status)


def test_meta_roundtrip(tmp_path):
    db = str(tmp_path / "t.db")
    with storage.session(db) as conn:
        assert storage.get_meta(conn, "missing") is None
        assert storage.get_meta(conn, "missing", "x") == "x"
        storage.set_meta(conn, "k", "v")
        assert storage.get_meta(conn, "k") == "v"
        storage.set_meta(conn, "k", "v2")
        assert storage.get_meta(conn, "k") == "v2"


def test_record_ingest_run_and_stats(tmp_path):
    db = str(tmp_path / "t.db")
    results = [
        _result("greenhouse", "acme", "success"),
        _result("lever", "beta", "success"),
        _result("brassring", "gamma", "failure"),
    ]
    with storage.session(db) as conn:
        storage.record_ingest_run(conn, results, 1000.0, 1012.5)
        assert storage.get_meta(conn, "last_ingest_boards") == "3"
        assert storage.get_meta(conn, "last_ingest_ok") == "2"
        assert storage.get_meta(conn, "last_ingest_failed") == "1"
        assert storage.get_meta(conn, "last_ingest_seconds") == "12.5"
        assert "brassring/gamma" in storage.get_meta(
            conn, "last_ingest_failed_sources")

        s = storage.stats(conn)
        assert s["last_updated"] is not None
        assert s["last_ingest_seconds"] == 12.5
        assert s["last_ingest_boards"] == 3
        assert s["sources_failed_last_run"] == 1


def test_ingest_lock_is_exclusive(tmp_path):
    lock_path = str(tmp_path / "ingest.lock")
    with ingest_lock(lock_path) as outer:
        assert outer is True
        # A second attempt while the first is held must not acquire it.
        with ingest_lock(lock_path) as inner:
            assert inner is False
    # Once released, it can be taken again.
    with ingest_lock(lock_path) as again:
        assert again is True
