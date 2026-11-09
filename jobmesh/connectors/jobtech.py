"""JobTech / Arbetsförmedlingen connector (Sweden's public job board).

Sweden's Public Employment Service publishes its entire job board (Platsbanken)
through JobTech Dev's open JobSearch API — no key, no registration. It covers
EVERY sector across Sweden (healthcare, trades, logistics, education, ...).

    GET https://jobsearch.api.jobtechdev.se/search?limit=100&offset=0

`board` is ignored; use "all".
Docs: https://jobtechdev.se/en/components/jobsearch
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from .base import Connector

API = "https://jobsearch.api.jobtechdev.se/search"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 30
LIMIT = 100
MAX_PAGES = 10     # bounded: up to ~1,000 most-recent postings per run


def _label(v):
    if isinstance(v, dict):
        return v.get("label") or v.get("name")
    return v


class JobTechConnector(Connector):
    platform = "jobtech"

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
                API, params={"limit": LIMIT, "offset": page * LIMIT}, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits") or []
            if not hits:
                break
            jobs.extend(self._to_job(h, at) for h in hits)
            if len(hits) < LIMIT:
                break
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("headline") or "(untitled)"
        emp = d.get("employer") or {}
        company = emp.get("name") or emp.get("workplace") or "Okänd"
        addr = d.get("workplace_address") or {}
        city = addr.get("municipality") or addr.get("city")
        region = addr.get("region")
        country = addr.get("country") or "Sweden"
        location = ", ".join(p for p in (city, region, country) if p) or "Sweden"
        jid = str(d.get("id") or d.get("webpage_url") or title)
        url = d.get("webpage_url") or (d.get("application_details") or {}).get("url")
        desc = d.get("description") or {}
        body = html_to_text(desc.get("text") or desc.get("text_formatted"))
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=jid,
            title=title, company=company, location=location, description=body,
            source_url=url, apply_url=url, salary=None,
            employment_type=_label(d.get("employment_type")),
            category=_label(d.get("occupation")) or _label(d.get("occupation_group")),
            remote=None,
            posted_at=d.get("publication_date"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
