"""Working Nomads connector (job board, remote).

Reads the public Working Nomads feed (no key):
    https://www.workingnomads.com/api/exposed_jobs/

Returns a JSON array of remote jobs. The `board` argument is ignored; use
"all" in config.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from .base import Connector

API = "https://www.workingnomads.com/api/exposed_jobs/"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 25


class WorkingNomadsConnector(Connector):
    platform = "workingnomads"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        resp = self._session.get(API, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        jobs = data if isinstance(data, list) else data.get("jobs", [])
        at = now_iso()
        return [self._to_job(d, at) for d in jobs]

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("title") or "(untitled)"
        company = d.get("company_name") or "Unknown"
        location = d.get("location") or None
        url = d.get("url")
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(d.get("id") or url),
            title=title, company=company, location=location,
            description=html_to_text(d.get("description")),
            source_url=url, apply_url=url,
            salary=None,
            employment_type=None,
            workplace_type="remote",
            category=d.get("category_name"),
            remote=True,
            posted_at=d.get("pub_date"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
