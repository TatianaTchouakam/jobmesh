"""Freshteam connector — public, server-rendered career sites.

Freshteam (Freshworks) hosts each customer's career site at
``{tenant}.freshteam.com/jobs``. The admin API (``/api/v1/job_postings``)
needs a key, but the public ``/jobs`` page is server-rendered: each job is
an ``<a class="heading" href="/jobs/{id}/{slug}">`` whose data attributes
carry the location and remote flag, with the title in a ``job-title`` div.
A plain request returns everything -- no key, no CSRF.

robots.txt is ``Disallow: /`` with an explicit ``Allow: /jobs``, so the
listing is permitted; our shared robots guard enforces that. A board is the
tenant slug (e.g. "integralresources"). Freshteam is being sunset, so some
tenants are inactive (0 jobs).
"""

from __future__ import annotations

import html as _html
import re

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 25
_TAG_RE = re.compile(r"<[^>]+>")
# each job card: the heading anchor (with data attrs) then its job-title div
_CARD_RE = re.compile(
    r'<a\s+href="(?P<href>/jobs/[^"]+)"[^>]*?class="heading"(?P<attrs>[^>]*)>'
    r'.*?<div class="job-title">\s*(?P<title>.*?)\s*</div>',
    re.DOTALL | re.IGNORECASE,
)
_LOC_RE = re.compile(r'data-portal-location="([^"]*)"', re.IGNORECASE)
_REMOTE_RE = re.compile(r'data-portal-remote-location=(?:"?)(true|false)', re.IGNORECASE)


class FreshteamConnector(Connector):
    platform = "freshteam"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{board}.freshteam.com"
        self._company = board.replace("-", " ").replace("_", " ").strip().title() or board

    def fetch(self) -> list[Job]:
        listing = f"{self._base}/jobs"
        if not robots_allowed(listing, self._session):
            return []
        resp = self._session.get(listing, timeout=TIMEOUT)
        resp.raise_for_status()
        fetched_at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for m in _CARD_RE.finditer(resp.text):
            job = self._to_job(m, fetched_at)
            if job is None or job.source_job_id in seen:
                continue
            seen.add(job.source_job_id)
            jobs.append(job)
        return jobs

    def _to_job(self, m: re.Match, fetched_at: str) -> Job | None:
        title = _html.unescape(_TAG_RE.sub("", m.group("title") or "")).strip()
        if not title:
            return None
        href = m.group("href").strip()
        jid = href.split("/jobs/", 1)[-1].split("/", 1)[0].rstrip("-") or href
        attrs = m.group("attrs") or ""
        loc_m = _LOC_RE.search(attrs)
        location = _html.unescape(loc_m.group(1)).strip() if loc_m else None
        rem_m = _REMOTE_RE.search(attrs)
        remote = bool(rem_m) and rem_m.group(1).lower() == "true"
        url = f"{self._base}{href}"
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=jid,
            title=title,
            company=self._company,
            location=location or ("Remote" if remote else None),
            description=None,
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=None,
            workplace_type="remote" if remote else None,
            category=None,
            remote=remote or detect_remote(location),
            posted_at=None,
            dedup_key=make_dedup_key(title, self._company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
