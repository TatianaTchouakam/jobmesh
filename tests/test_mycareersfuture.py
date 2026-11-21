"""Offline test: MyCareersFuture public jobs API (pagination, mapping, cap)."""
from jobmesh.connectors.mycareersfuture import MyCareersFutureConnector, _location, _salary


def _job(uid, title, company="Acme SG", overseas=False):
    return {"uuid": uid, "title": title, "description": "<p>Great role</p>",
            "postedCompany": {"name": company},
            "address": {"isOverseas": overseas, "overseasCountry": "Malaysia" if overseas else None,
                        "districts": [{"region": "West"}]},
            "employmentTypes": [{"employmentType": "Full Time"}],
            "positionLevels": [{"position": "Fresh/entry level"}],
            "salary": {"minimum": 3200, "maximum": 4000, "type": {"salaryType": "Monthly"}},
            "metadata": {"jobDetailsUrl": f"https://www.mycareersfuture.gov.sg/job/{title}-{uid}",
                         "originalPostingDate": "2026-11-21"}}


class _Resp:
    status_code = 200
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def __init__(self): self.pages = []
    def get(self, url, params=None, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(None)
        self.pages.append(params["page"])
        if params["page"] == 0:
            return _Resp({"results": [_job("u1", "Events Coordinator"),
                                      _job("u2", "Remote Analyst", overseas=True)], "total": 3})
        if params["page"] == 1:
            return _Resp({"results": [_job("u3", "CFO")], "total": 3})
        return _Resp({"results": []})   # empty -> stop


_Resp.text = "User-agent: *\nDisallow:\n"


def test_mcf_paginates_maps_stops():
    s = _Session()
    jobs = MyCareersFutureConnector(session=s).fetch()
    assert s.pages == [0, 1, 2]       # stops on empty page 2
    assert len(jobs) == 3
    a = jobs[0]
    assert a.source_job_id == "u1"
    assert a.title == "Events Coordinator"
    assert a.company == "Acme SG"
    assert a.location == "Singapore (West)"
    assert a.salary == "SGD 3200-4000/Monthly"
    assert a.employment_type == "Full-time"
    assert a.source_url == "https://www.mycareersfuture.gov.sg/job/Events Coordinator-u1"
    b = jobs[1]
    assert b.location == "Malaysia"   # overseas


def test_mcf_helpers():
    assert _location({"isOverseas": False, "districts": [{"region": "East"}]}) == "Singapore (East)"
    assert _location({"isOverseas": True, "overseasCountry": "India"}) == "India"
    assert _salary({"minimum": 5000, "maximum": 8000, "type": {"salaryType": "Monthly"}}) == "SGD 5000-8000/Monthly"
    assert _salary(None) is None
