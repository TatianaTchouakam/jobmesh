"""Homerun connector — offline: sitemap.xml (slug pages + /apply) + JSON-LD."""
from jobmesh.connectors.homerun import HomerunConnector

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://vacatures.acme.nl</loc></url>
<url><loc>https://vacatures.acme.nl/hoofd-hr</loc></url>
<url><loc>https://vacatures.acme.nl/hoofd-hr/nl/apply</loc></url>
<url><loc>https://vacatures.acme.nl/designer</loc></url>
<url><loc>https://vacatures.acme.nl/designer/nl/apply</loc></url>
</urlset>"""

def _page(jid, title, city):
    ld = ('{"@type":"JobPosting","title":"%s","datePosted":"2026-11-17",'
          '"employmentType":"FULL_TIME","hiringOrganization":{"@type":'
          '"Organization","name":"Acme"},"identifier":{"@type":"PropertyValue",'
          '"name":"Acme","value":"%s"},"jobLocation":{"@type":"Place","address":'
          '{"@type":"PostalAddress","addressCountry":"NL","addressLocality":"%s",'
          '"addressRegion":"Noord-Holland"}}}' % (title, jid, city))
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
        if url.endswith("/hoofd-hr"):
            return _Resp(_page("job_1", "Hoofd HR", "Hilversum"))
        if url.endswith("/designer"):
            return _Resp(_page("job_2", "Designer", "Amsterdam"))
        return _Resp("x", status=404)


def test_sitemap_skips_apply_and_maps():
    c = HomerunConnector("vacatures.acme.nl", session=_Session())
    jobs = c.fetch()
    assert len(jobs) == 2
    j = {x.source_job_id: x for x in jobs}
    assert j["job_1"].title == "Hoofd HR"
    assert j["job_1"].company == "Acme"
    assert j["job_1"].location == "Hilversum, Noord-Holland, NL"
    assert j["job_1"].apply_url == "https://vacatures.acme.nl/hoofd-hr/apply"
    assert j["job_2"].title == "Designer"
