"""Offline tests for the CSOD connector (detail-page JSON-LD, CC enumeration)."""
import requests
from jobmesh.connectors.csod import CsodConnector

JOB = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Analyst",
 "hiringOrganization":{"@type":"Organization","name":"IATA"},
 "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
   "addressLocality":"Geneva","addressCountry":"CH"}},"datePosted":"2026-11-20"}
</script></head><body>x</body></html>"""


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class _FakeSession:
    def __init__(self):
        self.headers = {}
    def get(self, url, timeout=None, **k):
        return _Resp(JOB)


URLS = ["https://iata.csod.com/ux/ats/careersite/1/home/requisition/3897?c=iata",
        "https://iata.csod.com/ux/ats/careersite/1/home/requisition/3850?c=iata"]


def test_csod_reads_detail_jsonld(monkeypatch):
    monkeypatch.setattr("jobmesh.connectors.csod.robots_allowed", lambda u, s=None: True)
    conn = CsodConnector("iata", session=_FakeSession(), url_source=URLS)
    jobs = conn.fetch()
    assert len(jobs) == 2
    assert all(j.source_platform == "csod" for j in jobs)
    assert {j.source_job_id for j in jobs} == {"3897", "3850"}
    assert jobs[0].title == "Analyst"
