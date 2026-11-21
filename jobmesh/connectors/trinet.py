"""TriNet Hire connector — public company career list (server-rendered table).

TriNet Hire career sites live at::

    https://app.trinethire.com/companies/{slug}/jobs

The job list is a server-rendered HTML table (no JS, no API key). Each row::

    <tr class="job" id="position_82">
      <td><a href="/companies/{slug}/jobs/126424-senior-accountant">Senior Accountant</a></td>
      <td class="type">Full-time</td>
      <td class="location">Hybrid or Remote</td>
    </tr>

robots.txt: the ``User-agent: *`` group is ``Allow: /`` — the per-path
``Disallow: /`` entries apply only to named AI-training crawlers (GPTBot,
ClaudeBot, CCBot, ...), not to a job-indexing bot; our robots helper checks
JobmeshBot's own user-agent, which is allowed.

A ``board`` is the full company slug, e.g. "22943-cabaletta-bio-inc".
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
HOST = "https://app.trinethire.com"

_ROW = re.compile(r'<tr class="job"[^>]*>([\s\S]*?)</tr>', re.IGNORECASE)
_LINK = re.compile(r'href="(/companies/[^"]+/jobs/(\d+)[^"]*)"[^>]*>([^<]+)</a>', re.IGNORECASE)
_TYPE = re.compile(r'<td class="type">([^<]*)</td>', re.IGNORECASE)
_LOC = re.compile(r'<td class="location">([^<]*)</td>', re.IGNORECASE)
_TITLE = re.compile(r"<title>\s*Careers at\s*([^<]+?)\s*</title>", re.IGNORECASE)


class TriNetConnector(Connector):
    platform = "trinet"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.slug = board.strip()
        self._url = f"{HOST}/companies/{self.slug}/jobs"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        resp = self._session.get(self._url, timeout=TIMEOUT)
        resp.raise_for_status()
        text = resp.text
        company = self._company(text)
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for block in _ROW.findall(text):
            lm = _LINK.search(block)
            if not lm:
                continue
            path, jid, title = lm.group(1), lm.group(2), lm.group(3)
            if jid in seen:
                continue
            seen.add(jid)
            title = html.unescape(title).strip() or "(untitled)"
            tm, locm = _TYPE.search(block), _LOC.search(block)
            employment = html.unescape(tm.group(1)).strip() if tm else None
            location = html.unescape(locm.group(1)).strip() if locm else None
            url = HOST + path
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=jid,
                title=title,
                company=company,
                location=location or None,
                description=None,
                source_url=url,
                apply_url=url,
                employment_type=employment or None,
                remote=detect_remote(f"{location or ''} {title}"),
                posted_at=None,
                dedup_key=make_dedup_key(title, company, location),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
        return jobs

    @staticmethod
    def _company(text: str) -> str:
        m = _TITLE.search(text)
        return html.unescape(m.group(1)).strip() if m else ""
