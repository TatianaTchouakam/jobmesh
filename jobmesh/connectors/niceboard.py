"""Niceboard connector — public, keyless job-board read API.

Niceboard (niceboard.co) is modern white-label job-board software used by
hundreds of communities, associations and niche boards. Every hosted board
exposes a public, unauthenticated read API that its own frontend calls:

    GET https://{board}.niceboard.co/api/jobs?...&limit=100&page=N&sortby=newest
    -> {"jobs": [ ... ], "count": <total> }

A board is the subdomain slug (e.g. "unitedwayjobbank"). The response is
rich: title, company, location, HTML description, salary, job type, remote
flags and dates. We paginate with ``count`` and build the canonical job URL
as ``/job/{uid}``.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, html_to_text, make_dedup_key
from .base import Connector

USER_AGENT = "JobmeshBot/0.1 (+https://github.com/TatianaTchouakam/jobmesh)"
TIMEOUT = 25
PAGE_SIZE = 100
MAX_PAGES = 50  # safety cap (5,000 jobs/board)

# The frontend sends this full (mostly empty) filter set; the API 400s without it.
BASE_PARAMS = {
    "company": "all",
    "jobtype": "[]",
    "category": "[]",
    "secondary_category": "[]",
    "tags": "[]",
    "city": "[]",
    "state": "[]",
    "country": "[]",
    "remote_ok": "false",
    "remote_only": "false",
    "salary_timeframe": "",
    "salary_min": "",
    "salary_max": "",
    "keyword": "",
    "custom_fields": "{}",
    "sortby": "newest",
}


class NiceboardConnector(Connector):
    platform = "niceboard"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        # board may be a bare slug ("unitedwayjobbank") -> {slug}.niceboard.co,
        # or a full custom host ("jobs.example.org") used as-is.
        self._base = f"https://{board}" if "." in board else f"https://{board}.niceboard.co"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        fetched_at = now_iso()
        jobs: list[Job] = []
        page = 1
        while page <= MAX_PAGES:
            params = {**BASE_PARAMS, "limit": PAGE_SIZE, "page": page}
            resp = self._session.get(
                f"{self._base}/api/jobs", params=params, timeout=TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("jobs") or []
            for j in items:
                jobs.append(self._to_job(j, fetched_at))
            total = data.get("count") or 0
            if len(jobs) >= total or not items:
                break
            page += 1
        return jobs

    def _to_job(self, data: dict, fetched_at: str) -> Job:
        title = data.get("title") or "(untitled)"
        company = data.get("company_name") or (data.get("company") or {}).get("name") or self.board
        location = data.get("location_name") or (data.get("location") or {}).get("name") or None
        uid = data.get("uid")
        url = f"{self._base}/job/{uid}" if uid else self._base
        apply_url = data.get("apply_url") or url
        remote = bool(data.get("is_remote") or data.get("remote_only")) or detect_remote(location)
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(data.get("id") or uid or title),
            title=title,
            company=company,
            location=location,
            description=html_to_text(data.get("description_html")),
            source_url=url,
            apply_url=apply_url,
            salary=self._salary(data),
            employment_type=(data.get("jobtype") or {}).get("name"),
            workplace_type="remote" if remote else None,
            category=(data.get("category") or {}).get("name"),
            remote=remote,
            posted_at=data.get("published_at") or data.get("created_at"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=bool(data.get("is_published", True)) and not data.get("is_filled"),
        )

    @staticmethod
    def _salary(data: dict) -> str | None:
        if data.get("salary_description"):
            return data["salary_description"]
        lo, hi = data.get("salary_min"), data.get("salary_max")
        if not lo and not hi:
            return None
        cur = data.get("salary_currency") or ""
        tf = data.get("salary_timeframe")
        rng = "-".join(str(x) for x in (lo, hi) if x)
        out = f"{cur} {rng}".strip()
        return f"{out} / {tf}" if tf else out
