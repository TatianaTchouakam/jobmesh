"""SmartJobBoard connector (sitemap -> job pages -> JSON-LD).

SmartJobBoard's public /rss feed is capped at 50 postings, but every
board publishes a full sitemap of its job pages, and each job page
carries a schema.org JobPosting JSON-LD block. This connector reads the
sitemap, then pulls JobPosting data from each job page -- unlocking the
whole board instead of the first 50.

A board is the site's base URL, e.g. "https://academiccareers.com".

Tunables (environment variables):
    SMARTJOBBOARD_MAX_JOBS   max job pages per board   (default 400)
    SMARTJOBBOARD_WORKERS    parallel page fetches     (default 8)
"""

from __future__ import annotations

import gzip
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests

from ..models import Job, now_iso
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job

USER_AGENT = (
    "Mozilla/5.0 (compatible; jobmesh/0.1; +https://github.com/; job index)"
)
TIMEOUT = 25
MAX_JOBS = int(os.environ.get("SMARTJOBBOARD_MAX_JOBS", "400"))
WORKERS = int(os.environ.get("SMARTJOBBOARD_WORKERS", "8"))
MAX_SUBSITEMAPS = 25


def _locs(content: bytes) -> list[str]:
    """Return every <loc> text in a sitemap (handles gzip)."""
    if content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except OSError:
            return []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    out = []
    for el in root.iter():
        tag = el.tag.split("}", 1)[-1].lower()
        if tag == "loc" and el.text:
            out.append(el.text.strip())
    return out


class SmartJobBoardConnector(Connector):
    platform = "smartjobboard"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board.rstrip("/"))
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def _job_urls(self) -> list[str]:
        resp = self._session.get(f"{self.board}/sitemap.xml", timeout=TIMEOUT)
        resp.raise_for_status()
        locs = _locs(resp.content)
        job_urls = [u for u in locs if "/job/" in u]
        # follow sub-sitemaps if the root was an index with no direct job urls
        if not job_urls:
            subs = [u for u in locs if u.endswith(".xml") or "sitemap" in u.lower()]
            for sub in subs[:MAX_SUBSITEMAPS]:
                try:
                    r = self._session.get(sub, timeout=TIMEOUT)
                    r.raise_for_status()
                    job_urls.extend(u for u in _locs(r.content) if "/job/" in u)
                except requests.RequestException:
                    continue
                if len(job_urls) >= MAX_JOBS:
                    break
        # de-duplicate, then crawl newest first: SmartJobBoard sitemaps list
        # jobs oldest-first by numeric id, and old ids are mostly closed roles.
        seen, ordered = set(), []
        for u in job_urls:
            if u not in seen:
                seen.add(u)
                ordered.append(u)

        def _job_id(u: str) -> int:
            m = re.search(r"/job/(\d+)", u)
            return int(m.group(1)) if m else -1

        ordered.sort(key=_job_id, reverse=True)
        return ordered[:MAX_JOBS]

    def _fetch_page(self, url: str, fetched_at: str) -> list[Job]:
        try:
            r = self._session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
        except requests.RequestException:
            return []
        jobs = []
        for p in parse_jobpostings(r.text):
            job = posting_to_job(p, self.platform, self.board, fetched_at, url)
            if job is not None:
                jobs.append(job)
        return jobs

    def fetch(self) -> list[Job]:
        urls = self._job_urls()
        fetched_at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        if not urls:
            return jobs
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for page_jobs in pool.map(lambda u: self._fetch_page(u, fetched_at), urls):
                for job in page_jobs:
                    if job.source_job_id in seen:
                        continue
                    seen.add(job.source_job_id)
                    jobs.append(job)
        return jobs
