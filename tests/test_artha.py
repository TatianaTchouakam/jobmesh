"""Offline test: Artha guest search API (paginated, Origin-scoped)."""
from jobmesh.connectors.artha import ArthaConnector, _location


def _job(_id, title, city, state, company="Acme", redirect=False):
    return {"_id": _id, "title": title, "slug": f"{title.lower()}-{_id}",
            "company": {"nm": company}, "activatedAt": "2026-11-21T11:36:15Z",
            "useRedirectUrl": redirect, "applyUrl": "https://r.artha.link/x" if redirect else None,
            "loc": {"city": {"nm": city}, "state": {"nm": state}, "country": {"nm": "United States"}}}


class _Resp:
    status_code = 200
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def __init__(self): self.pages = []
    def get(self, url, timeout=None, **k):
        return _Resp(None)  # robots.txt -> no rules
    def post(self, url, json=None, headers=None, timeout=None, **k):
        assert url.endswith("/jobs/search/guest")
        assert headers["Origin"] == "https://www.fpnajobs.com"
        page = json["page"]; self.pages.append(page)
        if page == 1:
            return _Resp({"data": {"data": [
                _job("a1", "Controller", "Pine Beach", "New Jersey"),
                _job("a2", "FP&A Analyst", "Toms River", "New Jersey", redirect=True)],
                "paginator": {"hasNextPage": True}}})
        return _Resp({"data": {"data": [_job("a3", "CFO", "Newark", "New Jersey")],
                               "paginator": {"hasNextPage": False}}})


_Resp.text = "User-agent: *\nAllow: /\n"


def test_artha_paginates_and_maps():
    s = _Session()
    jobs = ArthaConnector("www.fpnajobs.com", session=s).fetch()
    assert s.pages == [1, 2]
    assert len(jobs) == 3
    a = jobs[0]
    assert a.source_job_id == "a1"
    assert a.title == "Controller"
    assert a.company == "Acme"
    assert a.location == "Pine Beach, New Jersey, United States"
    assert a.source_url == "https://www.fpnajobs.com/job-detail/controller-a1"
    assert a.apply_url == a.source_url                    # not a redirect job
    b = jobs[1]
    assert b.apply_url == "https://r.artha.link/x"        # redirect job -> applyUrl


def test_artha_location_helper():
    assert _location({"city": {"nm": "Berlin"}, "country": {"nm": "Germany"}}) == "Berlin, Germany"
    assert _location(None) is None
