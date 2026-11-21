"""Vantaa connector — the City of Vantaa (Finland) open jobs API.

The City of Vantaa publishes its open positions as a keyless JSON array on
its public GIS open-data host (robots.txt absent / 404, nothing disallowed):

    GET https://gis.vantaa.fi/rest/tyopaikat/v1/kaikki
    -> [ {id, organisaatio, ammattiala, tyotehtava, tyoavain, osoite,
          haku_paattyy_pvm, x, y, linkki}, ... ]

``tyotehtava`` is the role title, ``linkki`` the apply URL (carrying a stable
``jid``), ``osoite`` the address, ``ammattiala`` the occupation field. No key.
``board`` is ignored; use "all".
"""

from __future__ import annotations

import re

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 25
API = "https://gis.vantaa.fi/rest/tyopaikat/v1/kaikki"
_JID = re.compile(r"jid=(\d+)")
COMPANY = "City of Vantaa"


class VantaaConnector(Connector):
    platform = "vantaa"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        if not robots_allowed(API, self._session):
            return []
        resp = self._session.get(API, timeout=TIMEOUT)
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            rows = rows.get("features") or rows.get("results") or []
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for row in rows:
            row = row.get("properties", row) if isinstance(row, dict) else {}
            title = (row.get("tyotehtava") or "").strip()
            if not title:
                continue
            url = row.get("linkki") or row.get("tyoavain")
            m = _JID.search(url or "")
            jid = m.group(1) if m else str(row.get("id") or title)
            if jid in seen:
                continue
            seen.add(jid)
            location = (row.get("osoite") or "").strip() or "Vantaa, Finland"
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=str(jid),
                title=title,
                company=COMPANY,
                location=location,
                description=(row.get("organisaatio") or "").strip() or None,
                source_url=url,
                apply_url=url,
                category=(row.get("ammattiala") or "").strip() or None,
                remote=detect_remote(f"{location} {title}"),
                posted_at=None,
                dedup_key=make_dedup_key(title, COMPANY, location),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
        return jobs
