"""JOIN connector — public, keyless company career pages.

JOIN (join.com) is an ATS for small teams, very common across the DACH
region and wider Europe (20k+ hiring companies). Each company has a
public career page at:
    https://join.com/companies/{slug}

The page is server-rendered (Next.js); its open jobs live in the embedded
``__NEXT_DATA__`` JSON at ``props.pageProps.pageData.jobs.items``, with
``pageData.company`` for the employer name and ``jobs.pagination`` for
paging. No auth is required. A board is the company slug (e.g. "join").

The list carries no job description; title/location/type/category/date and
the per-job detail URL are mapped.
"""

from __future__ import annotations

import json
import re

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key, normalize_workplace
from .base import Connector

BASE = "https://join.com/companies"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 20
MAX_PAGES = 20  # safety cap for very large career pages

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


class JoinConnector(Connector):
    platform = "join"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        fetched_at = now_iso()
        jobs: list[Job] = []
        company_name = self.board
        page = 1
        while page <= MAX_PAGES:
            suffix = f"?page={page}" if page > 1 else ""
            resp = self._session.get(f"{BASE}/{self.board}{suffix}", timeout=TIMEOUT)
            resp.raise_for_status()
            page_data = self._page_data(resp.text)
            company = page_data.get("company") or {}
            company_name = company.get("name") or company_name
            block = page_data.get("jobs") or {}
            for j in block.get("items") or []:
                jobs.append(self._to_job(j, company_name, fetched_at))
            pagination = block.get("pagination") or {}
            if page >= (pagination.get("pageCount") or 1):
                break
            page += 1
        return jobs

    def _page_data(self, html: str) -> dict:
        m = _NEXT_DATA_RE.search(html)
        if not m:
            raise ValueError(
                f"join: __NEXT_DATA__ not found for board {self.board!r}"
            )
        data = json.loads(m.group(1))
        return data.get("props", {}).get("pageProps", {}).get("pageData") or {}

    def _to_job(self, data: dict, company_name: str, fetched_at: str) -> Job:
        title = data.get("title") or "(untitled)"
        city = data.get("city") or {}
        location = (
            ", ".join(x for x in (city.get("cityName"), city.get("countryName")) if x)
            or None
        )
        workplace_raw = data.get("workplaceType")
        remote = (
            str(workplace_raw).upper() == "REMOTE"
            or bool(data.get("remoteType"))
            or detect_remote(location)
        )
        id_param = data.get("idParam") or data.get("id")
        url = (
            f"{BASE}/{self.board}/jobs/{id_param}"
            if id_param
            else f"{BASE}/{self.board}"
        )
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(data.get("id") or id_param or title),
            title=title,
            company=company_name,
            location=location,
            description=None,
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=(data.get("employmentType") or {}).get("name"),
            workplace_type=normalize_workplace(workplace_raw),
            category=(data.get("category") or {}).get("name"),
            remote=remote,
            posted_at=data.get("createdAt"),
            dedup_key=make_dedup_key(title, company_name, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
