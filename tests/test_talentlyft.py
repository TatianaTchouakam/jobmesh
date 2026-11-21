"""Offline test: TalentLyft sitemap + per-posting JSON-LD (skips talent-pool)."""
import json
from jobmesh.connectors.talentlyft import TalentLyftConnector

_SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://riverwalkertalentcareers.talentlyft.com/jobs/join-the-talent-pool-general-application-chUU</loc></url>
<url><loc>https://riverwalkertalentcareers.talentlyft.com/jobs/executive-director-at-nnaf-clrS</loc></url>
<url><loc>https://riverwalkertalentcareers.talentlyft.com/jobs/customer-service-rep-cl22</loc></url>
</urlset>"""

def _page(title, city, country="US"):
    ld={"@type":"JobPosting","title":title,"datePosted":"2026-11-12","employmentType":"FULL_TIME",
        "hiringOrganization":{"name":"Riverwalker"},
        "jobLocation":{"address":{"addressLocality":city,"addressCountry":country}},
        "description":"<p>Role</p>"}
    return f'<html><head><script type="application/ld+json">{json.dumps(ld)}</script></head><body>x</body></html>'


class _Resp:
    status_code=200
    def __init__(self,t): self.text=t
    def raise_for_status(self): pass


class _Session:
    headers={}
    def get(self,url,timeout=None,**k):
        if url.endswith("/robots.txt"): return _Resp("User-agent: *\nDisallow: /JobList\n")
        if url.endswith("/sitemap.xml"): return _Resp(_SITEMAP)
        if "executive-director" in url: return _Resp(_page("Executive Director","New York"))
        if "customer-service" in url: return _Resp(_page("Customer Service Rep","Atlanta"))
        return _Resp("<html></html>")


def test_talentlyft_skips_talent_pool_and_maps():
    jobs = TalentLyftConnector("riverwalkertalentcareers.talentlyft.com", session=_Session()).fetch()
    assert len(jobs) == 2            # talent-pool entry skipped
    titles = {j.title for j in jobs}
    assert titles == {"Executive Director", "Customer Service Rep"}
    a = [j for j in jobs if j.title == "Executive Director"][0]
    assert a.company == "Riverwalker"
    assert a.location == "New York, US"
    assert a.source_url.endswith("executive-director-at-nnaf-clrS")
