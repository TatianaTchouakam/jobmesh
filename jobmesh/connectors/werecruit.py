"""WeRecruit connector — public recruitment space (embedded JSON in server HTML).

WeRecruit career spaces live at::

    https://careers.werecruit.io/en/{account}

Each offer is an embedded JSON object in the server-rendered page, keyed off
its public URL::

    "Url":"https://careers.werecruit.io/en/atlantis/offers/{slug}-{id}",
    ... "TitleTranslated":"Compositor - Mid/Senior level F/M",
    "TimeTranslated":"Full time", "DepartmentId":"38---santa-cruz-de-tenerife"

robots.txt is ``User-agent: * / Allow: /`` — everything allowed. The numeric
``-{id}`` suffix distinguishes real offers from the "spontaneous application"
entry (hex id), which is skipped.

A ``board`` is the account slug, e.g. "atlantis".
"""

from __future__ import annotations

import html
import re

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
HOST = "https://careers.werecruit.io"

_URL = re.compile(
    r'"Url":"(https://careers\.werecruit\.io/en/[a-z0-9]+/offers/[a-z0-9-]+-(\d+))"',
    re.IGNORECASE)
_DEPT_PREFIX = re.compile(r"^\d+---")


def _field(window: str, key: str) -> str | None:
    m = re.search(r'"' + key + r'":"([^"]*)"', window)
    return html.unescape(m.group(1)).strip() if m else None


def _location(dept: str | None) -> str | None:
    if not dept:
        return None
    dept = _DEPT_PREFIX.sub("", dept)
    dept = dept.replace("-", " ").strip()
    return dept.title() or None


class WeRecruitConnector(Connector):
    platform = "werecruit"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.account = board.strip().strip("/")
        self._url = f"{HOST}/en/{self.account}"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        resp = self._session.get(self._url, timeout=TIMEOUT)
        resp.raise_for_status()
        text = resp.text
        company = self.account.replace("-", " ").title()
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for m in _URL.finditer(text):
            url, jid = m.group(1), m.group(2)
            if jid in seen:
                continue
            seen.add(jid)
            window = text[m.end():m.end() + 900]
            title = _field(window, "TitleTranslated") or "(untitled)"
            employment = _field(window, "TimeTranslated")
            location = _location(_field(window, "DepartmentId"))
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=jid,
                title=title,
                company=company,
                location=location,
                description=None,
                source_url=url,
                apply_url=url,
                employment_type=employment or None,
                remote=detect_remote(f"{location or ''} {title}"),
                posted_at=_field(window, "PublicationStartDate"),
                dedup_key=make_dedup_key(title, company, location),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
        return jobs
