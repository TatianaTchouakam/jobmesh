"""Recooty connector — platform-wide sitemap + schema.org JSON-LD.

Recooty (jobs.recooty.com) hosts many employers' career pages on one
domain. Its single public sitemap lists every live job across the whole
platform, and each job page carries a schema.org JobPosting JSON-LD
block. One connector therefore covers all Recooty tenants with no
per-tenant discovery.

    GET https://jobs.recooty.com/sitemap.xml      -> every job URL
    GET https://jobs.recooty.com/{tenant}/{slug}  -> JobPosting JSON-LD

Board token is "all" (the platform root). Tunables:
    RECOOTY_MAX_JOBS  (default 2000)   RECOOTY_WORKERS (default 8)
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests

from ..models import Job, now_iso
from .base import Connector
from ..robots import allowed as robots_allowed, UA_TOKEN, USER_AGENT
from .careersite import parse_jobpostings, posting_to_job
from .smartjobboard import _locs

ROOT = "https://jobs.recooty.com"
USER_AGENT = "JobmeshBot/0.1 (+https://github.com/TatianaTchouakam/jobmesh)"
TIMEOUT = 25
MAX_JOBS = int(os.environ.get("RECOOTY_MAX_JOBS", "2000"))
WORKERS = int(os.environ.get("RECOOTY_WORKERS", "8"))


def _is_job_url(url: str) -> bool:
    """Recooty job pages are {ROOT}/{tenant}/{job-slug} (two path parts)."""
    if not url.startswith(ROOT):
        return False
    parts = [p for p in urlparse(url).path.split("/") if p]
    return len(parts) == 2 and not url.endswith(".xml")


class RecootyConnector(Connector):
    platform = "recooty"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def _job_urls(self) -> list[str]:
        resp = self._session.get(f"{ROOT}/sitemap.xml", timeout=TIMEOUT)
        resp.raise_for_status()
        locs = _locs(resp.content)
        # follow sub-sitemaps if this was an index
        if not any(_is_job_url(u) for u in locs):
            subs = [u for u in locs if u.endswith(".xml")]
            locs = []
            for sub in subs[:25]:
                try:
                    r = self._session.get(sub, timeout=TIMEOUT)
                    r.raise_for_status()
                    locs.extend(_locs(r.content))
                except requests.RequestException:
                    continue
        seen, out = set(), []
        for u in locs:
            if _is_job_url(u) and u not in seen:
                seen.add(u)
                out.append(u)
        return out[:MAX_JOBS]

    def _fetch_page(self, url: str, fetched_at: str) -> list[Job]:
        if not robots_allowed(url, self._session):
            return []
        try:
            r = self._session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
        except requests.RequestException:
            return []
        out = []
        for p in parse_jobpostings(r.text):
            job = posting_to_job(p, self.platform, self.board, fetched_at, url)
            if job is not None:
                out.append(job)
        return out

    def fetch(self) -> list[Job]:
        urls = self._job_urls()
        fetched_at = now_iso()
        jobs, seen = [], set()
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
