"""Manatal connector (ATS — public career-page API).

Reads the public Manatal "career page" API (no key):
    GET https://api.careers-page.com/open/v1/career-pages/{board}/job-posts

`board` is the career-page slug. The exact JSON schema isn't formally
documented, so the mapping reads each field from a few likely names and
degrades gracefully.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

ROOT = "https://api.careers-page.com/open/v1/career-pages"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


class ManatalConnector(Connector):
    platform = "manatal"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        url = f"{ROOT}/{self.board}/job-posts"
        resp = self._session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        rows = (data.get("data") or data.get("results")
                or data.get("job_posts") or (data if isinstance(data, list) else []))
        company = self.board.replace("-", " ").title()
        at = now_iso()
        return [self._to_job(d, company, at) for d in rows]

    def _to_job(self, d: dict, company: str, at: str) -> Job:
        title = _first(d, "position_name", "title", "name") or "(untitled)"
        loc = _first(d, "location", "city", "location_name")
        if isinstance(loc, dict):
            parts = [loc.get("city"), loc.get("country")]
            loc = ", ".join(p for p in parts if p) or loc.get("name")
        url = _first(d, "url", "apply_url", "public_url", "link")
        comp = _first(d, "company_name", "company") or company
        if isinstance(comp, dict):
            comp = comp.get("name") or company
        is_remote = d.get("is_remote")
        remote = bool(is_remote) if isinstance(is_remote, bool) else detect_remote(loc)
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(_first(d, "id", "hash", "uuid", "slug") or url or title),
            title=title, company=comp, location=loc,
            description=html_to_text(_first(d, "description", "details")),
            source_url=url, apply_url=url,
            salary=None,
            employment_type=_first(d, "employment_type", "contract_type", "type"),
            category=_first(d, "department", "category"),
            remote=remote,
            posted_at=_first(d, "created_at", "published_at", "date"),
            dedup_key=make_dedup_key(title, comp, loc),
            first_seen=at, last_checked=at, is_open=True,
        )
