"""Offline test: Rival / SilkRoad server-rendered vacancy list."""
from jobmesh.connectors.rival import RivalConnector

_HTML = """<html><head><title>RAA - Be part of something bigger!</title></head><body>
<section class="sr-wrapper"><article class="sr-search__section">
<a id="Job-3248" class="sr-panel" href="/RAA/RAACareers/jobs/3248">
<div class="sr-panel__title" id="t-3248"> AI Hub - Capability &amp; Change Lead </div>
<div class="sr-panel__location"><span class="sr-panel__meta">Adelaide, SA</span></div></a>
<a id="Job-3247" class="sr-panel" href="/RAA/RAACareers/jobs/3247">
<div class="sr-panel__title"> Remote Data Engineer </div>
<div class="sr-panel__location"><span class="sr-panel__meta">Remote, Australia</span></div></a>
</article></section></body></html>"""


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def __init__(self): self.calls = 0
    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nDisallow: /bin/\nDisallow: /*/*/Ajax/\n")
        self.calls += 1
        # page 1 returns the list; any ?page=N returns the same -> dedup stops the loop
        return _Resp(_HTML)


def test_rival_parses_and_stops():
    s = _Session()
    jobs = RivalConnector("RAA/RAACareers", session=s).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "3248"
    assert a.title == "AI Hub - Capability & Change Lead"
    assert a.company == "RAA"
    assert a.location == "Adelaide, SA"
    assert a.source_url == "https://jobs.silkroad.com/RAA/RAACareers/jobs/3248"
    assert jobs[1].title == "Remote Data Engineer" and jobs[1].remote is True
    # page 2 yielded no new ids -> loop stopped (2 content fetches at most)
    assert s.calls <= 2
