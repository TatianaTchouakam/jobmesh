"""iSolvedHire connector — offline: sitemap.xml + per-posting JSON-LD JobPosting."""
from jobmesh.connectors.isolvedhire import IsolvedHireConnector

SITEMAP = """<?xml version='1.0' encoding='UTF-8'?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://acme.isolvedhire.com/jobs/</loc></url>
<url><loc>https://acme.isolvedhire.com/jobs/1902333.html</loc></url>
<url><loc>https://acme.isolvedhire.com/jobs/1828998.html</loc></url>
<url><loc>https://acme.isolvedhire.com/pages/jobmap/</loc></url>
</urlset>"""

def _jobpage(jid, title, city):
    ld = ('{"@context":"http://schema.org/","@type":"JobPosting","title":"%s",'
          '"url":"https://acme.isolvedhire.com/jobs/%s.html",'
          '"description":"<p>Do %s</p>","identifier":{"@type":"PropertyValue",'
          '"name":"acme","sameAs":"%s"},"datePosted":"2026-11-10 00:00:00",'
          '"employmentType":"FULL_TIME","hiringOrganization":{"@type":"Organization",'
          '"name":"Acme"},"jobLocation":{"@type":"Place","address":{"@type":'
          '"PostalAddress","addressLocality":"%s","addressRegion":"TS",'
          '"addressCountry":"IN"}}}' % (title, jid, title, jid, city))
    return ('<html><head><script type="application/ld+json">%s</script>'
            '</head><body>x</body></html>' % ld)


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

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
        if url.endswith("1902333.html"):
            return _Resp(_jobpage("1902333", "AI Engineer", "Hyderabad"))
        if url.endswith("1828998.html"):
            return _Resp(_jobpage("1828998", "Data Analyst", "Pune"))
        return _Resp("not found", status=404)


def test_sitemap_and_jsonld():
    c = IsolvedHireConnector("acme", session=_Session())
    jobs = c.fetch()
    assert len(jobs) == 2
    a = {j.source_job_id: j for j in jobs}
    assert a["1902333"].title == "AI Engineer"
    assert a["1902333"].company == "Acme"
    assert a["1902333"].location == "Hyderabad, TS, IN"
    assert a["1902333"].source_url == "https://acme.isolvedhire.com/jobs/1902333.html"
    assert "Do AI Engineer" in (a["1902333"].description or "")
    assert a["1828998"].title == "Data Analyst"
