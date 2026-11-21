"""Artha (Knovator) job-board connector — public guest search API.

Artha-powered job boards (e.g. fpnajobs.com) are Next.js sites fed by a keyless
public API. The tenant is identified by the request Origin, so we present the
board's own domain as the caller:

    POST https://api.arthajobboard.com/client/api/v1/jobs/search/guest
         Origin: https://{domain}
         {"page": N, "limit": 50}
    -> {"data": {"data": [ {title, slug, company:{nm}, loc:{city,state,country},
                            _id, activatedAt, useRedirectUrl, applyUrl}, ... ],
                 "paginator": {"hasNextPage": ..., "pageCount": ...}}}

robots.txt on the board domain is `User-agent: * / Allow: /`. A ``board`` is the
board's host, e.g. "www.fpnajobs.com".
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
API = "https://api.arthajobboard.com/client/api/v1/jobs/search/guest"
PAGE_SIZE = 50
MAX_PAGES = 20  # up to 1000 postings/board


def _location(loc) -> str | None:
    if not isinstance(loc, dict):
        return None
    parts = []
    for key in ("city", "state", "country"):
        v = loc.get(key)
        if isinstance(v, dict) and v.get("nm"):
            parts.append(v["nm"].strip())
    return ", ".join(parts) or None


class ArthaConnector(Connector):
    platform = "artha"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.domain = board.strip().strip("/")
        self.site = f"https://{self.domain}"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        # Robots is governed by the board's content host (Allow: /); the API is
        # served from the arthajobboard infra host.
        if not robots_allowed(f"{self.site}/", self._session):
            return []
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "Origin": self.site, "Referer": f"{self.site}/"}
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            resp = self._session.post(API, json={"page": page, "limit": PAGE_SIZE},
                                      headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            data = ((resp.json() or {}).get("data")) or {}
            rows = data.get("data") or []
            for row in rows:
                job = self._to_job(row, at)
                if job is not None and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    jobs.append(job)
            pag = data.get("paginator") or {}
            if not rows or not pag.get("hasNextPage"):
                break
        return jobs

    def _to_job(self, row: dict, at: str) -> Job | None:
        jid = row.get("_id")
        if not jid:
            return None
        title = (row.get("title") or "(untitled)").strip() or "(untitled)"
        comp = row.get("company") or {}
        company = (comp.get("nm") if isinstance(comp, dict) else None) or self.domain
        location = _location(row.get("loc"))
        slug = row.get("slug")
        detail = f"{self.site}/job-detail/{slug}" if slug else self.site
        apply_url = detail
        if row.get("useRedirectUrl"):
            apply_url = row.get("applyUrl") or row.get("redirectUrl") or detail
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(jid),
            title=title,
            company=company.strip() or self.domain,
            location=location,
            description=None,
            source_url=detail,
            apply_url=apply_url,
            remote=detect_remote(f"{location or ''} {title}"),
            posted_at=row.get("activatedAt"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )
