"""Offline test for the generic schema.org JobPosting (JSON-LD) connector."""

from __future__ import annotations

from jobmesh.connectors.careersite import CareerSiteConnector

HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting",
 "title":"Data Engineer",
 "description":"<p>Build <b>pipelines</b>.</p>",
 "datePosted":"2026-11-10",
 "employmentType":"FULL_TIME",
 "identifier":{"@type":"PropertyValue","value":"REQ-42"},
 "hiringOrganization":{"@type":"Organization","name":"Acme GmbH"},
 "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
   "addressLocality":"Berlin","addressCountry":"DE"}},
 "baseSalary":{"@type":"MonetaryAmount","currency":"EUR",
   "value":{"@type":"QuantitativeValue","minValue":60000,"maxValue":75000,"unitText":"YEAR"}},
 "url":"https://jobs.acme.de/data-engineer"}
</script>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"JobPosting","title":"Remote Analyst","jobLocationType":"TELECOMMUTE",
   "identifier":"REQ-43","hiringOrganization":{"name":"Acme GmbH"},
   "url":"https://jobs.acme.de/analyst"}
]}
</script>
</head><body></body></html>
"""


class _Resp:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, text):
        self.headers = {}
        self._text = text

    def get(self, *a, **k):
        return _Resp(self._text)


def test_careersite_extracts_jobpostings():
    conn = CareerSiteConnector(
        "https://jobs.acme.de/careers", session=_FakeSession(HTML)
    )
    jobs = conn.fetch()
    assert len(jobs) == 2
    by_id = {j.source_job_id: j for j in jobs}

    de = by_id["REQ-42"]
    assert de.title == "Data Engineer"
    assert de.company == "Acme GmbH"
    assert de.location == "Berlin, DE"
    assert de.employment_type == "Full-time"
    assert "pipelines" in de.description and "<b>" not in de.description
    assert de.salary == "EUR 60000-75000 YEAR"
    assert de.source_url == "https://jobs.acme.de/data-engineer"

    rem = by_id["REQ-43"]
    assert rem.remote is True


def test_careersite_tolerates_bad_blocks():
    bad = '<script type="application/ld+json">{ not json }</script>'
    conn = CareerSiteConnector("https://x/y", session=_FakeSession(bad))
    assert conn.fetch() == []
