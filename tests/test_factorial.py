"""Factorial connector — offline: sitemap.xml + per-posting JSON-LD JobPosting."""
from jobmesh.connectors.factorial import FactorialConnector

SITEMAP = """<?xml version='1.0'?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://careers.acme.com/</loc></url>
<url><loc>https://careers.acme.com/job_posting/bdr-jr-320887</loc></url>
<url><loc>https://careers.acme.com/job_posting/sales-ae-231864</loc></url>
</urlset>"""

def _page(jid, title, city, country):
    ld = ('{"@context":"http://schema.org/","@type":"JobPosting","title":"%s",'
          '"identifier":{"@type":"PropertyValue","name":"Factorial","value":"%s"},'
          '"datePosted":"2026-09-03","hiringOrganization":{"@type":"Organization",'
          '"name":"Factorial"},"jobLocation":{"@type":"Place","address":{"@type":'
          '"PostalAddress","addressCountry":"%s","addressLocality":"%s"}}}'
          % (title, jid, country, city))
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
        if "320887" in url:
            return _Resp(_page("320887", "BDR Jr.", "Ciudad de Mexico", "MX"))
        if "231864" in url:
            return _Resp(_page("231864", "Sales AE", "Barcelona", "ES"))
        return _Resp("x", status=404)


def test_sitemap_and_jsonld():
    c = FactorialConnector("careers.acme.com", session=_Session())
    jobs = c.fetch()
    assert len(jobs) == 2
    j = {x.source_job_id: x for x in jobs}
    assert j["320887"].title == "BDR Jr."
    assert j["320887"].company == "Factorial"
    assert j["320887"].location == "Ciudad de Mexico, MX"
    assert j["231864"].title == "Sales AE"
