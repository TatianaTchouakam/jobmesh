"""API gating: free limit cap + Pro-only CSV export."""
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


def test_export_requires_pro():
    assert c.get("/export.csv").status_code == 402


def test_export_with_key_ok():
    r = c.get("/export.csv", headers={"X-API-Key": _key()})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("title,company,location")
