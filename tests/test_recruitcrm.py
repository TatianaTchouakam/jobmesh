"""Offline test: Recruit CRM keyless agency jobs API."""
from jobmesh.connectors.recruitcrm import RecruitCrmConnector


class _Resp:
    status_code = 200
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        # robots.txt -> * Allow: /
        return _Resp(None) if not url.endswith("/robots.txt") else _Resp(None)
    def post(self, url, json=None, timeout=None, **k):
        assert "jobs-by-account/get?account=Intver_Global" in url
        return _Resp({"data": {"jobs": [
            {"slug": "abc123", "srno": "255", "name": "Procurement Engineer (India)",
             "companyname": "", "showcompany": 0, "city": "Mumbai",
             "locality": "Andheri East", "jdtext": "<p>Great role</p>"},
            {"slug": "def456", "srno": "256", "name": "Remote Software Engineer",
             "companyname": "Acme Ltd", "showcompany": 1, "city": "Singapore",
             "locality": "", "jdtext": "<p>Build things</p>"},
        ]}})


# robots helper needs a text attribute; give _Resp a benign one
_Resp.text = "User-agent: *\nAllow: /\n"


def test_recruitcrm_maps_jobs():
    jobs = RecruitCrmConnector("Intver_Global", session=_Session()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "255"
    assert a.title == "Procurement Engineer (India)"
    assert a.company == "Intver Global"            # showcompany=0 -> account name
    assert a.location == "Andheri East, Mumbai"
    assert a.source_url == "https://recruitcrm.io/apply/abc123"
    assert "Great role" in (a.description or "")
    b = jobs[1]
    assert b.company == "Acme Ltd"                  # showcompany=1 -> companyname
    assert b.location == "Singapore"
    assert b.remote is True
