"""Rate-limit handling for shared-cluster platforms (Workday & friends).

Covers the per-cluster limiter (serialize, pace, cap parallel clusters), the
429 -> RateLimited surfacing (against a real fake server that returns 429),
and the pipeline deferring a rate-limited board to later in the cycle without
ever closing its listings.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import jobmesh.pipeline as pipeline
from jobmesh import storage
from jobmesh.models import Job
from jobmesh.ratelimit import (ClusterLimiter, RateLimited, parse_retry_after,
                               get_limiter, reset_limiters)


# ---------------------------------------------------------------- Retry-After
class _Resp:
    def __init__(self, headers):
        self.headers = headers


def test_parse_retry_after_forms():
    assert parse_retry_after(_Resp({"Retry-After": "30"})) == 30.0
    assert parse_retry_after(_Resp({})) is None
    assert parse_retry_after(_Resp({"Retry-After": "not-a-number"})) is None
    # HTTP-date form: a time in the past clamps to 0, not negative
    past = "Wed, 21 Oct 1990 07:28:00 GMT"
    assert parse_retry_after(_Resp({"Retry-After": past})) == 0.0


# ------------------------------------------------------------- ClusterLimiter
def test_same_cluster_is_paced(monkeypatch):
    # Deterministic virtual clock: no dependence on wall time (robust under load).
    import jobmesh.ratelimit as rl
    clock = [1000.0]
    sleeps = []
    monkeypatch.setattr(rl.time, "monotonic", lambda: clock[0])

    def fake_sleep(d):
        sleeps.append(d)
        clock[0] += d

    monkeypatch.setattr(rl.time, "sleep", fake_sleep)
    lim = rl.ClusterLimiter(min_interval=0.3, max_parallel_clusters=4)
    for _ in range(3):
        with lim.slot("wd5"):
            pass
    paced = [s for s in sleeps if s > 0]
    # first request isn't paced; the next two each wait exactly the interval
    assert len(paced) == 2
    assert all(abs(s - 0.3) < 1e-9 for s in paced)


def test_max_parallel_clusters_is_capped():
    lim = ClusterLimiter(min_interval=0.0, max_parallel_clusters=2)
    active = 0
    peak = 0
    guard = threading.Lock()

    def worker(cluster):
        nonlocal active, peak
        with lim.slot(cluster):
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with guard:
                active -= 1

    ts = [threading.Thread(target=worker, args=(f"wd{i}",)) for i in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert peak <= 2


# ------------------------------------------------------- fake 429 HTTP server
class _Handler(BaseHTTPRequestHandler):
    fail_times = 0
    _seen = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        cls = type(self)
        cls._seen += 1
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        if cls._seen <= cls.fail_times:
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.end_headers()
            self.wfile.write(b"too many requests")
            return
        body = json.dumps({"total": 1, "jobPostings": [
            {"title": "Engineer", "externalPath": "/job/1",
             "locationsText": "Berlin", "bulletFields": ["R-1"]}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def fake_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    _Handler._seen = 0
    try:
        yield srv, f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()


def _workday_pointing_at(base_url):
    from jobmesh.connectors.workday import WorkdayConnector

    class _Local(WorkdayConnector):
        @property
        def _base(self):
            return base_url

    return _Local("acme:wd5:AcmeCareers:Acme")


def test_workday_raises_ratelimited_on_429(fake_server, monkeypatch):
    reset_limiters()
    monkeypatch.setenv("WORKDAY_MIN_INTERVAL", "0")
    reset_limiters()
    _, base = fake_server
    _Handler.fail_times = 5
    c = _workday_pointing_at(base)
    with pytest.raises(RateLimited) as ei:
        c.fetch()
    assert ei.value.retry_after == 0.0


def test_workday_succeeds_through_limiter(fake_server, monkeypatch):
    monkeypatch.setenv("WORKDAY_MIN_INTERVAL", "0")
    reset_limiters()
    _, base = fake_server
    _Handler.fail_times = 0
    c = _workday_pointing_at(base)
    jobs = c.fetch()
    assert len(jobs) == 1 and jobs[0].title == "Engineer"


# ------------------------------------------------ pipeline defers 429 boards
class _FlakyConnector:
    """429s the first `fail_first` fetches of a board, then succeeds."""
    calls: dict = {}
    fail_first = 1

    def __init__(self, platform, board):
        self.platform, self.board = platform, board

    def fetch(self):
        n = _FlakyConnector.calls.get(self.board, 0) + 1
        _FlakyConnector.calls[self.board] = n
        if self.board == "always429":
            raise RateLimited(retry_after=0.0)
        if n <= _FlakyConnector.fail_first:
            raise RateLimited(retry_after=0.0)
        return [Job(self.platform, self.board, f"{self.board}-1", "Role", "Acme")]


def test_pipeline_defers_and_recovers_429(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "_RL_BACKOFF", [0.0, 0.0, 0.0])
    monkeypatch.setattr(pipeline, "build_connector",
                        lambda p, b: _FlakyConnector(p, b))
    monkeypatch.setenv("INGEST_WORKERS", "4")
    _FlakyConnector.calls = {}
    _FlakyConnector.fail_first = 1
    db = str(tmp_path / "rl.db")
    with storage.session(db) as conn:
        results = pipeline.ingest(conn, {"workday": ["one", "two", "three"]})
        total = storage.count(conn)
    ok = [r for r in results if r.status == "success"]
    assert len(ok) == 3            # each 429'd once, then recovered in a later round
    assert total == 3


def test_persistent_429_fails_without_closing(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "_RL_BACKOFF", [0.0, 0.0, 0.0])
    monkeypatch.setattr(pipeline, "build_connector",
                        lambda p, b: _FlakyConnector(p, b))
    monkeypatch.setenv("INGEST_WORKERS", "1")
    _FlakyConnector.calls = {}
    db = str(tmp_path / "rl2.db")
    with storage.session(db) as conn:
        # seed an open job for the board that will be perpetually rate-limited
        storage.upsert_jobs(conn, [Job("workday", "always429", "keep-1",
                                       "Existing", "Acme")])
        conn.commit()
        results = pipeline.ingest(conn, {"workday": ["always429"]})
        still_open = conn.execute(
            "SELECT is_open FROM jobs WHERE source_board='always429'"
        ).fetchone()[0]
    assert [r.status for r in results] == ["failure"]
    assert "429" in results[0].error
    assert still_open == 1          # a 429 never closes a board's listings
