"""Offline test: Trakstar Hire server-rendered careers cards."""
from jobmesh.connectors.trakstar import TrakstarConnector

_HTML = """<html><head><title>
    BookMyShow jobs | BookMyShow openings | BookMyShow careers
</title></head><body>
<div class="js-card list-item js-careers-page-job-list-item" data-href="/jobs/fk0znk2/">
<a href="/jobs/fk0znk2/"><div class="row"><div class="col">
<h3 class="rb-h3 js-job-list-opening-name cut-text" data-toggle="tooltip" title="Assistant Manager - Company Secretary"> Assistant Manager - Company Secretary </h3>
<div class="rb-text-6 js-job-list-opening-loc cut-text" data-toggle="tooltip" title="Mumbai"> Mumbai </div>
</div></div></a></div>
<div class="js-card js-careers-page-job-list-item" data-href="/jobs/fk0p9wd/">
<a href="/jobs/fk0p9wd/">
<h3 class="js-job-list-opening-name" title="Remote Data Engineer"> Remote Data Engineer </h3>
<div class="js-job-list-opening-loc" title="Work From Home"> Work From Home </div>
</a></div>
</body></html>"""


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nDisallow: /prepare*\nAllow: /\n")
        return _Resp(_HTML)


def test_trakstar_parses_cards():
    jobs = TrakstarConnector("bookmyshow", session=_Session()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "fk0znk2"
    assert a.title == "Assistant Manager - Company Secretary"
    assert a.company == "BookMyShow"
    assert a.location == "Mumbai"
    assert a.source_url == "https://bookmyshow.hire.trakstar.com/jobs/fk0znk2/"
    assert a.remote is False
    b = jobs[1]
    assert b.title == "Remote Data Engineer" and b.remote is True
