"""HireHive connector (ATS).

Reads the public HireHive jobs API (no key):
    GET https://{board}.hirehive.com/api/v1/jobs   (supports ?page=)

`board` is the company's HireHive subdomain. The exact JSON schema isn't
formally documented and some fields come back as nested objects, so every
text field is flattened defensively before use.
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


def _s(v):
    """Flatten a value to a plain string (or None). HireHive sometimes
    returns objects like {"name": …} or {"text": …} where a string is
    expected, which used to crash the mapping."""
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, dict):
        return (v.get("name") or v.get("text") or v.get("html")
                or v.get("content") or v.get("title") or v.get("label")
                or v.get("value") or None)
    if isinstance(v, (list, tuple)):
        parts = [_s(x) for x in v]
        return ", ".join(p for p in parts if p) or None
    return str(v)


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
            if isinstance(data, dict):
                total_pages = _first(data, "totalPages", "total_pages")
                if total_pages and page >= int(total_pages):
                    break
            else:
                break   # a bare list isn't paginated
        return jobs

    def _to_job(self, d: dict, company: str, at: str) -> Job:
        title = _s(_first(d, "title", "name", "jobTitle")) or "(untitled)"
        loc = _s(_first(d, "location", "locationName", "city"))
        url = _s(_first(d, "url", "applicationUrl", "link", "publicUrl"))
        company_name = _s(_first(d, "companyName", "company")) or company
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(_s(_first(d, "id", "reference", "slug")) or url or title),
            title=title, company=company_name, location=loc,
            description=html_to_text(_s(_first(d, "description", "jobDescription"))),
            source_url=url, apply_url=url,
            salary=None,
            employment_type=_s(_first(d, "employmentType", "type", "contractType")),
            category=_s(_first(d, "department", "category")),
            remote=detect_remote(loc),
            posted_at=_s(_first(d, "createdAt", "datePosted", "publishedAt")),
            dedup_key=make_dedup_key(title, company_name, loc),
            first_seen=at, last_checked=at, is_open=True,
        )
