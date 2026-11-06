"""The Muse connector (job board).

Reads the public The Muse API (no key):
    https://www.themuse.com/api/public/jobs?page=N

Returns {"results": [...], "page_count": N} and is paginated; this reads a
few pages. The `board` argument is ignored; use "all" in config.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API = "https://www.themuse.com/api/public/jobs"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25
MAX_PAGES = 4


class TheMuseConnector(Connector):
    platform = "themuse"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        at = now_iso()
        jobs = []
        for page in range(MAX_PAGES):
            resp = self._session.get(API, params={"page": page}, timeout=TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            results = body.get("results", [])
            if not results:
                break
            for d in results:
                jobs.append(self._to_job(d, at))
            if page >= (body.get("page_count", 1) - 1):
                break
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("name") or "(untitled)"
        company = (d.get("company") or {}).get("name") or "Unknown"
        locs = d.get("locations") or []
        location = locs[0].get("name") if locs else None
        cats = d.get("categories") or []
        category = cats[0].get("name") if cats else None
        url = (d.get("refs") or {}).get("landing_page")
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(d.get("id")),
            title=title, company=company, location=location,
            description=html_to_text(d.get("contents")),
            source_url=url, apply_url=url,
            salary=None,
            employment_type=None,
            workplace_type=None,  # derived from location (e.g. "Flexible / Remote")
            category=category,
            remote=detect_remote(location),
            posted_at=d.get("publication_date"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
