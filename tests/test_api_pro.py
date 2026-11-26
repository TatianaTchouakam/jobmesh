"""API gating: free limit cap + export free-sample / full Premium export."""
import os, time
os.environ.setdefault("SECRET_KEY", "test-secret-please-change")
from fastapi.testclient import TestClient
from jobmesh.api import app
from jobmesh import pro

c = TestClient(app)


def _key():
    return pro.make_key("cus_t", "sub_t", int(time.time()) + 3600)


def test_free_limit_capped():
    d = c.get("/jobs?limit=200").json()
    assert d["limit"] == 50 and d["pro"] is False


def test_pro_limit_allowed():
    d = c.get("/jobs?limit=200&api_key=" + _key()).json()
    assert d["limit"] == 200 and d["pro"] is True


def test_export_csv_free_sample_capped():
    # no key -> free sample, flagged, at most 1000 data rows
    r = c.get("/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers.get("x-jobmesh-sample") == "true"
    assert "Premium" in r.headers.get("x-jobmesh-note", "")
    data_rows = len(r.text.splitlines()) - 1  # minus header
    assert 0 <= data_rows <= 1000


def test_export_csv_with_key_is_full():
    r = c.get("/export.csv", headers={"X-API-Key": _key()})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("title,company,location")
    assert "x-jobmesh-sample" not in {k.lower() for k in r.headers}


def test_export_json_free_sample():
    d = c.get("/export.json?limit=2000").json()
    assert d["pro"] is False and d["sample"] is True
    assert d["limit"] <= 1000 and d["count"] <= 1000
    assert "Premium" in d["note"]


def test_export_json_with_key_full_paginated():
    d = c.get("/export.json?limit=2000", headers={"X-API-Key": _key()}).json()
    assert d["pro"] is True and "sample" not in d
    assert d["limit"] == 2000
