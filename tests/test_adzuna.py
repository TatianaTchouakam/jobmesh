"""Offline test: Adzuna connector (credentials from env, country board, mapping)."""
import os
import pytest
from jobmesh.connectors.adzuna import AdzunaConnector, _salary

_PAGE1 = {"results": [
    {"id": 123, "title": "Data Engineer", "company": {"display_name": "Acme Canada"},
     "location": {"display_name": "Toronto, ON"}, "redirect_url": "https://adzuna/ca/123",
     "category": {"label": "IT Jobs"}, "salary_min": 90000, "salary_max": 120000,
     "contract_time": "full_time", "description": "<p>Build pipelines</p>", "created": "2026-11-20T00:00:00Z"},
]}


class _Resp:
    status_code = 200
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def __init__(self): self.calls = []
    def get(self, url, params=None, timeout=None, **k):
        self.calls.append((url, params))
        assert params["app_id"] == "ID" and params["app_key"] == "KEY"
        if "/ca/search/1" in url:
            return _Resp(_PAGE1)
        return _Resp({"results": []})


def test_adzuna_maps(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "ID")
    monkeypatch.setenv("ADZUNA_APP_KEY", "KEY")
    jobs = AdzunaConnector("ca", session=_Session()).fetch()
    assert len(jobs) == 1
    a = jobs[0]
    assert a.source_job_id == "123"
    assert a.title == "Data Engineer"
    assert a.company == "Acme Canada"
    assert a.location == "Toronto, ON"
    assert a.source_board == "ca"
    assert a.salary == "90,000–120,000"
    assert a.employment_type == "Full-time"       # normalized full_time


def test_adzuna_requires_credentials(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    with pytest.raises(RuntimeError):
        AdzunaConnector("gb", session=_Session()).fetch()


def test_adzuna_rejects_bad_country(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "ID"); monkeypatch.setenv("ADZUNA_APP_KEY", "KEY")
    with pytest.raises(ValueError):
        AdzunaConnector("xx", session=_Session()).fetch()


def test_salary_helper():
    assert _salary(50000, 50000) == "50,000"
    assert _salary(40000, 60000) == "40,000–60,000"
    assert _salary(None, None) is None
