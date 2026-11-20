"""Polymer connector — public, keyless jobs API.

Polymer (api.polymer.co) is a lightweight ATS for early-stage startups.
Its public API returns one organization's published jobs, no auth:
    GET https://api.polymer.co/v1/hire/organizations/{slug}/jobs

A board is the organization slug (e.g. "prospera"). The list endpoint
carries no description; title/company/location/url/type/date are mapped.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from .base import Connector

API_ROOT = "https://api.polymer.co/v1/hire/organizations"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 20


class PolymerConnector(Connector):
    platform = "polymer"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        resp = self._session.get(f"{API_ROOT}/{self.board}/jobs", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items") or data.get("jobs") or []
        fetched_at = now_iso()
        return [self._to_job(j, fetched_at) for j in items]

    def _to_job(self, data: dict, fetched_at: str) -> Job:
        title = data.get("title") or "(untitled)"
        company = data.get("organization_name") or self.board
        location = data.get("display_location") or ", ".join(
            x for x in (data.get("city"), data.get("state_region"), data.get("country")) if x
        ) or None
        rl = (data.get("remoteness_pretty") or "").lower()
        remote = ("remote" in rl and "no remote" not in rl) or detect_remote(location)
        url = data.get("job_post_url")
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(data.get("job_id") or data.get("id") or data.get("hash_id") or title),
            title=title,
            company=company,
            location=location,
            description=None,
            source_url=url,
            apply_url=url,
            salary=data.get("salary_pretty"),
            employment_type=data.get("kind_pretty"),
            workplace_type=None,
            category=data.get("job_category_name"),
            remote=remote,
            posted_at=data.get("published_at") or data.get("created_at"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
