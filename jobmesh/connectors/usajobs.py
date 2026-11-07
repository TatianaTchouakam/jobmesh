"""USAJobs connector (job board, free API key).

Reads the official US federal government job API:
    https://data.usajobs.gov/api/search

USAJobs lists United States federal openings across ALL sectors —
nursing and healthcare, administration, logistics, law enforcement,
engineering, finance, trades — so it is a strong NON-TECH, public-sector
source. One `board` = an optional keyword; use "all" for everything.

Credentials are READ FROM THE ENVIRONMENT, never hard-coded:
    USAJOBS_EMAIL     (the email you registered with)
    USAJOBS_API_KEY   (the Authorization-Key they email you)
Get them free at https://developer.usajobs.gov/APIRequest. If missing,
the connector raises a clear error (logged as a normal fetch failure).
"""

from __future__ import annotations

import os
import time

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API = "https://data.usajobs.gov/api/search"
HOST = "data.usajobs.gov"
RESULTS_PER_PAGE = 500     # USAJobs maximum
MAX_PAGES = 4
TIMEOUT = 30


def _credentials() -> tuple[str, str]:
    email = os.getenv("USAJOBS_EMAIL")
    key = os.getenv("USAJOBS_API_KEY")
    if not email or not key:
        raise RuntimeError(
            "USAJobs credentials missing: set USAJOBS_EMAIL and USAJOBS_API_KEY "
            "(free at https://developer.usajobs.gov/APIRequest)."
        )
    return email, key


class UsaJobsConnector(Connector):
    platform = "usajobs"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        email, key = (os.getenv("USAJOBS_EMAIL"), os.getenv("USAJOBS_API_KEY"))
        # Headers are set per-fetch too (so injected test sessions work),
        # but set sensible defaults here when credentials are present.
        if email:
            self._session.headers.setdefault("User-Agent", email)
        self._session.headers.setdefault("Host", HOST)
        if key:
            self._session.headers.setdefault("Authorization-Key", key)

    def fetch(self) -> list[Job]:
        email, key = _credentials()
        headers = {"Host": HOST, "User-Agent": email, "Authorization-Key": key}
        keyword = "" if (self.board or "all").lower() == "all" else self.board
        at = now_iso()
        jobs: list[Job] = []
        for page in range(1, MAX_PAGES + 1):
            items = self._get_page(headers, keyword, page)
            if not items:
                break
            jobs.extend(self._to_job(it, at) for it in items)
            if len(items) < RESULTS_PER_PAGE:
                break
        return jobs

    def _get_page(self, headers: dict, keyword: str, page: int) -> list[dict]:
        params = {"ResultsPerPage": RESULTS_PER_PAGE, "Page": page}
        if keyword:
            params["Keyword"] = keyword
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = self._session.get(
                    API, params=params, headers=headers, timeout=TIMEOUT)
                resp.raise_for_status()
                result = resp.json().get("SearchResult", {})
                return result.get("SearchResultItems", []) or []
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    def _to_job(self, item: dict, at: str) -> Job:
        d = item.get("MatchedObjectDescriptor") or {}
        title = d.get("PositionTitle") or "(untitled)"
        company = d.get("OrganizationName") or d.get("DepartmentName") or "US Government"
        location = d.get("PositionLocationDisplay")
        url = d.get("PositionURI")

        category = next(
            (c.get("Name") for c in (d.get("JobCategory") or []) if c.get("Name")),
            None,
        )
        employment_type = next(
            (s.get("Name") for s in (d.get("PositionSchedule") or []) if s.get("Name")),
            None,
        )
        salary = _salary(d.get("PositionRemuneration") or [])
        description = d.get("QualificationSummary") or (
            (d.get("UserArea") or {}).get("Details") or {}
        ).get("JobSummary")

        return Job(
            source_platform=self.platform,
            source_board="all",
            source_job_id=str(d.get("PositionID") or url),
            title=title,
            company=company,
            location=location,
            description=html_to_text(description),
            source_url=url,
            apply_url=url,
            salary=salary,
            employment_type=employment_type,
            category=category,
            remote=detect_remote(" ".join(x for x in (location, title) if x)),
            posted_at=d.get("PublicationStartDate") or d.get("PositionStartDate"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )


def _salary(remun: list[dict]) -> str | None:
    """Build a salary string from USAJobs' remuneration list."""
    if not remun:
        return None
    r = remun[0]
    lo, hi = r.get("MinimumRange"), r.get("MaximumRange")
    unit = (r.get("RateIntervalCode") or "").lower()
    suffix = {"py": "/yr", "ph": "/hr"}.get(unit, "")

    def fmt(v):
        try:
            return f"{int(round(float(v))):,}"
        except (TypeError, ValueError):
            return None
    lo_s, hi_s = fmt(lo), fmt(hi)
    if lo_s and hi_s:
        return f"{lo_s}–{hi_s}{suffix}" if lo_s != hi_s else f"{lo_s}{suffix}"
    one = lo_s or hi_s
    return f"{one}{suffix}" if one else None
