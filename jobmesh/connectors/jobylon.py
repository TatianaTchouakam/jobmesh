"""Jobylon connector — platform-wide sitemap + schema.org JSON-LD.

Jobylon (emp.jobylon.com) hosts many employers' vacancies on one domain.
Its sitemap index fans out to sub-sitemaps listing every live job across
the whole platform, and each job page carries a schema.org JobPosting
JSON-LD block. One connector covers all tenants, no per-tenant discovery.

    GET https://emp.jobylon.com/sitemap.xml   (index -> sub-sitemaps)
    GET https://emp.jobylon.com/jobs/{id}-{slug}/   -> JobPosting JSON-LD

Board token is "all". Tunables:
    JOBYLON_MAX_JOBS (default 2500)   JOBYLON_WORKERS (default 8)
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import requests

from ..models import Job, now_iso
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job
from .smartjobboard import _locs

ROOT = "https://emp.jobylon.com"
USER_AGENT = "JobmeshBot/0.1 (+https://github.com/TatianaTchouakam/jobmesh)"
TIMEOUT = 25
MAX_JOBS = int(os.environ.get("JOBYLON_MAX_JOBS", "2500"))
WORKERS = int(os.environ.get("JOBYLON_WORKERS", "8"))
MAX_SUBSITEMAPS = 60


def _is_job_url(url: str) -> bool:
    return url.startswith(ROOT) and "/jobs/" in url and not url.endswith(".xml")


class JobylonConnector(Connector):
    platform = "jobylon"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def _job_urls(self) -> list[str]:
        resp = self._session.get(f"{ROOT}/sitemap.xml", timeout=TIMEOUT)
        resp.raise_for_status()
        locs = _locs(resp.content)
        job_urls = [u for u in locs if _is_job_url(u)]
        if not job_urls:  # sitemap index -> follow sub-sitemaps
            subs = [u for u in locs if u.endswith(".xml")]
            for sub in subs[:MAX_SUBSITEMAPS]:
                try:
                    r = self._session.get(sub, timeout=TIMEOUT)
                    r.raise_for_status()
                    job_urls.extend(u for u in _locs(r.content) if _is_job_url(u))
                except requests.RequestException:
                    continue
                if len(job_urls) >= MAX_JOBS:
                    break
        seen, out = set(), []
        for u in job_urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out[:MAX_JOBS]

    def _fetch_page(self, url: str, fetched_at: str) -> list[Job]:
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
