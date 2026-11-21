"""Keka connector — public careers JSON API (India's leading SMB HR suite).

Keka hosts each customer at ``{sub}.keka.com/careers`` and serves the full
job list from a keyless JSON endpoint the embed widget calls:

    GET https://{host}/careers/api/embedjobs/default/active/{orgId}
    -> [ {id, title, description, departmentName, jobLocations:[{name,state,
          countryName,countryCode}], jobType, experience, jobNumber,
          salaryRange, publishedOn, skillNames}, ... ]

Job detail pages live at ``/careers/jobdetails/{id}``. robots.txt is
``Disallow: /`` with an explicit ``Allow: /careers/``, so the widget's
``/careers/api/...`` route is permitted. ``board`` is "host|orgId|Company"
(e.g. "hr.keka.com|<guid>|Keka"); jobType is an opaque integer enum, so we
leave employment_type unset rather than guess. No key, no CSRF.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key, normalize_date
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 25
MAX_JOBS = 1000


def _location(locs) -> str | None:
    if not isinstance(locs, list) or not locs:
        return None
    names, country = [], None
    for loc in locs:
        if not isinstance(loc, dict):
            continue
        n = (loc.get("name") or loc.get("city") or "").strip()
        if n and n not in names:
            names.append(n)
        country = country or (loc.get("countryName") or "").strip() or None
    place = " / ".join(names)
    if place and country and country not in place:
        return f"{place}, {country}"
    return place or country


class KekaConnector(Connector):
    platform = "keka"

    def __init__(self, board: str, session: requests.Session | None = None):
        host, _, rest = board.partition("|")
        org, _, company = rest.partition("|")
        super().__init__(host.strip())
        self._host = host.strip()
        self._org = org.strip()
        self._company = company.strip() or "Keka employer"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._url = f"https://{self._host}/careers/api/embedjobs/default/active/{self._org}"

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        resp = self._session.get(self._url, timeout=TIMEOUT, headers={"Accept": "application/json"})
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            rows = rows.get("jobs") or rows.get("data") or []
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for row in rows[:MAX_JOBS]:
            jid = row.get("id")
            if jid is None or str(jid) in seen:
                continue
            seen.add(str(jid))
            title = (row.get("title") or "(untitled)").strip()
            loc = _location(row.get("jobLocations"))
            desc = row.get("description") or row.get("excerpt")
            url = f"https://{self._host}/careers/jobdetails/{jid}"
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=str(jid),
                title=title,
                company=self._company,
                location=loc,
                description=html_to_text(desc) if desc else None,
                source_url=url,
                apply_url=url,
                category=(row.get("departmentName") or "").strip() or None,
                remote=detect_remote(f"{loc or ''} {title}"),
                posted_at=normalize_date(row.get("publishedOn")),
                dedup_key=make_dedup_key(title, self._company, loc),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
        return jobs
