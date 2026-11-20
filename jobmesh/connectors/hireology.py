"""Hireology connector — public, keyless career-site API.

Hireology (hireology.com) hosts each customer's career site at
``careers.hireology.com/{tenant}``; that front end reads a public,
unauthenticated JSON API:

    GET https://api.hireology.com/v2/public/careers/{tenant}?page_size=200&page=N
    -> {data: [...], count, page, page_size}

Each job carries the full HTML description, structured locations,
job_family (department), employment_status and a compensation block.
A board is the tenant slug (e.g. "hireology2", "sandiegopadres").
api.hireology.com has no robots.txt (404 -> crawling allowed); we still
pass every request through the shared robots guard with an honest UA.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

API = "https://api.hireology.com/v2/public/careers"
SITE = "https://careers.hireology.com"
TIMEOUT = 20
PAGE_SIZE = 200
MAX_PAGES = 50


class HireologyConnector(Connector):
    platform = "hireology"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        base = f"{API}/{self.board}"
        if not robots_allowed(base, self._session):
            return []
        fetched_at = now_iso()
        jobs: list[Job] = []
        page = 1
        while page <= MAX_PAGES:
            resp = self._session.get(
                base,
                params={"page_size": PAGE_SIZE, "page": page},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("data") or []
            for r in rows:
                job = self._to_job(r, fetched_at)
                if job is not None:
                    jobs.append(job)
            total = payload.get("count") or 0
            if len(jobs) >= total or len(rows) < PAGE_SIZE or not rows:
                break
            page += 1
        return jobs

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _location(d: dict) -> str | None:
        locs = d.get("locations") or []
        if locs:
            first = locs[0] or {}
            parts = [first.get("city"), first.get("state")]
            label = ", ".join(p for p in parts if p)
            if label:
                return label
        if d.get("remote"):
            return "Remote"
        return None

    @staticmethod
    def _salary(d: dict) -> str | None:
        comp = d.get("compensation") or {}
        period = comp.get("comp_period") or ""
        unit = f"/{period}" if period else ""
        if comp.get("is_comp_range") and comp.get("comp_range_min") and comp.get("comp_range_max"):
            lo = _money(comp["comp_range_min"])
            hi = _money(comp["comp_range_max"])
            if lo and hi:
                return f"{lo}-{hi}{unit}"
        single = comp.get("comp_single_amount")
        if single and single not in ("0", "0.0"):
            amt = _money(single)
            if amt:
                return f"{amt}{unit}"
        return None

    def _to_job(self, d: dict, fetched_at: str) -> Job | None:
        if str(d.get("status") or "").lower() not in ("", "open"):
            return None
        title = d.get("name") or "(untitled)"
        org = d.get("organization") or {}
        company = org.get("name") or self.board.replace("-", " ").title()
        location = self._location(d)
        url = d.get("career_site_url") or (
            f"{SITE}{d.get('career_site_path')}" if d.get("career_site_path") else f"{SITE}/{self.board}"
        )
        family = d.get("job_family") or {}
        remote = bool(d.get("remote"))
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(d.get("id") or title),
            title=title,
            company=company,
            location=location,
            description=html_to_text(d.get("job_description")),
            source_url=url,
            apply_url=url,
            salary=self._salary(d),
            employment_type=d.get("employment_status"),
            workplace_type="remote" if remote else None,
            category=family.get("name"),
            remote=remote or detect_remote(location),
            posted_at=d.get("created_at"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )


def _money(raw) -> str | None:
    try:
        n = int(round(float(raw)))
    except (TypeError, ValueError):
        return None
    return f"${n:,}"
