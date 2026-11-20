"""Deel connector — public, server-rendered career sites with JSON-LD.

Deel's ATS hosts each customer's job board at ``jobs.deel.com/{org}``. The
listing is a Next.js app, but the server HTML carries links to every job's
detail page (``/{org}/job-details/{uuid}/overview``), and each detail page
embeds a clean schema.org ``JobPosting`` in a ``<script type=
"application/ld+json">`` block. We read the listing, collect the job URLs,
then fetch each and reuse the shared JSON-LD parser.

robots.txt is ``Allow: /`` with only ``/api/`` and ``/*/job-details/*/
application`` disallowed, so the listing and the ``/overview`` detail pages
are permitted; our shared robots guard enforces that. A board is the org
slug (e.g. "zonos"). No key, no CSRF.
"""

from __future__ import annotations

import re

import requests

from ..models import now_iso
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job

BASE = "https://jobs.deel.com"
TIMEOUT = 25
MAX_JOBS = 400


class DeelConnector(Connector):
    platform = "deel"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"{BASE}/{board}"
        self._job_re = re.compile(
            rf"/{re.escape(board)}/job-details/([0-9a-fA-F-]{{36}})", re.IGNORECASE)

    def fetch(self) -> list:  # list[Job]
        if not robots_allowed(self._base, self._session):
            return []
        resp = self._session.get(self._base, timeout=TIMEOUT)
        resp.raise_for_status()
        ids: list[str] = []
        seen_ids: set[str] = set()
        for m in self._job_re.finditer(resp.text):
            jid = m.group(1).lower()
            if jid not in seen_ids:
                seen_ids.add(jid)
                ids.append(jid)
        fetched_at = now_iso()
        jobs = []
        seen: set[str] = set()
        for jid in ids[:MAX_JOBS]:
            url = f"{self._base}/job-details/{jid}/overview"
            if not robots_allowed(url, self._session):
                continue
            try:
                page = self._session.get(url, timeout=TIMEOUT)
                page.raise_for_status()
            except requests.RequestException:
                continue
            for posting in parse_jobpostings(page.text):
                job = posting_to_job(posting, self.platform, self.board, fetched_at, url)
                if job is None:
                    continue
                job.source_job_id = jid
                job.source_url = url
                job.apply_url = url
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
        return jobs
