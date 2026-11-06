"""Himalayas connector (job board, remote).

Reads the public Himalayas jobs API (no key):
    https://himalayas.app/jobs/api?limit=N

Returns jobs (every posting is remote). The `board` argument is ignored;
use "all" in config.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from .base import Connector

API = "https://himalayas.app/jobs/api"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25
LIMIT = 50


class HimalayasConnector(Connector):
    platform = "himalayas"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        resp = self._session.get(API, params={"limit": LIMIT}, timeout=TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        jobs = body.get("jobs", body if isinstance(body, list) else [])
        at = now_iso()
        return [self._to_job(j, at) for j in jobs]

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("title") or "(untitled)"
        company = d.get("companyName") or "Unknown"
        locs = d.get("locationRestrictions") or []
        location = ", ".join(str(x) for x in locs if x) if locs else "Remote"
        cats = d.get("categories") or []
        url = d.get("applicationLink") or d.get("guid")
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(d.get("guid") or url),
            title=title, company=company, location=location,
            description=html_to_text(d.get("description")),
            source_url=url, apply_url=url,
            salary=_salary(d.get("minSalary"), d.get("maxSalary"), d.get("currency")),
            employment_type=_first(d.get("employmentType")),
            workplace_type="remote",
            category=_first(cats),
            remote=True,
            posted_at=_epoch_to_iso(d.get("pubDate")),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )


def _first(v):
    if isinstance(v, list):
        return v[0] if v else None
    return v or None


def _salary(lo, hi, cur) -> str | None:
    cur = cur or ""
    try:
        lo = int(lo) if lo else 0
        hi = int(hi) if hi else 0
    except (ValueError, TypeError):
        return None
    if lo and hi:
        return f"{lo:,} - {hi:,} {cur}".strip()
    if lo or hi:
        return f"{(lo or hi):,} {cur}".strip()
    return None


def _epoch_to_iso(sec) -> str | None:
    if not sec:
        return None
    try:
        return datetime.fromtimestamp(int(sec), tz=timezone.utc).isoformat()
    except (ValueError, OSError, TypeError):
        return None
