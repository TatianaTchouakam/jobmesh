"""Tests for the JOIN (join.com) connector.

JOIN career pages are server-rendered; jobs live in an embedded
``__NEXT_DATA__`` script. We feed a fake session returning such HTML
and assert the mapping, pagination stop, and remote detection.
"""

import json

from jobmesh.connectors.join import JoinConnector


def _html(page_data: dict) -> str:
    payload = {"props": {"pageProps": {"pageData": page_data}}}
    return (
        "<!DOCTYPE html><html><head></head><body>"
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></body></html>"
    )


PAGE1 = _html(
    {
        "company": {"name": "JOIN"},
        "jobs": {
            "pagination": {"page": 1, "pageCount": 1, "pageSize": 5, "total": 2},
            "items": [
                {
                    "id": 14771122,
                    "idParam": "16947455-engineering-manager",
                    "title": "Engineering Manager",
                    "category": {"name": "Management, Team Leader"},
                    "city": {"cityName": "Barcelona", "countryName": "Spain"},
                    "country": {"iso3166": "ES"},
                    "employmentType": {"name": "Employee"},
                    "workplaceType": "HYBRID",
                    "remoteType": None,
                    "createdAt": "2025-08-29T16:34:57.775Z",
                },
                {
                    "id": 99,
                    "idParam": "99-remote-data-engineer",
                    "title": "Data Engineer",
                    "category": {"name": "Software Development"},
                    "city": {"cityName": "Berlin", "countryName": "Germany"},
                    "employmentType": {"name": "Employee"},
                    "workplaceType": "REMOTE",
                    "createdAt": "2025-09-01T00:00:00.000Z",
                },
            ],
        },
    }
)


class _Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, pages):
        self.headers = {}
        self._pages = pages
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        return _Resp(self._pages.pop(0))


def test_join_fetch_maps_and_stops():
    conn = JoinConnector("join", session=_FakeSession([PAGE1]))
    jobs = conn.fetch()

    assert len(jobs) == 2
    j0 = jobs[0]
    assert j0.source_platform == "join"
    assert j0.source_board == "join"
    assert j0.source_job_id == "14771122"
    assert j0.title == "Engineering Manager"
    assert j0.company == "JOIN"
    assert j0.location == "Barcelona, Spain"
    assert j0.workplace_type == "hybrid"
    assert j0.remote is False
    assert j0.category == "Engineering"  # Job normalizes category from title
    assert j0.source_url.endswith("/companies/join/jobs/16947455-engineering-manager")
    assert j0.apply_url == j0.source_url

    j1 = jobs[1]
    assert j1.title == "Data Engineer"
    assert j1.workplace_type == "remote"
    assert j1.remote is True


def test_join_paginates_until_pagecount():
    page1 = _html(
        {
            "company": {"name": "BigCo"},
            "jobs": {
                "pagination": {"page": 1, "pageCount": 2, "pageSize": 1, "total": 2},
                "items": [
                    {"id": 1, "idParam": "1-a", "title": "A", "city": {"cityName": "Paris", "countryName": "France"}}
                ],
            },
        }
    )
    page2 = _html(
        {
            "company": {"name": "BigCo"},
            "jobs": {
                "pagination": {"page": 2, "pageCount": 2, "pageSize": 1, "total": 2},
                "items": [
                    {"id": 2, "idParam": "2-b", "title": "B", "city": {"cityName": "Lyon", "countryName": "France"}}
                ],
            },
        }
    )
    sess = _FakeSession([page1, page2])
    jobs = JoinConnector("bigco", session=sess).fetch()
    assert [j.title for j in jobs] == ["A", "B"]
    assert len(sess.calls) == 2
    assert sess.calls[1].endswith("?page=2")
