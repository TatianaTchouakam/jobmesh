"""Workable connector.

Reads the public Workable careers widget API:
    https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true

No API key. Response is {"name": <company>, "jobs": [...]}. `details=true`
includes each job's description in the list response.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API_ROOT = "https://apply.workable.com/api/v1/widget/accounts"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 20


class WorkableConnector(Connector):
    platform = "workable"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        payload = self._get_payload()
        company = payload.get("name") or self.board.replace("-", " ").title()
        fetched_at = now_iso()
        return [
            self._to_job(j, company, fetched_at)
            for j in payload.get("jobs", [])
        ]

    def _get_payload(self) -> dict:
        url = f"{API_ROOT}/{self.board}"
        resp = self._session.get(
            url, params={"details": "true"}, timeout=TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    def _to_job(self, data: dict, company: str, fetched_at: str) -> Job:
        loc = data.get("location") or {}
        if isinstance(loc, dict):
            location = loc.get("location_str")
            telecommuting = loc.get("telecommuting")
            workplace = (loc.get("workplace_type") or "").lower()
        else:
            location, telecommuting, workplace = (loc or None), None, ""

        if isinstance(telecommuting, bool):
            remote = telecommuting
        elif workplace == "remote":
            remote = True
        elif workplace:
            remote = False
        else:
            remote = detect_remote(location)

        description = data.get("full_description") or data.get("description")
        title = data.get("title") or "(untitled)"
        url = data.get("url") or data.get("shortlink")

        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(data.get("id") or data.get("shortcode")),
            title=title,
            company=company,
            location=location,
            description=html_to_text(description),
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=data.get("employment_type"),
            remote=remote,
            posted_at=data.get("published_on") or data.get("created_at"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
