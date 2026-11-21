"""Offline test: HireBridge server-rendered career list parsing."""
from jobmesh.connectors.hirebridge import HireBridgeConnector

_HTML = """<html><head><title>
\tMenard, Inc Career Center
</title></head><body>
<div id="bgroup-1" class="jobgroupcontainer"><ul class="jobs">
<li onclick="x"><span class="job"><a href="/v3/Jobs/JobDetails.aspx?cid=5535&amp;jid=393832&amp;bid=1">Management Internship</a></span><span class="department"> </span></li></ul>
<ul class="jobs"><li><span class="job"><a href="/v3/Jobs/JobDetails.aspx?cid=5535&amp;jid=412644&amp;bid=1">Part-Time Outside Yard &amp; Receiving</a></span></li></ul>
<ul class="jobs"><li><span class="job"><a href="/v3/Jobs/JobDetails.aspx?cid=5535&amp;jid=393832&amp;bid=1">Management Internship</a></span></li></ul>
</div></body></html>"""


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nDisallow: /application\nDisallow: /company\n")
        return _Resp(_HTML)


def test_hirebridge_parses_list():
    jobs = HireBridgeConnector("5535", session=_Session()).fetch()
    assert len(jobs) == 2                      # duplicate jid collapsed
    j = jobs[0]
    assert j.source_job_id == "393832"
    assert j.title == "Management Internship"
    assert j.company == "Menard, Inc"
    assert j.source_url == "https://recruit.hirebridge.com/v3/Jobs/JobDetails.aspx?cid=5535&jid=393832&bid=1"
    assert jobs[1].title == "Part-Time Outside Yard & Receiving"
