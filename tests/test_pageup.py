"""Offline test: PageUp per-client RSS (job: namespaced fields, company from board)."""
from jobmesh.connectors.pageup import PageUpConnector

_RSS = """<?xml version="1.0"?>
<rss xmlns:job="urn:job" xmlns:a10="http://www.w3.org/2005/Atom"><channel>
<item>
  <guid>https://careers.pageuppeople.com/513/cw/en/job/701817</guid>
  <link>https://careers.pageuppeople.com/513/cw/en/job/701817</link>
  <title>Indigenous PhD Opportunity &amp; Return</title>
  <description>Be part of a team...</description>
  <pubDate>Fri, 20 Nov 2026 01:30:00 Z</pubDate>
  <job:refNo>701817</job:refNo>
  <job:description>&lt;h3&gt;Full role&lt;/h3&gt;</job:description>
  <job:applyLink>https://secure.dc2.pageuppeople.com/apply/513/gateway?lJobID=701817</job:applyLink>
  <job:location>Campus|Caulfield campus</job:location>
  <job:workType>Fixed-term (Full-time)</job:workType>
  <job:category>Academic|Scholarship</job:category>
</item>
<item>
  <link>https://careers.pageuppeople.com/513/cw/en/job/701900</link>
  <title>Remote Research Fellow</title>
  <job:refNo>701900</job:refNo>
  <job:location>Remote|Work from home</job:location>
  <job:workType>Continuing (Full-time)</job:workType>
</item>
</channel></rss>"""


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("robots.txt"):
            return _Resp("User-agent: *\nDisallow: /api/\n")
        assert url == "https://careers.pageuppeople.com/513/cw/en/rss"
        return _Resp(_RSS)


def test_pageup_rss():
    jobs = PageUpConnector("513|Monash University", session=_Session()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "701817"
    assert a.company == "Monash University"
    assert a.title == "Indigenous PhD Opportunity & Return"
    assert a.location == "Caulfield campus"
    assert a.category == "Other"  # model normalizes "Scholarship" -> Other
    assert a.apply_url.endswith("lJobID=701817")
    assert a.source_url.endswith("/job/701817")
    assert a.posted_at and a.posted_at.startswith("2026-11-20")
    b = jobs[1]
    assert b.company == "Monash University" and b.remote is True


def test_pageup_company_fallback():
    jobs = PageUpConnector("513", session=_Session()).fetch()
    assert jobs[0].company == "PageUp employer"
