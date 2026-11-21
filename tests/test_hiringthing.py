"""Offline test: HiringThing server-rendered job cards."""
from jobmesh.connectors.hiringthing import HiringThingConnector

_HTML = """<html><head><title>SMART Reading Career Opportunities</title></head><body>
<div class="jobs-list">
<div class="job-container" data-job-id="1077765" data-testid="x">
<div class="job-headline"><div class="job-title-and-category">
<a class="mobile-apply-link" href="/job/1077765/institutional-giving-development-officer-portland-metro">
<h2>Institutional Giving - Development Officer - Portland Metro</h2></a></div>
<div class="job-location-and-category"><div class="job-location"> Portland, OR </div></div></div></div>
<div class="job-container" data-job-id="1069861">
<a href="/job/1069861/development-coordinator"><h2>Development Coordinator</h2></a>
<div class="job-location"> Remote </div></div>
</div></body></html>"""


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nDisallow: /admin\n")
        return _Resp(_HTML)


def test_hiringthing_parses_cards():
    jobs = HiringThingConnector("smart", session=_Session()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "1077765"
    assert a.title == "Institutional Giving - Development Officer - Portland Metro"
    assert a.company == "SMART Reading"
    assert a.location == "Portland, OR"
    assert a.source_url == "https://smart.hiringthing.com/job/1077765/institutional-giving-development-officer-portland-metro"
    b = jobs[1]
    assert b.title == "Development Coordinator" and b.location == "Remote" and b.remote is True


def test_hiringthing_whitelabel_host():
    c = HiringThingConnector("careers.prismhr-hire.com")
    assert c.host == "https://careers.prismhr-hire.com"
    assert c._url == "https://careers.prismhr-hire.com/jobs"
