"""Remotive connector (job board).

Reads the public Remotive API (no key):
    https://remotive.com/api/remote-jobs

Returns {"jobs": [...]} in a single response. Remotive lists remote roles,
so every posting is marked remote. The `board` argument is ignored (a job
board has no per-company board); use "all" in config.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from .base import Connector

API = "https://remotive.com/api/remote-jobs"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25


class RemotiveConnector(Connector):
    platform = "remotive"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        resp = self._session.get(API, timeout=TIMEOUT)
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
        at = now_iso()
        return [self._to_job(j, at) for j in jobs]

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("title") or "(untitled)"
        company = d.get("company_name") or "Unknown"
        location = d.get("candidate_required_location")
        url = d.get("url")
        salary = d.get("salary") or None
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(d.get("id")),
            title=title, company=company, location=location,
            description=html_to_text(d.get("description")),
            source_url=url, apply_url=url,
            salary=salary,
            employment_type=d.get("job_type"),
            workplace_type="remote",
            category=d.get("category"),
            remote=True,
            posted_at=d.get("publication_date"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
