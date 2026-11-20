"""Jobvite connector — offline, against the real server-rendered row markup."""
from jobmesh.connectors.jobvite import JobviteConnector


def _row(jid, title, loc):
    return (f'<tr><td class="jv-job-list-name">\n'
            f'<a href="/nutanix/job/{jid}">{title}</a>\n</td>\n'
            f'<td class="jv-job-list-location">\n\n    {loc}\n    </td></tr>')


def _page(rows):
    return "<table>" + "".join(rows) + "</table>"


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(self.status_code)


class _FakeSession:
    def __init__(self, pages):
        self.headers = {}
        self._pages = pages  # dict: page number -> html

    def get(self, url, params=None, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("", status=404)          # no robots -> allowed
        p = (params or {}).get("p", 1)
        return _Resp(self._pages.get(p, _page([])))


def test_parses_rows():
    html = _page([
        _row("ozI4AfwF", "Advisory Enterprise Account Manager", "Philadelphia,\n            Pennsylvania"),
        _row("oK3NAfwU", "Backend Engineer", "Remote, United States"),
    ])
    c = JobviteConnector("nutanix", session=_FakeSession({1: html}))
    jobs = c.fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.title == "Advisory Enterprise Account Manager"
    assert a.company == "Nutanix"
    assert a.location == "Philadelphia, Pennsylvania"
    assert a.source_url == "https://jobs.jobvite.com/nutanix/job/ozI4AfwF"
    assert a.source_job_id == "ozI4AfwF"
    assert a.source_platform == "jobvite" and a.source_board == "nutanix"
    assert jobs[1].remote is True                 # "Remote, United States"


def test_pagination_and_stop():
    full = _page([_row(f"id{i}", f"Role {i}", "Austin, TX") for i in range(50)])
    full2 = _page([_row(f"id{i}", f"Role {i}", "Austin, TX") for i in range(50, 90)])  # 40 < 50 -> last
    c = JobviteConnector("nutanix", session=_FakeSession({1: full, 2: full2}))
    jobs = c.fetch()
    assert len(jobs) == 90                         # 50 + 40, all unique
    ids = {j.source_job_id for j in jobs}
    assert len(ids) == 90


def test_company_from_hyphen_slug():
    html = _page([_row("x1", "Nurse", "Berlin, Germany")])
    c = JobviteConnector("acme-health", session=_FakeSession({1: html}))
    assert c.fetch()[0].company == "Acme Health"
