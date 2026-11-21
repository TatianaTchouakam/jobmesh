"""Exenzo connector — job boards built on jobboardsoftware.com / exenzo.com.

Exenzo powers white-label job boards (mostly NL/EU). Each board exposes a
public, keyless JSON API:

    GET https://{tenant}.api.exenzo.com/api/public/v1/job-boards/1/jobs?page=N

The response is {"total", "data":[...], "currentPage", "lastPage"}; each job
carries title, organisation_name, city/country, apply_url, job_url, dates and
salary. A `board` is the tenant subdomain (e.g. "bb", "greenjobs", "overheid").
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
MAX_PAGES = 10


class ExenzoConnector(Connector):
    platform = "exenzo"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._api = f"https://{board}.api.exenzo.com/api/public/v1/job-boards/1/jobs"

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._api, self._session):
            return []
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        page = 1
        last = 1
        while page <= min(last, MAX_PAGES):
            resp = self._session.get(self._api, params={"page": page}, timeout=TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(data, list) or not data:
                break
            if isinstance(payload, dict):
                try:
                    last = int(payload.get("lastPage") or 1)
                except (TypeError, ValueError):
                    last = page
            for d in data:
                job = self._to_job(d, at)
                if job and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    jobs.append(job)
            page += 1
        return jobs

    def _to_job(self, d: dict, at: str) -> Job | None:
        jid = d.get("uuid") or d.get("id")
        if jid is None:
            return None
        loc_parts = [d.get("city") or d.get("location_name"), d.get("country_code")]
        location = ", ".join(p for p in loc_parts if p) or None
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(jid),
            title=d.get("title") or "(untitled)",
            company=(d.get("organisation_name") or "").strip() or "Unknown",
            location=location,
            description=html_to_text(d.get("description")),
            source_url=d.get("job_url") or d.get("apply_url"),
            apply_url=d.get("apply_url") or d.get("job_url"),
            remote=bool(d.get("remote")),
            posted_at=d.get("created_at"),
        )
