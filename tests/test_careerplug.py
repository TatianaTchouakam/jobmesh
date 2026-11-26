"""CareerPlug connector -- offline: /jobs list links -> per-posting JSON-LD."""
import json

from jobmesh.connectors.careerplug import CareerPlugConnector


def _fiche(jid, remote=False, loc=True):
    p = {
        "@context": "https://schema.org", "@type": "JobPosting",
        "title": f"Role {jid}",
        "description": "<div>Build <b>things</b> here</div>",
        "datePosted": "2026-10-12T15:36:57+00:00",
        "employmentType": "FULL_TIME",
        # CareerPlug keys the id as a labelled PropertyValue (the connector must
        # instead key on the /jobs/{id} path, not this).
        "identifier": {"@type": "PropertyValue", "name": "CareerPlug Job ID",
                       "value": jid},
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
    return f'<html><script type="application/ld+json">{json.dumps(p)}</script></html>'


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import RequestException
            raise RequestException(str(self.status_code))


class _Session:
    def __init__(self, list_html, fiches):
        self.headers = {}
        self._list = list_html
        self._fiches = fiches

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp("User-agent: *\nDisallow: /apps/\nDisallow: /j/\nDisallow: /jobs.js\n")
        if "/jobs?page=" in url:
            return _Resp("<html></html>")   # no further pages
        if url.endswith("/jobs"):
            return _Resp(self._list)
        for jid, html in self._fiches.items():
            if url.endswith(f"/jobs/{jid}"):
                return _Resp(html)
        return _Resp("", status=404)


def test_list_then_fiche_jsonld():
    list_html = ('<html><a href="/jobs/111">a</a>'
                 '<a href="/jobs/222">b</a></html>')
    fiches = {"111": _fiche("111", remote=True, loc=False),
              "222": _fiche("222", loc=True)}
    c = CareerPlugConnector("acmeco", session=_Session(list_html, fiches))
    jobs = c.fetch()
    assert len(jobs) == 2
    j = {x.source_job_id: x for x in jobs}          # keyed by /jobs/{id} path id
    a = j["111"]
    assert a.source_platform == "careerplug" and a.source_board == "acmeco"
    assert a.company == "Acme"
    assert a.source_url == "https://acmeco.careerplug.com/jobs/111"
    assert a.remote is True
    assert a.salary and "90000" in a.salary and "USD" in a.salary
    assert "Build things" in (a.description or "")
    assert j["222"].location == "Austin, TX, US"


def test_dedup_repeated_links():
    list_html = ('<html><a href="/jobs/777">x</a>'
                 '<a href="/jobs/777">x again</a></html>')
    c = CareerPlugConnector("acmeco2", session=_Session(list_html, {"777": _fiche("777")}))
    jobs = c.fetch()
    assert len(jobs) == 1 and jobs[0].source_job_id == "777"
