"""NAV (arbeidsplassen.no) connector — Norway's public job board.

Norway's Labour and Welfare Administration (NAV) publishes its public job
board through an open feed — no key. Covers ALL sectors across Norway.

    GET https://arbeidsplassen.nav.no/public-feed/api/v1/ads?size=100&page=0

`board` is ignored; use "all".
Docs: https://github.com/navikt/pam-public-feed
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from .base import Connector

API = "https://arbeidsplassen.nav.no/public-feed/api/v1/ads"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 30
SIZE = 100
MAX_PAGES = 10     # bounded: up to ~1,000 most-recent postings per run


def _label(seq):
    if isinstance(seq, list) and seq:
        x = seq[0]
        if isinstance(x, dict):
            return x.get("name") or x.get("label")
        return x
    return None


def _nav_location(ad: dict) -> str:
    locs = ad.get("locationList") or []
    if locs and isinstance(locs[0], dict):
        o = locs[0]
        parts = [o.get("municipal") or o.get("city"), o.get("county"),
                 o.get("country") or "Norway"]
        loc = ", ".join(p for p in parts if p)
        if loc:
            return loc
    loc = ad.get("location")
    return loc or "Norway"


class NavNoConnector(Connector):
    platform = "navno"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        at = now_iso()
        jobs: list[Job] = []
        for page in range(MAX_PAGES):
            resp = self._session.get(
                API, params={"size": SIZE, "page": page}, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("content") or data.get("ads") or []
            if not batch:
                break
            jobs.extend(self._to_job(d, at) for d in batch)
            if len(batch) < SIZE:
                break
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("title") or "(untitled)"
        company = d.get("businessName") or (d.get("employer") or {}).get("name") or "Ukjent"
        location = _nav_location(d)
        jid = str(d.get("uuid") or d.get("id") or d.get("link") or title)
        url = d.get("link") or d.get("url")
        body = html_to_text(d.get("description"))
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=jid,
            title=title, company=company, location=location, description=body,
            source_url=url, apply_url=url, salary=None,
            employment_type=d.get("engagementType") or d.get("extent"),
            category=_label(d.get("occupationCategories")),
            remote=None,
            posted_at=d.get("published"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
