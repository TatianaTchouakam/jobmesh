"""Tests for the Manatal connector (careers-page.com DRF API)."""

from jobmesh.connectors.manatal import ManatalConnector


def _job(i):
    return {
        "id": 1000 + i,
        "hash": f"H{i}",
        "organization_name": "Marketing",
        "position_name": f"Role {i}",
        "description": "<p>Do <strong>things</strong>.</p>",
        "country": "Thailand",
        "state": "Bangkok",
        "city": "Bangkok",
        "location_display": "Bangkok, Bangkok, Thailand",
    }


class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._p


class _FakeSession:
    """Serves `total` jobs, 20 per page (server cap), DRF-style."""
    def __init__(self, total):
        self.headers = {}
        self._all = [_job(i) for i in range(total)]
        self.calls = []
    def get(self, url, params=None, timeout=None):
        page = params["page"]
        self.calls.append(page)
        start = (page - 1) * 20
        chunk = self._all[start:start + 20]
        nxt = "x" if start + 20 < len(self._all) else None
        return _Resp({"count": len(self._all), "next": nxt, "results": chunk})


def test_manatal_maps_and_paginates():
    sess = _FakeSession(33)  # -> 2 pages (20 + 13)
    jobs = ManatalConnector("manatal", session=sess).fetch()
    assert len(jobs) == 33
    assert sess.calls == [1, 2]
    j = jobs[0]
    assert j.source_platform == "manatal"
    assert j.source_board == "manatal"
    assert j.source_job_id == "1000"
    assert j.title == "Role 0"
    assert j.company == "Manatal"          # from slug, not department
    assert j.category == "Marketing"       # organization_name = department
    assert j.location == "Bangkok, Bangkok, Thailand"
    assert "things" in (j.description or "")
    assert j.source_url == "https://www.careers-page.com/manatal/job/H0"


def test_manatal_company_from_hyphen_slug():
    conn = ManatalConnector("acme-corp")
    assert conn._company == "Acme Corp"
