"""Dayforce connector — public candidate-portal search API (Dayforce / Ceridian).

Dayforce career sites (jobs.dayforcehcm.com/{lang}/{namespace}/{BOARD}) are fed by
a keyless JSON API that the portal's own front end calls. It only needs the
public CSRF handshake every anonymous visitor gets (no login, no key):

    GET  https://jobs.dayforcehcm.com/api/auth/csrf        -> {"csrfToken": "..."} + cookie
    POST https://jobs.dayforcehcm.com/api/geo/{ns}/jobposting/search
         {"clientNamespace": ns, "jobBoardCode": BOARD, "cultureCode": "en-US",
          "distanceUnit": 0, "paginationStart": N}
    -> {"jobPostings": [...], "maxCount": M, "offset": N, "count": k}

robots.txt on jobs.dayforcehcm.com carries content signals only (no Disallow).
A `board` is the client namespace (e.g. "mydayforce"), optionally followed by
"|BOARDCODE" when the portal is not the default "CANDIDATEPORTAL".
"""

from __future__ import annotations

import html

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
HOST = "https://jobs.dayforcehcm.com"
MAX_PAGES = 100  # safety cap


class DayforceConnector(Connector):
    platform = "dayforce"

    def __init__(self, board: str, session: requests.Session | None = None,
                 culture: str = "en-US"):
        super().__init__(board)
        ns, _, code = board.partition("|")
        self.namespace = ns.strip()
        self.board_code = (code.strip() or "CANDIDATEPORTAL")
        self.culture = culture
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._search_url = f"{HOST}/api/geo/{self.namespace}/jobposting/search"

    def _csrf(self) -> str:
        resp = self._session.get(f"{HOST}/api/auth/csrf", timeout=TIMEOUT)
        resp.raise_for_status()
        return (resp.json() or {}).get("csrfToken") or ""

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._search_url, self._session):
            return []
        token = self._csrf()
        headers = {"Content-Type": "application/json", "X-CSRF-Token": token}
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        start = 0
        for _ in range(MAX_PAGES):
            body = {"clientNamespace": self.namespace, "jobBoardCode": self.board_code,
                    "cultureCode": self.culture, "distanceUnit": 0,
                    "paginationStart": start, "csrfToken": token}
            resp = self._session.post(self._search_url, json=body,
                                      headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json() or {}
            rows = data.get("jobPostings") or []
            for row in rows:
                job = self._to_job(row, at)
                if job is not None and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    jobs.append(job)
            start += len(rows)
            total = data.get("maxCount") or 0
            if not rows or start >= total:
                break
        return jobs

    def _to_job(self, row: dict, at: str) -> Job | None:
        pid = row.get("jobPostingId")
        if pid is None:
            return None
        title = (row.get("jobTitle") or "").strip() or "(untitled)"
        locs = row.get("postingLocations") or []
        location = "; ".join(
            l.get("formattedAddress") for l in locs if l.get("formattedAddress")) or None
        if row.get("hasVirtualLocation") and not location:
            location = "Remote"
        url = f"{HOST}/{self.culture}/{self.namespace}/{self.board_code}/jobs/{pid}"
        desc = row.get("jobDescription")
        company = self.namespace
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(pid),
            title=title,
            company=company,
            location=location,
            description=html_to_text(html.unescape(desc)) if desc else None,
            source_url=url,
            apply_url=url,
            remote=True if row.get("hasVirtualLocation") else detect_remote(location),
            posted_at=row.get("postingStartTimestampUTC"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )
