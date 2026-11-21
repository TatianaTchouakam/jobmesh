"""Offline test: TriNet Hire server-rendered career table."""
from jobmesh.connectors.trinet import TriNetConnector

_HTML = """<html><head><title>Careers at Cabaletta Bio Inc.</title></head><body>
<table class="job-list"><thead><tr><th>Role</th><th>Type</th><th>Location</th></tr></thead>
<tbody>
<tr class="job" id="position_82"><td><a class="break-all-word" href="/companies/22943-cabaletta-bio-inc/jobs/126424-senior-accountant">Senior Accountant</a></td><td class="type">Full-time</td><td class="location">Hybrid or Remote</td></tr>
<tr class="job" id="position_81"><td><a href="/companies/22943-cabaletta-bio-inc/jobs/124900-assoc-dir">Associate Director, Stats &amp; Programming</a></td><td class="type">Full-time</td><td class="location">Philadelphia, PA</td></tr>
<tr class="job" id="position_80"><td><a href="/companies/22943-cabaletta-bio-inc/jobs/126424-senior-accountant">Senior Accountant</a></td><td class="type">Full-time</td><td class="location">Dup</td></tr>
</tbody></table></body></html>"""


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nAllow: /\n")
        return _Resp(_HTML)


def test_trinet_parses_table():
    jobs = TriNetConnector("22943-cabaletta-bio-inc", session=_Session()).fetch()
    assert len(jobs) == 2                       # duplicate jid 126424 collapsed
    a = jobs[0]
    assert a.source_job_id == "126424"
    assert a.title == "Senior Accountant"
    assert a.company == "Cabaletta Bio Inc."
    assert a.employment_type == "Full-time"
    assert a.location == "Hybrid or Remote"
    assert a.remote is True
    assert a.source_url == "https://app.trinethire.com/companies/22943-cabaletta-bio-inc/jobs/126424-senior-accountant"
    b = jobs[1]
    assert b.title == "Associate Director, Stats & Programming"
    assert b.location == "Philadelphia, PA"
    assert b.remote is False
