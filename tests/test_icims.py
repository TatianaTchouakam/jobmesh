"""iCIMS connector — offline: sitemap.xml + per-posting JSON-LD (via ?in_iframe=1)."""
from jobmesh.connectors.icims import IcimsConnector

SITEMAP = """<?xml version='1.0'?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://acme.icims.com/jobs/intro</loc></url>
<url><loc>https://acme.icims.com/jobs/201699/client-implementation-consultant/job</loc></url>
<url><loc>https://acme.icims.com/jobs/198547/therapist/job</loc></url>
</urlset>"""

def _page(title, city, region):
    ld = ('{"@type":"JobPosting","title":"%s","datePosted":"2026-11-20T23:00:00.000Z",'
          '"hiringOrganization":{"@type":"Organization","name":"PharMerica"},'
          '"jobLocation":[{"@type":"Place","address":{"@type":"PostalAddress",'
          '"addressCountry":"US","addressLocality":"%s","addressRegion":"%s"}}]}'
          % (title, city, region))
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
        if "201699" in url:
            return _Resp(_page("Client Implementation Consultant", "Louisville", "KY"))
        if "198547" in url:
            return _Resp(_page("Therapist", "Pune", "MH"))
        return _Resp("x", status=404)


def test_sitemap_and_iframe_jsonld():
    c = IcimsConnector("acme", session=_Session())
    jobs = c.fetch()
    assert len(jobs) == 2
    j = {x.source_job_id: x for x in jobs}
    assert j["201699"].title == "Client Implementation Consultant"
    assert j["201699"].company == "PharMerica"
    assert j["201699"].location == "Louisville, KY, US"
    assert j["201699"].source_url.endswith("/job")
    assert j["198547"].title == "Therapist"
