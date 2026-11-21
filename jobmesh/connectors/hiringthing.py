"""HiringThing connector — public careers page (server-rendered job cards).

HiringThing career sites live at::

    https://{sub}.hiringthing.com/jobs

Each job is a server-rendered card::

    <div class="job-container" data-job-id="1077765">
      ... <a href="/job/1077765/slug"><h2>Institutional Giving - Development Officer</h2></a>
      <div class="job-location"> Portland, OR </div>

robots.txt: ``User-agent: * / Disallow: /admin`` — /jobs and /job/ are allowed.
A ``board`` is the subdomain, e.g. "smart" (or a full white-label host with a dot).
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

_CARD = re.compile(r'class="job-container"[^>]*data-job-id="(\d+)"([\s\S]*?)(?=class="job-container"|</body>|$)',
                   re.IGNORECASE)
_HREF = re.compile(r'href="(/job/\d+/[^"]+)"', re.IGNORECASE)
_TITLE = re.compile(r"<h2[^>]*>([\s\S]*?)</h2>", re.IGNORECASE)
_LOC = re.compile(r'class="job-location"[^>]*>\s*([^<]+?)\s*</div>', re.IGNORECASE)
_PAGE_TITLE = re.compile(r"<title>\s*([^<]+?)\s*(?:Career Opportunities|Careers|</title>)", re.IGNORECASE)


def _clean(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).strip()


class HiringThingConnector(Connector):
    platform = "hiringthing"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        b = board.strip()
        self.host = f"https://{b}" if "." in b else f"https://{b}.hiringthing.com"
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
        company = _clean(m.group(1)) if m else ""
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for jid, block in _CARD.findall(text):
            if jid in seen:
                continue
            seen.add(jid)
            hm = _HREF.search(block)
            if not hm:
                continue
            tm = _TITLE.search(block)
            title = _clean(tm.group(1)) if tm else "(untitled)"
            lm = _LOC.search(block)
            location = _clean(lm.group(1)) if lm else None
            url = self.host + hm.group(1)
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=jid,
                title=title or "(untitled)",
                company=company,
                location=location or None,
                description=None,
                source_url=url,
                apply_url=url,
                remote=detect_remote(f"{location or ''} {title}"),
                posted_at=None,
                dedup_key=make_dedup_key(title, company, location),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
        return jobs
