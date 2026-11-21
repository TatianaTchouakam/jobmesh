"""Homerun connector — career sites on the Homerun ATS ({company}.homerun.co).

Homerun is an SMB ATS (mostly NL/EU). Each board publishes a public `sitemap.xml`
listing job URLs (`/{slug}`), and every posting page carries a schema.org
JobPosting block. Boards are reachable at `{company}.homerun.co` or on a custom
domain the subdomain redirects to (requests follows the redirect). Like `phenom`
and `jobiqo`, we read the sitemap and parse per-posting JSON-LD — keyless, no
headless. A `board` is the site host (e.g. "vacatures.vpro.nl" or
"opensocial.homerun.co").
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
_LDJSON = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


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


class HomerunConnector(Connector):
    platform = "homerun"

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
        sitemap = f"{self._base}/sitemap.xml"
        if not robots_allowed(sitemap, self._session):
            return []
        locs = _LOC.findall(self._get(sitemap))
        # Job pages are the slug URLs; skip the bare host and /apply pages.
        bare = {self._base, self._base + "/"}
        job_urls: list[str] = []
        seen: set[str] = set()
        for u in locs:
            if u in bare or "/apply" in u:
                continue
            if u not in seen:
                seen.add(u)
                job_urls.append(u)
        at = now_iso()
        jobs: list[Job] = []
        done: set[str] = set()
        for url in job_urls[:MAX_JOBS]:
            job = self._fetch_job(url, at)
            if job is not None and job.source_job_id not in done:
                done.add(job.source_job_id)
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
        jid = str((data.get("identifier") or {}).get("value") or url)
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=jid,
            title=data.get("title") or "(untitled)",
            company=(org.get("name") or self.board).strip() or self.board,
            location=location,
            description=html_to_text(data.get("description")),
            source_url=url,
            apply_url=url.rstrip("/") + "/apply",
            employment_type=emp,
            posted_at=data.get("datePosted"),
        )
