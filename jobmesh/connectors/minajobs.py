"""MinaJobs connector — Cameroon job board (SimpleJobScript engine).

MinaJobs (cm.minajobs.net) is the largest general job board in Cameroon.
Every opening is server-rendered at ``/emplois/{slug}-{id}`` and carries a
clean schema.org ``JobPosting`` JSON-LD block (title, description,
datePosted, validThrough, employmentType, hiringOrganization, and a full
PostalAddress with addressLocality / addressRegion / addressCountry=CM).

We paginate the public listing ``/emplois?page=N`` to collect job URLs,
then fetch each detail page and reuse the shared JSON-LD parser. No key,
no cookie, no CSRF.

robots.txt (User-agent: *) disallows only /_lib, /_tpl, /_tools, /_config,
/js, /uploads and /admin — the /emplois listing and detail pages are
permitted. A board is the host (default "cm.minajobs.net").
"""

from __future__ import annotations

import re

import requests

from ..models import now_iso
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job

TIMEOUT = 25
MAX_PAGES = 70
MAX_JOBS = 700
DEFAULT_HOST = "cm.minajobs.net"

# /emplois/{slug}-{numericId} — detail links; the trailing number is the id.
_JOB_RE = re.compile(r"/emplois/([a-z0-9][a-z0-9\-]*?-(\d+))(?![\w-])", re.IGNORECASE)


class MinaJobsConnector(Connector):
    platform = "minajobs"

    def __init__(self, board: str | None = None,
                 session: requests.Session | None = None):
        super().__init__(board or DEFAULT_HOST)
        self._host = self.board or DEFAULT_HOST
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault(
            "Accept",
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        self._session.headers.setdefault("Accept-Language", "fr-FR,fr;q=0.9,en;q=0.8")
        # Force a decoder we can always read: urllib3 otherwise advertises "br",
        # and a missing/mismatched brotli lib silently truncates the HTML to the
        # first job card (we saw exactly 1 result). gzip/deflate are built in.
        self._session.headers["Accept-Encoding"] = "gzip, deflate"
        self._base = f"https://{self._host}"

    def _collect_urls(self) -> list[str]:
        paths: list[str] = []
        seen_ids: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            url = f"{self._base}/emplois?page={page}"
            if not robots_allowed(url, self._session):
                break
            try:
                resp = self._session.get(url, timeout=TIMEOUT)
                resp.raise_for_status()
            except requests.RequestException:
                break
            new = 0
            for m in _JOB_RE.finditer(resp.text):
                path, jid = m.group(1), m.group(2)
                if jid in seen_ids:
                    continue
                seen_ids.add(jid)
                paths.append(path)
                new += 1
            if new == 0:
                break
            if len(paths) >= MAX_JOBS:
                break
        return paths[:MAX_JOBS]

    def fetch(self) -> list:
        listing = f"{self._base}/emplois"
        if not robots_allowed(listing, self._session):
            return []
        at = now_iso()
        jobs = []
        seen: set[str] = set()
        for path in self._collect_urls():
            url = f"{self._base}/emplois/{path}"
            # MinaJobs' JSON-LD identifier is a PropertyValue whose *name* is the
            # constant "MinaJobs" (the real id is in .value), so the shared parser
            # would give every posting the same id and collapse them. The stable
            # per-job id is the trailing number in the URL slug.
            mid = re.search(r"-(\d+)$", path)
            job_id = mid.group(1) if mid else path
            if not robots_allowed(url, self._session):
                continue
            try:
                page = self._session.get(url, timeout=TIMEOUT)
                page.raise_for_status()
            except requests.RequestException:
                continue
            for posting in parse_jobpostings(page.text):
                job = posting_to_job(posting, self.platform, self._host, at, url)
                if job is None:
                    continue
                job.source_job_id = job_id
                job.source_url = url
                job.apply_url = url
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
        return jobs
