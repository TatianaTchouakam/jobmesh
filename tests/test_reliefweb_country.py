"""Offline test: ReliefWeb country filter (board='Cameroon' -> country filter)."""
import os
from jobmesh.connectors.reliefweb import ReliefWebConnector

_JOB = {"id": 123, "fields": {"title": "Programme Officer",
        "source": [{"name": "UNICEF"}], "city": [{"name": "Yaoundé"}],
        "country": [{"name": "Cameroon"}], "date": {"created": "2026-11-20T00:00:00+00:00"},
        "url_alias": "https://reliefweb.int/job/123", "type": [{"name": "Job"}],
        "career_categories": [{"name": "Programme"}], "body-html": "<p>Role</p>"}}


class _Resp:
    status_code = 200
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def __init__(self): self.last_params = None
    def get(self, url, params=None, timeout=None, **k):
        self.last_params = params
        return _Resp({"data": [_JOB]})


def test_reliefweb_cameroon_filter(monkeypatch):
    monkeypatch.setenv("RELIEFWEB_APPNAME", "jobmesh-approved")
    s = _Session()
    jobs = ReliefWebConnector("Cameroon", session=s).fetch()
    assert s.last_params["filter[field]"] == "country"
    assert s.last_params["filter[value]"] == "Cameroon"
    assert len(jobs) == 1
    a = jobs[0]
    assert a.company == "UNICEF"
    assert a.location == "Yaoundé, Cameroon"
    assert a.source_board == "Cameroon"


def test_reliefweb_all_has_no_country_filter(monkeypatch):
    monkeypatch.setenv("RELIEFWEB_APPNAME", "jobmesh-approved")
    s = _Session()
    ReliefWebConnector("all", session=s).fetch()
    assert "filter[field]" not in s.last_params
