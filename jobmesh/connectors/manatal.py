"""Manatal connector — public, keyless career-page API.

Manatal (manatal.com) hosts each customer's career page at
``careers-page.com/{tenant}``; the page's front end reads a public,
unauthenticated DRF API:

    GET https://www.careers-page.com/api/v1.0/c/{tenant}/jobs/?page_size=50&page=N
    -> {count, next, previous, results: [...]}

The server caps the page at 20, so we page through using ``count``/``next``.
Each job carries the full HTML description. A board is the tenant slug
(e.g. "manatal"). careers-page.com has no robots.txt (crawling allowed).
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API = "https://www.careers-page.com/api/v1.0/c"
PAGE = "https://www.careers-page.com"
USER_AGENT = "JobmeshBot/0.1 (+https://github.com/TatianaTchouakam/jobmesh)"
TIMEOUT = 20
PAGE_SIZE = 50  # server caps at 20
MAX_PAGES = 50


class ManatalConnector(Connector):
    platform = "manatal"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        # the tenant slug is the employer; organization_name is the department
        self._company = board.replace("-", " ").replace("_", " ").strip().title()

    def fetch(self) -> list[Job]:
        fetched_at = now_iso()
        jobs: list[Job] = []
        page = 1
        while page <= MAX_PAGES:
            resp = self._session.get(
                f"{API}/{self.board}/jobs/",
                params={"page_size": PAGE_SIZE, "page": page},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            for r in results:
                jobs.append(self._to_job(r, fetched_at))
            total = data.get("count") or 0
            if len(jobs) >= total or not results or not data.get("next"):
                break
            page += 1
        return jobs

    def _to_job(self, d: dict, fetched_at: str) -> Job:
        title = d.get("position_name") or "(untitled)"
        location = d.get("location_display") or ", ".join(
            x for x in (d.get("city"), d.get("state"), d.get("country")) if x
        ) or None
        h = d.get("hash")
        url = f"{PAGE}/{self.board}/job/{h}" if h else f"{PAGE}/{self.board}"
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(d.get("id") or h or title),
            title=title,
            company=self._company,
            location=location,
            description=html_to_text(d.get("description")),
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=None,
            workplace_type=None,
            category=d.get("organization_name"),
            remote=detect_remote(location),
            posted_at=None,
            dedup_key=make_dedup_key(title, self._company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
