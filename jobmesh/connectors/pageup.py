"""PageUp connector — public, server-rendered career sites with JSON-LD.

PageUp hosts each customer's career site at ``{tenant}.pageuppeople.com``
(some run on custom domains). The listing page server-renders a link to
every job (``/jobs/{slug}``), and each job page embeds a clean schema.org
``JobPosting`` in a ``<script type="application/ld+json">`` block. We read
the listing, collect the job URLs, then fetch each and reuse the shared
JSON-LD parser.

robots.txt allows ``/jobs/{slug}`` detail pages (only ``/api/``, ``/me/``
and ``/jobs/search?query=`` are disallowed), so our shared robots guard
permits the crawl. A board is the tenant subdomain prefix (e.g.
"pupcareers"). No key, no CSRF.
"""

from __future__ import annotations

import re

import requests

from ..models import now_iso
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job

TIMEOUT = 25
MAX_JOBS = 400
# job detail slugs; skip the listing/filter/search utility paths
_JOB_RE = re.compile(r'href="(/jobs/(?!search|filter|favourite)[a-z0-9][a-z0-9-]{4,})"', re.IGNORECASE)


class PageUpConnector(Connector):
    platform = "pageup"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{board}.pageuppeople.com"

    def fetch(self) -> list:
        if not robots_allowed(f"{self._base}/", self._session):
            return []
        resp = self._session.get(f"{self._base}/", timeout=TIMEOUT)
        resp.raise_for_status()
        paths: list[str] = []
        seen_paths: set[str] = set()
        for m in _JOB_RE.finditer(resp.text):
            path = m.group(1)
            if path not in seen_paths:
                seen_paths.add(path)
                paths.append(path)
        fetched_at = now_iso()
        jobs = []
        seen: set[str] = set()
        for path in paths[:MAX_JOBS]:
            url = f"{self._base}{path}"
            if not robots_allowed(url, self._session):
                continue
            try:
                page = self._session.get(url, timeout=TIMEOUT)
                page.raise_for_status()
            except requests.RequestException:
                continue
            slug = path.rsplit("/", 1)[-1]
            for posting in parse_jobpostings(page.text):
                job = posting_to_job(posting, self.platform, self.board, fetched_at, url)
                if job is None:
                    continue
                job.source_job_id = slug
                job.source_url = url
                job.apply_url = url
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
        return jobs
