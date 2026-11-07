"""ReliefWeb connector (UN humanitarian / NGO jobs, worldwide).

ReliefWeb (run by UN OCHA) exposes an official, public, keyless API. It
lists humanitarian and development jobs from thousands of NGOs and
agencies, with a very strong presence across Africa and the Global South —
mostly non-tech roles (programme, logistics, health, WASH, finance, M&E).

    GET https://api.reliefweb.int/v1/jobs
        ?appname=jobmesh-jobindex&profile=full
        &limit=100&offset=0&sort[]=date.created:desc

`appname` is just a courtesy identifier (not a secret). `board` is
ignored; use "all".

Docs: https://apidoc.reliefweb.int/
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API = "https://api.reliefweb.int/v1/jobs"
APPNAME = "jobmesh-jobindex"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 30
LIMIT = 100
MAX_PAGES = 10     # bounded: up to ~1,000 most-recent jobs per run


def _names(seq) -> str | None:
    """Join the .name of a list of {name:...} descriptors."""
    if not isinstance(seq, list):
        return None
    out = [x.get("name") for x in seq if isinstance(x, dict) and x.get("name")]
    return ", ".join(out) if out else None


def _first_name(seq):
    if isinstance(seq, list):
        for x in seq:
            if isinstance(x, dict) and x.get("name"):
                return x["name"]
    return None


class ReliefWebConnector(Connector):
    platform = "reliefweb"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        at = now_iso()
        jobs: list[Job] = []
        for page in range(MAX_PAGES):
            resp = self._session.get(
                API,
                params={"appname": APPNAME, "profile": "full",
                        "limit": LIMIT, "offset": page * LIMIT,
                        "sort[]": "date.created:desc"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("data") or []
            if not batch:
                break
            jobs.extend(self._to_job(d, at) for d in batch)
            if len(batch) < LIMIT:
                break
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        f = d.get("fields") or {}
        title = f.get("title") or "(untitled)"
        company = _first_name(f.get("source")) or "NGO / Agency"
        # location: city + country
        city = _first_name(f.get("city"))
        country = _first_name(f.get("country"))
        location = ", ".join(p for p in (city, country) if p) or country
        dates = f.get("date") or {}
        url = f.get("url_alias") or f.get("url")
        body = html_to_text(f.get("body-html") or f.get("body")) \
            or html_to_text(f.get("how_to_apply"))
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(d.get("id") or url or title),
            title=title, company=company, location=location,
            description=body,
            source_url=url, apply_url=url,
            salary=None,
            employment_type=_first_name(f.get("type")),
            category=_names(f.get("career_categories")),
            remote=detect_remote(location),
            posted_at=dates.get("created"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
