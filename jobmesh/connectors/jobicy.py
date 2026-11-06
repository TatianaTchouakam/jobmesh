"""Jobicy connector (job board).

Reads the public Jobicy API (no key):
    https://jobicy.com/api/v2/remote-jobs

Returns {"jobs": [...]}. Every posting is remote. The `board` argument is
ignored; use "all" in config.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from .base import Connector

API = "https://jobicy.com/api/v2/remote-jobs"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25


class JobicyConnector(Connector):
    platform = "jobicy"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        resp = self._session.get(API, params={"count": 50}, timeout=TIMEOUT)
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
        at = now_iso()
        return [self._to_job(j, at) for j in jobs]

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("jobTitle") or "(untitled)"
        company = d.get("companyName") or "Unknown"
        location = d.get("jobGeo") or None
        url = d.get("url")
        jt = d.get("jobType") or []
        ind = d.get("jobIndustry") or []
        desc = d.get("jobDescription") or d.get("jobExcerpt")
        salary = _salary(d.get("annualSalaryMin"), d.get("annualSalaryMax"),
                         d.get("salaryCurrency"))
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(d.get("id")),
            title=title, company=company, location=location,
            description=html_to_text(desc),
            source_url=url, apply_url=url,
            salary=salary,
            employment_type=(jt[0] if jt else None),
            workplace_type="remote",
            category=(ind[0] if ind else None),
            remote=True,
            posted_at=d.get("pubDate"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )


def _salary(lo, hi, cur) -> str | None:
    cur = cur or "USD"
    try:
        lo = int(lo) if lo else 0
        hi = int(hi) if hi else 0
    except (ValueError, TypeError):
        return None
    if lo and hi:
        return f"{lo:,} - {hi:,} {cur}"
    if lo or hi:
        return f"{(lo or hi):,} {cur}"
    return None
