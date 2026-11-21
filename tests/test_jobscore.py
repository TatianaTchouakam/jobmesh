"""JobScore connector — offline: official feed.json {company_name, jobs:[...]}."""
from jobmesh.connectors.jobscore import JobScoreConnector

FEED = {
    "company_name": "Solutions 2 GO",
    "jobs": [
        {"id": "d4_5UD9", "atom_id": "a1", "title": "eCommerce Lead",
         "company_name": "Solutions 2 GO",
         "apply_url": "https://careers.jobscore.com/apply/x/d4_5UD9",
         "detail_url": "https://careers.jobscore.com/jobs/solutions2go/ecommerce-lead",
         "department": "Sales", "location": "Hybrid in Santiago, Chile",
         "city": "Santiago", "state": "RM", "country": "Chile",
         "experience_level": "Mid", "description": "<p>Lead</p>",
         "job_type": "Full-time", "remote": True, "opened_date": "2026-11-10"},
        {"id": "e9_7Hq", "title": "Warehouse Associate",
         "detail_url": "https://careers.jobscore.com/jobs/solutions2go/wh",
         "apply_url": "https://careers.jobscore.com/apply/x/e9_7Hq",
         "city": "Brampton", "state": "ON", "country": "Canada",
         "job_type": "Part-time", "remote": False, "opened_date": "2026-11-12"},
    ],
}


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


class _Session:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("", status=404)
        return _Resp(FEED)


def test_feed_json_maps():
    c = JobScoreConnector("solutions2go", session=_Session())
    jobs = c.fetch()
    assert len(jobs) == 2
    j = {x.source_job_id: x for x in jobs}
    a = j["d4_5UD9"]
    assert a.title == "eCommerce Lead"
    assert a.company == "Solutions 2 GO"
    assert a.location == "Hybrid in Santiago, Chile"
    assert a.apply_url.endswith("/d4_5UD9")
    assert a.remote is True
    b = j["e9_7Hq"]
    assert b.location == "Brampton, ON, Canada"
    assert b.remote is False
