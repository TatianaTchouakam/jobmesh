"""Offline tests for the JobBoardFire connector."""

import requests

from jobmesh.connectors.jobboardfire import JobBoardFireConnector


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


SITEMAP = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://jobs.example.com/jobs/product-marketing-lead-spektr-15zk0q</loc></url>
  <url><loc>https://jobs.example.com/jobs/product-marketing-manager-float-h3nd6x</loc></url>
</urlset>"""

JOB = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Product Marketing Lead",
 "description":"<p>Lead</p>","datePosted":"2026-10-29T10:26:32.345Z",
 "hiringOrganization":{"@type":"Organization","name":"spektr"},
 "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
   "addressLocality":"New York","addressCountry":"US"}}}
</script></head><body>x</body></html>"""


class _FakeSession:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout=None, **kw):
        if url.endswith("sitemap-jobs.xml"):
            return _Resp(SITEMAP)
        if "float-h3nd6x" in url:
            return _Resp(JOB.replace("Product Marketing Lead", "Product Marketing Manager"))
        return _Resp(JOB)


def _no_robots(monkeypatch):
    monkeypatch.setattr("jobmesh.connectors.jobboardfire.robots_allowed",
                        lambda url, session=None: True)


def test_jobboardfire_reads_sitemap_jobs(monkeypatch):
    _no_robots(monkeypatch)
    conn = JobBoardFireConnector("jobs.example.com", session=_FakeSession())
    jobs = conn.fetch()
    assert len(jobs) == 2
    titles = {j.title for j in jobs}
    assert "Product Marketing Lead" in titles
    assert all(j.source_platform == "jobboardfire" for j in jobs)
    # stable id from URL slug
    assert any(j.source_job_id.endswith("15zk0q") for j in jobs)


def test_jobboardfire_host_normalised(monkeypatch):
    _no_robots(monkeypatch)
    conn = JobBoardFireConnector("https://jobs.example.com/", session=_FakeSession())
    assert conn._sitemap == "https://jobs.example.com/sitemap-jobs.xml"
