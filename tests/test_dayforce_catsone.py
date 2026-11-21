"""Offline tests: Dayforce (CSRF handshake + paginated search) and CATS (.data turbo-stream)."""
import json

from jobmesh.connectors.dayforce import DayforceConnector
from jobmesh.connectors.catsone import CatsOneConnector, decode_turbo_stream


class _Resp:
    def __init__(self, payload=None, status=200, text=None):
        self._p, self.status_code = payload, status
        self.text = text if text is not None else (json.dumps(payload) if payload is not None else "")

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


def _posting(pid, title, loc="Mauritius", virtual=False):
    return {"jobPostingId": pid, "jobTitle": title,
            "jobDescription": "At Dayforce, we&rsquo;re <b>hiring</b>",
            "hasVirtualLocation": virtual,
            "postingStartTimestampUTC": "2025-07-06T20:00:00+00:00",
            "postingLocations": [{"formattedAddress": loc}] if loc else []}


class _DfSession:
    def __init__(self):
        self.headers, self.posts = {}, []

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(status=200, text="# content signals only\n")
        assert url.endswith("/api/auth/csrf")
        return _Resp({"csrfToken": "tok"})

    def post(self, url, json=None, headers=None, timeout=None, **k):
        assert url.endswith("/api/geo/acme/jobposting/search")
        assert headers["X-CSRF-Token"] == "tok"
        self.posts.append(json["paginationStart"])
        if json["paginationStart"] == 0:
            return _Resp({"jobPostings": [_posting(1, "Engineer"), _posting(2, "Analyst")],
                          "maxCount": 3, "offset": 0, "count": 2})
        return _Resp({"jobPostings": [_posting(3, "Remote Dev", loc=None, virtual=True)],
                      "maxCount": 3, "offset": 2, "count": 1})


def test_dayforce_paginates_and_maps():
    s = _DfSession()
    jobs = DayforceConnector("acme", session=s).fetch()
    assert s.posts == [0, 2]
    assert [j.source_job_id for j in jobs] == ["1", "2", "3"]
    a = jobs[0]
    assert a.title == "Engineer" and a.location == "Mauritius"
    assert a.source_url == "https://jobs.dayforcehcm.com/en-US/acme/CANDIDATEPORTAL/jobs/1"
    assert "we’re" in a.description and "<b>" not in a.description
    assert jobs[2].remote is True


def test_dayforce_board_code():
    c = DayforceConnector("acme|CAREERS")
    assert c.namespace == "acme" and c.board_code == "CAREERS"


# turbo-stream payload as served by {slug}.catsone.com/careers/{id}.data
TURBO = [
    {"_1": 2, "_14": 15},
    "portals/cats-careers/portal", {"_3": 4}, "data", {"_5": 6}, "portal",
    {"_7": 8, "_9": -5}, "name", "Southern Adventist University", "parentPortalId",
    None, None, None, None,
    "portals/cats-careers/jobs", {"_3": 16}, {"_17": 18}, "jobs", [19, 26],
    {"_20": 21, "_22": 23, "_24": 25, "_27": 28},
    "jobId", "16875174", "positionTitle", "Vice President", "city", "Collegedale",
    {"_20": 29, "_22": 30, "_27": 31},
    "state", "Tennessee", "16872702", "Network Technician", "TN",
]


def test_decode_turbo_stream():
    root = decode_turbo_stream(TURBO)
    assert root["portals/cats-careers/portal"]["data"]["portal"]["name"].startswith("Southern")
    assert root["portals/cats-careers/jobs"]["data"]["jobs"][0]["positionTitle"] == "Vice President"


class _CatsSession:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(status=200, text="User-agent: *\nDisallow: \n")
        assert url == "https://sau.catsone.com/careers/112762.data"
        return _Resp(text=json.dumps(TURBO))


def test_catsone_maps_jobs():
    jobs = CatsOneConnector("sau|112762", session=_CatsSession()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.company == "Southern Adventist University"
    assert a.title == "Vice President" and a.location == "Collegedale, Tennessee"
    assert a.source_url == "https://sau.catsone.com/careers/112762/jobs/16875174"
    assert jobs[1].location == "TN"


def test_catsone_board_from_url():
    c = CatsOneConnector("https://icrecruiting.catsone.com/careers/20594")
    assert (c.slug, c.portal_id) == ("icrecruiting", "20594")
