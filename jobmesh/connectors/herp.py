"""HERP connector — Japanese SMB/startup ATS with schema.org JSON-LD.

HERP hosts each customer at ``herp.careers/v1/{company}``. The list page
server-renders a link to every opening (``/v1/{company}/{shortId}``), and
each job page embeds one clean schema.org ``JobPosting`` in a
``<script type="application/ld+json">`` block (title, description,
datePosted, hiringOrganization, jobLocation). We read the listing, collect
the job URLs, then fetch each and reuse the shared JSON-LD parser.

robots.txt disallows only ``/ref/``, ``/*?viaCareers=`` and ``/apply$`` —
the listing and detail pages are permitted. A board is the company slug
(e.g. "herpinc"). No key, no CSRF.
"""

from __future__ import annotations

import re

import requests

from ..models import now_iso
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job

TIMEOUT = 25
MAX_JOBS = 300


class HerpConnector(Connector):
    platform = "herp"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = "https://herp.careers/v1"
        # job detail short-ids under /v1/{company}/{id}; skip utility segments
        self._job_re = re.compile(
            rf"/v1/{re.escape(board)}/([A-Za-z0-9]{{8,}})(?![\w-])")

    def fetch(self) -> list:
        listing = f"{self._base}/{self.board}"
        if not robots_allowed(listing, self._session):
            return []
        resp = self._session.get(listing, timeout=TIMEOUT)
        resp.raise_for_status()
        ids: list[str] = []
        seen_ids: set[str] = set()
        for m in self._job_re.finditer(resp.text):
            jid = m.group(1)
            if jid.lower().startswith("requisition") or jid in seen_ids:
                continue
            seen_ids.add(jid)
            ids.append(jid)
        at = now_iso()
        jobs = []
        seen: set[str] = set()
        for jid in ids[:MAX_JOBS]:
            url = f"{self._base}/{self.board}/{jid}"
            if not robots_allowed(url, self._session):
                continue
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
        return jobs
