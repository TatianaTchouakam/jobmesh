"""Recruitee connector.

Reads the public Recruitee careers API:
    https://{company}.recruitee.com/api/offers/

No API key. Response is {"offers": [...]}, with the HTML description
included directly in the list response.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 20


class RecruiteeConnector(Connector):
    platform = "recruitee"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        raw_jobs = self._get_jobs()
        company = self.board.replace("-", " ").title()
        fetched_at = now_iso()
        return [self._to_job(j, company, fetched_at) for j in raw_jobs]

    def _get_jobs(self) -> list[dict]:
        url = f"https://{self.board}.recruitee.com/api/offers/"
        resp = self._session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("offers", [])

    def _to_job(self, data: dict, company: str, fetched_at: str) -> Job:
        location = data.get("location") or self._location_from_parts(data)

        remote_flag = data.get("remote")
        remote = remote_flag if isinstance(remote_flag, bool) else detect_remote(location)

        emp_code = data.get("employment_type_code")
        employment_type = emp_code.replace("_", " ").title() if emp_code else None

        title = data.get("title") or "(untitled)"
        url = data.get("careers_url")

        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(data.get("id")),
            title=title,
            company=company,
            location=location,
            description=html_to_text(data.get("description")),
            source_url=url,
            apply_url=data.get("careers_apply_url") or url,
            salary=None,
            employment_type=employment_type,
            remote=remote,
            posted_at=data.get("published_at") or data.get("created_at"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )

    @staticmethod
    def _location_from_parts(data: dict) -> str | None:
        parts = [data.get("city"), data.get("country_code")]
        joined = ", ".join(p for p in parts if p)
        return joined or None
