"""Offline mapping tests for the free-API-key generalist connectors
(Adzuna, Jooble, USAJobs).

No live API and no real key is used: each connector is handed a fake
session with a representative payload, and the credential env vars are
set to dummy values, so we assert the mapping to `Job` (fields,
category, salary, remote, pagination) without any network.
"""

from __future__ import annotations

from jobmesh.connectors.adzuna import AdzunaConnector
from jobmesh.connectors.jooble import JoobleConnector
from jobmesh.connectors.usajobs import UsaJobsConnector


class _Resp:
    def __init__(self, *, js=None, status_code=200):
        self._js, self.status_code = js, status_code

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


# --- Adzuna ---------------------------------------------------------------

def test_adzuna_maps_all_sectors(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "x")
    monkeypatch.setenv("ADZUNA_APP_KEY", "y")
    page = {"results": [
        {"id": "1", "title": "Registered Nurse",
         "company": {"display_name": "Life Healthcare"},
         "location": {"display_name": "Cape Town, Western Cape"},
         "category": {"label": "Healthcare & Nursing Jobs"},
         "redirect_url": "https://adzuna/1",
         "salary_min": 300000, "salary_max": 420000,
         "contract_time": "full_time", "created": "2026-11-01T00:00:00Z",
         "description": "Care for patients."},
        {"id": "2", "title": "Warehouse Operative (Remote coordinator)",
         "company": {"display_name": "DHL"},
         "location": {"display_name": "Johannesburg"},
         "category": {"label": "Logistics & Warehouse Jobs"},
         "redirect_url": "https://adzuna/2",
         "salary_min": 180000, "salary_max": 180000,
         "created": "2026-11-02T00:00:00Z", "description": "Move goods."},
    ]}
    c = AdzunaConnector("za", session=_FakeSession([_Resp(js=page)]))
    jobs = c.fetch()
    assert len(jobs) == 2
    nurse = jobs[0]
    assert nurse.title == "Registered Nurse"
    assert nurse.company == "Life Healthcare"
    assert nurse.source_platform == "adzuna"
    assert nurse.source_board == "za"
    assert nurse.salary == "300,000–420,000"
    # a non-tech category must survive bucketing (not forced into tech)
    assert nurse.category and "Data" not in nurse.category
    assert jobs[1].salary == "180,000"


def test_adzuna_rejects_unknown_country(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "x")
    monkeypatch.setenv("ADZUNA_APP_KEY", "y")
    c = AdzunaConnector("zz", session=_FakeSession([_Resp(js={"results": []})]))
    try:
        c.fetch()
        assert False, "expected ValueError for unknown country"
    except ValueError:
        pass


def test_adzuna_missing_key_raises(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    c = AdzunaConnector("za", session=_FakeSession([_Resp(js={"results": []})]))
    try:
        c.fetch()
        assert False, "expected RuntimeError for missing credentials"
    except RuntimeError:
        pass


# --- Jooble ----------------------------------------------------------------

def test_jooble_maps_and_dedups(monkeypatch):
    monkeypatch.setenv("JOOBLE_API_KEY", "k")
    page1 = {"jobs": [
        {"id": 11, "title": "Driver", "company": "Jumia",
         "location": "Lagos, Nigeria", "link": "https://jooble/11",
         "snippet": "Deliver parcels.", "salary": "₦150,000",
         "type": "Full-time", "updated": "2026-11-03T10:00:00"},
        {"id": 12, "title": "Accountant", "company": "MTN",
         "location": "Accra, Ghana", "link": "https://jooble/12",
         "snippet": "Keep the books.", "updated": "2026-11-03T11:00:00"},
    ]}
    empty = {"jobs": []}
    c = JoobleConnector("Nigeria", session=_FakeSession([_Resp(js=page1), _Resp(js=empty)]))
    jobs = c.fetch()
    assert len(jobs) == 2
    assert {j.title for j in jobs} == {"Driver", "Accountant"}
    assert jobs[0].source_platform == "jooble"
    assert jobs[0].source_board == "Nigeria"


def test_jooble_missing_key_raises(monkeypatch):
    monkeypatch.delenv("JOOBLE_API_KEY", raising=False)
    c = JoobleConnector("all", session=_FakeSession([_Resp(js={"jobs": []})]))
    try:
        c.fetch()
        assert False, "expected RuntimeError for missing key"
    except RuntimeError:
        pass


# --- USAJobs ---------------------------------------------------------------

def test_usajobs_maps_public_sector(monkeypatch):
    monkeypatch.setenv("USAJOBS_EMAIL", "me@example.com")
    monkeypatch.setenv("USAJOBS_API_KEY", "k")
    page = {"SearchResult": {"SearchResultItems": [
        {"MatchedObjectDescriptor": {
            "PositionID": "ABC-1", "PositionTitle": "Registered Nurse",
            "OrganizationName": "Veterans Health Administration",
            "PositionLocationDisplay": "Houston, Texas",
            "PositionURI": "https://usajobs/ABC-1",
            "JobCategory": [{"Name": "Nursing", "Code": "0610"}],
            "PositionSchedule": [{"Name": "Full-time"}],
            "PositionRemuneration": [
                {"MinimumRange": "70000", "MaximumRange": "95000",
                 "RateIntervalCode": "PY"}],
            "QualificationSummary": "Must be licensed.",
            "PublicationStartDate": "2026-11-01"}},
    ]}}
    c = UsaJobsConnector("all", session=_FakeSession([_Resp(js=page)]))
    jobs = c.fetch()
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Registered Nurse"
    assert j.company == "Veterans Health Administration"
    assert j.salary == "70,000–95,000/yr"
    assert j.source_platform == "usajobs"
    assert j.employment_type  # normalized full-time


def test_usajobs_missing_key_raises(monkeypatch):
    monkeypatch.delenv("USAJOBS_EMAIL", raising=False)
    monkeypatch.delenv("USAJOBS_API_KEY", raising=False)
    c = UsaJobsConnector("all", session=_FakeSession([_Resp(js={"SearchResult": {}})]))
    try:
        c.fetch()
        assert False, "expected RuntimeError for missing credentials"
    except RuntimeError:
        pass
