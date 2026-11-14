"""Offline test for the SmartJobBoard sitemap -> JSON-LD crawler."""

from __future__ import annotations

from jobmesh.connectors.smartjobboard import SmartJobBoardConnector

SITEMAP = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://board.example.com/</loc></url>
  <url><loc>https://board.example.com/job/1/data-engineer/</loc></url>
  <url><loc>https://board.example.com/job/2/analyst/</loc></url>
  <url><loc>https://board.example.com/companies/</loc></url>
</urlset>"""


def _job_html(title, company, jid):
    return f"""<html><head>
    <script type="application/ld+json">
    {{"@context":"https://schema.org","@type":"JobPosting","title":"{title}",
      "identifier":"{jid}","hiringOrganization":{{"name":"{company}"}},
      "jobLocation":{{"@type":"Place","address":{{"addressLocality":"Berlin"}}}},
      "datePosted":"2026-11-10"}}
    </script></head><body></body></html>"""


PAGES = {
    "https://board.example.com/sitemap.xml": SITEMAP,
    "https://board.example.com/job/1/data-engineer/": _job_html("Data Engineer", "Acme", "1"),
    "https://board.example.com/job/2/analyst/": _job_html("Analyst", "Acme", "2"),
}


class _Resp:
    def __init__(self, body):
        if isinstance(body, bytes):
            self.content, self.text = body, body.decode()
        else:
            self.text, self.content = body, body.encode()
        self.status_code = 200

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, pages):
        self.headers = {}
        self._pages = pages

    def get(self, url, *a, **k):
        return _Resp(self._pages[url])


def test_smartjobboard_crawls_sitemap_and_maps_jsonld():
    conn = SmartJobBoardConnector("https://board.example.com/", session=_FakeSession(PAGES))
    assert set(conn._job_urls()) == {
        "https://board.example.com/job/1/data-engineer/",
        "https://board.example.com/job/2/analyst/",
    }
    jobs = conn.fetch()
    assert len(jobs) == 2
    titles = sorted(j.title for j in jobs)
    assert titles == ["Analyst", "Data Engineer"]
    for j in jobs:
        assert j.source_platform == "smartjobboard"
        assert j.source_board == "https://board.example.com"
        assert j.company == "Acme"
        assert j.location == "Berlin"
