"""Offline test: SuccessFactors CSB (sitemap -> microdata detail pages)."""
from jobmesh.connectors.successfactors import SuccessFactorsConnector, _clean_date

_SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://jobs.boehringer-ingelheim.com/job/Sydney-Rep-Aust/1455502833/</loc></url>
<url><loc>https://jobs.boehringer-ingelheim.com/job/Wien-Analyst-Ost/1455577933/</loc></url>
<url><loc>https://jobs.boehringer-ingelheim.com/content/About-Us/</loc></url>
</urlset>"""

def _detail(title, locality, region, date):
    return (f'<html><head>'
            f'<meta property="og:title" content="{title}" />'
            f'<meta property="og:description" content="{title}" />'
            f'<meta itemprop="addressLocality" content="{locality}" />'
            f'<meta itemprop="addressRegion" content="{region}" />'
            f'<meta itemprop="addressCountry" content="DE" />'
            f'<meta itemprop="datePosted" content="{date}" />'
            f'<meta itemprop="hiringOrganization" content="BoehringerPRD" />'
            f'</head><body><span itemprop="description" class="rtltextaligneligible">'
            f'<span class="jobdescription"><p>Real job description here.</p></span></span>'
            f'</body></html>')


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("robots.txt"):
            return _Resp("User-agent: *\nDisallow: /services/\nDisallow: /applybutton/\n")
        if url.endswith("/sitemap.xml"):
            return _Resp(_SITEMAP)
        if "1455502833" in url:
            return _Resp(_detail("GP Sales Representative", "Sydney, AU", "NSW", "Mon Nov 09 00:00:00 UTC 2026"))
        if "1455577933" in url:
            return _Resp(_detail("Principal System Analyst", "Wien", "AT", "Tue Nov 10 00:00:00 UTC 2026"))
        raise AssertionError("unexpected " + url)


def test_successfactors_sitemap_microdata():
    jobs = SuccessFactorsConnector("jobs.boehringer-ingelheim.com|Boehringer Ingelheim", session=_Session()).fetch()
    assert len(jobs) == 2                         # content page skipped (no /job/{id}/)
    a = jobs[0]
    assert a.source_job_id == "1455502833"
    assert a.title == "GP Sales Representative"
    assert a.company == "Boehringer Ingelheim"    # clean name from board, not "BoehringerPRD"
    assert a.location == "Sydney, AU, NSW"
    assert a.description == "Real job description here."
    assert a.source_url.endswith("/1455502833/")
    assert a.posted_at.startswith("2026-11-09")


def test_clean_date_strips_utc():
    assert _clean_date("Mon Nov 09 00:00:00 UTC 2026").startswith("2026-11-09")
    assert _clean_date(None) is None
