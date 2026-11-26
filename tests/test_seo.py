"""SEO landing pages (server-rendered + JSON-LD) and their sitemap entries."""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-please-change")
from fastapi.testclient import TestClient
from jobmesh.api import app

c = TestClient(app)
H = {"accept": "text/html"}


def test_country_page():
    r = c.get("/jobs/in/de", headers=H)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "JobPosting" in r.text and "<h1>" in r.text and "canonical" in r.text


def test_unknown_country_404():
    assert c.get("/jobs/in/xx", headers=H).status_code == 404


def test_country_city_page():
    assert c.get("/jobs/in/de/berlin", headers=H).status_code == 200


def test_role_page():
    assert c.get("/jobs/role/data-engineer", headers=H).status_code == 200
    assert c.get("/jobs/role/zzz-no-such-role", headers=H).status_code == 404


def test_type_page():
    assert c.get("/jobs/type/full-time", headers=H).status_code == 200
    assert c.get("/jobs/type/banana", headers=H).status_code == 404


def test_sitemap_lists_seo_pages():
    sm = c.get("/sitemap.xml").text
    assert "/jobs/in/de" in sm and "/jobs/role/" in sm and "/jobs/type/" in sm
