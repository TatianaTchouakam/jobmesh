"""softgarden connector (ATS — very common in Germany/DACH).

Reads the public softgarden career feed (no key):
    https://{board}.career.softgarden.de/jobs.feed.json

`board` is the employer's softgarden career slug (e.g. "home24",
"goldbeck"). The feed's exact field names vary between employers (some
emit schema.org JobPosting objects), so the mapping reads each field from
a few likely names and degrades gracefully.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 25


def _extract_rows(data) -> list:
    """Find the list of job objects in a feed whose wrapper key is unknown."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("jobs", "items", "results", "data", "postings",
                  "elements", "content", "jobAds", "vacancies"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        # schema.org DataFeed: {"dataFeedElement": [{"item": {JobPosting}}, ...]}
        # or ItemList: {"itemListElement": [{"item": {...}}, ...]}
        for wrap in ("dataFeedElement", "itemListElement"):
            seq = data.get(wrap)
            if isinstance(seq, list):
                return [e.get("item", e) if isinstance(e, dict) else e for e in seq]
        # last resort: the first list-of-dicts value anywhere in the object
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


def _text(v):
    """Flatten a value that may be a string or a nested object/list."""
    if isinstance(v, dict):
        return v.get("name") or v.get("value") or v.get("label")
    if isinstance(v, list):
        return ", ".join(x for x in (_text(i) for i in v) if x) or None
    return v


class SoftgardenConnector(Connector):
    platform = "softgarden"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        url = f"https://{self.board}.career.softgarden.de/jobs.feed.json"
        resp = self._session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        rows = _extract_rows(resp.json())
        default_company = self.board.replace("-", " ").title()
        at = now_iso()
        return [self._to_job(d, default_company, at) for d in rows]

    def _to_job(self, d: dict, default_company: str, at: str) -> Job:
        title = _first(d, "title", "jobTitle", "name") or "(untitled)"

        # schema.org JobPosting carries an `identifier` object {name, value}:
        # name is the hiring company, value is the posting id.
        ident = d.get("identifier")
        ident_name = ident.get("name") if isinstance(ident, dict) else None
        ident_value = ident.get("value") if isinstance(ident, dict) else None

        company = _text(_first(d, "hiringOrganization", "company",
                               "companyName")) or ident_name or default_company

        loc = _first(d, "location", "jobLocation", "locationName", "city")
        if isinstance(loc, dict):
            addr = loc.get("address") if isinstance(loc.get("address"), dict) else loc
            parts = [addr.get("addressLocality") or addr.get("city"),
                     addr.get("addressCountry") or addr.get("country")]
            loc = ", ".join(p for p in parts if p) or _text(loc)
        else:
            loc = _text(loc)

        url = _first(d, "jobUrl", "url", "applyUrl", "link")
        emp = _text(_first(d, "employmentType", "contractType", "jobType"))
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(ident_value or _first(d, "id", "jobId", "guid")
                              or url or title),
            title=title, company=company, location=loc,
            description=html_to_text(_text(_first(d, "description", "jobDescription"))),
            source_url=url, apply_url=url,
            salary=None,
            employment_type=emp,
            category=_text(_first(d, "department", "category", "industry")),
            remote=detect_remote(loc),
            posted_at=_first(d, "datePosted", "publicationDate", "date", "createdAt"),
            dedup_key=make_dedup_key(title, company, loc),
            first_seen=at, last_checked=at, is_open=True,
        )
