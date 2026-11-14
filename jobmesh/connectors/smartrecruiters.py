"""SmartRecruiters connector.

Reads the public SmartRecruiters Posting API:
    https://api.smartrecruiters.com/v1/companies/{company}/postings

No API key. The list response is paginated ({content, totalFound, offset,
limit}). The full description lives on a per-posting detail endpoint; to
keep one board to a few requests, this connector indexes the list fields
(title, company, location, type, date, link) and leaves the description
to be enriched later.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from .base import Connector

API_ROOT = "https://api.smartrecruiters.com/v1/companies"
PUBLIC_ROOT = "https://jobs.smartrecruiters.com"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 20
PAGE_SIZE = 100
MAX_PAGES = 12  # safety cap (raised 13 nov. 2026: 500 -> 1200 postings/board to unlock capped boards)


class SmartRecruitersConnector(Connector):
    platform = "smartrecruiters"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        raw_jobs = self._get_jobs()
        fetched_at = now_iso()
        return [self._to_job(j, fetched_at) for j in raw_jobs]

    def _get_jobs(self) -> list[dict]:
        url = f"{API_ROOT}/{self.board}/postings"
        offset, collected = 0, []
        for _ in range(MAX_PAGES):
            resp = self._session.get(
                url, params={"limit": PAGE_SIZE, "offset": offset},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            body = resp.json()
            page = body.get("content", [])
            collected.extend(page)
            total = body.get("totalFound", len(collected))
            offset += PAGE_SIZE
            if len(page) < PAGE_SIZE or offset >= total:
                break
        return collected

    def _to_job(self, data: dict, fetched_at: str) -> Job:
        company_obj = data.get("company") or {}
        company = company_obj.get("name") or self.board

        location = self._format_location(data.get("location") or {})
        remote_flag = (data.get("location") or {}).get("remote")
        remote = remote_flag if isinstance(remote_flag, bool) else detect_remote(location)

        emp = data.get("typeOfEmployment") or {}
        employment_type = emp.get("label") if isinstance(emp, dict) else None

        title = data.get("name") or "(untitled)"
        job_id = str(data.get("id"))
        url = f"{PUBLIC_ROOT}/{self.board}/{job_id}"

        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=job_id,
            title=title,
            company=company,
            location=location,
            description=None,  # enrich via the per-posting detail endpoint later
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=employment_type,
            category=(data.get("department") or {}).get("label")
            or (data.get("function") or {}).get("label"),
            remote=remote,
            posted_at=data.get("releasedDate"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )

    @staticmethod
    def _format_location(loc: dict) -> str | None:
        parts = [loc.get("city"), loc.get("region"), loc.get("country")]
        joined = ", ".join(p for p in parts if p)
        return joined or None
