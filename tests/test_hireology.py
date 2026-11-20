"""Hireology connector — offline parsing + pagination, using a real API shape."""
from jobmesh.connectors.hireology import HireologyConnector


class _Resp:
    def __init__(self, js):
        self._js = js

    def raise_for_status(self):
        pass

    def json(self):
        return self._js


class _FakeSession:
    """Serves a /robots.txt (404) then queued API pages in order."""
    def __init__(self, pages):
        self.headers = {}
        self._pages = list(pages)
        self._i = 0

    def get(self, url, params=None, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(None)  # body unused; 404 -> allowed (fail-open)
        page = self._pages[min(self._i, len(self._pages) - 1)]
        self._i += 1
        return _Resp(page)


def _job(i, status="Open"):
    return {
        "id": 1000 + i,
        "name": f"Role {i}",
        "status": status,
        "employment_status": "Full Time - salary",
        "job_description": "<p>Build <b>things</b></p>",
        "locations": [{"city": "Chicago", "state": "IL"}],
        "remote": False,
        "job_family": {"name": "General"},
        "organization": {"name": "Acme Co", "type": "Company"},
        "career_site_url": f"https://careers.hireology.com/acme/{1000+i}/description",
        "created_at": "2026-10-19T21:33:01.902Z",
        "compensation": {"is_comp_range": True, "comp_range_min": "110000.0",
                         "comp_range_max": "120000.0", "comp_period": "year"},
    }


def test_maps_core_fields():
    page = {"data": [_job(1)], "count": 1, "page": 1, "page_size": 200}
    c = HireologyConnector("acme", session=_FakeSession([page]))
    j = c.fetch()[0]
    assert j.title == "Role 1"
    assert j.company == "Acme Co"
    assert j.location == "Chicago, IL"
    assert j.salary == "$110,000-$120,000/year"
    assert j.source_url.endswith("/1001/description")
    assert "Build things" in (j.description or "")
    assert j.source_platform == "hireology" and j.source_board == "acme"


def test_pagination_and_closed_filtered():
    # 250 open jobs across two full pages + one closed job that must be dropped
    p1 = {"data": [_job(i) for i in range(200)], "count": 250, "page": 1, "page_size": 200}
    p2 = {"data": [_job(i) for i in range(200, 250)] + [_job(999, status="Closed")],
          "count": 250, "page": 2, "page_size": 200}
    c = HireologyConnector("acme", session=_FakeSession([p1, p2]))
    jobs = c.fetch()
    assert len(jobs) == 250  # closed one filtered out
    assert all(j.is_open for j in jobs)


def test_remote_location_fallback():
    d = _job(5)
    d["locations"] = []
    d["remote"] = True
    page = {"data": [d], "count": 1, "page": 1, "page_size": 200}
    c = HireologyConnector("acme", session=_FakeSession([page]))
    j = c.fetch()[0]
    assert j.location == "Remote" and j.remote is True and j.workplace_type == "remote"
