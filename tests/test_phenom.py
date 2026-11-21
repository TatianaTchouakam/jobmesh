"""Phenom connector — offline: sitemap.xml + per-posting schema.org JobPosting."""
from jobmesh.connectors.phenom import PhenomConnector

SITEMAP = """<?xml version='1.0'?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://careers.acme.com/us/en</loc></url>
<url><loc>https://careers.acme.com/us/en/job/JR107356/Vice-President</loc></url>
<url><loc>https://careers.acme.com/us/en/job/JR107447/Coordinator</loc></url>
</urlset>"""

def _page(jid, title, city, region):
    ld = ('{"@type":"JobPosting","title":"%s","datePosted":"2026-09-21",'
          '"employmentType":["FULL_TIME"],"hiringOrganization":{"@type":'
          '"Organization","name":"Acme Mortgage"},"identifier":{"@type":'
          '"PropertyValue","name":"Acme","value":"%s"},"jobLocation":{"@type":'
          '"Place","address":{"@type":"PostalAddress","addressCountry":'
          '"United States","addressLocality":"%s","addressRegion":"%s"}}}'
          % (title, jid, city, region))
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
        if "JR107356" in url:
            return _Resp(_page("JR107356", "Vice President", "Marlton", "New Jersey"))
        if "JR107447" in url:
            return _Resp(_page("JR107447", "Coordinator", "Fishers", "Indiana"))
        return _Resp("x", status=404)


def test_sitemap_and_jsonld():
    c = PhenomConnector("careers.acme.com", session=_Session())
    jobs = c.fetch()
    assert len(jobs) == 2
    j = {x.source_job_id: x for x in jobs}
    assert j["JR107356"].title == "Vice President"
    assert j["JR107356"].company == "Acme Mortgage"
    assert j["JR107356"].location == "Marlton, New Jersey, United States"
    assert j["JR107447"].title == "Coordinator"
