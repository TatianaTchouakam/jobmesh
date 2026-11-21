"""Offline test: GoHire sitemap.txt -> schema.org JSON-LD per job."""
from jobmesh.connectors.gohire import GoHireConnector

_SITEMAP = """http://careers.gohire.io/
http://careers.gohire.io/ats-specialist-307892/
http://careers.gohire.io/data-engineer-307890/
"""

def _detail(title, jid, locality, country):
    return ('<html><head><script type="application/ld+json">'
            '{"@context":"https://schema.org/","@type":"JobPosting",'
            f'"title":"{title}","description":"<p>Role</p>",'
            f'"identifier":{{"@type":"PropertyValue","name":"GoHire","value":"{jid}"}},'
            '"datePosted":"2026-11-20","validThrough":"2027-02-20",'
            '"hiringOrganization":{"@type":"Organization","name":"GoHire"},'
            f'"jobLocation":{{"@type":"Place","address":{{"@type":"PostalAddress","addressLocality":"{locality}","addressCountry":"{country}"}}}},'
            '"employmentType":"FULL_TIME"}'
            '</script></head><body>x</body></html>')


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("robots.txt"):
            return _Resp("User-agent: *\nAllow: /\n")
        if url.endswith("/sitemap.txt"):
            return _Resp(_SITEMAP)
        assert url.startswith("https://"), "must upgrade http->https: " + url
        if "307892" in url:
            return _Resp(_detail("ATS Specialist", "307892", "York", "United Kingdom"))
        if "307890" in url:
            return _Resp(_detail("Data Engineer", "307890", "London", "United Kingdom"))
        raise AssertionError("unexpected " + url)


def test_gohire_sitemap_jsonld():
    jobs = GoHireConnector("careers.gohire.io", session=_Session()).fetch()
    assert len(jobs) == 2                         # homepage URL (no -id/) skipped
    a = next(j for j in jobs if j.source_job_id == "307892")
    assert a.title == "ATS Specialist"
    assert a.company == "GoHire"
    assert "York" in (a.location or "")
    assert a.employment_type == "Full-time"       # normalized FULL_TIME
    assert a.source_url.startswith("https://careers.gohire.io/")
    assert a.posted_at.startswith("2026-11-20")
