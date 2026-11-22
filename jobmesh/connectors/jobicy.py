"""Jobicy connector (job board) — worldwide remote jobs.

Reads Jobicy's public, keyless v2 API (cursor-paginated):
    https://jobicy.com/api/v2/remote-jobs?count=50&cursor=...

robots.txt permits it for a citing crawler (``Content-Signal: search=yes``;
only query-param and private paths, plus some named SEO bots, are blocked —
the /api/ path is allowed). Jobicy's own notice asks only that it be credited
with a direct link to the source job URL, which we preserve as source_url /
apply_url. The board argument is ignored; use "all".
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

API = "https://jobicy.com/api/v2/remote-jobs"
TIMEOUT = 25
PAGE_SIZE = 50
MAX_PAGES = 6


class JobicyConnector(Connector):
    platform = "jobicy"

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
        cursor = None
        for _ in range(MAX_PAGES):
            params = {"count": PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = self._session.get(API, params=params, timeout=TIMEOUT)
                resp.raise_for_status()
            except requests.RequestException:
                break
            body = resp.json()
            rows = body.get("jobs") or []
            if not rows:
                break
            for d in rows:
                job = self._to_job(d, at)
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
            if not body.get("hasMore") or not body.get("nextCursor"):
                break
            cursor = body["nextCursor"]
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("jobTitle") or "(untitled)"
        company = d.get("companyName") or "Unknown"
        location = d.get("jobGeo") or "Anywhere"
        types = d.get("jobType") or []
        industry = d.get("jobIndustry") or []
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(d.get("id")),
            title=title, company=company, location=location,
            description=html_to_text(d.get("jobExcerpt") or d.get("jobDescription")),
            source_url=d.get("url"), apply_url=d.get("url"),
            salary=None,
            employment_type=types[0] if types else None,
            workplace_type="remote",
            category=industry[0] if industry else None,
            remote=True,
            posted_at=d.get("pubDate"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
