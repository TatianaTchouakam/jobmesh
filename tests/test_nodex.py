"""Offline test: Nodex sitemap + per-posting JSON-LD."""
import json
from jobmesh.connectors.nodex import NodexConnector

_SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://www.work.healthcare/find-jobs</loc></url>
<url><loc>https://www.work.healthcare/job/registered-veterinary-nurse-london</loc></url>
<url><loc>https://www.work.healthcare/job/private-associate-dentist-tangmere</loc></url>
</urlset>"""

def _jobpage(title, city, country="GB"):
    ld = {"@context":"https://schema.org","@type":"JobPosting","title":title,
          "datePosted":"2026-11-10","employmentType":"FULL_TIME",
          "hiringOrganization":{"@type":"Organization","name":"A Vet Clinic"},
          "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":city,"addressCountry":country}},
          "description":"<p>Great role</p>"}
    return f'<html><head><script type="application/ld+json">{json.dumps(ld)}</script></head><body>x</body></html>'


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nDisallow: /find-jobs?*\n")
        if url.endswith("/sitemap.xml"):
            return _Resp(_SITEMAP)
        if "registered-veterinary-nurse" in url:
            return _Resp(_jobpage("Registered Veterinary Nurse", "London"))
        if "private-associate-dentist" in url:
            return _Resp(_jobpage("Private Associate Dentist", "Tangmere"))
        return _Resp("<html></html>")


def test_nodex_sitemap_jsonld():
    jobs = NodexConnector("www.work.healthcare", session=_Session()).fetch()
    assert len(jobs) == 2            # find-jobs (not /job/) excluded
    a = jobs[0]
    assert a.title == "Registered Veterinary Nurse"
    assert a.company == "A Vet Clinic"
    assert a.location == "London, GB"
    assert a.employment_type == "Full-time"
    assert a.source_url.endswith("/job/registered-veterinary-nurse-london")
    assert "Great role" in (a.description or "")
