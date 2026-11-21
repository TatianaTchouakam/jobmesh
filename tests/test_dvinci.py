"""d.vinci connector — offline: /jobPublication/list.json array with jobOpening."""
from jobmesh.connectors.dvinci import DvinciConnector

FEED = [
    {"id": 20294, "position": "Projektkoordinator (m/w/d)",
     "pageDescription": "<p>Spannend</p>",
     "jobPublicationURL": "https://cadenas.dvinci-hr.com/de/jobs/20294/pk",
     "applicationFormURL": "https://cadenas.dvinci-hr.com/de/jobs/20294/apply",
     "startDate": "2026-10-06T22:00Z",
     "jobOpening": {"company": {"name": "CADENAS GmbH"},
                    "location": "Augsburg (onsite)", "department": "Product Management",
                    "workingTimes": [{"name": "Full-time"}],
                    "salaryRange": "45,000.00 to 50,000.00 EUR gross per year"}},
    {"id": 20301, "position": "Werkstudent",
     "jobPublicationURL": "https://cadenas.dvinci-hr.com/de/jobs/20301/ws",
     "jobOpening": {"company": {"name": "CADENAS GmbH"},
                    "locations": [{"address": {"city": "Munich",
                                               "country": {"isoA2": "DE"}}}]}},
]


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


def test_list_json_maps():
    c = DvinciConnector("cadenas", session=_Session())
    jobs = c.fetch()
    assert len(jobs) == 2
    j = {x.source_job_id: x for x in jobs}
    a = j["20294"]
    assert a.title == "Projektkoordinator (m/w/d)"
    assert a.company == "CADENAS GmbH"
    assert a.location == "Augsburg (onsite)"
    assert a.salary.startswith("45,000")
    assert a.apply_url.endswith("/apply")
    assert j["20301"].location == "Munich, DE"
