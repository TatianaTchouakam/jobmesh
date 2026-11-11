"""Reed.co.uk connector — UK's largest job board (public API, free key).

Reed exposes an official public Jobseeker API. Free API key (self-service at
https://www.reed.co.uk/developers/jobseeker). Covers ALL sectors across the UK.

    GET https://www.reed.co.uk/api/1.0/search?resultsToTake=100&resultsToSkip=0
    Auth: HTTP Basic — username = API key, password = empty.

The API key is READ FROM THE ENVIRONMENT, never hard-coded:
    REED_API_KEY
`board` is ignored; use "all".
Docs: https://www.reed.co.uk/developers/jobseeker
"""

from __future__ import annotations

import os

import requests
from requests.auth import HTTPBasicAuth

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API = "https://www.reed.co.uk/api/1.0/search"
USER_AGENT = "jobmesh/0.1 (+https://jobmesh.world; job index; contact via site)"
TIMEOUT = 30
PAGE = 100          # Reed's max per request
MAX_PAGES = 5       # bounded: up to ~500 most-recent postings per run


def _key() -> str:
    key = os.getenv("REED_API_KEY")
    if not key:
        raise RuntimeError(
            "REED_API_KEY is not set. Get a free key at "
            "https://www.reed.co.uk/developers/jobseeker and set it as an env var.")
    return key


class ReedConnector(Connector):
    platform = "reed"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        at = now_iso()
        auth = HTTPBasicAuth(_key(), "")
        jobs: list[Job] = []
        for page in range(MAX_PAGES):
            params = {"resultsToTake": PAGE, "resultsToSkip": page * PAGE}
            # `board` can carry an optional keyword filter; "all" = no filter.
            if self.board and self.board != "all":
                params["keywords"] = self.board
            r = self._session.get(API, params=params, auth=auth, timeout=TIMEOUT)
            r.raise_for_status()
            results = (r.json() or {}).get("results") or []
            if not results:
                break
            jobs.extend(self._to_job(d, at) for d in results)
            if len(results) < PAGE:
                break
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("jobTitle") or "(untitled)"
        company = d.get("employerName") or "Undisclosed"
        location = d.get("locationName") or "United Kingdom"
        if "kingdom" not in location.lower() and "uk" not in location.lower():
            location = location + ", United Kingdom"
        jid = str(d.get("jobId") or d.get("jobUrl") or title)
        url = d.get("jobUrl")
        body = html_to_text(d.get("jobDescription"))
        lo, hi = d.get("minimumSalary"), d.get("maximumSalary")
        salary = None
        if lo or hi:
            cur = d.get("currency") or "GBP"
            salary = f"{lo or ''}{'–' if lo and hi else ''}{hi or ''} {cur}".strip()
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=jid,
            title=title, company=company, location=location, description=body,
            source_url=url, apply_url=url, salary=salary,
            employment_type=("Part-time" if d.get("partTime")
                             else "Full-time" if d.get("fullTime") else None),
            category=None,
            remote=detect_remote(location),
            posted_at=d.get("date"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
