"""Offline tests for the BrassRing connector (detail-page JSON-LD, CC enumeration)."""
import requests
from jobmesh.connectors.brassring import BrassRingConnector

JOB = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Project Engineer",
 "hiringOrganization":{"@type":"Organization","name":"Bechtel"},
 "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
   "addressLocality":"Houston","addressCountry":"US"}},"datePosted":"2026-11-18"}
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


URLS = ["https://sjobs.brassring.com/TGnewUI/Search/home/HomeWithPreLoad?partnerid=26639&siteid=5507&PageType=JobDetails&jobid=944903",
        "https://sjobs.brassring.com/TGnewUI/Search/home/HomeWithPreLoad?partnerid=26639&siteid=5507&PageType=JobDetails&jobid=944902"]


def test_brassring_reads_detail_jsonld(monkeypatch):
    monkeypatch.setattr("jobmesh.connectors.brassring.robots_allowed", lambda u, s=None: True)
    conn = BrassRingConnector("26639|5507", session=_FakeSession(), url_source=URLS)
    jobs = conn.fetch()
    assert len(jobs) == 2
    assert all(j.source_platform == "brassring" for j in jobs)
    assert {j.source_job_id for j in jobs} == {"944903", "944902"}
    assert jobs[0].company == "Bechtel"
