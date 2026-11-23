"""Offline test: Paycor per-client ATOM feed (newton: namespaced fields, company from board)."""
import pytest
import requests

from jobmesh import robots
from jobmesh.connectors.paycor import PaycorConnector


@pytest.fixture(autouse=True)
def _fresh_robots_cache():
    robots._cache.clear()
    yield
    robots._cache.clear()

_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:newton="http://newtonsoftware.com/atom">
  <title>Careers</title>
  <entry>
    <title>Warehouse Associate &amp; Driver Helper</title>
    <link href="https://recruitingbypaycor.com/career/JobIntroduction.action?clientId=abc123&amp;id=j1"/>
    <id>j1</id>
    <updated>2026-11-20T14:02:11Z</updated>
    <published>2026-11-18T09:00:00Z</published>
    <summary type="html">&lt;p&gt;Load and unload trucks.&lt;/p&gt;</summary>
    <newton:jobid>WH-102</newton:jobid>
    <newton:department>Operations</newton:department>
    <newton:location>Cincinnati</newton:location>
    <newton:state>OH</newton:state>
    <newton:country>United States</newton:country>
  </entry>
  <entry>
    <title>Remote Payroll Specialist</title>
    <link href="https://recruitingbypaycor.com/career/JobIntroduction.action?clientId=abc123&amp;id=j2"/>
    <id>j2</id>
    <updated>2026-11-21T10:00:00Z</updated>
    <newton:location>Remote</newton:location>
  </entry>
  <entry>
    <title>Duplicate</title>
    <id>j2</id>
  </entry>
</feed>"""

_HOME = """<html><head>
<link rel="alternate" type="application/atom+xml" href="/career/CareerAtomFeed.action?clientId=abc123">
</head><body>Careers</body></html>"""


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class _Session:
    def __init__(self, routes):
        self.headers, self.routes, self.calls = {}, routes, []
    def get(self, url, timeout=None, **k):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nDisallow: /api/\n")
        for key, resp in self.routes.items():
            if key in url:
                return resp
        return _Resp("not found", 404)


def test_paycor_atom_from_declared_feed():
    s = _Session({
        "CareerHome.action": _Resp(_HOME),
        "CareerAtomFeed.action": _Resp(_ATOM),
    })
    jobs = PaycorConnector("abc123|Acme Logistics", session=s).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_platform == "paycor"
    assert a.source_job_id == "j1"
    assert a.company == "Acme Logistics"
    assert a.title == "Warehouse Associate & Driver Helper"
    assert a.location == "Cincinnati, OH, United States"
    assert a.description and "Load and unload" in a.description
    assert a.apply_url.endswith("clientId=abc123&id=j1")
    assert a.posted_at.startswith("2026-11-18")
    assert jobs[1].remote is True


def test_paycor_no_feed_raises_instead_of_empty():
    """A missing feed must be a fetch failure, never a silent 0 (no mass-close)."""
    s = _Session({})
    with pytest.raises(Exception):
        PaycorConnector("nope|X", session=s).fetch()


def test_paycor_respects_robots():
    class _Blocked(_Session):
        def get(self, url, timeout=None, **k):
            if url.endswith("/robots.txt"):
                return _Resp("User-agent: *\nDisallow: /career/\n")
            return super().get(url, timeout, **k)
    s = _Blocked({"CareerAtomFeed.action": _Resp(_ATOM)})
    with pytest.raises(Exception):
        PaycorConnector("abc123|Acme", session=s).fetch()
    assert not any("CareerAtomFeed" in c for c in s.calls)
