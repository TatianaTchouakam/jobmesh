"""Rise (joinrise.io) connector (job board — all companies, one feed).

Reads the public Rise jobs API (no key):
    https://api.joinrise.io/api/v1/jobs/public?page=1&limit=50&sort=desc&sortedBy=createdAt

This is a cross-employer feed (no per-company token), so `board` is
ignored; use "all" in config. Rise asks that results link back and credit
Rise — jobmesh already links each posting to its source URL.

The exact response schema isn't formally documented, so the mapping reads
each field from a few likely names and degrades gracefully.
"""

from __future__ import annotations

import time

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API = "https://api.joinrise.io/api/v1/jobs/public"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 35
LIMIT = 20          # a lighter page is easier on their backend (avoids 504s)
MAX_PAGES = 10
RETRIES = 3         # Rise's gateway is prone to transient 504s — retry a few.
BACKOFF = 2.0       # seconds, grows per attempt


def _first(d: dict, *keys):
    """Return the first present, truthy value among `keys`."""
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


class JoinRiseConnector(Connector):
    platform = "joinrise"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        at = now_iso()
        jobs: list[Job] = []
        for page in range(1, MAX_PAGES + 1):
            data = self._get_page(page, first=(page == 1))
            if data is None:          # a later page gave up — keep what we have
                break
            batch = (data.get("jobs") or data.get("data")
                     or data.get("results") or [])
            if not batch:
                break
            jobs.extend(self._to_job(j, at) for j in batch)
            if not _has_more(data, page):
                break
        return jobs

    def _get_page(self, page: int, first: bool) -> dict | None:
        """GET one page, retrying transient 5xx/timeout a few times.

        On the first page we raise after exhausting retries, so a total
        outage is logged as a failure. On later pages we return None so a
        partial result is still indexed rather than lost.
        """
        last_exc: Exception | None = None
        for attempt in range(RETRIES):
            try:
                resp = self._session.get(
                    API,
                    params={"page": page, "limit": LIMIT,
                            "sort": "desc", "sortedBy": "createdAt"},
                    timeout=TIMEOUT,
                )
                if resp.status_code >= 500:
                    resp.raise_for_status()
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < RETRIES - 1:
                    time.sleep(BACKOFF * (attempt + 1))
        if first:
            raise last_exc  # type: ignore[misc]
        return None

    def _to_job(self, d: dict, at: str) -> Job:
        title = _first(d, "title", "jobTitle", "name", "role") or "(untitled)"
        comp = d.get("company")
        company = (comp.get("name") if isinstance(comp, dict) else comp) \
            or _first(d, "companyName", "company_name") or "Unknown"
        location = _first(d, "location", "jobLoc", "jobLocation", "city")
        if isinstance(location, dict):
            location = location.get("name") or location.get("city")
        url = _first(d, "url", "applyUrl", "jobUrl", "link")
        slug = _first(d, "slug", "id", "_id")
        if not url and slug:
            url = f"https://www.joinrise.io/jobs/{slug}"
        arrangement = str(_first(d, "workArrangement", "workplaceType",
                                 "locationType") or "").lower() or None
        remote = (arrangement == "remote") if arrangement else detect_remote(location)
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(slug or url or title),
            title=title, company=company, location=location,
            description=html_to_text(_first(d, "description", "jobDescription")),
            source_url=url, apply_url=url,
            salary=None,
            employment_type=_first(d, "employmentType", "jobType", "type"),
            workplace_type=arrangement,
            category=_first(d, "category", "department", "industry"),
            remote=remote,
            posted_at=_first(d, "createdAt", "postedAt", "datePosted", "published_at"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )


def _has_more(data: dict, page: int) -> bool:
    for k in ("hasMore", "has_more", "hasNextPage"):
        if k in data:
            return bool(data[k])
    meta = data.get("meta") or data.get("pagination") or {}
    total_pages = meta.get("totalPages") or meta.get("total_pages") or data.get("totalPages")
    if total_pages:
        try:
            return page < int(total_pages)
        except (ValueError, TypeError):
            return False
    return False
