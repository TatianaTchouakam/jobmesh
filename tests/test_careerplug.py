"""CareerPlug connector — offline, against the real JSON-LD ItemList shape."""
import json
from jobmesh.connectors.careerplug import CareerPlugConnector


def _itemlist_html(postings):
    ld = {"@context": "https://schema.org", "@type": "ItemList",
          "numberOfItems": len(postings),
          "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": p}
                              for i, p in enumerate(postings)]}
    return f'<html><body><script type="application/ld+json">{json.dumps(ld)}</script></body></html>'


def _posting(jid, remote=False, loc=True):
    p = {
        "@type": "JobPosting",
        "title": f"Role {jid}",
        "description": "<div>Build <b>things</b> here</div>",
        "datePosted": "2026-10-12T15:36:57+00:00",
        "employmentType": "FULL_TIME",
        "identifier": {"@type": "PropertyValue", "name": "CareerPlug Job ID", "value": jid},
        "hiringOrganization": {"@type": "Organization", "name": "Acme"},
        "baseSalary": {"@type": "MonetaryAmount", "currency": "USD",
                       "value": {"@type": "QuantitativeValue", "unitText": "YEAR",
                                 "minValue": "90000.00", "maxValue": "120400.00"}},
    }
    if remote:
        p["jobLocationType"] = "TELECOMMUTE"
    if loc:
        p["jobLocation"] = {"@type": "Place", "address": {"@type": "PostalAddress",
                            "addressLocality": "Austin", "addressRegion": "TX",
                            "addressCountry": "US"}}
    return p


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(self.status_code)


class _FakeSession:
    def __init__(self, page1_html):
        self.headers = {}
        self._page1 = page1_html

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nDisallow: /apps/\nDisallow: /admin/\n")
        if "?page=" in url:
            return _Resp("<html></html>")        # no more postings -> stop
        if url.endswith("/jobs"):
            return _Resp(self._page1)
        return _Resp("", status=404)


def test_itemlist_mapped_with_per_job_urls():
    html = _itemlist_html([_posting("111", remote=True, loc=False),
                           _posting("222", loc=True)])
    c = CareerPlugConnector("acmeco", session=_FakeSession(html))
    jobs = c.fetch()
    assert len(jobs) == 2
    j = {x.source_job_id: x for x in jobs}
    a = j["111"]
    assert a.source_platform == "careerplug" and a.source_board == "acmeco"
    assert a.company == "Acme"
    assert a.source_url == "https://acmeco.careerplug.com/jobs/111"
    assert a.apply_url == "https://acmeco.careerplug.com/jobs/111/apps/new"
    assert a.remote is True                      # TELECOMMUTE
    assert a.salary and "90000" in a.salary and "120400" in a.salary and "USD" in a.salary
    assert "Build things" in (a.description or "")
    b = j["222"]
    assert b.location == "Austin, TX, US"


def test_robots_and_dedup():
    # same posting id twice -> deduped to one
    html = _itemlist_html([_posting("777"), _posting("777")])
    c = CareerPlugConnector("acmeco2", session=_FakeSession(html))
    jobs = c.fetch()
    assert len(jobs) == 1 and jobs[0].source_job_id == "777"
