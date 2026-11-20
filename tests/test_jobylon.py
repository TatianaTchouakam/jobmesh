"""Tests for the Jobylon connector (sitemap index -> JSON-LD)."""

from jobmesh.connectors.jobylon import JobylonConnector

INDEX = ('<sitemapindex><sitemap><loc>https://emp.jobylon.com/sitemap-jobs-1.xml'
         '</loc></sitemap></sitemapindex>')
SUB = ('<urlset>'
       '<url><loc>https://emp.jobylon.com/jobs/1-acme-data-engineer/</loc></url>'
       '<url><loc>https://emp.jobylon.com/jobs/2-acme-ml-engineer/</loc></url>'
       '<url><loc>https://emp.jobylon.com/companies/acme/</loc></url>'  # not a job
       '</urlset>')

def _page(title):
    ld = ('{"@context":"https://schema.org","@type":"JobPosting",'
          f'"title":"{title}","description":"<p>Nordic role.</p>",'
          '"hiringOrganization":{"name":"Coor"},'
          '"jobLocation":{"address":{"addressLocality":"Goteborg","addressCountry":"SE"}},'
          '"datePosted":"2026-11-18"}')
    return f'<html><head><script type="application/ld+json">{ld}</script></head></html>'


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
            return _Resp(content=INDEX.encode())
        if url.endswith("sitemap-jobs-1.xml"):
            return _Resp(content=SUB.encode())
        if "/jobs/1-" in url:
            return _Resp(text=_page("Data Engineer"))
        if "/jobs/2-" in url:
            return _Resp(text=_page("ML Engineer"))
        return _Resp(text="<html></html>")


def test_jobylon_follows_index_and_parses():
    jobs = JobylonConnector("all", session=_FakeSession()).fetch()
    assert sorted(j.title for j in jobs) == ["Data Engineer", "ML Engineer"]
    assert jobs[0].source_platform == "jobylon"
    assert jobs[0].company == "Coor"
