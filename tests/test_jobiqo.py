"""Jobiqo connector — offline: sitemap.xml + per-posting schema.org JobPosting."""
from jobmesh.connectors.jobiqo import JobiqoConnector

SITEMAP = """<?xml version='1.0'?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://careers.acme.org/jobs</loc></url>
<url><loc>https://careers.acme.org/job/grant-specialist-56715</loc></url>
<url><loc>https://careers.acme.org/job/controller-57998</loc></url>
</urlset>"""

def _page(jid, title, city, region):
    ld = ('{"@type":"JobPosting","title":"%s","datePosted":"2026-10-22T15:03:25-04:00",'
          '"employmentType":"FULL_TIME","hiringOrganization":{"@type":"Organization",'
          '"name":"United Way SHR"},"jobLocation":{"@type":"Place","address":{"@type":'
          '"PostalAddress","addressCountry":"US","addressLocality":"%s",'
          '"addressRegion":"%s"}}}' % (title, city, region))
    return '<html><script type="application/ld+json">%s</script></html>' % ld


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


class _Session:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("", status=404)
        if url.endswith("/sitemap.xml"):
            return _Resp(SITEMAP)
        if "56715" in url:
            return _Resp(_page("56715", "Grant Specialist", "Norfolk", "VA"))
        if "57998" in url:
            return _Resp(_page("57998", "Controller", "Dayton", "OH"))
        return _Resp("x", status=404)


def test_sitemap_and_jsonld():
    c = JobiqoConnector("careers.acme.org", session=_Session())
    jobs = c.fetch()
    assert len(jobs) == 2
    j = {x.source_job_id: x for x in jobs}
    assert j["56715"].title == "Grant Specialist"
    assert j["56715"].company == "United Way SHR"
    assert j["56715"].location == "Norfolk, VA, US"
    assert j["57998"].title == "Controller"


SITEMAP_LIST = """<?xml version='1.0'?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://jobs.acme.at/job/multi-loc-42</loc></url>
</urlset>"""

_PAGE_LIST = ('<html><script type="application/ld+json">{"@type":"JobPosting",'
             '"title":"Multi-loc","hiringOrganization":{"@type":"Organization",'
             '"name":"WKO"},"jobLocation":[{"@type":"Place","address":{"@type":'
             '"PostalAddress","addressLocality":"Vienna","addressRegion":"W",'
             '"addressCountry":"AT"}},{"@type":"Place","address":{"@type":'
             '"PostalAddress","addressLocality":"Graz"}}]}</script></html>')


class _SessionList:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("", status=404)
        if url.endswith("/sitemap.xml"):
            return _Resp(SITEMAP_LIST)
        return _Resp(_PAGE_LIST)


def test_joblocation_as_list_does_not_crash():
    c = JobiqoConnector("jobs.acme.at", session=_SessionList())
    jobs = c.fetch()
    assert len(jobs) == 1
    assert jobs[0].location == "Vienna, W, AT"
