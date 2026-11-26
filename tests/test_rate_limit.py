"""Rate-limit headers, 429, and request_id in error bodies."""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-please-change")
from fastapi.testclient import TestClient
from jobmesh import api
from jobmesh.api import app

c = TestClient(app)


def test_ratelimit_headers_on_api():
    r = c.get("/stats")
    assert r.headers.get("x-ratelimit-limit")
    assert "x-ratelimit-remaining" in r.headers
    assert r.headers.get("x-request-id")


def test_request_id_in_404_json():
    r = c.get("/jobs/no-such-uid")
    assert r.status_code == 404
    assert r.json().get("request_id")


def test_429_when_over_limit():
    old_enabled, old_free = api.RATE_LIMIT_ENABLED, api.RATE_FREE
    api.RATE_LIMIT_ENABLED = True
    api.RATE_FREE = 2
    api._rl_hits.clear()
    try:
        assert c.get("/stats").status_code == 200
        assert c.get("/stats").status_code == 200
        r = c.get("/stats")
        assert r.status_code == 429
        assert r.json().get("request_id")
        assert r.headers.get("retry-after")
        assert r.headers.get("x-ratelimit-remaining") == "0"
    finally:
        api.RATE_LIMIT_ENABLED = old_enabled
        api.RATE_FREE = old_free
        api._rl_hits.clear()
