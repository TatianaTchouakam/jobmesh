"""Offline mapping test for the Polymer connector."""
from __future__ import annotations
from jobmesh.connectors.polymer import PolymerConnector

SAMPLE = {"items": [
    {"id": 41828, "job_id": 41828, "hash_id": "9wnyiuh6dwo1",
     "title": "Real Estate Associate", "organization_name": "Próspera",
     "display_location": "Roatán, HN", "city": "Roatán", "country": "HN",
     "kind_pretty": "Full-time", "remoteness_pretty": "No remote",
     "job_category_name": "Real Estate", "salary_pretty": None,
     "job_post_url": "https://jobs.prospera.co/41828",
     "published_at": "2026-11-16T14:16:32.073Z"},
    {"id": 2, "title": "Remote Engineer", "organization_name": "Próspera",
     "display_location": "Remote", "remoteness_pretty": "Fully remote",
     "job_post_url": "https://jobs.prospera.co/2", "kind_pretty": "Full-time"},
]}


class _Resp:
    def __init__(self, js): self._js=js; self.status_code=200
    def raise_for_status(self): pass
    def json(self): return self._js


class _FakeSession:
    def __init__(self, js): self.headers={}; self._js=js
    def get(self, *a, **k): return _Resp(self._js)


def test_polymer_maps_items():
    jobs = PolymerConnector("prospera", session=_FakeSession(SAMPLE)).fetch()
    assert len(jobs) == 2
    j = jobs[0]
    assert j.source_platform == "polymer"
    assert j.source_board == "prospera"
    assert j.source_job_id == "41828"
    assert j.title == "Real Estate Associate"
    assert j.company == "Próspera"
    assert j.location == "Roatán, HN"
    assert j.employment_type == "Full-time"
    assert j.remote is False
    assert jobs[1].remote is True  # "Fully remote"
