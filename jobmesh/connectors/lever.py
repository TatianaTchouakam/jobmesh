"""Lever connector.

Reads the public Lever postings API:
    https://api.lever.co/v0/postings/{site}?mode=json

No API key. Returns a JSON array of postings; descriptions already come
as plain text (`descriptionPlain`). An unknown site returns 404, which
surfaces as a fetch failure (so the pipeline won't close that board).
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from .base import Connector

API_ROOT = "https://api.lever.co/v0/postings"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 20


class LeverConnector(Connector):
    platform = "lever"

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
        url = f"{API_ROOT}/{self.board}"
        resp = self._session.get(url, params={"mode": "json"}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        # Lever returns a bare array of postings.
        return data if isinstance(data, list) else []

    def _to_job(self, data: dict, company: str, fetched_at: str) -> Job:
        categories = data.get("categories") or {}
        location = categories.get("location")

        # workplaceType is one of: remote / on-site / hybrid / unspecified.
        workplace = (data.get("workplaceType") or "").lower()
        if workplace == "remote":
            remote = True
        elif workplace in ("on-site", "onsite", "hybrid"):
            remote = False
        else:
            remote = detect_remote(location)

        title = data.get("text") or "(untitled)"

        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(data.get("id")),
            title=title,
            company=company,
            location=location,
            description=data.get("descriptionPlain"),
            source_url=data.get("hostedUrl"),
            apply_url=data.get("applyUrl") or data.get("hostedUrl"),
            salary=None,  # not exposed as a structured field by Lever
            employment_type=categories.get("commitment"),
            remote=remote,
            posted_at=_epoch_ms_to_iso(data.get("createdAt")),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )


def _epoch_ms_to_iso(ms: int | None) -> str | None:
    """Convert Lever's epoch-milliseconds timestamp to an ISO-8601 string."""
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()