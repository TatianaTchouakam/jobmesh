"""JobScore connector — official per-company JSON job feed.

JobScore career sites (careers.jobscore.com/careers/{slug}) declare an official
JSON feed in the page <head>:

    GET https://careers.jobscore.com/jobs/{slug}/feed.json
    -> {"company_name": ..., "jobs": [ ... ]}

(.xml and .atom variants exist too.) A `board` is the company slug (e.g.
"solutions2go"). robots.txt allows it (only /apply_flow/ is disallowed), so this
reads an official, unauthenticated feed — no scraping.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

HOST = "https://careers.jobscore.com"
TIMEOUT = 30


class JobScoreConnector(Connector):
    platform = "jobscore"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._url = f"{HOST}/jobs/{board}/feed.json"

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        resp = self._session.get(self._url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("jobs") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        default_company = (
            (data.get("company_name") if isinstance(data, dict) else None)
            or self.board)
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for j in rows:
            job = self._to_job(j, default_company, at)
            if job is not None and job.source_job_id not in seen:
                seen.add(job.source_job_id)
                jobs.append(job)
        return jobs

    def _to_job(self, j: dict, default_company: str, at: str) -> Job | None:
        jid = j.get("id") or j.get("atom_id")
        if not jid:
            return None
        location = j.get("location") or ", ".join(
            p for p in (j.get("city"), j.get("state"), j.get("country")) if p
        ) or None
        remote = j.get("remote")
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(jid),
            title=j.get("title") or "(untitled)",
            company=j.get("company_name") or default_company,
            location=location,
            description=html_to_text(j.get("description")),
            source_url=j.get("detail_url") or j.get("share_url"),
            apply_url=j.get("apply_url") or j.get("detail_url"),
            employment_type=j.get("job_type"),
            category=j.get("department"),
            level=j.get("experience_level"),
            remote=bool(remote) if remote is not None else None,
            posted_at=j.get("opened_date") or j.get("created_on"),
        )
