"""Deel connector — offline: listing -> per-job JSON-LD JobPosting."""
import json
from jobmesh.connectors.deel import DeelConnector

ROBOTS = ("User-agent: *\nAllow: /\nDisallow: /api/\n"
          "Disallow: /*/job-details/*/application\n")
U1 = "93ce9ab3-461c-48de-abab-b7db49a519a9"
U2 = "14abe804-e6aa-485b-80ed-415b43d785bc"


def _listing(board, ids):
    links = "".join(f'<a href="/{board}/job-details/{i}/overview">Role</a>' for i in ids)
    return f"<html><body>{links}</body></html>"


def _jobpage(title, city, country, org, emp="FULL_TIME"):
    ld = {"@context": "https://schema.org/", "@type": "JobPosting", "title": title,
          "description": "<p>Build things</p>", "datePosted": "2026-11-02",
          "employmentType": emp,
          "hiringOrganization": {"@type": "Organization", "name": org},
          "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress",
                          "addressLocality": city, "addressCountry": country}}}
    return f'<html><head><script type="application/ld+json">{json.dumps(ld)}</script></head></html>'


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


class _FakeSession:
    def __init__(self, board, pages):
        self.headers = {}
        self._board = board
        self._pages = pages  # dict path-suffix -> html

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(ROBOTS)
        if url.endswith(f"/{self._board}"):
            return _Resp(self._pages["listing"])
        for uid, html in self._pages.get("jobs", {}).items():
            if uid in url:
                return _Resp(html)
        return _Resp("", status=404)


def test_listing_to_jsonld():
    pages = {"listing": _listing("zonos", [U1, U2]),
             "jobs": {U1: _jobpage("Software Engineer (Backend)", "Utrecht", "NL", "Zonos"),
                      U2: _jobpage("Customer Success Manager", "Gold Coast", "AU", "Zonos")}}
    c = DeelConnector("zonos", session=_FakeSession("zonos", pages))
    jobs = c.fetch()
    assert len(jobs) == 2
    a = next(j for j in jobs if j.source_job_id == U1)
    assert a.title == "Software Engineer (Backend)"
    assert a.company == "Zonos"
    assert a.location == "Utrecht, NL"
    assert a.source_url == f"https://jobs.deel.com/zonos/job-details/{U1}/overview"
    assert a.source_platform == "deel" and a.source_board == "zonos"
    assert "Build things" in (a.description or "")
