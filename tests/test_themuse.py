"""Offline test: The Muse connector (keyless public API, pagination, mapping)."""
from jobmesh.connectors.themuse import TheMuseConnector


def _page(results, page_count):
    return {"results": results, "page_count": page_count}


_JOB = {"id": 55, "name": "Product Designer",
        "company": {"name": "MuseCo"}, "locations": [{"name": "Remote"}],
        "categories": [{"name": "Design"}], "contents": "<p>Design things</p>",
        "refs": {"landing_page": "https://themuse/jobs/55"},
        "publication_date": "2026-11-18T00:00:00Z"}


class _Resp:
    status_code = 200
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, params=None, timeout=None, **k):
        if params["page"] == 0:
            return _Resp(_page([_JOB], 1))
        return _Resp(_page([], 1))


def test_themuse_maps():
    jobs = TheMuseConnector(session=_Session()).fetch()
    assert len(jobs) == 1
    a = jobs[0]
    assert a.source_job_id == "55"
    assert a.title == "Product Designer"
    assert a.company == "MuseCo"
    assert a.location == "Remote"
    assert a.remote is True
    assert a.source_url == "https://themuse/jobs/55"
