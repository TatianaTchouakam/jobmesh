"""Offline test: JobMount per-category RSS (company/location from description)."""
from jobmesh.connectors.jobmount import JobMountConnector, _company_location

_RSS = """<rss version="2.0"><channel>
<title>AWC RSS Feed</title>
<item>
  <title>Water Resources Specialist I or II</title>
  <link>https://jobnet.wacities.org/career/45340/Water-Resources-Specialist?utm_source=rss</link>
  <description>City of Port Townsend.
, Port Townsend &lt;br /&gt;
The City is recruiting...</description>
  <category>Public Works/Maintenance, Water/Wastewater</category>
  <guid>https://jobnet.wacities.org/career/45340/Water-Resources-Specialist?utm_source=rss</guid>
  <pubDate>Thu, 20 Nov 2026 00:00:00 Z</pubDate>
</item>
<item>
  <title>Maintenance Technician</title>
  <link>https://jobnet.wacities.org/career/45335/Maintenance-Technician</link>
  <description>City of Gig Harbor.
, Gig Harbor &lt;br /&gt;Details</description>
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
            return _Resp("User-agent: *\nDisallow: /admin\nDisallow: /candidate/\n")
        assert url == "https://jobnet.wacities.org/public-works-maintenance?rss"
        return _Resp(_RSS)


def test_jobmount_rss():
    jobs = JobMountConnector("jobnet.wacities.org/public-works-maintenance", session=_Session()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "45340"
    assert a.title == "Water Resources Specialist I or II"
    assert a.company == "City of Port Townsend"
    assert a.location == "Port Townsend"
    assert a.source_url == "https://jobnet.wacities.org/career/45340/Water-Resources-Specialist"
    assert "utm" not in a.source_url
    assert isinstance(a.category, str) and a.category  # normalized by model
    assert jobs[1].company == "City of Gig Harbor" and jobs[1].location == "Gig Harbor"


def test_jobmount_company_helper():
    assert _company_location("Acme Corp.\n, Seattle <br />x") == ("Acme Corp", "Seattle")
    assert _company_location(None) == ("JobMount employer", None)
