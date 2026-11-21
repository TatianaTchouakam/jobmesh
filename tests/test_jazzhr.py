"""JazzHR connector — offline: server-rendered <li class="list-group-item"> rows."""
from jobmesh.connectors.jazzhr import JazzHrConnector

PAGE = """<html><body>
<div class='jobs-list'><h2>Current Openings</h2>
<ul class='list-group'>
<li class="list-group-item">
  <h3 class='list-group-item-heading'>
    <a href="https://acme.applytojob.com/apply/vMHpWDZa3l/Account-Executive"> Account Executive </a>
  </h3>
  <ul class='list-inline list-group-item-text'>
    <li><i class='fa fa-map-marker'></i>Remote</li>
  </ul>
</li>
<li class="list-group-item">
  <h3 class='list-group-item-heading'>
    <a href="https://acme.applytojob.com/apply/Zb12Cd34Ef/Senior-Engineer"> Senior Engineer </a>
  </h3>
  <ul class='list-inline list-group-item-text'>
    <li><i class='fa fa-map-marker'></i>Berlin, DE</li>
  </ul>
</li>
</ul></div></body></html>"""


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


class _Session:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("", status=404)
        return _Resp(PAGE)


def test_parses_list_rows():
    c = JazzHrConnector("acme", session=_Session())
    jobs = c.fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.title == "Account Executive"
    assert a.source_job_id == "vMHpWDZa3l"
    assert a.location == "Remote"
    assert a.apply_url == "https://acme.applytojob.com/apply/vMHpWDZa3l/Account-Executive"
    assert jobs[1].title == "Senior Engineer"
    assert jobs[1].location == "Berlin, DE"
