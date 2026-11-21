"""Rival (SilkRoad Recruiting) connector — public career list (server-rendered).

Rival / SilkRoad career sites live at::

    https://jobs.silkroad.com/{Tenant}/{Board}

The vacancy list is rendered server-side (no JS, no key). Each card::

    <a class="sr-panel" href="/RAA/RAACareers/jobs/3248">
      <div class="sr-panel__title">AI Hub - Capability &amp; Change Lead</div>
      <div class="sr-panel__location"><span class="sr-panel__meta">Adelaide, SA</span></div>
    </a>

robots.txt disallows only /bin/, /Content/, /Scripts/, /Views/, /*/*/Ajax/ …
— the board page and /jobs/ pages are allowed. Crawl-Delay: 10.

A ``board`` is ``{Tenant}/{Board}`` exactly as it appears in the job links,
e.g. "RAA/RAACareers".
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
HOST = "https://jobs.silkroad.com"
MAX_PAGES = 50

_JOB = re.compile(r'class="sr-panel"[^>]*href="([^"]+/jobs/(\d+))"([\s\S]*?)</a>', re.IGNORECASE)
_TITLE_IN = re.compile(r'sr-panel__title[^>]*>([\s\S]*?)</div>', re.IGNORECASE)
_LOC_IN = re.compile(r'sr-panel__meta[^>]*>([\s\S]*?)</span>', re.IGNORECASE)
_PAGE_TITLE = re.compile(r"<title>([^<|-]+)", re.IGNORECASE)


def _clean(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).strip()


class RivalConnector(Connector):
    platform = "rival"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.slug = board.strip().strip("/")
        self._url = f"{HOST}/{self.slug}"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        company = ""
        for page in range(1, MAX_PAGES + 1):
            url = self._url if page == 1 else f"{self._url}?page={page}"
            resp = self._session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            text = resp.text
            if not company:
                m = _PAGE_TITLE.search(text)
                company = _clean(m.group(1)) if m else self.slug.split("/")[0]
            new_on_page = 0
            for path, jid, inner in _JOB.findall(text):
                if jid in seen:
                    continue
                seen.add(jid)
                new_on_page += 1
                tm, lm = _TITLE_IN.search(inner), _LOC_IN.search(inner)
                title = _clean(tm.group(1)) if tm else "(untitled)"
                location = _clean(lm.group(1)) if lm else None
                url_job = HOST + path if path.startswith("/") else path
                jobs.append(Job(
                    source_platform=self.platform,
                    source_board=self.board,
                    source_job_id=jid,
                    title=title or "(untitled)",
                    company=company,
                    location=location or None,
                    description=None,
                    source_url=url_job,
                    apply_url=url_job,
                    remote=detect_remote(f"{location or ''} {title}"),
                    posted_at=None,
                    dedup_key=make_dedup_key(title, company, location),
                    first_seen=at,
                    last_checked=at,
                    is_open=True,
                ))
            if new_on_page == 0:
                break
        return jobs
