"""Offline tests for the MinaJobs (Cameroon) connector."""

import requests

from jobmesh.connectors.minajobs import MinaJobsConnector


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


LISTING_P1 = """
<html><body>
<a href="/emplois/lead-devops-engineer-50585">Lead DevOps Engineer</a>
<a href="/emplois/manager-reseau-50596">Manager Réseau</a>
<a href="/emplois/lead-devops-engineer-50585">dup link same id</a>
</body></html>
"""

# page 2 returns no new job ids -> pagination stops
LISTING_EMPTY = "<html><body><a href='/emplois'>Toutes les offres</a></body></html>"

JOB_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting",
 "title":"Lead DevOps Engineer","description":"<p>Infra & CI/CD</p>",
 "identifier":"50585","datePosted":"2026-11-19T14:44:56.225Z",
 "validThrough":"2026-12-31T23:59:59.000Z","employmentType":"FULL_TIME",
 "hiringOrganization":{"@type":"Organization","name":"@fric payment solutions"},
 "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
   "addressLocality":"Douala","addressRegion":"Littoral","addressCountry":"CM"}}}
</script></head><body>offer</body></html>
"""


class _FakeSession:
    """Serves listing page 1, then empty pages, and the detail page."""
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None, **kw):
        self.calls.append(url)
        if "/emplois?page=1" in url:
            return _Resp(LISTING_P1)
        if "/emplois?page=" in url:
            return _Resp(LISTING_EMPTY)
        if url.endswith("/emplois"):
            return _Resp(LISTING_P1)
        # detail pages — serve a distinct posting per id
        if "manager-reseau-50596" in url:
            return _Resp(JOB_HTML.replace("50585", "50596")
                                 .replace("Lead DevOps Engineer", "Manager Réseau"))
        return _Resp(JOB_HTML)


def _no_robots(monkeypatch):
    monkeypatch.setattr("jobmesh.connectors.minajobs.robots_allowed",
                        lambda url, session=None: True)


def test_minajobs_parses_jsonld(monkeypatch):
    _no_robots(monkeypatch)
    conn = MinaJobsConnector("cm.minajobs.net", session=_FakeSession())
    jobs = conn.fetch()
    assert len(jobs) == 2
    j = next(x for x in jobs if "DevOps" in x.title)
    assert j.company == "@fric payment solutions"
    assert j.location == "Douala, Littoral, CM"
    assert j.source_platform == "minajobs"
    assert j.source_board == "cm.minajobs.net"
    assert j.source_url.endswith("/emplois/lead-devops-engineer-50585")
    assert j.source_job_id == "50585"  # id from URL, not JSON-LD PropertyValue name
    assert j.posted_at.startswith("2026-11-19")
    assert j.is_open is True


def test_minajobs_default_host(monkeypatch):
    _no_robots(monkeypatch)
    conn = MinaJobsConnector(session=_FakeSession())
    assert conn.board == "cm.minajobs.net"


def test_minajobs_robots_blocked(monkeypatch):
    monkeypatch.setattr("jobmesh.connectors.minajobs.robots_allowed",
                        lambda url, session=None: False)
    conn = MinaJobsConnector("cm.minajobs.net", session=_FakeSession())
    assert conn.fetch() == []
