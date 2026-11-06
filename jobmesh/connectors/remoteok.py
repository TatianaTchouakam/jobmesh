"""Remote OK connector (job board).

Reads the public Remote OK API (no key):
    https://remoteok.com/api

Returns a JSON array whose first element is a legal/disclaimer object; the
rest are jobs. Every posting is remote. The `board` argument is ignored;
use "all" in config.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from .base import Connector

API = "https://remoteok.com/api"
# Remote OK rejects empty/unknown clients, so send a descriptive UA.
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25


class RemoteOkConnector(Connector):
    platform = "remoteok"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        resp = self._session.get(API, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []
        at = now_iso()
        jobs = []
        for d in data:
            # skip the leading legal/disclaimer entry (no "position" field)
            if not isinstance(d, dict) or not d.get("position"):
                continue
            jobs.append(self._to_job(d, at))
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("position") or "(untitled)"
        company = d.get("company") or "Unknown"
        location = d.get("location") or None
        url = d.get("url") or d.get("apply_url")
        tags = d.get("tags") or []
        salary = _salary(d.get("salary_min"), d.get("salary_max"))
        posted = d.get("date") or _epoch_to_iso(d.get("epoch"))
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(d.get("id") or d.get("slug")),
            title=title, company=company, location=location,
            description=html_to_text(d.get("description")),
            source_url=url, apply_url=url,
            salary=salary,
            employment_type=None,
            workplace_type="remote",
            category=(tags[0] if tags else None),
            remote=True,
            posted_at=posted,
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )


def _salary(lo, hi) -> str | None:
    try:
        lo = int(lo) if lo else 0
        hi = int(hi) if hi else 0
    except (ValueError, TypeError):
        return None
    if lo and hi:
        return f"${lo:,} - ${hi:,}"
    if lo or hi:
        return f"${(lo or hi):,}"
    return None


def _epoch_to_iso(sec) -> str | None:
    if not sec:
        return None
    try:
        return datetime.fromtimestamp(int(sec), tz=timezone.utc).isoformat()
    except (ValueError, OSError, TypeError):
        return None
