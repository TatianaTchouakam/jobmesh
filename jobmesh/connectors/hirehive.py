"""HireHive connector (ATS).

Reads the public HireHive jobs API (no key):
    GET https://{board}.hirehive.com/api/v1/jobs   (supports ?page=)

`board` is the company's HireHive subdomain. The exact JSON schema isn't
formally documented, so the mapping reads each field from a few likely
names and degrades gracefully.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25
MAX_PAGES = 10


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


class HireHiveConnector(Connector):
    platform = "hirehive"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        at = now_iso()
        company = self.board.replace("-", " ").title()
        jobs: list[Job] = []
        for page in range(1, MAX_PAGES + 1):
            url = f"https://{self.board}.hirehive.com/api/v1/jobs"
            resp = self._session.get(url, params={"page": page}, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            batch = (data.get("jobs") or data.get("data")
                     or (data if isinstance(data, list) else []))
            if not batch:
                break
            jobs.extend(self._to_job(j, company, at) for j in batch)
            if len(batch) == 0:
                break
            # Stop when the API signals the last page, else cap via MAX_PAGES.
            if isinstance(data, dict):
                total_pages = _first(data, "totalPages", "total_pages")
                if total_pages and page >= int(total_pages):
                    break
            else:
                break   # a bare list isn't paginated
        return jobs

    def _to_job(self, d: dict, company: str, at: str) -> Job:
        title = _first(d, "title", "name", "jobTitle") or "(untitled)"
        loc = _first(d, "location", "locationName", "city")
        if isinstance(loc, dict):
            loc = loc.get("name") or loc.get("city")
        url = _first(d, "url", "applicationUrl", "link", "publicUrl")
        company_name = _first(d, "companyName", "company") or company
        if isinstance(company_name, dict):
            company_name = company_name.get("name") or company
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(_first(d, "id", "reference", "slug") or url or title),
            title=title, company=company_name, location=loc,
            description=html_to_text(_first(d, "description", "jobDescription")),
            source_url=url, apply_url=url,
            salary=None,
            employment_type=_first(d, "employmentType", "type", "contractType"),
            category=_first(d, "department", "category"),
            remote=detect_remote(loc),
            posted_at=_first(d, "createdAt", "datePosted", "publishedAt"),
            dedup_key=make_dedup_key(title, company_name, loc),
            first_seen=at, last_checked=at, is_open=True,
        )
