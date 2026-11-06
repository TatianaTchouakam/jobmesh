"""Offline mapping tests for the newer connectors.

Live APIs aren't called in CI; instead each connector is handed a fake
session whose responses carry representative payloads, so we assert the
mapping to `Job` (fields, pagination, remote detection, salary) without
any network.
"""

from __future__ import annotations

from jobmesh.connectors.workday import WorkdayConnector
from jobmesh.connectors.fourdayweek import FourDayWeekConnector
from jobmesh.connectors.teamtailor import TeamtailorConnector
from jobmesh.connectors.jobspresso import JobspressoConnector
from jobmesh.connectors.pythonjobs import PythonJobsConnector


class _Resp:
    def __init__(self, *, js=None, content=None, status_code=200):
        self._js, self.content, self.status_code = js, content, status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._js


class _FakeSession:
    """Returns queued responses in order; repeats the last one."""

    def __init__(self, responses):
        self.headers = {}
        self._responses = list(responses)
        self._i = 0

    def _next(self):
        r = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return r

    def get(self, *a, **k):
        return self._next()

    def post(self, *a, **k):
        return self._next()


def test_workday_paginates_and_maps():
    page = {"total": 2, "jobPostings": [
        {"title": "Senior Data Engineer",
         "externalPath": "/job/CA/Senior-Data-Engineer_JR1",
         "locationsText": "Santa Clara, CA", "bulletFields": ["JR1"]},
        {"title": "ML Researcher",
         "externalPath": "/job/Remote/ML-Researcher_JR2",
         "locationsText": "Remote, US", "bulletFields": ["JR2"]},
    ]}
    empty = {"total": 2, "jobPostings": []}
    c = WorkdayConnector("nvidia:wd5:NVIDIAExternalCareerSite:NVIDIA",
                         session=_FakeSession([_Resp(js=page), _Resp(js=empty)]))
    jobs = c.fetch()
    assert len(jobs) == 2
    j = jobs[0]
    assert j.company == "NVIDIA"
    assert j.source_url.startswith(
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/")
    assert jobs[1].remote is True        # "Remote, US" -> remote


def test_fourdayweek_salary_in_cents():
    js = {"data": [{
        "title": "Backend Engineer", "slug": "be-1",
        "url": "https://4dayweek.io/job/be-1",
        "company": {"name": "Acme"},
        "locations": [{"country": "Germany", "work_arrangement": "remote",
                       "is_primary": True}],
        "work_arrangement": "remote",
        "salary_min": 8000000, "salary_max": 12000000,
        "salary_currency": "EUR", "posted_at": "2026-11-01T00:00:00Z",
        "description": "<p>Build APIs.</p>",
    }], "has_more": False}
    c = FourDayWeekConnector(session=_FakeSession([_Resp(js=js)]))
    j = c.fetch()[0]
    assert j.salary == "80,000 - 120,000 EUR"
    assert j.workplace_type == "remote" and j.remote is True
    assert j.company == "Acme"


def test_teamtailor_reads_namespaced_tags():
    xml = (b'<?xml version="1.0"?><rss xmlns:tt="http://x"><channel>'
           b'<title>Jobs at Acme</title><item><title>Data Analyst</title>'
           b'<link>https://acme.teamtailor.com/jobs/1</link>'
           b'<description>&lt;p&gt;Analyse&lt;/p&gt;</description>'
           b'<tt:location>Berlin</tt:location><tt:department>Data</tt:department>'
           b'<tt:remote>true</tt:remote><guid>tt-1</guid></item></channel></rss>')
    c = TeamtailorConnector("acme", session=_FakeSession([_Resp(content=xml)]))
    j = c.fetch()[0]
    assert j.company == "Acme" and j.location == "Berlin"
    assert j.remote is True and j.source_job_id == "tt-1"


def test_jobspresso_reads_wpjm_tags():
    xml = (b'<?xml version="1.0"?><rss xmlns:job_listing="http://x"><channel>'
           b'<item><title>Remote Python Developer</title>'
           b'<link>https://jobspresso.co/job/123</link>'
           b'<description>&lt;p&gt;Remote&lt;/p&gt;</description>'
           b'<job_listing:company>Globex</job_listing:company>'
           b'<job_listing:location>Anywhere</job_listing:location>'
           b'<job_listing:job_type>Full Time</job_listing:job_type>'
           b'<guid>jp-123</guid></item></channel></rss>')
    c = JobspressoConnector(session=_FakeSession([_Resp(content=xml)]))
    j = c.fetch()[0]
    assert j.company == "Globex" and j.remote is True
    assert j.employment_type == "Full-time"   # normalized


def test_pythonjobs_splits_title():
    xml = (b'<?xml version="1.0"?><rss><channel><item>'
           b'<title>Senior Data Engineer: DataWorks GmbH</title>'
           b'<link>https://www.python.org/jobs/7777/</link>'
           b'<description>&lt;p&gt;Python&lt;/p&gt;</description>'
           b'<category>Remote</category><category>Berlin</category>'
           b'<guid>py-7777</guid></item></channel></rss>')
    c = PythonJobsConnector(session=_FakeSession([_Resp(content=xml)]))
    j = c.fetch()[0]
    assert j.title == "Senior Data Engineer" and j.company == "DataWorks GmbH"
    assert j.remote is True


# --- Round 2 platforms ------------------------------------------------------

def test_joinrise_defensive_mapping():
    js = {"jobs": [{
        "title": "Data Engineer", "company": {"name": "Rise Inc"},
        "location": "Remote", "url": "https://www.joinrise.io/jobs/de-1",
        "workArrangement": "remote", "createdAt": "2026-11-05T00:00:00Z",
        "description": "<p>Pipelines</p>", "slug": "de-1",
    }], "hasMore": False}
    from jobmesh.connectors.joinrise import JoinRiseConnector
    c = JoinRiseConnector(session=_FakeSession([_Resp(js=js)]))
    j = c.fetch()[0]
    assert j.title == "Data Engineer" and j.company == "Rise Inc"
    assert j.workplace_type == "remote" and j.remote is True


def test_rippling_flat_array():
    arr = [{"uuid": "abc", "name": "Backend Engineer", "department": "Eng",
            "url": "https://ats.rippling.com/acme/jobs/abc",
            "workLocation": {"city": "Berlin", "country": "DE"}}]
    from jobmesh.connectors.rippling import RipplingConnector
    c = RipplingConnector("acme", session=_FakeSession([_Resp(js=arr)]))
    j = c.fetch()[0]
    assert j.title == "Backend Engineer" and j.company == "Acme"
    assert j.location == "Berlin, DE" and j.source_job_id == "abc"


def test_hirehive_maps():
    js = {"jobs": [{"id": 7, "title": "QA Engineer", "location": "Dublin",
                    "url": "https://acme.hirehive.com/job/7",
                    "description": "<p>Test</p>", "department": "Quality"}]}
    from jobmesh.connectors.hirehive import HireHiveConnector
    c = HireHiveConnector("acme", session=_FakeSession([_Resp(js=js)]))
    j = c.fetch()[0]
    assert j.title == "QA Engineer" and j.source_job_id == "7"


def test_manatal_maps():
    js = {"data": [{"id": "h1", "position_name": "Recruiter",
                    "location": {"city": "Paris", "country": "FR"},
                    "url": "https://careers-page.com/acme/h1",
                    "description": "<p>Hire</p>", "is_remote": False}]}
    from jobmesh.connectors.manatal import ManatalConnector
    c = ManatalConnector("acme", session=_FakeSession([_Resp(js=js)]))
    j = c.fetch()[0]
    assert j.title == "Recruiter" and j.location == "Paris, FR"
