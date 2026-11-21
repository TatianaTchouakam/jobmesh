"""FirstStage connector — public jobs page (server-rendered card list).

FirstStage career pages live at::

    https://{sub}.firststage.co/jobs

Each job is an anchor card in the server HTML::

    <a href="https://first.firststage.co/jobs/{id}/view?layout=list">
      <span class="font-medium ...link-text...">Founding Engineer</span>
      <span>...<svg class="lucide-map-pin">...</svg> London, United Kingdom </span>
    </a>

No robots.txt (SPA 404) — fail-open. A ``board`` is the subdomain, e.g. "firststage".
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

_JOB = re.compile(
    r'<a[^>]*href="(https://[a-z0-9-]+\.firststage\.co/jobs/([A-Za-z0-9]+)/view[^"]*)"[^>]*>([\s\S]*?)</a>',
    re.IGNORECASE)
_TITLE = re.compile(r'<span class="font-medium[^"]*"[^>]*>([^<]+)</span>', re.IGNORECASE)
_LOC = re.compile(r'lucide-map-pin[\s\S]*?</svg>\s*([^<]+?)\s*</span>', re.IGNORECASE)
_PAGE_TITLE = re.compile(r"<title>\s*Jobs at\s*([^<|]+?)\s*(?:\||</title>)", re.IGNORECASE)


class FirstStageConnector(Connector):
    platform = "firststage"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.sub = board.strip()
        self.host = f"https://{self.sub}.firststage.co"
        self._url = f"{self.host}/jobs"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        resp = self._session.get(self._url, timeout=TIMEOUT)
        resp.raise_for_status()
        text = resp.text
        m = _PAGE_TITLE.search(text)
        company = html.unescape(m.group(1)).strip() if m else self.sub.title()
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for url, jid, inner in _JOB.findall(text):
            if jid in seen:
                continue
            seen.add(jid)
            tm = _TITLE.search(inner)
            title = html.unescape(tm.group(1)).strip() if tm else "(untitled)"
            lm = _LOC.search(inner)
            location = html.unescape(lm.group(1)).strip() if lm else None
            detail = url.split("?")[0]
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=jid,
                title=title or "(untitled)",
                company=company,
                location=location or None,
                description=None,
                source_url=detail,
                apply_url=detail,
                remote=detect_remote(f"{location or ''} {title}"),
                posted_at=None,
                dedup_key=make_dedup_key(title, company, location),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
        return jobs
