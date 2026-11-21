"""iCIMS connector — career portals on {portal}.icims.com.

iCIMS renders listings in an iframe, but every posting exposes a full schema.org
JobPosting when fetched with `?in_iframe=1`, and each portal publishes a public
`sitemap.xml` of its job URLs (`/jobs/{id}/{slug}/job`). Like `recooty` and
`isolvedhire`, we read the sitemap and parse per-posting JSON-LD — keyless, no
headless. A `board` is the portal subdomain (e.g. "careers-brightspring").
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

_JOB_URL = re.compile(r"https?://[^<\s\"]+/jobs/(\d+)/[^<\s\"]+/job")
_LDJSON = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def _first_address(job_location) -> dict:
    if isinstance(job_location, list):
        job_location = job_location[0] if job_location else {}
    if isinstance(job_location, dict):
        return job_location.get("address") or {}
    return {}


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


class IcimsConnector(Connector):
    platform = "icims"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{board}.icims.com"

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
        sep = "&" if "?" in url else "?"
        r = self._session.get(f"{url}{sep}in_iframe=1", timeout=TIMEOUT)
        r.raise_for_status()
        data = _job_posting(r.text)
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
