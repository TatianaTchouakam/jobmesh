"""Offline test: EURES EU search API (pagination, mapping, cap)."""
from jobmesh.connectors.eures import EuresConnector, _location, _posted


def _jv(jid, title, company, cc):
    return {"id": jid, "title": title, "description": "<p>EU role</p>",
            "employer": {"name": company, "website": "https://x.eu"},
            "locationMap": {cc: [cc + "213"]}, "creationDate": 1789550150212,
            "positionScheduleCodes": ["fulltime"], "numberOfPosts": 1}


class _Resp:
    status_code = 200
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def __init__(self): self.pages = []
    def get(self, url, timeout=None, **k):
        return _Resp(None)                      # robots.txt
    def post(self, url, json=None, timeout=None, headers=None, **k):
        assert url.endswith("/public/jv-search/search")
        self.pages.append(json["page"])
        if json["page"] == 1:
            return _Resp({"numberRecords": 3, "jvs": [
                _jv("id1", "Busmechanieker", "Hansea", "BE"),
                _jv("id2", "Remote Developer", "TechCo", "DE")]})
        if json["page"] == 2:
            return _Resp({"numberRecords": 3, "jvs": [_jv("id3", "Nurse", "Hospital", "FR")]})
        return _Resp({"jvs": []})


_Resp.text = "User-agent: *\nDisallow: /eures/private/\n"


def test_eures_paginates_and_maps():
    s = _Session()
    jobs = EuresConnector(session=s).fetch()
    assert s.pages == [1, 2, 3]
    assert len(jobs) == 3
    a = jobs[0]
    assert a.source_job_id == "id1"
    assert a.title == "Busmechanieker"
    assert a.company == "Hansea"
    assert a.location == "Belgium"
    assert a.employment_type == "Full-time"
    assert a.source_url == "https://europa.eu/eures/portal/jv-se/jv-details/id1?lang=en"
    assert a.posted_at and a.posted_at.startswith("20")
    b = jobs[1]
    assert b.location == "Germany" and b.remote is True


def test_eures_helpers():
    assert _location({"ES": ["ES1"], "IT": ["IT1"]}) == "Spain, Italy"
    assert _location({}) is None
    assert _posted(1789550150212).startswith("20")
    assert _posted(None) is None
