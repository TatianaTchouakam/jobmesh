"""GoHire connector — hosted career sites with schema.org JSON-LD.

GoHire (SMB ATS, UK) gives every customer a hosted careers page that is
built for Google for Jobs, so each job detail page server-renders a clean
schema.org ``JobPosting`` JSON-LD block (title, description, identifier,
datePosted, validThrough, hiringOrganization, jobLocation, employmentType,
baseSalary). The board also publishes a plain-text sitemap at
``/sitemap.txt`` listing every job URL (``/{slug}-{id}/``).

So this is the shared "sitemap + schema.org JobPosting" recipe: read
robots.txt, read the sitemap, parse the JSON-LD of each job — no token, no
DOM scraping. robots.txt is ``Allow: /``. A board is the careers host
(e.g. "careers.gohire.io" or a customer's "careers.acme.com").
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
_JOB_URL = re.compile(r"-(\d+)/?$")


class GoHireConnector(Connector):
    platform = "gohire"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{board}"

    def fetch(self) -> list:
        sitemap = f"{self._base}/sitemap.txt"
        if not robots_allowed(sitemap, self._session):
            return []
        resp = self._session.get(sitemap, timeout=TIMEOUT)
        resp.raise_for_status()
        urls: list[tuple[str, str]] = []
        seen_ids: set[str] = set()
        for raw in resp.text.split():
            if not raw.startswith(("http://", "https://")):
                continue
            url = raw.replace("http://", "https://", 1)
            m = _JOB_URL.search(url)
            if not m:
                continue
            jid = m.group(1)
            if jid not in seen_ids:
                seen_ids.add(jid)
                urls.append((jid, url))
        at = now_iso()
        jobs = []
        seen: set[str] = set()
        for jid, url in urls[:MAX_JOBS]:
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
                ident = posting.get("identifier")
                if isinstance(ident, dict) and ident.get("value"):
                    job.source_job_id = str(ident["value"])
                else:
                    job.source_job_id = jid
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
        return jobs
