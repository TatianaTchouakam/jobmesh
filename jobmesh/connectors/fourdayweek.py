"""4 Day Week connector (job board — four-day-week roles).

Reads the public 4dayweek.io v2 JSON API (no key):
    https://4dayweek.io/api/v2/jobs?page=1&limit=50

Response: {"data": [...], "page", "limit", "total", "has_more"}. Salary
figures are given in cents. The `board` argument is ignored; use "all".

Docs: https://4dayweek.io/developers
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from .base import Connector

API = "https://4dayweek.io/api/v2/jobs"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25
LIMIT = 50
MAX_PAGES = 12     # Safety cap.


class FourDayWeekConnector(Connector):
    platform = "fourdayweek"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        at = now_iso()
        jobs: list[Job] = []
        page = 1
        for _ in range(MAX_PAGES):
            resp = self._session.get(
                API, params={"page": page, "limit": LIMIT}, timeout=TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("data") or []
            if not batch:
                break
            jobs.extend(self._to_job(j, at) for j in batch)
            if not data.get("has_more"):
                break
            page += 1
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("title") or "(untitled)"
        company = (d.get("company") or {}).get("name") or "Unknown"
        locs = d.get("locations") or []
        primary = next((l for l in locs if l.get("is_primary")), (locs[0] if locs else {}))
        location = primary.get("country") or None
        arrangement = (d.get("work_arrangement")
                       or primary.get("work_arrangement") or "").lower() or None
        url = d.get("url")
        salary = _salary(d.get("salary_min"), d.get("salary_max"),
                         d.get("salary_currency"))
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(d.get("slug") or d.get("id") or url),
            title=title, company=company, location=location,
            description=html_to_text(d.get("description")),
            source_url=url, apply_url=url,
            salary=salary,
            employment_type=None,
            workplace_type=arrangement,     # remote / hybrid / onsite
            category=None,
            remote=(arrangement == "remote") if arrangement else None,
            posted_at=d.get("posted_at"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )


def _salary(lo, hi, cur) -> str | None:
    """Salaries come in cents; render a readable range."""
    cur = cur or "USD"
    try:
        lo = int(lo) // 100 if lo else 0
        hi = int(hi) // 100 if hi else 0
    except (ValueError, TypeError):
        return None
    if lo and hi:
        return f"{lo:,} - {hi:,} {cur}"
    if lo or hi:
        return f"{(lo or hi):,} {cur}"
    return None
