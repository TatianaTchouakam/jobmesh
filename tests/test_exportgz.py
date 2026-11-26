"""Pre-generated gzip bulk exports and their Premium-gated routes."""
import gzip
import json
import os
import time
os.environ.setdefault("SECRET_KEY", "test-secret-please-change")
from fastapi.testclient import TestClient
from jobmesh import api, exportfiles, pro
from jobmesh.api import app, _CSV_COLS, DB_PATH

c = TestClient(app)


def _key():
    return pro.make_key("cus", "sub", int(time.time()) + 3600)


def test_write_gz_exports(tmp_path):
    n = exportfiles.write_gz_exports(DB_PATH, str(tmp_path), _CSV_COLS, limit=300)
    assert n > 0
    nd = tmp_path / "jobs.ndjson.gz"
    cv = tmp_path / "jobs.csv.gz"
    assert nd.exists() and cv.exists()
    with gzip.open(nd, "rt", encoding="utf-8") as f:
        json.loads(f.readline())            # valid NDJSON
    with gzip.open(cv, "rt", encoding="utf-8") as f:
        assert f.readline().startswith("title,company,location")


def test_gz_routes_gating(tmp_path):
    # without a key -> 402
    assert c.get("/export/jobs.csv.gz").status_code == 402
    assert c.get("/export/jobs.ndjson.gz").status_code == 402
    old = api.EXPORT_DIR
    api.EXPORT_DIR = str(tmp_path)
    try:
        # with a key but not generated yet -> 503
        assert c.get("/export/jobs.csv.gz", headers={"X-API-Key": _key()}).status_code == 503
        exportfiles.write_gz_exports(DB_PATH, str(tmp_path), _CSV_COLS, limit=300)
        r = c.get("/export/jobs.csv.gz", headers={"X-API-Key": _key()})
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/gzip")
    finally:
        api.EXPORT_DIR = old
