"""Read-model API: jobs by id/url, companies, filter-values, suggest, changes,
and the posted_after / seen_within / has_salary / include_closed filters."""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-please-change")
from fastapi.testclient import TestClient
from jobmesh.api import app

c = TestClient(app)


def _a_job():
    return c.get("/jobs?limit=1").json()["results"][0]


def test_job_by_id():
    j = _a_job()
    r = c.get(f"/jobs/{j['uid']}")
    assert r.status_code == 200 and r.json()["uid"] == j["uid"]
    assert c.get("/jobs/does-not-exist-uid").status_code == 404


def test_job_by_url():
    j = _a_job()
    url = j.get("source_url") or j.get("apply_url")
    assert c.get(f"/jobs/by-url", params={"url": url}).status_code == 200
    assert c.get("/jobs/by-url", params={"url": "https://nope.example/x"}).status_code == 404


def test_companies_list():
    d = c.get("/companies?limit=5").json()
    assert d["count"] <= 5 and d["total"] >= d["count"]
    assert "has_more" in d and all("open_jobs" in r for r in d["data"])


def test_company_detail():
    comp = c.get("/companies?limit=1").json()["data"][0]["company"]
    d = c.get(f"/companies/{comp}").json()
    assert d["open_jobs"] >= 1 and d["count"] >= 1
    assert c.get("/companies/__nope_company__").status_code == 404


def test_filter_values():
    d = c.get("/filter-values").json()
    for k in ("platform", "category", "level", "employment_type", "workplace_type"):
        assert k in d


def test_suggest():
    d = c.get("/suggest?q=data").json()
    assert d["query"] == "data" and len(d["suggestions"]) >= 1


def test_has_salary_filter():
    total = c.get("/jobs?limit=1").json()["total"]
    sal = c.get("/jobs?has_salary=true&limit=1").json()["total"]
    assert 0 <= sal <= total


def test_include_closed_filter():
    open_total = c.get("/jobs?limit=1").json()["total"]
    all_total = c.get("/jobs?include_closed=true&limit=1").json()["total"]
    assert all_total >= open_total


def test_posted_after_filter():
    r = c.get("/jobs?posted_after=2026-01-01&limit=3")
    assert r.status_code == 200 and "total" in r.json()


def test_changes_cursor():
    d = c.get("/changes?limit=3").json()
    assert d["count"] >= 1 and d["cursor"]
    assert all(x["change_type"] in ("new", "modified", "closed") for x in d["data"])
    d2 = c.get("/changes", params={"since": d["cursor"], "limit": 3}).json()
    assert "data" in d2
