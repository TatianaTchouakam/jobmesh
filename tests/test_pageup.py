"""PageUp connector — offline: listing -> per-job JSON-LD JobPosting."""
import json
from jobmesh.connectors.pageup import PageUpConnector

ROBOTS = ("User-agent: *\nDisallow: /api/\nDisallow: /me/\n"
          "Disallow: /jobs/search?query=\n")


def _listing(slugs):
    links = ('<a href="/jobs/search">Search</a><a href="/jobs/filter">Filter</a>'
             + "".join(f'<a href="/jobs/{s}">Role</a>' for s in slugs))
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
    def __init__(self, listing, jobs, robots=ROBOTS):
        self.headers = {}
        self._listing = listing
        self._jobs = jobs
        self._robots = robots

    def get(self, url, timeout=None, **k):
        if url.endswith("/robots.txt"):
            return _Resp(self._robots)
        if url.endswith("/"):
            return _Resp(self._listing)
        for slug, html in self._jobs.items():
            if url.endswith(f"/jobs/{slug}"):
                return _Resp(html)
        return _Resp("", status=404)


def test_listing_to_jsonld():
    jobs = {"finance-business-partner-australia": _jobpage("Finance Business Partner", "Melbourne", "AU", "PageUp"),
            "account-executive-usa": _jobpage("Account Executive", "New York", "US", "PageUp")}
    c = PageUpConnector("pupcareers",
                        session=_FakeSession(_listing(list(jobs)), jobs))
    got = c.fetch()
    assert len(got) == 2   # search/filter links excluded
    a = next(j for j in got if j.source_job_id == "finance-business-partner-australia")
    assert a.title == "Finance Business Partner"
    assert a.company == "PageUp"
    assert a.location == "Melbourne, AU"
    assert a.source_url == "https://pupcareers.pageuppeople.com/jobs/finance-business-partner-australia"
    assert a.source_platform == "pageup" and a.source_board == "pupcareers"
    assert "Build things" in (a.description or "")
