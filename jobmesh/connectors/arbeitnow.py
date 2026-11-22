"""Arbeitnow connector (job board) — Germany / EU.

Reads Arbeitnow's public, keyless "job-board-api":
    https://www.arbeitnow.com/api/job-board-api?page=N

Returns {"data": [...], "links": {...}, "meta": {...}}, paginated (300/page).
robots.txt is fully permissive (``User-agent: * / Disallow:``); only a
tracking query param is disallowed. The board argument is ignored; use "all".
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

API = "https://www.arbeitnow.com/api/job-board-api"
TIMEOUT = 25
MAX_PAGES = 10


def _iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


class ArbeitnowConnector(Connector):
    platform = "arbeitnow"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        if not robots_allowed(API, self._session):
            return []
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            try:
                resp = self._session.get(API, params={"page": page}, timeout=TIMEOUT)
                resp.raise_for_status()
            except requests.RequestException:
                break
            data = resp.json().get("data") or []
            if not data:
                break
            for d in data:
                job = self._to_job(d, at)
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("title") or "(untitled)"
        company = d.get("company_name") or "Unknown"
        location = d.get("location")
        slug = d.get("slug") or d.get("url") or f"{company}:{title}"
        types = d.get("job_types") or []
        remote = bool(d.get("remote"))
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(slug),
            title=title, company=company, location=location,
            description=html_to_text(d.get("description")),
            source_url=d.get("url"), apply_url=d.get("url"),
            salary=None,
            employment_type=types[0] if types else None,
            workplace_type="remote" if remote else None,
            category=None,
            remote=remote or detect_remote(location),
            posted_at=_iso(d.get("created_at")),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
