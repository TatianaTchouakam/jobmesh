"""Paycom connector -- offline: seeded fiche ids -> per-posting JSON-LD, 404=closed."""
import json

from jobmesh.connectors.paycom import PaycomConnector, _parse_board


def _fiche(jid, title):
    p = {"@context": "https://schema.org", "@type": "JobPosting", "title": title,
         "hiringOrganization": {"@type": "Organization", "name": "Acme LLC"},
         "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress",
                         "addressLocality": "Coburg", "addressRegion": "OR",
                         "addressCountry": "USA"}}}
    return f'<html><script type="application/ld+json">{json.dumps(p)}</script></html>'


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


class _Session:
    def __init__(self, pages):
        self.headers = {}
        self._pages = pages

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nDisallow: /\nAllow: /v4/ats/web.php/portal/\n")
        for jid, html in self._pages.items():
            if url.endswith(f"/jobs/{jid}"):
                return _Resp(html) if html else _Resp("", status=404)
        return _Resp("", status=404)


def test_board_parsing():
    key, ids = _parse_board("ABC123:111,222,333")
    assert key == "ABC123" and ids == ["111", "222", "333"]


def test_fiches_mapped_and_404_skipped():
    board = "ABC123:111,222,999"
    pages = {"111": _fiche("111", "Warehouse Associate"),
             "222": _fiche("222", "Forklift Operator"),
             "999": None}                     # 404 -> closed / absent
    c = PaycomConnector(board, session=_Session(pages))
    jobs = c.fetch()
    ids = sorted(j.source_job_id for j in jobs)
    assert ids == ["111", "222"]              # 999 absent (404)
    j = {x.source_job_id: x for x in jobs}
    assert j["111"].title == "Warehouse Associate"
    assert j["111"].company == "Acme LLC"
    assert j["111"].location == "Coburg, OR, USA"
    assert j["111"].source_url.endswith("/portal/ABC123/jobs/111")
