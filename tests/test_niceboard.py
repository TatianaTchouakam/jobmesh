"""Tests for the Niceboard connector (public keyless /api/jobs)."""

from jobmesh.connectors.niceboard import NiceboardConnector


def _job(i, **over):
    d = {
        "id": 1000 + i,
        "uid": f"UID{i}",
        "title": f"Role {i}",
        "company_name": "Acme",
        "location_name": "Houston, TX, USA",
        "description_html": "<p>Do <strong>things</strong>.</p>",
        "apply_url": None,
        "jobtype": {"name": "Full time"},
        "category": {"name": "Engineering"},
        "is_remote": False,
        "remote_only": False,
        "salary_min": 50000,
        "salary_max": 70000,
        "salary_currency": "USD",
        "salary_timeframe": "year",
        "published_at": "2026-11-19T22:25:03.496Z",
        "is_published": True,
        "is_filled": False,
    }
    d.update(over)
    return d


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _FakeSession:
    """Returns pages of `count` jobs, PAGE_SIZE at a time, honouring page param."""

    def __init__(self, jobs):
        self.headers = {}
        self._jobs = jobs
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params["page"])
        size = params["limit"]
        page = params["page"]
        start = (page - 1) * size
        chunk = self._jobs[start : start + size]
        return _Resp({"jobs": chunk, "count": len(self._jobs)})


def test_niceboard_maps_fields():
    sess = _FakeSession([_job(1, is_remote=True, remote_only=True)])
    jobs = NiceboardConnector("demo", session=sess).fetch()
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source_platform == "niceboard"
    assert j.source_board == "demo"
    assert j.source_job_id == "1001"
    assert j.title == "Role 1"
    assert j.company == "Acme"
    assert j.location == "Houston, TX, USA"
    assert "things" in (j.description or "")  # HTML stripped
    assert j.source_url == "https://demo.niceboard.co/job/UID1"
    assert j.apply_url == j.source_url  # apply_url null -> job page
    assert j.employment_type == "Full-time"  # normalized by Job model
    assert j.remote is True
    assert j.workplace_type == "remote"
    assert j.salary == "USD 50000-70000 / year"


def test_niceboard_paginates_by_count():
    # 150 jobs, PAGE_SIZE 100 -> 2 pages
    sess = _FakeSession([_job(i) for i in range(150)])
    jobs = NiceboardConnector("big", session=sess).fetch()
    assert len(jobs) == 150
    assert sess.calls == [1, 2]


def test_niceboard_filled_job_is_closed():
    sess = _FakeSession([_job(1, is_filled=True)])
    jobs = NiceboardConnector("demo", session=sess).fetch()
    assert jobs[0].is_open is False
