"""Paylocity connector — offline: window.pageData JSON embedded in the board page."""
import json
from jobmesh.connectors.paylocity import PaylocityConnector, _extract_pagedata

BOARD = "0005a0af-b8ae-4a24-9ae3-458109fffbda"


def _page(jobs, company="Acme Inc"):
    data = {"ModuleTitle": company, "ModuleId": 123, "Jobs": jobs}
    # Mimic the real page: pageData assigned inside a <script>, plus noise.
    return (
        "<!DOCTYPE html><html><head>"
        "<script>window.dataLayer=[{\"x\":1}];</script>"
        f"<script>window.pageData = {json.dumps(data)}; window.other = 2;</script>"
        "</head><body></body></html>"
    )


def _job(jid, title, dept=None, city="Austin", state="TX", remote=False):
    return {
        "JobId": jid, "JobTitle": title, "LocationName": city,
        "PublishedDate": "2026-11-02T08:00:00-05:00",
        "Description": "<p>Great role</p>", "HiringDepartment": dept,
        "IsRemote": remote,
        "JobLocation": {"City": city, "State": state, "Country": "USA"},
    }


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


class _FakeSession:
    def __init__(self, page):
        self.headers = {}
        self._page = page

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("", status=404)          # no robots -> fail-open allow
        return _Resp(self._page)


def test_extract_pagedata_is_string_aware():
    # a brace inside a description value must not unbalance the match
    page = _page([_job(1, "Dev", "Engineering")])
    page = page.replace("Great role", "Great role { nested } brace")
    data = _extract_pagedata(page)
    assert data is not None
    assert data["ModuleTitle"] == "Acme Inc"
    assert len(data["Jobs"]) == 1


def test_fetch_parses_jobs():
    jobs_in = [
        _job(2380845, "Backend Engineer", "Engineering"),
        _job(2380846, "Warehouse Associate", "Operations", city="Essex", state="MA"),
    ]
    c = PaylocityConnector(BOARD, session=_FakeSession(_page(jobs_in)))
    jobs = c.fetch()
    assert len(jobs) == 2

    a = jobs[0]
    assert a.title == "Backend Engineer"
    assert a.company == "Acme Inc"
    assert a.location == "Austin, TX, USA"
    assert a.source_job_id == "2380845"
    assert a.source_url == "https://recruiting.paylocity.com/Recruiting/Jobs/Details/2380845"
    assert a.apply_url == "https://recruiting.paylocity.com/Recruiting/Jobs/Apply/2380845"
    # category is normalized from the department + title
    assert a.category == "Engineering"
    assert a.posted_at == "2026-11-02T08:00:00-05:00"


def test_empty_board_returns_nothing():
    # a "Job Not Found" page has no window.pageData
    page = "<html><head><script>window.dataLayer=[{}];</script></head></html>"
    c = PaylocityConnector(BOARD, session=_FakeSession(page))
    assert c.fetch() == []


def test_paylocity_429_raises_ratelimited():
    """A shared-host 429 is surfaced as RateLimited (pipeline defers the board)."""
    from jobmesh.ratelimit import RateLimited, reset_limiters
    import os
    os.environ["PAYLOCITY_MIN_INTERVAL"] = "0"
    reset_limiters()

    class _RL(_FakeSession):
        def get(self, url, timeout=None, **k):
            if url.endswith("/robots.txt"):
                return _Resp("", status=404)
            r = _Resp("too many", status=429)
            r.headers = {"Retry-After": "7"}
            return r

    import pytest
    with pytest.raises(RateLimited) as ei:
        PaylocityConnector(BOARD, session=_RL(_page([]))).fetch()
    assert ei.value.retry_after == 7.0
