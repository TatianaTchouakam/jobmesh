"""Offline test: Kula.ai official RSS feed (job: fields, multiline location)."""
from jobmesh.connectors.kula import KulaConnector, _location

_RSS = """<?xml version="1.0"?>
<rss xmlns:job="urn:job"><channel>
<item>
  <title>Technical Account Manager - US TimeZone</title>
  <link>https://careers.kula.ai/rocketlane/2112/apply</link>
  <guid>https://careers.kula.ai/rocketlane/2112/apply</guid>
  <pubDate>Fri, 13 Mar 2026 16:32:12 +0000</pubDate>
  <category>Post Sales</category>
  <description>&lt;h3&gt;About the Role&lt;/h3&gt;&lt;p&gt;Rocketlane...&lt;/p&gt;</description>
  <job:referencenumber>2112-778</job:referencenumber>
  <job:employmentType>FULL_TIME</job:employmentType>
  <job:workplace>OFFICE</job:workplace>
  <job:location>
        Chennai, India
        false
        true
      </job:location>
</item>
<item>
  <title>Remote Engineer</title>
  <link>https://careers.kula.ai/rocketlane/2200/apply</link>
  <job:employmentType>FULL_TIME</job:employmentType>
  <job:workplace>REMOTE</job:workplace>
  <job:location>
        Remote
        true
      </job:location>
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
            return _Resp("User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /*/portal\n")
        assert url == "https://careers.kula.ai/rocketlane/feed"
        return _Resp(_RSS)


def test_kula_rss():
    jobs = KulaConnector("rocketlane|Rocketlane", session=_Session()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "2112"
    assert a.title == "Technical Account Manager - US TimeZone"
    assert a.company == "Rocketlane"
    assert a.location == "Chennai, India"          # multiline cleaned, flags dropped
    assert a.employment_type == "Full-time"        # normalized FULL_TIME
    assert a.workplace_type == "onsite"            # OFFICE
    assert a.source_url.endswith("/2112/apply")
    assert a.posted_at.startswith("2026-03-13")
    b = jobs[1]
    assert b.location == "Remote" and b.remote is True and b.workplace_type == "remote"


def test_kula_location_helper():
    assert _location("\n  Paris, France\n  false\n  true\n") == "Paris, France"
    assert _location(None) is None
    assert _location("\n true \n false \n") is None   # only flags


def test_kula_company_fallback():
    jobs = KulaConnector("rocketlane", session=_Session()).fetch()
    assert jobs[0].company == "Rocketlane"            # slug title-cased
