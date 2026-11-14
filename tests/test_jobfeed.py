"""Offline test for the generic XML/RSS job-feed connector."""

from __future__ import annotations

from jobmesh.connectors.jobfeed import JobFeedConnector

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Example Board</title>
  <item>
    <title>Senior Data Engineer</title>
    <company>Acme Nonprofit</company>
    <location>Tallahassee, FL</location>
    <link>https://jobs.example.org/jobs/123</link>
    <description><![CDATA[<p>Build <b>ETL</b> pipelines.</p>]]></description>
    <pubDate>Mon, 10 Nov 2026 00:00:00 GMT</pubDate>
    <jobtype>Full Time</jobtype>
    <category>Technology</category>
    <referencenumber>123</referencenumber>
  </item>
</channel></rss>
"""

JOBS_XML = """<?xml version="1.0"?>
<jobs>
  <job>
    <jobtitle>Remote Grant Analyst</jobtitle>
    <companyname>Helix Foundation</companyname>
    <location>Remote</location>
    <joburl>https://jobs.example.org/j/9</joburl>
    <jobdescription>Analyze grants.</jobdescription>
    <salary>$60,000</salary>
    <reference>REQ-9</reference>
  </job>
</jobs>
"""


class _Resp:
    def __init__(self, content):
        self.content = content.encode() if isinstance(content, str) else content
        self.status_code = 200

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, content):
        self.headers = {}
        self._content = content

    def get(self, *a, **k):
        return _Resp(self._content)


def test_jobfeed_parses_rss():
    conn = JobFeedConnector("https://jobs.example.org/feed", session=_FakeSession(RSS))
    jobs = conn.fetch()
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source_platform == "jobfeed"
    assert j.title == "Senior Data Engineer"
    assert j.company == "Acme Nonprofit"
    assert j.location == "Tallahassee, FL"
    assert j.source_url == "https://jobs.example.org/jobs/123"
    assert "ETL" in j.description and "<b>" not in j.description
    assert j.employment_type == "Full-time"
    assert j.source_job_id == "123"


def test_jobfeed_parses_custom_jobs_xml():
    conn = JobFeedConnector("https://jobs.example.org/standard.xml", session=_FakeSession(JOBS_XML))
    jobs = conn.fetch()
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Remote Grant Analyst"
    assert j.company == "Helix Foundation"
    assert j.remote is True
    assert j.salary == "$60,000"
    assert j.source_job_id == "REQ-9"
