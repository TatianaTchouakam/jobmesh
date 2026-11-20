"""HiBob connector — offline parsing against the real /api/job-ad shape."""
from jobmesh.connectors.hibob import HibobConnector


class _Resp:
    def __init__(self, js):
        self._js = js

    def raise_for_status(self):
        pass

    def json(self):
        return self._js


class _FakeSession:
    """Routes robots.txt / career-site / job-ad to canned bodies."""
    def __init__(self, job_ad, career_site=None):
        self.headers = {}
        self._job_ad = job_ad
        self._career_site = {"companyName": "Acme"} if career_site is None else career_site

    def get(self, url, params=None, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(None)
        if url.endswith("/api/career-site"):
            return _Resp(self._career_site)
        if url.endswith("/api/job-ad"):
            return _Resp(self._job_ad)
        return _Resp({})


def _job(i, workspace="Hybrid"):
    return {
        "id": f"uuid-{i}",
        "title": f"Engineer {i}",
        "department": "Tech",
        "employmentType": "Permanent",
        "workspaceType": workspace,
        "country": "Germany",
        "postingLocations": [{"city": "Berlin", "region": "BE", "country": "Germany",
                              "showCity": True, "showRegion": False, "displayValue": "Germany"}],
        "description": "<p>Build <b>things</b></p>",
        "requirements": "<p>Python</p>",
        "responsibilities": "<p>Ship</p>",
        "benefits": "<p>Snacks</p>",
        "publishedAt": "2026-11-17T05:05:08Z",
        "payTransparencyMinSalary": 70000, "payTransparencyMaxSalary": 90000,
        "payTransparencySalaryCurrency": "EUR", "payTransparencySalaryPayPeriod": "Year",
    }


def test_maps_core_fields():
    data = {"jobAdDetails": [_job(1)]}
    c = HibobConnector("acme-abc123", session=_FakeSession(data, {"companyName": "Acme Corp"}))
    j = c.fetch()[0]
    assert j.title == "Engineer 1"
    assert j.company == "Acme Corp"          # from /api/career-site
    assert j.location == "Berlin, Germany"    # showRegion False -> region dropped
    assert j.workplace_type == "hybrid"
    assert j.category == "Engineering"   # normalized from dept "Tech" + title by Job model
    assert j.salary == "EUR 70,000-90,000/year"
    assert j.source_url == "https://acme-abc123.careers.hibob.com/jobs/uuid-1"
    assert "Build things" in (j.description or "") and "Python" in (j.description or "")
    assert j.source_platform == "hibob" and j.source_board == "acme-abc123"


def test_remote_flag_and_multiple():
    data = {"jobAdDetails": [_job(1, "Remote"), _job(2, "On site"), _job(3, "Hybrid")]}
    c = HibobConnector("acme-abc123", session=_FakeSession(data))
    jobs = c.fetch()
    assert len(jobs) == 3
    by_ws = {j.source_job_id: j for j in jobs}
    assert by_ws["uuid-1"].workplace_type == "remote" and by_ws["uuid-1"].remote is True
    assert by_ws["uuid-2"].workplace_type == "onsite"
    assert by_ws["uuid-3"].workplace_type == "hybrid"


def test_company_fallback_when_career_site_missing():
    # career-site has no name -> fall back to subdomain prefix (hash stripped)
    data = {"jobAdDetails": [_job(1)]}
    c = HibobConnector("northwind-9f2a1b", session=_FakeSession(data, {}))
    j = c.fetch()[0]
    assert j.company == "Northwind"
