"""EURES connector — the EU's job mobility portal (public search API).

EURES (europa.eu/eures) exposes a keyless public JSON search API over the EU/EEA
job market (millions of postings), like the national portals already indexed:

    POST https://europa.eu/eures/api/jv-searchengine/public/jv-search/search
         {"resultsPerPage":100,"page":N,"sortSearch":"BEST_MATCH","keywords":[], ...}
    -> {"numberRecords": 1923508,
        "jvs": [ {id, title, description, employer:{name,website},
                  locationMap:{"BE":["BE213"]}, creationDate:<epoch ms>,
                  positionScheduleCodes:[...], numberOfPosts}, ... ]}

robots.txt on europa.eu does not disallow /eures/api/. Capped at a few thousand
postings so this very large portal does not dominate the index. ``board`` is
unused (single portal); default "eures".
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed
from .base import Connector

TIMEOUT = 30
API = "https://europa.eu/eures/api/jv-searchengine/public/jv-search/search"
# europa.eu WAF rejects a bare bot UA (400) — Mozilla-compatible form keeps our
# identity + contact URL while passing the gateway, like the UN/JobBoard feeds.
_UA = "Mozilla/5.0 (compatible; JobmeshBot/0.1; +https://github.com/TatianaTchouakam/jobmesh)"
_HDRS = {"User-Agent": _UA, "Accept": "application/json",
         "Accept-Language": "en", "Origin": "https://europa.eu",
         "Referer": "https://europa.eu/eures/portal/jv-se/search?lang=en"}
DETAIL = "https://europa.eu/eures/portal/jv-se/jv-details/"
PAGE_SIZE = 50   # europa.eu caps resultsPerPage at 50 (100 -> 400)
MAX_JOBS = 5000

_BODY = {"sortSearch": "BEST_MATCH", "keywords": [], "publicationPeriod": None,
         "occupationUris": [], "skillUris": [], "requiredExperienceCodes": [],
         "positionScheduleCodes": [], "sectorCodes": [],
         "educationAndQualificationLevelCodes": [], "positionOfferingCodes": [],
         "locationCodes": [], "euresFlagCodes": [], "otherBenefitsCodes": [],
         "requiredLanguages": [], "minNumberPost": None, "sessionId": "jobmesh"}

_COUNTRY = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia",
    "CY": "Cyprus", "CZ": "Czechia", "DK": "Denmark", "EE": "Estonia",
    "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece",
    "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LV": "Latvia",
    "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SK": "Slovakia",
    "SI": "Slovenia", "ES": "Spain", "SE": "Sweden", "IS": "Iceland",
    "LI": "Liechtenstein", "NO": "Norway", "CH": "Switzerland", "UK": "United Kingdom",
}


def _location(loc_map) -> str | None:
    if not isinstance(loc_map, dict) or not loc_map:
        return None
    names = [_COUNTRY.get(cc, cc) for cc in loc_map.keys()]
    return ", ".join(names) or None


def _posted(epoch_ms) -> str | None:
    if not isinstance(epoch_ms, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


class EuresConnector(Connector):
    platform = "eures"

    def __init__(self, board: str = "eures", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", _UA)

    def fetch(self) -> list[Job]:
        if not robots_allowed(API, self._session):
            return []
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        pages = (MAX_JOBS // PAGE_SIZE) + 1
        for page in range(1, pages + 1):
            body = dict(_BODY, resultsPerPage=PAGE_SIZE, page=page)
            resp = self._session.post(API, json=body, timeout=TIMEOUT, headers=_HDRS)
            resp.raise_for_status()
            rows = (resp.json() or {}).get("jvs") or []
            if not rows:
                break
            for row in rows:
                job = self._to_job(row, at)
                if job is not None and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    jobs.append(job)
            if len(jobs) >= MAX_JOBS:
                break
        return jobs

    def _to_job(self, row: dict, at: str) -> Job | None:
        jid = row.get("id")
        if not jid:
            return None
        title = row.get("title")
        title = (title if isinstance(title, str) else str(title or "")).strip() or "(untitled)"
        emp = row.get("employer") or {}
        company = (emp.get("name") if isinstance(emp, dict) else None) or "EURES employer"
        location = _location(row.get("locationMap"))
        sched = row.get("positionScheduleCodes") or []
        employment = sched[0] if sched else None
        desc = row.get("description")
        url = f"{DETAIL}{jid}?lang=en"
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(jid),
            title=title,
            company=company.strip() or "EURES employer",
            location=location,
            description=html_to_text(desc) if desc else None,
            source_url=url,
            apply_url=url,
            employment_type=employment,
            remote=detect_remote(f"{location or ''} {title}"),
            posted_at=_posted(row.get("creationDate")),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )
