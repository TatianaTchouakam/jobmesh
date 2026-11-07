"""Greenhouse connector.

Reads the official, public Greenhouse Job Board API:
    https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

No API key, no login. `content=true` returns each job's full description,
departments and offices in the same list response, so one request per
board is enough. The API returns every open job at once (no pagination).

Docs: https://developers.greenhouse.io/job-board.html
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

# Greenhouse serves US-region boards from boards-api.greenhouse.io and
# EU data-residency boards from boards-api.eu.greenhouse.io. We try the US
# root first and fall back to EU on a 404, so boards in either region work.
API_ROOTS = (
    "https://boards-api.greenhouse.io/v1/boards",
    "https://boards-api.eu.greenhouse.io/v1/boards",
)
# A descriptive User-Agent is good API etiquette.
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 20  # seconds

# Metadata field names that commonly carry these attributes. Greenhouse
# boards are free to name custom fields anything, so we match loosely.
_SALARY_HINTS = ("salary", "compensation", "pay range", "pay band")
_TYPE_HINTS = ("employment type", "job type", "contract type", "worker type")
_REMOTE_HINTS = ("remote", "workplace", "work location", "location type")


class GreenhouseConnector(Connector):
    platform = "greenhouse"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._root: str | None = None   # cached working region root

    # -- public API -------------------------------------------------------

    def fetch(self) -> list[Job]:
        raw_jobs = self._get_jobs()
        company = self._company_name()
        fetched_at = now_iso()
        return [self._to_job(j, company, fetched_at) for j in raw_jobs]

    # -- HTTP -------------------------------------------------------------

    def _get(self, suffix: str) -> requests.Response:
        """GET `{root}/{board}{suffix}`, trying each region root on 404."""
        last: requests.Response | None = None
        roots = ([self._root] if self._root else list(API_ROOTS))
        for root in roots:
            resp = self._session.get(
                f"{root}/{self.board}{suffix}",
                params={"content": "true"} if suffix.endswith("/jobs") else None,
                timeout=TIMEOUT,
            )
            if resp.status_code == 404:
                last = resp
                continue
            resp.raise_for_status()
            self._root = root            # remember the region that worked
            return resp
        if last is not None:
            last.raise_for_status()
        raise RuntimeError("no greenhouse region responded")

    def _get_jobs(self) -> list[dict]:
        return self._get("/jobs").json().get("jobs", [])

    def _company_name(self) -> str:
        """Fetch the board's display name; fall back to the token."""
        try:
            return self._get("").json().get("name") or self.board
        except requests.RequestException:
            return self.board

    # -- mapping ----------------------------------------------------------

    def _to_job(self, data: dict, company: str, fetched_at: str) -> Job:
        location = (data.get("location") or {}).get("name")
        metadata = data.get("metadata") or []

        salary = self._from_metadata(metadata, _SALARY_HINTS)
        employment_type = self._from_metadata(metadata, _TYPE_HINTS)

        remote_meta = self._from_metadata(metadata, _REMOTE_HINTS)
        if remote_meta is not None:
            remote = "remote" in remote_meta.lower()
        else:
            remote = detect_remote(location)

        # Greenhouse gives first_published on most boards; updated_at always.
        posted_at = data.get("first_published") or data.get("updated_at")
        url = data.get("absolute_url")
        title = data.get("title") or "(untitled)"

        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(data.get("id")),
            title=title,
            company=company,
            location=location,
            description=html_to_text(data.get("content")),
            source_url=url,
            apply_url=url,  # Greenhouse listing page is also the apply page
            salary=salary,
            employment_type=employment_type,
            category=next(
                (d.get("name") for d in (data.get("departments") or [])
                 if d.get("name")), None
            ),
            remote=remote,
            posted_at=posted_at,
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )

    @staticmethod
    def _from_metadata(metadata: list[dict], hints: tuple[str, ...]) -> str | None:
        """Return the first metadata value whose name matches a hint."""
        for entry in metadata:
            name = (entry.get("name") or "").lower()
            if any(h in name for h in hints):
                value = entry.get("value")
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value if v)
                if value:
                    return str(value)
        return None
