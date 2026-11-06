"""BambooHR connector (ATS).

Reads the public BambooHR careers list (no key):
    https://{subdomain}.bamboohr.com/careers/list

Returns {"result": [...]}. The list has the core fields; full descriptions
live on a per-job detail page, so this indexes the list (title, company,
department, location, type, link) — description is enriched later.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25


class BambooHrConnector(Connector):
    platform = "bamboohr"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        url = f"https://{self.board}.bamboohr.com/careers/list"
        resp = self._session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        result = resp.json().get("result", [])
        company = self.board.replace("-", " ").title()
        at = now_iso()
        return [self._to_job(d, company, at) for d in result]

    def _to_job(self, d: dict, company: str, at: str) -> Job:
        title = d.get("jobOpeningName") or d.get("title") or "(untitled)"
        location = self._location(d)
        remote_raw = str(d.get("isRemote") or "").lower()
        remote = remote_raw in ("yes", "1", "true") or detect_remote(location)
        job_id = str(d.get("id"))
        url = f"https://{self.board}.bamboohr.com/careers/{job_id}"
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=job_id,
            title=title, company=company, location=location,
            description=None,  # enrich via the per-job detail page later
            source_url=url, apply_url=url,
            salary=None,
            employment_type=d.get("employmentStatusLabel"),
            workplace_type=("remote" if remote else None),
            category=d.get("departmentLabel"),
            remote=remote,
            posted_at=d.get("datePosted") or d.get("postedDate"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )

    @staticmethod
    def _location(d: dict) -> str | None:
        loc = d.get("location")
        if isinstance(loc, dict):
            parts = [loc.get("city"), loc.get("state"), loc.get("country")]
            return ", ".join(p for p in parts if p) or None
        if isinstance(loc, str):
            return loc or None
        parts = [d.get("locationCity"), d.get("locationState"), d.get("locationCountry")]
        return ", ".join(p for p in parts if p) or None
