"""Offline test: MyCareersFuture public jobs API (pagination, mapping, cap)."""
from jobmesh.connectors.mycareersfuture import MyCareersFutureConnector, _location, _salary


def _job(uid, title, company="Acme SG", overseas=False):
    return {"uuid": uid, "title": title, "description": "<p>Great role</p>",
            "postedCompany": {"name": company},
            "address": {"isOverseas": overseas, "overseasCountry": "Malaysia" if overseas else None,
                        "districts": [{"region": "West"}]},
            "employmentTypes": [{"employmentType": "Full Time"}],
            "positionLevels": [{"position": "Fresh/entry level"}],
            "salary": {"minimum": 3200, "maximum": 4000, "type": {"salaryType": "Monthly"}},
            "metadata": {"jobDetailsUrl": f"https://www.mycareersfuture.gov.sg/job/{title}-{uid}",
                         "originalPostingDate": "2026-11-21"}}


class _Resp:
    status_code = 200
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def __init__(self): self.pages = []
    def get(self, url, params=None, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(None)
        self.pages.append(params["page"])
        if params["page"] == 0:
            return _Resp({"results": [_job("u1", "Events Coordinator"),
                                      _job("u2", "Remote Analyst", overseas=True)], "total": 3})
        if params["page"] == 1:
            return _Resp({"results": [_job("u3", "CFO")], "total": 3})
        return _Resp({"results": []})   # empty -> stop


_Resp.text = "User-agent: *\nDisallow:\n"


def test_mcf_paginates_maps_stops():
    s = _Session()
    jobs = MyCareersFutureConnector(session=s).fetch()
    assert s.pages == [0, 1, 2]       # stops on empty page 2
    assert len(jobs) == 3
    a = jobs[0]
    assert a.source_job_id == "u1"
    assert a.title == "Events Coordinator"
    assert a.company == "Acme SG"
    assert a.location == "Singapore (West)"
    assert a.salary == "SGD 3200-4000/Monthly"
    assert a.employment_type == "Full-time"
    assert a.source_url == "https://www.mycareersfuture.gov.sg/job/Events Coordinator-u1"
    b = jobs[1]
    assert b.location == "Malaysia"   # overseas


def test_mcf_helpers():
    assert _location({"isOverseas": False, "districts": [{"region": "East"}]}) == "Singapore (East)"
    assert _location({"isOverseas": True, "overseasCountry": "India"}) == "India"
    assert _salary({"minimum": 5000, "maximum": 8000, "type": {"salaryType": "Monthly"}}) == "SGD 5000-8000/Monthly"
    assert _salary(None) is None


def test_mcf_reads_beyond_old_cap_and_dedupes(monkeypatch):
    """The catalogue is far larger than the old 5000 cap; read it all, with
    uuid de-duplication across pages, and honour the configurable cap."""
    import jobmesh.connectors.mycareersfuture as mcf
    monkeypatch.setattr(mcf, "PAGE_PAUSE", 0.0)
    monkeypatch.setattr(mcf, "MAX_JOBS", 6500)

    class _BigSession:
        headers = {}
        def __init__(self): self.max_page = 0
        def get(self, url, params=None, timeout=None, **k):
            if url.endswith("/robots.txt"):
                r = _Resp(None); r.text = "User-agent: *\nDisallow:\n"; return r
            pg = params["page"]; self.max_page = max(self.max_page, pg)
            # 100 unique jobs per page for 80 pages (8000 > old 5000 cap),
            # and repeat one uuid every page to exercise de-dup.
            if pg >= 80:
                return _Resp({"results": [], "total": 8000})
            rows = [_job(f"u{pg}-{i}", f"Role {pg}-{i}") for i in range(100)]
            rows.append(_job("dup", "Repeated Role"))   # same uuid every page
            return _Resp({"results": rows, "total": 8000})

    s = _BigSession()
    jobs = mcf.MyCareersFutureConnector(session=s).fetch()
    ids = [j.source_job_id for j in jobs]
    assert len(jobs) > 5000                 # old cap no longer limits us
    assert len(jobs) <= 6500 + 100           # configurable cap respected (soft, per page)
    assert ids.count("dup") == 1             # de-duplicated across pages
    assert s.max_page >= 50                  # really paged deep
