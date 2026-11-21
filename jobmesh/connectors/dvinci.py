"""d.vinci connector — public job-publication feed (German ATS).

d.vinci career sites expose a keyless, public JSON feed their own front end
reads:

    GET https://{tenant}.dvinci-hr.com/jobPublication/list.json
    -> [ { "id", "position", "jobPublicationURL", "jobOpening": {...} }, ... ]

The same path works on *.dvinci-easy.com and on clients' own domains. robots.txt
allows `/`. A `board` is the tenant slug (e.g. "cadenas") or a full host
(e.g. "jobs.example.de").
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30


class DvinciConnector(Connector):
    platform = "dvinci"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._base = f"https://{board}" if "." in board else f"https://{board}.dvinci-hr.com"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._url = f"{self._base}/jobPublication/list.json"

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        resp = self._session.get(self._url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        rows = data if isinstance(data, list) else (data.get("jobPublications") or [])
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for pub in rows:
            job = self._to_job(pub, at)
            if job is not None and job.source_job_id not in seen:
                seen.add(job.source_job_id)
                jobs.append(job)
        return jobs

    def _to_job(self, pub: dict, at: str) -> Job | None:
        pid = pub.get("id")
        if pid is None:
            return None
        jo = pub.get("jobOpening") or {}
        company = ((jo.get("company") or {}).get("name") or "").strip() or self.board
        location = jo.get("location")
        if not location:
            locs = jo.get("locations") or []
            if locs:
                addr = locs[0].get("address") or {}
                location = ", ".join(
                    p for p in (addr.get("city"),
                                (addr.get("country") or {}).get("isoA2")) if p) or None
        wt = jo.get("workingTimes") or []
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(pid),
            title=pub.get("position") or "(untitled)",
            company=company,
            location=location,
            description=html_to_text(pub.get("pageDescription") or pub.get("introduction")),
            source_url=pub.get("jobPublicationURL"),
            apply_url=pub.get("applicationFormURL") or pub.get("jobPublicationURL"),
            employment_type=(wt[0].get("name") if wt else None),
            category=jo.get("department"),
            salary=jo.get("salaryRange"),
            posted_at=pub.get("startDate") or jo.get("createdDate"),
        )
