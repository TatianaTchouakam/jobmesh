"""Tests for the Recooty connector (platform sitemap + JSON-LD)."""

from jobmesh.connectors.recooty import RecootyConnector

SITEMAP = (
    "<urlset>"
    "<url><loc>https://jobs.recooty.com/</loc></url>"
    "<url><loc>https://jobs.recooty.com/acme/data-engineer-ac101</loc></url>"
    "<url><loc>https://jobs.recooty.com/acme/ml-engineer-ac102</loc></url>"
    "<url><loc>https://jobs.recooty.com/acme</loc></url>"  # tenant landing, skipped
    "</urlset>"
)

def _page(title):
    ld = (
        '{"@context":"https://schema.org","@type":"JobPosting",'
        f'"title":"{title}","description":"<p>Build things.</p>",'
        '"hiringOrganization":{"name":"Acme"},'
        '"jobLocation":{"address":{"addressLocality":"Berlin","addressCountry":"DE"}},'
        '"datePosted":"2026-11-18"}'
    )
    return f'<html><head><script type="application/ld+json">{ld}</script></head><body></body></html>'


class _Resp:
    def __init__(self, *, content=None, text=None):
        self.content = content
        self._text = text
    @property
    def text(self):
        return self._text
    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self):
        self.headers = {}
    def get(self, url, timeout=None):
        if url.endswith("/sitemap.xml"):
            return _Resp(content=SITEMAP.encode())
        if url.endswith("ac101"):
            return _Resp(text=_page("Data Engineer"))
        if url.endswith("ac102"):
            return _Resp(text=_page("ML Engineer"))
        return _Resp(text="<html></html>")


def test_recooty_crawls_sitemap_and_parses_jsonld():
    jobs = RecootyConnector("all", session=_FakeSession()).fetch()
    titles = sorted(j.title for j in jobs)
    assert titles == ["Data Engineer", "ML Engineer"]
    j = jobs[0]
    assert j.source_platform == "recooty"
    assert j.company == "Acme"
    assert "Build things" in (j.description or "")
