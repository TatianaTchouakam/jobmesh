"""Exenzo connector — offline: public JSON API with {total,data,lastPage} pages."""
from jobmesh.connectors.exenzo import ExenzoConnector


def _job(i):
    return {"id": i, "uuid": f"u{i}", "title": f"Role {i}",
            "organisation_name": "Vitens", "city": "Zwolle", "country_code": "NL",
            "description": "<p>Work</p>", "job_url": f"https://bb.exenzo.com/v/{i}",
            "apply_url": f"https://apply/{i}", "remote": 0,
            "created_at": "2026-11-20 15:18:56"}


class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status_code = status

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


class _Session:
    def __init__(self, pages):
        self.headers = {}
        self._pages = pages

    def get(self, url, params=None, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(None, status=404)
        page = (params or {}).get("page", 1)
        return _Resp(self._pages.get(page, {"data": [], "lastPage": max(self._pages)}))


def test_fetch_paginates_and_maps():
    pages = {
        1: {"total": 3, "currentPage": 1, "lastPage": 2, "data": [_job(1), _job(2)]},
        2: {"total": 3, "currentPage": 2, "lastPage": 2, "data": [_job(3)]},
    }
    c = ExenzoConnector("bb", session=_Session(pages))
    jobs = c.fetch()
    assert len(jobs) == 3
    a = jobs[0]
    assert a.title == "Role 1"
    assert a.company == "Vitens"
    assert a.location == "Zwolle, NL"
    assert a.source_url == "https://bb.exenzo.com/v/1"
    assert a.apply_url == "https://apply/1"
    assert a.source_job_id == "u1"
