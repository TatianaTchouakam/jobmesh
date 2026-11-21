"""Factorial connector — career sites on the Factorial ATS.

Factorial career sites publish a public `sitemap.xml` of job URLs
(`/job_posting/{slug}-{id}`), and every posting page carries a schema.org
JobPosting block. robots.txt allows `/`. Like `phenom`/`jobiqo`, we read the
sitemap and parse per-posting JSON-LD — keyless, no headless. A `board` is the
career-site host (e.g. "careers.factorial.com").
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
MAX_JOBS = 400

_LOC = re.compile(r"<loc>([^<]+)</loc>")
_LDJSON = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
_JOB_ID = re.compile(r"-(\d+)/?$")


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


class FactorialConnector(Connector):
    platform = "factorial"

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
        seen: set[str] = set()
        urls: list[str] = []
        for u in locs:
            if "/job_posting/" in u and u not in seen:
                seen.add(u)
                urls.append(u)
        at = now_iso()
        jobs: list[Job] = []
        done: set[str] = set()
        for url in urls[:MAX_JOBS]:
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
        m = _JOB_ID.search(url)
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
