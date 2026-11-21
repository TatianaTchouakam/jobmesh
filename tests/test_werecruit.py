"""Offline test: WeRecruit embedded-JSON offer parsing."""
from jobmesh.connectors.werecruit import WeRecruitConnector, _location

_HTML = r'''<html><body><script>var data = [
{"PublicationStartDate":"2026-11-09T17:05:11Z","Url":"https://careers.werecruit.io/en/atlantis/offers/compositor---midsenior-level-454402","ImageUrl":"x.jpg","TitleTranslated":"Compositor - Mid/Senior level F/M","TypeTranslated":"Temporary contract - 9 months","TimeTranslated":"Full time","DepartmentId":"38---santa-cruz-de-tenerife","Id":"guid1"},
{"Url":"https://careers.werecruit.io/en/atlantis/offers/spontaneous-application-d35c49","TitleTranslated":"Spontaneous","TimeTranslated":"","DepartmentId":""},
{"PublicationStartDate":"2026-11-10T00:00:00Z","Url":"https://careers.werecruit.io/en/atlantis/offers/remote-dev-999","TitleTranslated":"Remote Developer","TimeTranslated":"Full time","DepartmentId":"Remote","Id":"guid2"}
];</script></body></html>'''


class _Resp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nAllow: /\n")
        return _Resp(_HTML)


def test_werecruit_parses_offers_skips_spontaneous():
    jobs = WeRecruitConnector("atlantis", session=_Session()).fetch()
    assert len(jobs) == 2                       # spontaneous (hex id) skipped
    a = jobs[0]
    assert a.source_job_id == "454402"
    assert a.title == "Compositor - Mid/Senior level F/M"
    assert a.company == "Atlantis"
    assert a.location == "Santa Cruz De Tenerife"
    assert a.employment_type == "Full-time"
    assert a.source_url.endswith("compositor---midsenior-level-454402")
    b = jobs[1]
    assert b.source_job_id == "999" and b.title == "Remote Developer" and b.remote is True


def test_werecruit_location_strip():
    assert _location("38---santa-cruz-de-tenerife") == "Santa Cruz De Tenerife"
    assert _location("Remote") == "Remote"
    assert _location(None) is None
