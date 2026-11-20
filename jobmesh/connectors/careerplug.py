"""CareerPlug connector — public, server-rendered JSON-LD careers pages.

CareerPlug hosts each customer's careers site at
``{tenant}.careerplug.com``. The ``/jobs`` listing page is server-rendered
and embeds a complete schema.org ``ItemList`` of ``JobPosting`` objects in
a ``<script type="application/ld+json">`` block — one request returns every
open job with full description, employment type, salary and remote flag.

We reuse the shared JSON-LD parser (``careersite.parse_jobpostings`` already
recurses into ``itemListElement``/``item``) and only override the platform
name and the per-job URL, which CareerPlug keys by a numeric job id in the
posting's ``identifier``. A board is the tenant slug (e.g. "cplugjobs").

robots.txt on the careers host allows ``/jobs`` (only ``/apps/`` and admin
paths are disallowed), and we crawl ``/jobs`` only; the stored apply URL is
a link we never fetch. Every request passes the shared robots guard with an
honest User-Agent.
"""

from __future__ import annotations

import requests

from ..models import now_iso
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job

TIMEOUT = 25
MAX_PAGES = 25


class CareerPlugConnector(Connector):
    platform = "careerplug"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{board}.careerplug.com"

    def fetch(self) -> list[Job]:  # noqa: F821  (Job via posting_to_job)
        listing = f"{self._base}/jobs"
        if not robots_allowed(listing, self._session):
            return []
        fetched_at = now_iso()
        jobs = []
        seen: set[str] = set()
        page = 1
        while page <= MAX_PAGES:
            url = listing if page == 1 else f"{listing}?page={page}"
            resp = self._session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            postings = parse_jobpostings(resp.text)
            new_on_page = 0
            for p in postings:
                job = posting_to_job(p, self.platform, self.board, fetched_at, listing)
                if job is None:
                    continue
                jid = self._job_id(p)
                if jid:
                    job.source_job_id = jid
                    job.source_url = f"{self._base}/jobs/{jid}"
                    job.apply_url = f"{self._base}/jobs/{jid}/apps/new"
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
                new_on_page += 1
            # stop when a page adds nothing (no pagination, or past the last page)
            if new_on_page == 0:
                break
            page += 1
        return jobs

    @staticmethod
    def _job_id(posting: dict) -> str | None:
        ident = posting.get("identifier")
        if isinstance(ident, dict):
            v = ident.get("value")
            return str(v) if v not in (None, "") else None
        if isinstance(ident, (str, int)):
            return str(ident)
        return None
