"""Offline tests for the Jobicy (worldwide remote) connector."""

import requests
from jobmesh.connectors.jobicy import JobicyConnector


class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


def _page(ids, cursor_out, more):
    return {"jobs": [{"id": i, "jobTitle": f"Role {i}", "companyName": "VTEX",
                      "jobType": ["Full-Time"], "jobGeo": "Brazil",
                      "url": f"https://jobicy.com/jobs/{i}", "pubDate": "2026-11-22T16:10:59+00:00",
                      "jobIndustry": ["Software Engineering"]} for i in ids],
            "nextCursor": cursor_out, "hasMore": more}


class _FakeSession:
    def __init__(self): self.headers = {}
    def get(self, url, params=None, timeout=None, **kw):
        if not params.get("cursor"):
            return _Resp(_page([1, 2], "CUR2", True))
        if params.get("cursor") == "CUR2":
            return _Resp(_page([3, 4], None, False))
        return _Resp({"jobs": []})


def _no_robots(mp):
    mp.setattr("jobmesh.connectors.jobicy.robots_allowed", lambda u, s=None: True)


def test_jobicy_paginates_by_cursor(monkeypatch):
    _no_robots(monkeypatch)
    jobs = JobicyConnector(session=_FakeSession()).fetch()
    assert len(jobs) == 4
    j = jobs[0]
    assert j.source_platform == "jobicy"
    assert j.company == "VTEX"
    assert j.remote is True
    assert j.workplace_type == "remote"
    assert j.source_url.startswith("https://jobicy.com/jobs/")
    assert j.posted_at.startswith("2026-11-22")


def test_jobicy_robots_blocked(monkeypatch):
    monkeypatch.setattr("jobmesh.connectors.jobicy.robots_allowed", lambda u, s=None: False)
    assert JobicyConnector(session=_FakeSession()).fetch() == []
