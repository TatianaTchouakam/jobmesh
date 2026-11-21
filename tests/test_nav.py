"""Offline test: NAV Arbeidsplassen feed (public-token fallback, ACTIVE filter)."""
from jobmesh.connectors.nav import NavConnector

_FEED = {
    "version": "1.0", "title": "Stillingsfeeden",
    "next_url": None,
    "items": [
        {"id": "u1", "url": "/api/v1/feedentry/u1", "title": "Helsecoach",
         "date_modified": "2026-11-19T21:24:01+01:00",
         "_feed_entry": {"uuid": "u1", "status": "ACTIVE", "title": "Helsecoach",
                         "businessName": "CROSSFIT VERFTET MINDE AS", "municipal": "BERGEN",
                         "sistEndret": "2026-11-19T21:24:01+01:00"}},
        {"id": "u2", "url": "/api/v1/feedentry/u2", "title": "Gammel stilling",
         "_feed_entry": {"uuid": "u2", "status": "INACTIVE", "title": "Gammel stilling",
                         "businessName": "OLD AS", "municipal": "OSLO"}},
        {"id": "u3", "url": "/api/v1/feedentry/u3", "title": "Utvikler",
         "_feed_entry": {"uuid": "u3", "status": "ACTIVE", "title": "Utvikler",
                         "businessName": "Tech AS", "municipal": "OSLO",
                         "sistEndret": "2026-11-20T10:00:00+01:00"}},
    ],
}


class _Resp:
    def __init__(self, payload=None, text="", status=200):
        self._p = payload; self.text = text; self.status_code = status
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, headers=None, timeout=None, **k):
        if url.endswith("robots.txt"):
            return _Resp(text="")                      # 404/empty -> allowed
        if url.endswith("/api/publicToken"):
            return _Resp(text="PUBLIC-TEST-TOKEN")
        assert "Bearer PUBLIC-TEST-TOKEN" in (headers or {}).get("Authorization", "")
        assert "/api/v1/feed" in url
        return _Resp(payload=_FEED)


def test_nav_feed_active_only(monkeypatch):
    monkeypatch.delenv("NAV_TOKEN", raising=False)     # force public-token fallback
    jobs = NavConnector(session=_Session()).fetch()
    assert len(jobs) == 2                              # INACTIVE dropped
    ids = {j.source_job_id for j in jobs}
    assert ids == {"u1", "u3"}
    a = next(j for j in jobs if j.source_job_id == "u1")
    assert a.title == "Helsecoach"
    assert a.company == "CROSSFIT VERFTET MINDE AS"
    assert a.location == "Bergen, Norway"
    assert a.source_url.endswith("/stillinger/stilling/u1")
    assert a.posted_at.startswith("2026-11-19")


def test_nav_uses_env_token(monkeypatch):
    monkeypatch.setenv("NAV_TOKEN", "PRIVATE")
    class S(_Session):
        def get(self, url, headers=None, timeout=None, **k):
            if url.endswith("robots.txt"): return _Resp(text="")
            assert "publicToken" not in url            # env token -> no public fetch
            assert "Bearer PRIVATE" in (headers or {}).get("Authorization", "")
            return _Resp(payload=_FEED)
    jobs = NavConnector(session=S()).fetch()
    assert len(jobs) == 2
