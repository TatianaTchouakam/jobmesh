"""Bundesagentur für Arbeit connector (Germany's federal job board).

The German Federal Employment Agency publishes its whole job board through
an official REST API. It covers EVERY sector across Germany — healthcare,
trades, logistics, retail, hospitality, administration, industry — so it is
the single best source of non-tech German roles.

    GET https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs
        ?size=100&page=1
    Header: X-API-Key: jobboerse-jobsuche

The API key is a fixed, documented public value used by the official job
search site itself — the same for everyone, with no registration. We pull a
bounded number of the most recent postings (no search term = all sectors)
so the index stays a reasonable size.

Docs: https://github.com/bundesAPI/jobsuche-api
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import make_dedup_key
from .base import Connector

API = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
# Documented public client id, used as the API key by the official site.
API_KEY = "jobboerse-jobsuche"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 30
SIZE = 100
MAX_PAGES = 20     # bounded: up to ~2,000 recent postings per run


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


class BundesagenturConnector(Connector):
    platform = "bundesagentur"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")
        self._session.headers.setdefault("X-API-Key", API_KEY)

    def fetch(self) -> list[Job]:
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            resp = self._session.get(
                API, params={"size": SIZE, "page": page}, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("stellenangebote") or data.get("jobs") or []
            if not batch:
                break
            for d in batch:
                job = self._to_job(d, at)
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
            if len(batch) < SIZE:
                break
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = _first(d, "titel", "stellenangebotsTitel", "beruf") or "(untitled)"
        company = _first(d, "arbeitgeber", "arbeitgeberName") or "Unbekannt"
        location = _format_location(d.get("arbeitsort"))
        ref = _first(d, "refnr", "referenznummer", "hashId") or title
        ext = d.get("externeUrl")
        url = ext or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}"
        # `beruf` (occupation) is a strong category signal; feed it to the
        # categoriser alongside the title.
        beruf = d.get("beruf")
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(ref),
            title=title, company=company, location=location,
            description=None,
            source_url=url, apply_url=url,
            salary=None,
            employment_type=_first(d, "arbeitszeit", "angebotsart"),
            category=beruf,
            remote=None,
            posted_at=_first(d, "aktuelleVeroeffentlichungsdatum",
                             "eintrittsdatum", "modifikationsTimestamp"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )


def _format_location(ort) -> str | None:
    if not ort:
        return None
    if isinstance(ort, str):
        return ort or None
    if isinstance(ort, dict):
        parts = [ort.get("ort"), ort.get("region")]
        loc = ", ".join(p for p in parts if p)
        land = ort.get("land")
        if land and land.lower() not in (loc or "").lower():
            loc = (loc + ", " + land) if loc else land
        return loc or None
    return None
