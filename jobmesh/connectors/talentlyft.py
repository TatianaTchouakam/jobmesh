"""TalentLyft connector — public career sites (sitemap + per-posting JSON-LD).

TalentLyft career sites ({board}.talentlyft.com) render the listing client-side,
but each posting page is server-rendered with a schema.org JobPosting block and
the site publishes a public `sitemap.xml` of `/jobs/{slug}` URLs. Like `nodex`
and `jobiqo`, we read the sitemap and parse per-posting JSON-LD — keyless.

robots.txt allows `/` and `/jobs/*` (only /JobList, /JobsSimple, /js are
disallowed, which we never use). Generic "talent pool / general application"
entries are skipped. A `board` is the full host, e.g.
"riverwalkertalentcareers.talentlyft.com".
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
MAX_JOBS = 300

_LOC = re.compile(r"<loc>([^<]+)</loc>")
_LDJSON = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
_SKIP = re.compile(r"(talent-pool|general-application|spontaneous)", re.IGNORECASE)
_SLUG = re.compile(r"/jobs/([a-z0-9-]+)/?$", re.IGNORECASE)


def _job_posting(html_text: str) -> dict | None:
    for block in _LDJSON.findall(html_text):
        try:
            obj = json.loads(block.strip())
        except (ValueError, TypeError):
            continue
        for it in (obj if isinstance(obj, list) else [obj]):
            if isinstance(it, dict) and it.get("@type") == "JobPosting":
                return it
    return None


def _first_address(job_location) -> dict:
    if isinstance(job_location, list):
        job_location = job_location[0] if job_location else {}
    if isinstance(job_location, dict):
        return job_location.get("address") or {}
    return {}


class TalentLyftConnector(Connector):
    platform = "talentlyft"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{board}"

    def _get(self, url: str) -> str:
        r = self._session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.text

    def fetch(self) -> list[Job]:
        if not robots_allowed(f"{self._base}/sitemap.xml", self._session):
            return []
        locs = _LOC.findall(self._get(f"{self._base}/sitemap.xml"))
        urls, seen = [], set()
        for u in locs:
            if "/jobs/" in u and not _SKIP.search(u) and u not in seen:
                seen.add(u)
                urls.append(u)
        at = now_iso()
        jobs: list[Job] = []
        for url in urls[:MAX_JOBS]:
            try:
                job = self._fetch_job(url, at)
            except requests.RequestException:
                continue
            if job is not None:
                jobs.append(job)
        return jobs

    def _fetch_job(self, url: str, at: str) -> Job | None:
        data = _job_posting(self._get(url))
        if not data:
            return None
        org = data.get("hiringOrganization") or {}
        addr = _first_address(data.get("jobLocation"))
        location = ", ".join(
            p for p in (addr.get("addressLocality"), addr.get("addressRegion"),
                        addr.get("addressCountry")) if p) or None
        emp = data.get("employmentType")
        if isinstance(emp, list):
            emp = emp[0] if emp else None
        m = _SLUG.search(url)
        jid = str((data.get("identifier") or {}).get("value") or (m.group(1) if m else url))
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=jid,
            title=data.get("title") or "(untitled)",
            company=(org.get("name") or self.board).strip() or self.board,
            location=location,
            description=html_to_text(data.get("description")),
            source_url=url,
            apply_url=data.get("url") or url,
            employment_type=emp,
            posted_at=data.get("datePosted"),
        )
