"""Zoho Recruit connector — offline, against the real embedded-JSON markup."""
import json
from jobmesh.connectors.zohorecruit import ZohoRecruitConnector

ROBOTS = "User-agent: *\nAllow: /jobs\nAllow: /jobs/\nAllow: /jobs/*\nDisallow: /\n"


def _encode(obj: dict) -> str:
    # Zoho embeds job JSON with HTML-entity-encoded quotes inside the page.
    return json.dumps(obj).replace('"', "&#34;")


def _page(objs):
    # surround with unrelated config arrays like the real page
    noise = '<script>var cfg=[{&#34;id&#34;:&#34;5&#34;,&#34;fields&#34;:[{&#34;x&#34;:1}]}];'
    body = ",".join(_encode(o) for o in objs)
    return f'<html><body>{noise}var joblist=[{body}];</script></body></html>'


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(self.status_code)


class _FakeSession:
    def __init__(self, page):
        self.headers = {}
        self._page = page

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(ROBOTS)
        if url.endswith("/jobs/Careers"):
            return _Resp(self._page)
        return _Resp("", status=404)


def _job(jid, title, **kw):
    o = {"Remote_Job": False, "Posting_Title": title, "City": None, "State": None,
         "Country": None, "Industry": "Technology", "Job_Description": "<p>Do things</p>",
         "Job_Type": "Full time", "id": jid, "Publish": True, "Date_Opened": "2026-09-29"}
    o.update(kw)
    return o


def test_extracts_and_maps():
    page = _page([
        _job("111", "Backend Engineer", City="Berlin", Country="Germany",
             Job_Description="Build services {with scale}"),   # brace inside description
        _job("222", "Remote Designer", Remote_Job=True),
        _job("333", "Hidden Role", Publish=False),              # unpublished -> filtered
    ])
    c = ZohoRecruitConnector("acme-co", session=_FakeSession(page))
    jobs = c.fetch()
    assert len(jobs) == 2
    j = {x.source_job_id: x for x in jobs}
    a = j["111"]
    assert a.title == "Backend Engineer"
    assert a.company == "Acme Co"
    assert a.location == "Berlin, Germany"
    assert a.employment_type == "Full-time"   # normalized by Job model
    assert a.category == "Engineering"   # normalized by Job model from title
    assert "Build services" in (a.description or "")   # brace-in-description handled
    assert a.source_url == "https://acme-co.zohorecruit.com/jobs/Careers/111/Backend-Engineer?source=CareerSite"
    assert a.source_platform == "zohorecruit" and a.source_board == "acme-co"
    b = j["222"]
    assert b.remote is True and b.workplace_type == "remote" and b.location == "Remote"


def test_robots_blocks_when_disallowed():
    # if robots forbids everything with no /jobs allow, connector returns []
    class _Blocked(_FakeSession):
        def get(self, url, timeout=None, **k):
            if url.endswith("/robots.txt"):
                return _Resp("User-agent: *\nDisallow: /\n")
            return _Resp(self._page)
    c = ZohoRecruitConnector("blocked-co", session=_Blocked(_page([_job("1", "X")])))
    assert c.fetch() == []
