"""Offline tests for the Africarrieres (pan-African) connector."""

import requests

from jobmesh.connectors.africarrieres import AfricarrieresConnector


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


SITEMAP = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://africarrieres.com/cameroun/fr</loc></url>
  <url><loc>https://africarrieres.com/cameroun/fr/emplois</loc></url>
  <url><loc>https://africarrieres.com/cameroun/fr/entreprises/wave</loc></url>
  <url><loc>https://africarrieres.com/cameroun/fr/emplois/agent-admin-officer</loc></url>
  <url><loc>https://africarrieres.com/cameroun/fr/emplois/juriste-senior-hf</loc></url>
  <url><loc>https://africarrieres.com/cameroun/fr/articles/un-article</loc></url>
</urlset>"""

JOB = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting","title":"Agent Admin Officer",
 "description":"<p>Admin</p>","datePosted":"2026-11-19T15:43:50+00:00",
 "hiringOrganization":{"@type":"Organization","name":"Wave"},
 "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
   "addressLocality":"Yaoundé","addressCountry":"CM"}}}
</script></head><body>x</body></html>"""


class _FakeSession:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout=None, **kw):
        if url.endswith("sitemap-cm-fr.xml"):
            return _Resp(SITEMAP)
        if "/emplois/juriste-senior-hf" in url:
            return _Resp(JOB.replace("Agent Admin Officer", "Juriste Senior H/F"))
        return _Resp(JOB)


def _no_robots(monkeypatch):
    monkeypatch.setattr("jobmesh.connectors.africarrieres.robots_allowed",
                        lambda url, session=None: True)


def test_africarrieres_only_job_urls(monkeypatch):
    _no_robots(monkeypatch)
    conn = AfricarrieresConnector("cm-fr", session=_FakeSession())
    jobs = conn.fetch()
    # 2 /emplois/{slug} detail pages — listing, entreprises, articles excluded
    assert len(jobs) == 2
    j = next(x for x in jobs if "Admin" in x.title)
    assert j.company == "Wave"
    assert j.location == "Yaoundé, CM"
    assert j.source_platform == "africarrieres"
    assert j.source_board == "cm-fr"
    assert j.source_job_id == "agent-admin-officer"
    assert j.source_url.endswith("/emplois/agent-admin-officer")
    assert j.posted_at.startswith("2026-11-19")


def test_africarrieres_robots_blocked(monkeypatch):
    monkeypatch.setattr("jobmesh.connectors.africarrieres.robots_allowed",
                        lambda url, session=None: False)
    conn = AfricarrieresConnector("cm-fr", session=_FakeSession())
    assert conn.fetch() == []
