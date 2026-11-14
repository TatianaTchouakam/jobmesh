"""Jooble connector (job board, free API key).

Reads the public Jooble API:
    POST https://jooble.org/api/{apikey}
    body: {"keywords": "", "location": "<country or city>", "page": N}

Jooble aggregates listings from 70+ countries (including many African
markets) across ALL sectors, so it is a strong source for worldwide,
non-tech coverage. One `board` = one location string, e.g. "Nigeria",
"South Africa", "Germany"; use "all" for no location filter.

The API key is READ FROM THE ENVIRONMENT, never hard-coded:
    JOOBLE_API_KEY
Get it free at https://jooble.org/api/about. If it is missing, the
connector raises a clear error (logged as a normal fetch failure).
"""

from __future__ import annotations

import os
import time

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API_ROOT = "https://jooble.org/api"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25
# Jooble's default free key allows ~500 requests total. Keep page depth
# low (2 pages per location) so a handful of countries per ingest stays
# well inside the budget. Reply to Jooble's key email to raise the limit.
MAX_PAGES = 2


def _api_key() -> str:
    key = os.getenv("JOOBLE_API_KEY")
    if not key:
        raise RuntimeError(
            "Jooble API key missing: set JOOBLE_API_KEY "
            "(free at https://jooble.org/api/about)."
        )
    return key


class JoobleConnector(Connector):
    platform = "jooble"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Content-Type", "application/json")

    def fetch(self) -> list[Job]:
        key = _api_key()
        location = "" if (self.board or "all").lower() == "all" else self.board
        at = now_iso()
        jobs: list[Job] = []
        seen_ids: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            batch = self._get_page(key, location, page)
            if not batch:
                break
            fresh = 0
            for d in batch:
                jid = str(d.get("id") or d.get("link") or "")
                if jid and jid in seen_ids:
                    continue
                seen_ids.add(jid)
                jobs.append(self._to_job(d, location or "all", at))
                fresh += 1
            if fresh == 0:
                break   # pages started repeating -> stop
        return jobs

    def _get_page(self, key: str, location: str, page: int) -> list[dict]:
        url = f"{API_ROOT}/{key}"
        payload = {"keywords": "", "location": location, "page": page}
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                resp = self._session.post(url, json=payload, timeout=TIMEOUT)
                # Jooble throttles free keys hard (HTTP 429). Back off and
                # retry instead of failing the whole location immediately.
                if resp.status_code in (429, 503):
                    retry_after = resp.headers.get("Retry-After")
                    try:
                        wait = float(retry_after) if retry_after else 0.0
                    except ValueError:
                        wait = 0.0
                    wait = max(wait, 5.0 * (attempt + 1))
                    time.sleep(min(wait, 60.0))
                    continue
                resp.raise_for_status()
                return resp.json().get("jobs", []) or []
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
        if last_exc:
            raise last_exc  # type: ignore[misc]
        return []

    def _to_job(self, d: dict, board: str, at: str) -> Job:
        title = d.get("title") or "(untitled)"
        company = d.get("company") or "Unknown"
        location = d.get("location")
        url = d.get("link")
        salary = d.get("salary") or None

        return Job(
            source_platform=self.platform,
            source_board=board,
            source_job_id=str(d.get("id") or url or make_dedup_key(title, company, location)),
            title=title,
            company=company,
            location=location,
            description=html_to_text(d.get("snippet")),
            source_url=url,
            apply_url=url,
            salary=salary,
            employment_type=d.get("type"),
            category=None,   # Jooble gives no category; bucketed from the title
            remote=detect_remote(" ".join(x for x in (location, title) if x)),
            posted_at=d.get("updated"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )
