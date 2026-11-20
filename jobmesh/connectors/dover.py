"""Dover connector — public, keyless job-board feed.

Dover (jobs.dover.com) hosts one career board per company. Each board
exposes a public, unauthenticated JSON feed:

    GET https://jobs.dover.com/feed/v1/boards/{tenant}/jobs
    -> {"jobs": [ {id, title, company_name, content, location, ...} ]}

The whole platform is discoverable: a single careers sitemap lists every
tenant, so the special board token "all" self-discovers and fetches them
all (bounded, concurrent). A specific tenant slug fetches just that board.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, html_to_text, make_dedup_key
from .base import Connector
from ..robots import allowed as robots_allowed, UA_TOKEN, USER_AGENT

ROOT = "https://jobs.dover.com"
CAREERS_SITEMAP = f"{ROOT}/feed/careers_sitemap"
USER_AGENT = "JobmeshBot/0.1 (+https://github.com/TatianaTchouakam/jobmesh)"
TIMEOUT = 20
MAX_BOARDS = int(os.getenv("DOVER_MAX_BOARDS", "3000"))
WORKERS = int(os.getenv("DOVER_WORKERS", "16"))

_TENANT_RE = re.compile(r"https://jobs\.dover\.com/([a-z0-9][a-z0-9-]*)", re.I)
_SKIP = {"feed", "api", "sitemap", "assets", "static"}


class DoverConnector(Connector):
    platform = "dover"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    # -- discovery ---------------------------------------------------------
    def _tenants(self) -> list[str]:
        resp = self._session.get(CAREERS_SITEMAP, timeout=TIMEOUT)
        resp.raise_for_status()
        seen, out = set(), []
        for m in _TENANT_RE.finditer(resp.text):
            t = m.group(1).lower()
            if t in _SKIP or t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out[:MAX_BOARDS]

    def _fetch_board(self, tenant: str, fetched_at: str) -> list[Job]:
        _url = f"{ROOT}/feed/v1/boards/{tenant}/jobs"
        if not robots_allowed(_url, self._session):
            return []
    def _fetch_board(self, tenant: str, fetched_at: str) -> list[Job]:
        resp = self._session.get(
            f"{ROOT}/feed/v1/boards/{tenant}/jobs", timeout=TIMEOUT
        )
        resp.raise_for_status()
        items = resp.json().get("jobs") or []
        return [self._to_job(j, tenant, fetched_at) for j in items]

    # -- fetch -------------------------------------------------------------
    def fetch(self) -> list[Job]:
        fetched_at = now_iso()
        if self.board != "all":
            return self._fetch_board(self.board, fetched_at)

        tenants = self._tenants()
        jobs: list[Job] = []
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(self._fetch_board, t, fetched_at): t for t in tenants}
            for fut in as_completed(futs):
                try:
                    jobs.extend(fut.result())
                except Exception:
                    # one dead board must not fail the whole platform run
                    continue
        return jobs

    # -- mapping -----------------------------------------------------------
    def _to_job(self, data: dict, tenant: str, fetched_at: str) -> Job:
        title = data.get("title") or "(untitled)"
        company = data.get("company_name") or tenant
        loc = (data.get("location") or {})
        location = loc.get("name") if isinstance(loc, dict) else (loc or None)
        remote_raw = str(data.get("remote") or "").lower()
        remote = remote_raw in ("only", "yes", "true", "remote") or detect_remote(location)
        url = data.get("absolute_url")
        return Job(
            source_platform=self.platform,
            source_board=tenant,
            source_job_id=str(data.get("id") or data.get("internal_job_id") or title),
            title=title,
            company=company,
            location=location,
            description=html_to_text(data.get("content")),
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=None,
            workplace_type="remote" if remote else None,
            category=(data.get("department") or [None])[0] if isinstance(data.get("department"), list) else None,
            remote=remote,
            posted_at=data.get("first_published") or data.get("updated_at"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
