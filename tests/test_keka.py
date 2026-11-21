"""Offline test: Keka careers JSON API (location join, detail URL, dept->category)."""
from jobmesh.connectors.keka import KekaConnector, _location

_ROWS = [
    {"id": 146905, "title": "HRBP", "description": "<div>About Keka</div>",
     "departmentName": "Human Resources",
     "jobLocations": [{"name": "Hyderabad", "state": "TG", "countryName": "India", "countryCode": "IN"}],
     "jobType": 2, "jobNumber": "KEKA/1474", "publishedOn": "2026-11-10T11:45:40.273Z"},
    {"id": 146906, "title": "Remote Designer", "excerpt": "Design things",
     "departmentName": "Design",
     "jobLocations": [{"name": "Remote", "countryName": "India"}],
     "publishedOn": "2026-11-09T00:00:00.000Z"},
]


class _Resp:
    status_code = 200
    def __init__(self, payload=None, text=""): self._p = payload; self.text = text
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, headers=None, **k):
        if url.endswith("robots.txt"):
            return _Resp(text="User-agent: *\nDisallow: /\nAllow: /careers/\n")
        assert url == "https://hr.keka.com/careers/api/embedjobs/default/active/ORG"
        return _Resp(payload=_ROWS)


def test_keka_maps():
    jobs = KekaConnector("hr.keka.com|ORG|Keka", session=_Session()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "146905"
    assert a.company == "Keka"
    assert a.title == "HRBP"
    assert a.location == "Hyderabad, India"
    assert a.source_url == "https://hr.keka.com/careers/jobdetails/146905"
    assert a.posted_at.startswith("2026-11-10")
    assert a.employment_type is None          # jobType enum not guessed
    assert jobs[1].remote is True


def test_keka_location_helper():
    assert _location([{"name": "Pune", "countryName": "India"}]) == "Pune, India"
    assert _location([]) is None
    assert _location([{"name": "Berlin", "countryName": "Germany"},
                      {"name": "Munich", "countryName": "Germany"}]) == "Berlin / Munich, Germany"


def test_keka_company_fallback():
    jobs = KekaConnector("hr.keka.com|ORG", session=_Session()).fetch()
    assert jobs[0].company == "Keka employer"
