"""Generic sitemap + JSON-LD connector — offline.

Covers: sitemap-index recursion, pinned-company override, job-looking-URL
preference, robots.txt obeyed, and JSON-LD JobPosting extraction.
"""
from jobmesh.connectors.sitemapjsonld import SitemapJsonLdConnector
import pytest
import jobmesh.robots as _robots


@pytest.fixture(autouse=True)
def _clear_robots_cache():
    # robots parsers are cached per-origin globally; isolate each test.
    _robots._cache.clear()
    yield
    _robots._cache.clear()

INDEX = """<?xml version='1.0'?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://careers.acme.com/sitemap-jobs.xml</loc></sitemap>
<sitemap><loc>https://careers.acme.com/sitemap-pages.xml</loc></sitemap>
</sitemapindex>"""

JOBS_SITEMAP = """<?xml version='1.0'?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://careers.acme.com/jobs/101/data-engineer</loc></url>
<url><loc>https://careers.acme.com/jobs/102/analyst</loc></url>
<url><loc>https://careers.acme.com/about</loc></url>
</urlset>"""


def _page(title, org=None):
    org_ld = ('"hiringOrganization":{"@type":"Organization","name":"%s"},' % org) if org else ""
    ld = ('{"@type":"JobPosting","title":"%s","datePosted":"2026-11-20",'
          '%s'
          '"jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",'
          '"addressLocality":"Berlin","addressCountry":"DE"}}}' % (title, org_ld))
    return '<html><script type="application/ld+json">%s</script></html>' % ld


class _Resp:
    def __init__(self, text="", content=None, status=200):
        self.text = text
        self.content = content if content is not None else text.encode()
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


class _Session:
    def __init__(self, robots=""):
        self.headers = {}
        self._robots = robots

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(self._robots, status=200 if self._robots else 404)
        if url.endswith("sitemap.xml"):
            return _Resp(INDEX)
        if url.endswith("sitemap-jobs.xml"):
            return _Resp(JOBS_SITEMAP)
        if url.endswith("sitemap-pages.xml"):
            return _Resp("<urlset></urlset>")
        if "/jobs/101/" in url:
            return _Resp(_page("Data Engineer", org="Acme GmbH"))
        if "/jobs/102/" in url:
            return _Resp(_page("Analyst"))  # no hiringOrganization in JSON-LD
        if "/about" in url:
            return _Resp("<html>no jobs here</html>")
        return _Resp("x", status=404)


def test_index_recursion_and_company_pin():
    board = "https://careers.acme.com/sitemap.xml|Acme Corp"
    c = SitemapJsonLdConnector(board, session=_Session())
    jobs = c.fetch()
    titles = sorted(j.title for j in jobs)
    assert titles == ["Analyst", "Data Engineer"]
    # pinned company overrides whatever the JSON-LD says (or omits)
    assert {j.company for j in jobs} == {"Acme Corp"}
    j = {x.title: x for x in jobs}
    assert j["Data Engineer"].location == "Berlin, DE"
    assert j["Data Engineer"].source_url.endswith("/jobs/101/data-engineer")
    assert j["Data Engineer"].source_board == board


def test_company_from_jsonld_when_not_pinned():
    c = SitemapJsonLdConnector("https://careers.acme.com/sitemap.xml", session=_Session())
    jobs = c.fetch()
    j = {x.title: x for x in jobs}
    assert j["Data Engineer"].company == "Acme GmbH"


def test_robots_disallow_blocks_fetch():
    robots = "User-agent: JobmeshBot\nDisallow: /\n"
    c = SitemapJsonLdConnector(
        "https://careers.acme.com/sitemap.xml|Acme", session=_Session(robots=robots))
    assert c.fetch() == []
