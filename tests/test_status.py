"""Public status/coverage surface: /sources, /status, and /stats negotiation."""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-please-change")

from fastapi.testclient import TestClient

from jobmesh.api import app

c = TestClient(app)


def test_sources_registry_shape():
    d = c.get("/sources").json()
    assert d["required_total"] == d["ats_total"] + d["boards_total"]
    assert d["required_total"] == len(d["sources"])
    assert sum(d["status_counts"].values()) == d["required_total"]
    assert 0 <= d["active"] <= d["required_total"]
    for row in d["sources"]:
        assert row.get("name") and row.get("status")


def test_stats_content_negotiation():
    j = c.get("/stats", headers={"Accept": "application/json"}).json()
    assert "open_postings" in j
    assert "last_updated" in j and "sources_failed_last_run" in j
    h = c.get("/stats", headers={"Accept": "text/html"})
    assert h.status_code == 200
    assert "text/html" in h.headers["content-type"]


def test_status_page_is_html():
    r = c.get("/status")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "coverage" in r.text.lower()
