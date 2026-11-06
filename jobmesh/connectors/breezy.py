"""Breezy HR connector.

Reads the public Breezy HR JSON feed:
    https://{company}.breezy.hr/json

No API key. The response is a bare array of positions, with the whole
company list returned in one response. Field shapes vary a little between
boards (some fields are strings, some are objects), so the mapping reads
defensively.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 20


class BreezyConnector(Connector):
    platform = "breezy"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        raw_jobs = self._get_jobs()
        company = self.board.replace("-", " ").title()
        fetched_at = now_iso()
        return [self._to_job(j, company, fetched_at) for j in raw_jobs]

    def _get_jobs(self) -> list[dict]:
        url = f"https://{self.board}.breezy.hr/json"
        resp = self._session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("positions", [])

    def _to_job(self, data: dict, company: str, fetched_at: str) -> Job:
        location, remote = self._location(data.get("location"))
        if remote is None:
            remote = detect_remote(location)

        title = data.get("name") or "(untitled)"
        slug = data.get("friendly_id") or data.get("_id")
        url = f"https://{self.board}.breezy.hr/p/{slug}" if slug else None

        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(data.get("_id") or data.get("friendly_id")),
            title=title,
            company=company,
            location=location,
            description=html_to_text(data.get("description")),
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=self._name_of(data.get("type")),
            remote=remote,
            posted_at=data.get("published_date") or data.get("creation_date"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )

    @staticmethod
    def _location(loc) -> tuple[str | None, bool | None]:
        """Return (location_text, remote_flag_or_None) from varied shapes."""
        if isinstance(loc, dict):
            return loc.get("name"), loc.get("is_remote")
        if isinstance(loc, str):
            return (loc or None), None
        return None, None

    @staticmethod
    def _name_of(value):
        """Employment type may be a string or an object with a 'name'."""
        if isinstance(value, dict):
            return value.get("name")
        if isinstance(value, str):
            return value or None
        return None
