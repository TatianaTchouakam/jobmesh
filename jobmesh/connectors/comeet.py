"""Comeet (Spark Hire Recruit) connector.

Reads Comeet's public Careers API:
    https://www.comeet.co/careers-api/2.0/company/{uid}/positions?token={token}&details=true

No account needed: the company UID and public token are the same pair a
Comeet-hosted careers page embeds in its page source, so they are public.

A board is written as "uid:token" (or "uid:token:Company Name" to set a
nice display name), e.g.  "E5.007:5E7236A0BCE5E7295111B55E70BCE:Acme".
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API_ROOT = "https://www.comeet.co/careers-api/2.0/company"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 20


def _strip_token(url: str | None) -> str | None:
    """Drop a ?token=... (or &token=...) query so we never store the token."""
    if not url:
        return url
    for sep in ("?token=", "&token="):
        if sep in url:
            head, _, tail = url.partition(sep)
            # keep any other params that came after the token
            rest = tail.split("&", 1)
            kept = rest[1] if len(rest) > 1 else ""
            return head + (("?" + kept) if (sep == "?token=" and kept) else "")
    return url


class ComeetConnector(Connector):
    platform = "comeet"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        parts = board.split(":", 2)
        self.uid = parts[0]
        self.token = parts[1] if len(parts) > 1 else ""
        self.company_name = parts[2] if len(parts) > 2 else None
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        positions = self._get_positions()
        fetched_at = now_iso()
        company = self.company_name or self.uid
        return [self._to_job(p, company, fetched_at) for p in positions]

    def _get_positions(self) -> list[dict]:
        url = f"{API_ROOT}/{self.uid}/positions"
        resp = self._session.get(
            url, params={"token": self.token, "details": "true"}, timeout=TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("positions") or data.get("data") or []
        return data or []

    @staticmethod
    def _description(data: dict) -> str | None:
        details = data.get("details")
        if isinstance(details, list):
            chunks = []
            for section in details:
                if not isinstance(section, dict):
                    continue
                name = section.get("name")
                value = section.get("value")
                if value:
                    chunks.append(f"{name}\n{value}" if name else str(value))
            if chunks:
                return html_to_text("\n\n".join(chunks))
        return html_to_text(data.get("description"))

    def _to_job(self, data: dict, company: str, fetched_at: str) -> Job:
        loc = data.get("location") or {}
        if isinstance(loc, dict):
            location = loc.get("name") or ", ".join(
                x for x in (loc.get("city"), loc.get("state"), loc.get("country")) if x
            ) or None
        else:
            location = loc or None

        title = data.get("name") or "(untitled)"
        url = (
            _strip_token(data.get("url_active_page"))
            or _strip_token(data.get("url_comeet_hosted_page"))
            or _strip_token(data.get("position_url"))
        )

        department = data.get("department")
        if not department:
            for cat in data.get("categories") or []:
                if isinstance(cat, dict) and (cat.get("name") or "").lower() == "department":
                    department = cat.get("value")
                    break

        return Job(
            source_platform=self.platform,
            source_board=self.uid,
            source_job_id=str(data.get("uid") or data.get("id") or title),
            title=title,
            company=company,
            location=location,
            description=self._description(data),
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=data.get("employment_type") or data.get("position_type"),
            workplace_type=None,
            category=department,
            remote=detect_remote(location),
            posted_at=data.get("time_updated") or data.get("time_created"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
