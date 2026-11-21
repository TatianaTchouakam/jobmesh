"""NAV Arbeidsplassen connector — Norway's public job-vacancy feed.

NAV (the Norwegian Labour and Welfare Administration) publishes an official
JSON-feed of job vacancies for arbeidsplassen.no, covering most publicly
advertised Norwegian vacancies. Its API terms (arbeidsplassen.nav.no/vilkar-api)
explicitly grant the right to republish and show the ads ("Konsumenter av
APIet har rett til å republisere og vise mottekne jobbannonsar"), free, with
one duty: drop ads once they turn INACTIVE.

    GET https://pam-stilling-feed.nav.no/api/v1/feed?last=true
        Authorization: Bearer <token>
    -> { items: [ { id, url, title, date_modified,
                    _feed_entry: { uuid, status, title, businessName,
                                   municipal, sistEndret } } ], next_url, ... }

Each item's ``_feed_entry`` already carries the fields we index, so no N+1
detail call is needed. robots.txt on the API host is 404 (nothing disallowed).

Credentials (free, no employer account):
    NAV_TOKEN   — a stable private token (email nav.team.arbeidsplassen@nav.no,
                  accept the terms). If unset, the connector falls back to NAV's
                  public experimentation token at /api/publicToken (fine for a
                  demo; use the private token in production).
``board`` is ignored; use "all".
"""

from __future__ import annotations

import os

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key, normalize_date
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
BASE = "https://pam-stilling-feed.nav.no"
FEED = f"{BASE}/api/v1/feed"
PUBLIC_TOKEN_URL = f"{BASE}/api/publicToken"
STILLING_URL = "https://arbeidsplassen.nav.no/stillinger/stilling/"
MAX_PAGES = 5
MAX_JOBS = 2000


class NavConnector(Connector):
    platform = "nav"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def _token(self) -> str:
        tok = os.getenv("NAV_TOKEN")
        if tok:
            return tok.strip()
        # NAV publishes a public experimentation token; fine for a demo.
        r = self._session.get(PUBLIC_TOKEN_URL, timeout=TIMEOUT)
        r.raise_for_status()
        return r.text.strip().strip('"')

    def fetch(self) -> list[Job]:
        if not robots_allowed(FEED, self._session):
            return []
        headers = {"Authorization": f"Bearer {self._token()}",
                   "Accept": "application/json"}
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        url = f"{FEED}?last=true"
        for _ in range(MAX_PAGES):
            r = self._session.get(url, headers=headers, timeout=TIMEOUT)
            if r.status_code == 304:
                break
            r.raise_for_status()
            body = r.json() or {}
            items = body.get("items") or []
            if not items:
                break
            for item in items:
                job = self._to_job(item, at)
                if job is not None and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    jobs.append(job)
            if len(jobs) >= MAX_JOBS:
                break
            nxt = body.get("next_url")
            if not nxt:
                break
            url = nxt if nxt.startswith("http") else BASE + nxt
        return jobs

    def _to_job(self, item: dict, at: str) -> Job | None:
        fe = item.get("_feed_entry") or {}
        if (fe.get("status") or "").upper() != "ACTIVE":
            return None          # drop INACTIVE ads (NAV terms)
        uuid = fe.get("uuid") or item.get("id")
        if not uuid:
            return None
        title = (fe.get("title") or item.get("title") or "").strip() or "(untitled)"
        company = (fe.get("businessName") or "").strip() or "NAV employer"
        muni = (fe.get("municipal") or "").strip()
        location = f"{muni.title()}, Norway" if muni else "Norway"
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(uuid),
            title=title,
            company=company,
            location=location,
            description=None,
            source_url=f"{STILLING_URL}{uuid}",
            apply_url=f"{STILLING_URL}{uuid}",
            remote=detect_remote(f"{location} {title}"),
            posted_at=normalize_date(fe.get("sistEndret") or item.get("date_modified")),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )
