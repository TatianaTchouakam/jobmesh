"""Tests for the Dover connector (keyless feed + sitemap self-discovery)."""

from jobmesh.connectors.dover import DoverConnector


JOB = {
    "id": "abc-123",
    "title": "Data Engineer",
    "company_name": "Vanta",
    "content": "<p>Build <strong>pipelines</strong>.</p>",
    "location": {"name": "Remote - US"},
    "remote": "only",
    "department": ["Engineering"],
    "absolute_url": "https://jobs.dover.com/vanta/abc-123",
    "first_published": "2026-11-17T11:41:57Z",
}

SITEMAP = (
    "<sitemapindex>"
    "<url><loc>https://jobs.dover.com/vanta</loc></url>"
    "<url><loc>https://jobs.dover.com/angellist</loc></url>"
    "<url><loc>https://jobs.dover.com/feed/jobs_sitemap</loc></url>"  # skipped
    "</sitemapindex>"
)


class _Resp:
    def __init__(self, *, text=None, payload=None):
        self._text = text
        self._payload = payload

    @property
    def text(self):
        return self._text

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url.endswith("/feed/careers_sitemap"):
            return _Resp(text=SITEMAP)
        # board feed
        return _Resp(payload={"jobs": [JOB]})


def test_dover_single_board_maps():
    jobs = DoverConnector("vanta", session=_FakeSession()).fetch()
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source_platform == "dover"
    assert j.source_board == "vanta"
    assert j.source_job_id == "abc-123"
    assert j.title == "Data Engineer"
    assert j.company == "Vanta"
    assert j.location == "Remote - US"
    assert "pipelines" in (j.description or "")
    assert j.remote is True
    assert j.workplace_type == "remote"
    assert j.source_url == "https://jobs.dover.com/vanta/abc-123"


def test_dover_all_discovers_tenants():
    sess = _FakeSession()
    jobs = DoverConnector("all", session=sess).fetch()
    # vanta + angellist (feed/* skipped) -> 2 boards, 1 job each
    assert len(jobs) == 2
    assert sess.calls[0].endswith("/feed/careers_sitemap")
    boards = {j.source_board for j in jobs}
    assert boards == {"vanta", "angellist"}
