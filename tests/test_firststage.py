"""Offline test: FirstStage server-rendered job card list."""
from jobmesh.connectors.firststage import FirstStageConnector

_HTML = """<html><head><title>Jobs at First | First</title></head><body>
<a class="group" target="_top" href="https://firststage.firststage.co/jobs/4gpRKqyttE/view?layout=list">
<span class="font-medium text-balance link-text">Founding Engineer</span>
<span class="flex"><svg class="lucide lucide-map-pin"></svg> London, United Kingdom </span>
<span class="capitalize">full time</span></a>
<a target="_top" href="https://firststage.firststage.co/jobs/ZZ9/view?layout=list">
<span class="font-medium link-text">Remote Designer</span>
<span><svg class="lucide-map-pin"></svg> Remote </span></a>
</body></html>"""


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("")           # no robots -> fail-open
        return _Resp(_HTML)


def test_firststage_parses_cards():
    jobs = FirstStageConnector("firststage", session=_Session()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "4gpRKqyttE"
    assert a.title == "Founding Engineer"
    assert a.company == "First"
    assert a.location == "London, United Kingdom"
    assert a.source_url == "https://firststage.firststage.co/jobs/4gpRKqyttE/view"
    b = jobs[1]
    assert b.title == "Remote Designer" and b.location == "Remote" and b.remote is True
