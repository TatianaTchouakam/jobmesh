"""Rippling connector (ATS).

Reads the public, keyless Rippling job-board API:
    GET https://api.rippling.com/platform/api/ats/v1/board/{board}/jobs

`board` is the slug Rippling assigned the customer (usually the company
name in lowercase). The response is a flat JSON array of postings; a role
open in several locations appears once per location with the same `uuid`,
so we key on `uuid` (duplicates across locations collapse to one row).
Listing-level only — description, salary and date live on the posting
page.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25


class RipplingConnector(Connector):
    platform = "rippling"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        url = f"https://api.rippling.com/platform/api/ats/v1/board/{self.board}/jobs"
        resp = self._session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        rows = data if isinstance(data, list) else (data.get("jobs") or [])
        company = self.board.replace("-", " ").title()
        at = now_iso()
        return [self._to_job(d, company, at) for d in rows]

    def _to_job(self, d: dict, company: str, at: str) -> Job:
        title = d.get("name") or d.get("title") or "(untitled)"
        loc = d.get("workLocation") or d.get("location")
        if isinstance(loc, dict):
            parts = [loc.get("city"), loc.get("state"), loc.get("country")]
            location = ", ".join(p for p in parts if p) or loc.get("label")
        else:
            location = loc
        url = d.get("url")
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(d.get("uuid") or d.get("id") or url or title),
            title=title, company=company, location=location,
            description=None,
            source_url=url, apply_url=url,
            salary=None,
            employment_type=d.get("employmentType"),
            category=d.get("department"),
            remote=detect_remote(location),
            posted_at=None,
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
