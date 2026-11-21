"""Offline test: Taleo careersection REST (paginated searchjobs + column mapping)."""
import json

from jobmesh.connectors.taleo import TaleoConnector, _parse_location


class _Resp:
    def __init__(self, payload=None, status=200, text=""):
        self._p, self.status_code, self.text = payload, status, text

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


def _row(jid, contest, title, loc='["United States-Colorado-Englewood"]', date="Nov 20, 2026"):
    return {"jobId": jid, "contestNo": contest, "linkedColumn": 0,
            "locationsColumns": [1], "column": [title, loc, date]}


class _TaleoSession:
    def __init__(self):
        self.headers, self.pages, self.seeded = {}, [], False

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(status=404, text="not found")      # fail-open -> allowed
        self.seeded = True                                   # seed cookie GET
        return _Resp(text="<html>shell</html>")

    def post(self, url, data=None, headers=None, timeout=None, **k):
        assert "/careersection/rest/jobboard/searchjobs?lang=en&portal=101430233" in url
        page = json.loads(data)["pageNo"]
        self.pages.append(page)
        if page == 1:
            rows = [_row(str(700000 + i), str(190000 + i), f"Engineer {i}") for i in range(25)]
            return _Resp({"requisitionList": rows})          # full page -> keep paging
        if page == 2:
            return _Resp({"requisitionList": [
                _row("794347", "198078", "Building Performance Engineer",
                     loc='["Multiple Locations"]')]})        # short page -> stop
        raise AssertionError("should have stopped after page 2")


def test_taleo_paginates_maps_and_builds_urls():
    s = _TaleoSession()
    jobs = TaleoConnector("hdr|101430233", session=s).fetch()
    assert s.seeded is True
    assert s.pages == [1, 2]
    assert len(jobs) == 26
    last = jobs[-1]
    assert last.title == "Building Performance Engineer"
    assert last.location == "Multiple Locations"
    assert last.company == "HDR"
    assert last.source_url == "https://hdr.taleo.net/careersection/ex/jobdetail.ftl?job=198078"
    assert last.apply_url == last.source_url
    assert last.posted_at == "2026-11-20T00:00:00"  # normalized to ISO
    first = jobs[0]
    assert first.location == "United States-Colorado-Englewood"
    assert first.source_job_id == "700000"


def test_taleo_board_with_section():
    c = TaleoConnector("acme|xf|55")
    assert c.tenant == "acme" and c.section == "xf" and c.portal == "55"


def test_taleo_parse_location_variants():
    assert _parse_location('["A","B"]') == "A; B"
    assert _parse_location('["Solo"]') == "Solo"
    assert _parse_location("") is None
    assert _parse_location("Plain text") == "Plain text"
