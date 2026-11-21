"""iSolvedHire connector — career sites on {tenant}.isolvedhire.com.

iSolvedHire (isolved Talent Acquisition, the ApplicantPro engine) renders its
job list as a Vue SPA, but every individual posting is server-rendered at
`/jobs/{id}.html` with a clean schema.org JobPosting block, and the board
exposes a public `sitemap.xml` listing those pages. So, like the `recooty`
connector, we read the sitemap and parse JSON-LD per posting — no headless, no
token. A `board` is the tenant subdomain (e.g. "isolved").
"""

from __future__ import annotations

import json
import re

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
MAX_JOBS = 300  # safety cap on postings fetched per board

_JOB_URL = re.compile(r"https?://[^<\s]+/jobs/(\d+)\.html")
_LDJSON = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def _first_address(job_location) -> dict:
    if isinstance(job_location, list):
        job_location = job_location[0] if job_location else {}
    if isinstance(job_location, dict):
        return job_location.get("address") or {}
    return {}


class IsolvedHireConnector(Connector):
    platform = "isolvedhire"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{board}.isolvedhire.com"

    def fetch(self) -> list[Job]:
        sitemap = f"{self._base}/sitemap.xml"
        if not robots_allowed(sitemap, self._session):
            return []
        resp = self._session.get(sitemap, timeout=TIMEOUT)
        resp.raise_for_status()
        seen: set[str] = set()
        urls: list[tuple[str, str]] = []
        for m in _JOB_URL.finditer(resp.text):
            jid = m.group(1)
            if jid not in seen:
                seen.add(jid)
                urls.append((jid, m.group(0)))
        at = now_iso()
        jobs: list[Job] = []
        for jid, url in urls[:MAX_JOBS]:
            job = self._fetch_job(jid, url, at)
            if job is not None:
                jobs.append(job)
        return jobs

    def _fetch_job(self, jid: str, url: str, at: str) -> Job | None:
        r = self._session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = self._job_posting(r.text)
        if not data:
            return None
        org = data.get("hiringOrganization") or {}
        loc = _first_address(data.get("jobLocation"))
        location = ", ".join(
            p for p in (loc.get("addressLocality"), loc.get("addressRegion"),
                        loc.get("addressCountry")) if p) or None
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str((data.get("identifier") or {}).get("sameAs") or jid),
            title=data.get("title") or "(untitled)",
            company=(org.get("name") or self.board).strip() or self.board,
            location=location,
            description=html_to_text(data.get("description")),
            source_url=data.get("url") or url,
            apply_url=data.get("url") or url,
            employment_type=data.get("employmentType"),
            posted_at=data.get("datePosted"),
        )

    @staticmethod
    def _job_posting(html_text: str) -> dict | None:
        for block in _LDJSON.findall(html_text):
            try:
                obj = json.loads(block.strip())
            except (ValueError, TypeError):
                continue
            items = obj if isinstance(obj, list) else [obj]
            for it in items:
                if isinstance(it, dict) and it.get("@type") == "JobPosting":
                    return it
        return None
