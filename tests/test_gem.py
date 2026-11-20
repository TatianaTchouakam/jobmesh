"""Gem connector — offline, against the real public GraphQL response shape."""
from jobmesh.connectors.gem import GemConnector

ROBOTS_404 = ("<html><title>404 page not found</title></html>", 404)


def _post(jid, ext, title, locs, dept, loctype="IN_OFFICE", emp="FULL_TIME"):
    return {"id": jid, "extId": ext, "title": title, "locations": locs,
            "job": {"department": {"name": dept}, "locationType": loctype,
                    "employmentType": emp}}


class _Resp:
    def __init__(self, js=None, text="", status=200):
        self._js = js
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400 and self._js is None:
            pass  # robots 404 text response is fine

    def json(self):
        return self._js


class _FakeSession:
    def __init__(self, posts, team="Acme"):
        self.headers = {}
        self._posts = posts
        self._team = team

    def get(self, url, timeout=None, **k):   # robots.txt
        return _Resp(text="404 page not found", status=404)

    def post(self, url, json=None, timeout=None, **k):
        data = [{"data": {
            "oatsExternalJobPostings": {"jobPostings": self._posts},
            "jobBoardExternal": {"teamDisplayName": self._team}}}]
        return _Resp(js=data)


def test_graphql_mapped():
    posts = [
        _post("gid1", "ext-abc", "Applied AI Scientist",
              [{"name": "Boston, MA", "city": "Cambridge", "isoCountry": "USA", "isRemote": False}],
              "Dry Lab"),
        _post("gid2", "ext-def", "Remote Engineer",
              [{"name": None, "city": None, "isoCountry": None, "isRemote": True}],
              "Engineering", loctype="REMOTE"),
    ]
    c = GemConnector("nabla-bio", session=_FakeSession(posts, team="Nabla Bio"))
    jobs = c.fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.title == "Applied AI Scientist"
    assert a.company == "Nabla Bio"            # from teamDisplayName
    assert a.location == "Boston, MA"
    assert a.source_job_id == "ext-abc"
    assert a.source_url == "https://jobs.gem.com/nabla-bio/ext-abc"
    assert a.workplace_type == "onsite"        # IN_OFFICE
    assert a.source_platform == "gem" and a.source_board == "nabla-bio"
    b = jobs[1]
    assert b.remote is True and b.workplace_type == "remote" and b.location == "Remote"


def test_robots_404_allows():
    # a 404 robots (no file) must fail open to allowed, so jobs come through
    c = GemConnector("nabla-bio", session=_FakeSession([_post("g", "e", "Role", [], "X")]))
    assert len(c.fetch()) == 1
