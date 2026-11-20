"""Freshteam connector — offline, against the real server-rendered card markup."""
from jobmesh.connectors.freshteam import FreshteamConnector

ROBOTS = "User-agent: *\nAllow: /jobs\nDisallow: /\n"


def _card(jid, title, loc, remote):
    return (f'<div class="job-list">'
            f'<a href="/jobs/{jid}/{title.lower().replace(" ", "-")}" class="heading" '
            f'data-portal-title="{title}" data-portal-location="{loc}" '
            f'data-portal-job-type="4" data-portal-remote-location={str(remote).lower()}>'
            f'<div class="row"><div class="job-list-info">'
            f'<div class="job-title"> {title}</div></div></div></a></div>')


def _page(cards):
    return "<html><body>" + "".join(cards) + "</body></html>"


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(self.status_code)


class _FakeSession:
    def __init__(self, page, robots=ROBOTS):
        self.headers = {}
        self._page = page
        self._robots = robots

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(self._robots)
        if url.endswith("/jobs"):
            return _Resp(self._page)
        return _Resp("", status=404)


def test_parses_cards():
    page = _page([
        _card("8SJM1YVoaMj-", "Call Center Agent (Remote)", "Washington, United States of America", True),
        _card("abc123", "Warehouse Lead", "Dallas, United States of America", False),
    ])
    c = FreshteamConnector("acme-co", session=_FakeSession(page))
    jobs = c.fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.title == "Call Center Agent (Remote)"
    assert a.company == "Acme Co"
    assert a.location == "Washington, United States of America"
    assert a.remote is True and a.workplace_type == "remote"
    assert a.source_job_id == "8SJM1YVoaMj"
    assert a.source_url == "https://acme-co.freshteam.com/jobs/8SJM1YVoaMj-/call-center-agent-(remote)"
    assert a.source_platform == "freshteam" and a.source_board == "acme-co"
    assert jobs[1].remote is False and jobs[1].location == "Dallas, United States of America"


def test_robots_blocks_disallowed():
    page = _page([_card("x1", "Nurse", "Berlin, Germany", False)])
    c = FreshteamConnector("blocked-fresh", session=_FakeSession(page, robots="User-agent: *\nDisallow: /\n"))
    assert c.fetch() == []
