"""Pinpoint connector (ATS).

Reads the public Pinpoint postings feed (no key):
    https://{company}.pinpointhq.com/postings.json

The feed is JSON:API-shaped ({"data": [{"id", "attributes": {...}}]}). The
exact attribute names aren't publicly documented, so the mapping reads
defensively: an unexpected shape yields no jobs rather than bad data.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 25


class PinpointConnector(Connector):
    platform = "pinpoint"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        url = f"https://{self.board}.pinpointhq.com/postings.json"
        resp = self._session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data") if isinstance(body, dict) else body
        if not isinstance(data, list):
            return []
        company = self.board.replace("-", " ").title()
        at = now_iso()
        jobs = []
        for item in data:
            job = self._to_job(item, company, at)
            if job is not None:
                jobs.append(job)
        return jobs

    def _to_job(self, item: dict, company: str, at: str) -> Job | None:
        if not isinstance(item, dict):
            return None
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else item
        title = attrs.get("title") or attrs.get("name")
        if not title:
            return None  # unexpected shape -> skip rather than emit junk

        location = self._location(attrs.get("location"))
        workplace = (attrs.get("workplace_type") or attrs.get("remote") or "")
        wp = str(workplace).lower()
        if "remote" in wp:
            workplace_type = "remote"
        elif wp in ("hybrid",):
            workplace_type = "hybrid"
        elif wp in ("on_site", "onsite", "office"):
            workplace_type = "onsite"
        else:
            workplace_type = None

        job_id = str(item.get("id") or attrs.get("id") or "")
        links = item.get("links") if isinstance(item.get("links"), dict) else {}
        url = (links.get("careers_page_url") or attrs.get("url")
               or attrs.get("careers_url")
               or (f"https://{self.board}.pinpointhq.com/postings/{job_id}" if job_id else None))

        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=job_id,
            title=title, company=company, location=location,
            description=html_to_text(attrs.get("description")),
            source_url=url, apply_url=url,
            salary=None,
            employment_type=attrs.get("employment_type"),
            workplace_type=workplace_type,
            category=self._name(attrs.get("department")),
            remote=(workplace_type == "remote") if workplace_type else detect_remote(location),
            posted_at=attrs.get("created_at") or attrs.get("published_at"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )

    @staticmethod
    def _location(loc) -> str | None:
        if isinstance(loc, dict):
            return (loc.get("name")
                    or ", ".join(p for p in [loc.get("city"), loc.get("country")] if p)
                    or None)
        if isinstance(loc, str):
            return loc or None
        return None

    @staticmethod
    def _name(v):
        if isinstance(v, dict):
            return v.get("name")
        if isinstance(v, str):
            return v or None
        return None
