"""Offline test: UN Careers RSS feed parsing (Duty Station, Job ID from description)."""
from jobmesh.connectors.uncareers import UnCareersConnector, _field

_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>UN Jobs</title>
<item>
<title><![CDATA[Programme Officer]]></title>
<link>https://careers.un.org/jobSearchDescription/287216?language=en</link>
<guid>https://careers.un.org/jobSearchDescription/287216?language=en</guid>
<pubDate>Mon, 17 Nov 2026 00:00:00 GMT</pubDate>
<description><![CDATA[
  Level : P-3 <br>
  Job ID : 287216 <br>
  Job Network : Economic, Social and Development <br>
  Job Family : Programme Management <br>
  Department/Office : United Nations Office for Partnerships <br>
  Duty Station : NEW YORK <br>
]]></description>
</item>
<item>
<title><![CDATA[Remote Data Analyst]]></title>
<link>https://careers.un.org/jobSearchDescription/287300?language=en</link>
<description><![CDATA[ Job ID : 287300 <br> Duty Station : REMOTE <br> Department/Office : UNDP <br> ]]></description>
</item>
</channel></rss>"""


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text; self.content = text.encode()
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("")               # no robots -> allowed
        return _Resp(_RSS)


def test_uncareers_parses_feed():
    jobs = UnCareersConnector("careers.un.org", session=_Session()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "287216"
    assert a.title == "Programme Officer"
    assert a.company == "United Nations Office for Partnerships"
    assert a.location == "New York"            # Duty Station title-cased
    assert a.level == "P-3"
    assert a.source_url.endswith("/jobSearchDescription/287216?language=en")
    b = jobs[1]
    assert b.location == "Remote" and b.remote is True


def test_field_extraction():
    d = "Level : P-3 <br> Duty Station : GENEVA <br>"
    assert _field(d, "Duty Station") == "GENEVA"
    assert _field(d, "Level") == "P-3"
    assert _field(d, "Nope") is None
