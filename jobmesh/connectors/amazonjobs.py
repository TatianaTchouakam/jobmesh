"""Amazon Jobs connector.

Amazon's careers site exposes a public, keyless JSON search endpoint that its
own listing page calls:

    GET https://www.amazon.jobs/en/search.json?result_limit=100&offset=N&sort=recent

robots.txt allows it (only /internal is disallowed). One "board" covers the
whole of Amazon Jobs, so the board token is just a scope label ("all").
"""
from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import (detect_remote, html_to_text, make_dedup_key,
                         normalize_category, normalize_date, normalize_employment)
from .base import Connector

BASE = "https://www.amazon.jobs"
API = BASE + "/en/search.json"
USER_AGENT = "JobmeshBot/0.1 (+https://github.com/TatianaTchouakam/jobmesh)"
TIMEOUT = 25
PAGE = 100
MAX_PAGES = 100   # API result window caps at ~10000


class AmazonJobsConnector(Connector):
    platform = "amazonjobs"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board or "all")
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        at = now_iso()
        out: list[Job] = []
        offset = 0
        for _ in range(MAX_PAGES):
            r = self._session.get(
                API, params={"result_limit": PAGE, "offset": offset, "sort": "recent"},
                timeout=TIMEOUT)
            r.raise_for_status()
            jobs = (r.json() or {}).get("jobs") or []
            if not jobs:
                break
            for j in jobs:
                out.append(self._to_job(j, at))
            if len(jobs) < PAGE:
                break
            offset += PAGE
        return out

    def _to_job(self, j: dict, at: str) -> Job:
        title = j.get("title") or "(untitled)"
        company = j.get("company_name") or "Amazon"
        location = j.get("normalized_location") or j.get("location")
        path = j.get("job_path") or ""
        url = (BASE + path) if path.startswith("/") else (path or None)
        desc = html_to_text(j.get("description") or j.get("description_short"))
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(j.get("id") or j.get("id_icims") or title),
            title=title,
            company=company,
            location=location,
            description=desc,
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=normalize_employment(j.get("job_schedule_type")),
            category=normalize_category(j.get("job_category"), title),
            remote=detect_remote(location),
            posted_at=normalize_date(j.get("posted_date")),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )
