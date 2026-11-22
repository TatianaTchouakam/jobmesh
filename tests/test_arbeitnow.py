"""Offline tests for the Arbeitnow (DE/EU) connector."""

import requests
from jobmesh.connectors.arbeitnow import ArbeitnowConnector


class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


PAGE1 = {"data": [
    {"slug": "devops-dortmund-12632", "title": "DevOps Engineer",
     "company_name": "Acme GmbH", "location": "Dortmund", "url": "https://arbeitnow.com/jobs/x",
     "remote": False, "created_at": 1795374032, "job_types": ["berufserfahren"]},
    {"slug": "data-remote-9001", "title": "Data Engineer", "company_name": "RemoteCo",
     "location": "Berlin", "url": "https://arbeitnow.com/jobs/y", "remote": True,
     "created_at": 1795374000, "job_types": ["Vollzeit"]},
], "links": {"next": None}, "meta": {}}


class _FakeSession:
    def __init__(self): self.headers = {}
    def get(self, url, params=None, timeout=None, **kw):
        return _Resp(PAGE1 if params.get("page") == 1 else {"data": []})


def _no_robots(mp):
    mp.setattr("jobmesh.connectors.arbeitnow.robots_allowed", lambda u, s=None: True)


def test_arbeitnow_parses(monkeypatch):
    _no_robots(monkeypatch)
    jobs = ArbeitnowConnector(session=_FakeSession()).fetch()
    assert len(jobs) == 2
    d = next(j for j in jobs if "DevOps" in j.title)
    assert d.company == "Acme GmbH"
    assert d.location == "Dortmund"
    assert d.source_platform == "arbeitnow"
    assert d.source_job_id == "devops-dortmund-12632"
    assert d.posted_at and d.posted_at.startswith("20")
    r = next(j for j in jobs if j.remote)
    assert r.workplace_type == "remote"


def test_arbeitnow_robots_blocked(monkeypatch):
    monkeypatch.setattr("jobmesh.connectors.arbeitnow.robots_allowed", lambda u, s=None: False)
    assert ArbeitnowConnector(session=_FakeSession()).fetch() == []
