"""CSOD (Cornerstone) connector — token-free, via public job-detail JSON-LD.

A Cornerstone careersite (``{tenant}.csod.com/ux/ats/careersite/...``) is a SPA:
the job list loads from a route that needs a page-minted token, so there is no
token-free way to enumerate jobs from the site itself, and there is no sitemap.
But each job-detail page is server-rendered with a clean schema.org
``JobPosting`` JSON-LD block (what the site publishes for Google for Jobs), and
robots.txt allows it (``Crawl-delay: 10``, no Disallow). Verified 24/11 on
``iata.csod.com``.

So we enumerate the public job-detail URLs from the Common Crawl index (open
web, no token) and read each page's JSON-LD. ``board`` is the tenant slug, e.g.
"iata". robots.txt is honoured on every fetch; JobmeshBot UA; polite pace.
"""

from __future__ import annotations

import re

import requests

from ..models import now_iso
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job
from .. import ccindex

TIMEOUT = 25
MAX_JOBS = 2000
REQUEST_DELAY = 0.4
_REQ_ID = re.compile(r"/requisition/(\d+)", re.IGNORECASE)


class CsodConnector(Connector):
    platform = "csod"

    def __init__(self, board: str, session: requests.Session | None = None,
                 url_source=None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._host = f"{board}.csod.com"
        self._url_source = url_source  # tests inject a list/callable

    def _discover(self) -> list[str]:
        return ccindex.detail_urls(
            self._session, self._host, "/ux/ats/careersite",
            must_contain=["/requisition/"], limit=MAX_JOBS)

    def fetch(self) -> list:
        src = self._url_source
        urls = (src() if callable(src) else src) if src is not None else self._discover()
        at = now_iso()
        jobs = []
        seen: set[str] = set()
        import time
        for url in urls:
            if not robots_allowed(url, self._session):
                continue
            m = _REQ_ID.search(url)
            jid = m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1]
            try:
                page = self._session.get(url, timeout=TIMEOUT)
                page.raise_for_status()
            except requests.RequestException:
                continue
            for posting in parse_jobpostings(page.text):
                job = posting_to_job(posting, self.platform, self.board, at, url)
                if job is None:
                    continue
                job.source_job_id = jid
                job.source_url = url
                job.apply_url = url
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
            if self._url_source is None:
                time.sleep(REQUEST_DELAY)
        return jobs
