"""CareerPlug connector -- per-employer career portals on {board}.careerplug.com.

Each employer's public careers page lists its openings server-side at
``/jobs`` (robots allows it), with a ``/jobs/{id}`` link per posting, and every
posting page carries a schema.org ``JobPosting`` JSON-LD block. We read the
list, then pull the JSON-LD from each posting -- keyless, no headless browser,
same recipe as iCIMS. robots.txt is honoured on every request; the routes
CareerPlug disallows (``/apps/``, ``/j/``, ``/jobs.js`` ...) are never touched.

A ``board`` is the employer subdomain, e.g. ``scenthound-careers``.
"""

from __future__ import annotations

import re

import requests

from ..models import Job, now_iso
from ..ratelimit import get_limiter
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job

TIMEOUT = 25
MAX_JOBS = 300
MAX_LIST_PAGES = 15   # /jobs paginates 30 per page
_JOB_LINK = re.compile(r'href="(/jobs/\d+)(?:[?#][^"]*)?"')


class CareerPlugConnector(Connector):
    platform = "careerplug"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{board}.careerplug.com"

    def _get(self, url: str):
        # Polite, per-host paced fetch (CareerPlug shares infrastructure across
        # employer subdomains); robots is checked by the caller.
        with get_limiter("careerplug").slot(self.board):
            return self._session.get(url, timeout=TIMEOUT)

    def fetch(self) -> list[Job]:
        listing = f"{self._base}/jobs"
        if not robots_allowed(listing, self._session):
            return []
        # The /jobs list is paginated (30 per page via ?page=N). Walk pages
        # until one adds no new postings, bounded by MAX_LIST_PAGES / MAX_JOBS.
        paths: list[str] = []
        seen_paths: set[str] = set()
        for page in range(1, MAX_LIST_PAGES + 1):
            url = listing if page == 1 else f"{listing}?page={page}"
            if not robots_allowed(url, self._session):
                break
            try:
                resp = self._get(url)
                resp.raise_for_status()
            except requests.RequestException:
                if page == 1:
                    raise
                break        # no more list pages
            added = 0
            for m in _JOB_LINK.finditer(resp.text):
                path = m.group(1)
                if path not in seen_paths:
                    seen_paths.add(path)
                    paths.append(path)
                    added += 1
            if added == 0 or len(paths) >= MAX_JOBS:
                break
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for path in paths[:MAX_JOBS]:
            url = f"{self._base}{path}"
            if not robots_allowed(url, self._session):
                continue
            # The posting id is the number in /jobs/{id} -- stable and unique.
            # (CareerPlug's JSON-LD identifier is a labelled PropertyValue, so
            # the shared mapper can't key on it.)
            m = re.search(r"/jobs/(\d+)", path)
            job_id = m.group(1) if m else path
            if job_id in seen:
                continue
            try:
                r = self._get(url)
                r.raise_for_status()
            except requests.RequestException:
                continue
            postings = parse_jobpostings(r.text)
            if not postings:
                continue
            job = posting_to_job(postings[0], self.platform, self.board, at, url)
            if job is None:
                continue
            job.source_job_id = job_id
            seen.add(job_id)
            jobs.append(job)
        return jobs
