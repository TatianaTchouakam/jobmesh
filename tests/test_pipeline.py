"""Pipeline tests: concurrent fetch with serial, thread-safe DB writes."""

import jobmesh.pipeline as pipeline
from jobmesh import storage
from jobmesh.models import Job


class _FakeConnector:
    def __init__(self, platform, board):
        self.platform, self.board = platform, board

    def fetch(self):
        if self.board == "boom":
            raise RuntimeError("boom")
        return [
            Job(self.platform, self.board, f"{self.board}-{i}", f"Role {i}", "Acme")
            for i in range(3)
        ]


def _patch(monkeypatch):
    monkeypatch.setattr(pipeline, "build_connector",
                        lambda p, b: _FakeConnector(p, b))


def _run(tmp_path, monkeypatch, workers):
    _patch(monkeypatch)
    monkeypatch.setenv("INGEST_WORKERS", str(workers))
    db = str(tmp_path / f"t{workers}.db")
    boards = {"fakeats": ["a", "b", "boom", "c"], "other": ["x", "y"]}
    with storage.session(db) as conn:
        results = pipeline.ingest(conn, boards)
        total = storage.count(conn)
    ok = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status == "failure"]
    return results, ok, failed, total


def test_concurrent_ingest_is_correct(tmp_path, monkeypatch):
    results, ok, failed, total = _run(tmp_path, monkeypatch, workers=8)
    assert len(results) == 6                 # 4 + 2 boards
    assert len(ok) == 5 and len(failed) == 1 # "boom" fails
    assert failed[0].board == "boom"
    assert total == 15                       # 5 good boards x 3 jobs, all written


def test_sequential_matches_concurrent(tmp_path, monkeypatch):
    _, ok_c, failed_c, total_c = _run(tmp_path, monkeypatch, workers=8)
    _, ok_s, failed_s, total_s = _run(tmp_path, monkeypatch, workers=1)
    assert (len(ok_c), len(failed_c), total_c) == (len(ok_s), len(failed_s), total_s)


def test_no_db_corruption_under_load(tmp_path, monkeypatch):
    # many boards, high concurrency -> single-writer must keep SQLite consistent
    _patch(monkeypatch)
    monkeypatch.setenv("INGEST_WORKERS", "16")
    db = str(tmp_path / "load.db")
    boards = {"fakeats": [f"b{i}" for i in range(50)]}
    with storage.session(db) as conn:
        results = pipeline.ingest(conn, boards)
        total = storage.count(conn)
    assert all(r.status == "success" for r in results)
    assert total == 150                      # 50 boards x 3 jobs
