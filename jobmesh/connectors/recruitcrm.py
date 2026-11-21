"""Recruit CRM connector — public agency jobs page API (keyless).

Recruit CRM hosted jobs pages live at ``recruitcrm.io/jobs/{account}`` and are
fed by a keyless public API on a companion host::

    POST https://albatross.recruitcrm.io/v1/external-pages/jobs-by-account/get?account={account}
         {}
    -> {"data": {"jobs": [
          {"slug": "...", "srno": "255", "name": "Procurement Engineer",
           "companyname": "", "showcompany": 0, "city": "Mumbai",
           "locality": "Andheri East", "jdtext": "<p>...</p>"}, ...]}}

robots.txt on recruitcrm.io: the ``User-agent: *`` group is ``Allow: /`` (the
per-path Disallow entries apply only to named search/AI crawlers). The apply
link for each posting is ``recruitcrm.io/apply/{slug}``.

A ``board`` is the agency account name, e.g. "Intver_Global".
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
API = "https://albatross.recruitcrm.io/v1/external-pages/jobs-by-account/get"
SITE = "https://recruitcrm.io"


class RecruitCrmConnector(Connector):
    platform = "recruitcrm"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.account = board.strip()
        self._url = f"{API}?account={self.account}"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        # Robots is governed by the CONTENT host recruitcrm.io (its `User-agent: *`
        # group is `Allow: /`); the jobs are served to that public page from the
        # albatross infra API host, which is pure transport.
        if not robots_allowed(f"{SITE}/jobs/{self.account}", self._session):
            return []
        # The external-pages API gates on Origin/Referer (embedded-widget API),
        # so present the public jobs page as the caller.
        headers = {
            "Origin": SITE,
            "Referer": f"{SITE}/jobs/{self.account}",
            "Accept": "application/json",
        }
        resp = self._session.post(self._url, json={}, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        rows = data.get("jobs") or []
        at = now_iso()
        account_name = self.account.replace("_", " ").strip()
        jobs: list[Job] = []
        seen: set[str] = set()
        for row in rows:
            slug = row.get("slug")
            jid = str(row.get("srno") or slug or "")
            if not slug or jid in seen:
                continue
            seen.add(jid)
            title = (row.get("name") or "(untitled)").strip() or "(untitled)"
            location = ", ".join(
                p for p in (row.get("locality"), row.get("city")) if p) or None
            company = (row.get("companyname") or "").strip() if row.get("showcompany") else ""
            company = company or account_name
            url = f"{SITE}/apply/{slug}"
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=jid,
                title=title,
                company=company,
                location=location,
                description=html_to_text(row.get("jdtext")) if row.get("jdtext") else None,
                source_url=url,
                apply_url=url,
                remote=detect_remote(f"{location or ''} {title}"),
                posted_at=None,
                dedup_key=make_dedup_key(title, company, location),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
        return jobs
