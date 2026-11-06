"""Ashby connector.

Reads the public Ashby job board API:
    https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true

No API key. Response is {"jobs": [...]}. With includeCompensation=true,
salary bands are included when the employer exposes them. Roles with
isListed=false are excluded (not meant for a public board).
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from .base import Connector

API_ROOT = "https://api.ashbyhq.com/posting-api/job-board"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 20


class AshbyConnector(Connector):
    platform = "ashby"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        raw_jobs = self._get_jobs()
        company = self.board.replace("-", " ").title()
        fetched_at = now_iso()
        jobs = []
        for data in raw_jobs:
            # Skip roles the employer hasn't listed on its public board.
            if data.get("isListed") is False:
                continue
            jobs.append(self._to_job(data, company, fetched_at))
        return jobs

    def _get_jobs(self) -> list[dict]:
        url = f"{API_ROOT}/{self.board}"
        resp = self._session.get(
            url, params={"includeCompensation": "true"}, timeout=TIMEOUT
        )
        resp.raise_for_status()
        return resp.json().get("jobs", [])

    def _to_job(self, data: dict, company: str, fetched_at: str) -> Job:
        location = data.get("location")

        is_remote = data.get("isRemote")
        if isinstance(is_remote, bool):
            remote = is_remote
        else:
            workplace = (data.get("workplaceType") or "").lower()
            if workplace == "remote":
                remote = True
            elif workplace in ("hybrid", "onsite", "on-site"):
                remote = False
            else:
                remote = detect_remote(location)

        title = data.get("title") or "(untitled)"
        job_url = data.get("jobUrl")

        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(data.get("id")),
            title=title,
            company=company,
            location=location,
            description=data.get("descriptionPlain"),
            source_url=job_url,
            apply_url=data.get("applyUrl") or job_url,
            salary=_salary(data.get("compensation")),
            employment_type=data.get("employmentType"),
            workplace_type=data.get("workplaceType"),
            category=data.get("department") or data.get("team"),
            remote=remote,
            posted_at=data.get("publishedAt"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )


def _salary(compensation) -> str | None:
    """Pull a human-readable salary band from Ashby's compensation object."""
    if isinstance(compensation, dict):
        summary = compensation.get("compensationTierSummary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    return None
