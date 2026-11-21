"""MyCareersFuture connector — Singapore's national jobs portal (public API).

The Singapore government's MyCareersFuture portal exposes a keyless public JSON
API (no auth), like the Bundesagentur/JobTech national portals:

    GET https://api.mycareersfuture.gov.sg/v2/jobs?limit=100&page=N
    -> {"results": [ {uuid, title, description, salary:{min,max,type},
                      postedCompany:{name}, address:{...,isOverseas,overseasCountry},
                      employmentTypes:[{employmentType}], positionLevels:[{position}],
                      metadata:{jobDetailsUrl, originalPostingDate}}, ... ],
        "total": 81373}

robots.txt: `User-agent: * / Disallow:` (empty = allow all). Capped at a few
thousand postings so one large national portal does not dominate the index.
``board`` is unused (single portal); default "mycareersfuture.gov.sg".
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
API = "https://api.mycareersfuture.gov.sg/v2/jobs"
SITE = "https://www.mycareersfuture.gov.sg"
PAGE_SIZE = 100
MAX_JOBS = 5000


def _location(addr) -> str | None:
    if not isinstance(addr, dict):
        return None
    if addr.get("isOverseas") and addr.get("overseasCountry"):
        return str(addr["overseasCountry"]).strip()
    districts = addr.get("districts") or []
    region = districts[0].get("region") if districts and isinstance(districts[0], dict) else None
    return f"Singapore ({region})" if region else "Singapore"


def _salary(sal) -> str | None:
    if not isinstance(sal, dict):
        return None
    lo, hi = sal.get("minimum"), sal.get("maximum")
    t = (sal.get("type") or {}).get("salaryType") if isinstance(sal.get("type"), dict) else None
    if not lo and not hi:
        return None
    rng = f"{lo}-{hi}" if lo and hi else str(lo or hi)
    return f"SGD {rng}" + (f"/{t}" if t else "")


class MyCareersFutureConnector(Connector):
    platform = "mycareersfuture"

    def __init__(self, board: str = "mycareersfuture.gov.sg",
                 session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        if not robots_allowed(f"{SITE}/", self._session):
            return []
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for page in range(0, (MAX_JOBS // PAGE_SIZE) + 1):
            resp = self._session.get(API, params={"limit": PAGE_SIZE, "page": page},
                                     timeout=TIMEOUT)
            resp.raise_for_status()
            rows = (resp.json() or {}).get("results") or []
            if not rows:
                break
            for row in rows:
                job = self._to_job(row, at)
                if job is not None and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    jobs.append(job)
            if len(jobs) >= MAX_JOBS:
                break
        return jobs

    def _to_job(self, row: dict, at: str) -> Job | None:
        uid = row.get("uuid")
        if not uid:
            return None
        title = (row.get("title") or "(untitled)").strip() or "(untitled)"
        comp = row.get("postedCompany") or row.get("hiringCompany") or {}
        company = (comp.get("name") if isinstance(comp, dict) else None) or "Singapore employer"
        location = _location(row.get("address"))
        meta = row.get("metadata") or {}
        url = (meta.get("jobDetailsUrl") if isinstance(meta, dict) else None) \
            or f"{SITE}/job/{uid}"
        emp = (row.get("employmentTypes") or [{}])[0].get("employmentType")
        lvl = (row.get("positionLevels") or [{}])[0].get("position")
        posted = meta.get("originalPostingDate") or meta.get("newPostingDate") if isinstance(meta, dict) else None
        desc = row.get("description")
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(uid),
            title=title,
            company=company.strip() or "Singapore employer",
            location=location,
            description=html_to_text(desc) if desc else None,
            source_url=url,
            apply_url=url,
            salary=_salary(row.get("salary")),
            employment_type=emp,
            level=lvl,
            remote=detect_remote(f"{location or ''} {title}"),
            posted_at=posted,
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )
