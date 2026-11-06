"""Arbeitnow connector (job board, Germany/EU).

Reads the public Arbeitnow API (no key):
    https://www.arbeitnow.com/api/job-board-api

Returns {"data": [...], "links": {"next": url}} and is paginated; this
reads a few pages. The `board` argument is ignored; use "all" in config.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API = "https://www.arbeitnow.com/api/job-board-api"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25
MAX_PAGES = 4


class ArbeitnowConnector(Connector):
    platform = "arbeitnow"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        at = now_iso()
        jobs, url = [], API
        for _ in range(MAX_PAGES):
            resp = self._session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            for d in body.get("data", []):
                jobs.append(self._to_job(d, at))
            url = (body.get("links") or {}).get("next")
            if not url:
                break
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("title") or "(untitled)"
        company = d.get("company_name") or "Unknown"
        location = d.get("location") or None
        url = d.get("url")
        remote = bool(d.get("remote"))
        job_types = d.get("job_types") or []
        tags = d.get("tags") or []
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(d.get("slug")),
            title=title, company=company, location=location,
            description=html_to_text(d.get("description")),
            source_url=url, apply_url=url,
            salary=None,
            employment_type=(job_types[0] if job_types else None),
            workplace_type=("remote" if remote else None),
            category=(tags[0] if tags else None),
            remote=remote if remote else detect_remote(location),
            posted_at=_epoch_to_iso(d.get("created_at")),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )


def _epoch_to_iso(sec) -> str | None:
    if not sec:
        return None
    try:
        return datetime.fromtimestamp(int(sec), tz=timezone.utc).isoformat()
    except (ValueError, OSError, TypeError):
        return None
