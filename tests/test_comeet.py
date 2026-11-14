"""Offline mapping test for the Comeet (Spark Hire Recruit) connector.

No network: a fake session returns a representative positions payload and
we assert the mapping to `Job`, board/token parsing, and token stripping.
"""

from __future__ import annotations

from jobmesh.connectors.comeet import ComeetConnector, _strip_token


class _Resp:
    def __init__(self, *, js=None, status_code=200):
        self._js, self.status_code = js, status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._js


class _FakeSession:
    def __init__(self, response):
        self.headers = {}
        self._response = response

    def get(self, *a, **k):
        return self._response


SAMPLE = [
    {
        "uid": "87.405",
        "name": "Backend Engineer",
        "location": {"name": "Austin, TX", "city": "Austin",
                     "state": "TX", "country": "US"},
        "department": "Engineering",
        "employment_type": "Full-time",
        "position_url": "https://www.comeet.co/careers-api/2.0/company/30.005/positions/87.405?token=SECRET123",
        "url_active_page": "https://www.comeet.com/jobs/acme/engineering/87.405",
        "time_updated": "2026-11-01T00:00:00Z",
        "details": [
            {"name": "Description", "value": "<p>Own the pricing platform.</p>"},
            {"name": "Requirements", "value": "<p>5y Python.</p>"},
        ],
    }
]


def test_comeet_parses_board_and_maps():
    conn = ComeetConnector("30.005:TOKENABC:Acme", session=_FakeSession(_Resp(js=SAMPLE)))
    assert conn.uid == "30.005"
    assert conn.token == "TOKENABC"
    assert conn.company_name == "Acme"

    jobs = conn.fetch()
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source_platform == "comeet"
    assert j.source_board == "30.005"
    assert j.source_job_id == "87.405"
    assert j.title == "Backend Engineer"
    assert j.company == "Acme"
    assert j.location == "Austin, TX"
    assert j.employment_type == "Full-time"
    assert "pricing platform" in (j.description or "")
    # the public page, not the token-bearing API url
    assert j.apply_url == "https://www.comeet.com/jobs/acme/engineering/87.405"
    assert "token" not in (j.source_url or "")


def test_comeet_defaults_company_to_uid_when_unnamed():
    conn = ComeetConnector("30.005:TOKENABC", session=_FakeSession(_Resp(js=SAMPLE)))
    assert conn.company_name is None
    jobs = conn.fetch()
    assert jobs[0].company == "30.005"


def test_strip_token_removes_only_the_token():
    assert _strip_token("https://x/p?token=ABC") == "https://x/p"
    assert _strip_token("https://x/p?token=ABC&foo=1") == "https://x/p?foo=1"
    assert _strip_token("https://x/p?foo=1") == "https://x/p?foo=1"
    assert _strip_token(None) is None
