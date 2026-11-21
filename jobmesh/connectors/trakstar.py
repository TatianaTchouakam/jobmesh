"""Trakstar Hire connector — public careers page (server-rendered, ex-Recruiterbox).

Trakstar Hire career sites live at::

    https://{sub}.hire.trakstar.com/

The openings list is rendered server-side (no JS, no key). Each card::

    <div class="js-card ... js-careers-page-job-list-item" data-href="/jobs/fk0znk2/">
      <a href="/jobs/fk0znk2/">
        <h3 class="... js-job-list-opening-name ..." title="Assistant Manager - Company Secretary"> ... </h3>
        <div class="... js-job-list-opening-loc ..." title="Mumbai"> ... </div>

robots.txt ``User-agent: *``: ``Allow: /`` (only /prepare* and
/published_jobs_list_v2* are disallowed) — the openings list is allowed.

A ``board`` is the subdomain, e.g. "bookmyshow".
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

_CARD = re.compile(r'data-href="/jobs/([\w]+)/"([\s\S]*?)(?=data-href="/jobs/[\w]+/"|</body>|$)',
                   re.IGNORECASE)
_NAME = re.compile(r'js-job-list-opening-name[^>]*\btitle="([^"]*)"', re.IGNORECASE)
_LOC = re.compile(r'js-job-list-opening-loc[^>]*\btitle="([^"]*)"', re.IGNORECASE)
_TITLE = re.compile(r"<title>\s*([^<|]+?)\s+jobs\b", re.IGNORECASE)


class TrakstarConnector(Connector):
    platform = "trakstar"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.sub = board.strip()
        self.host = f"https://{self.sub}.hire.trakstar.com"
        self._url = f"{self.host}/"
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
        for code, block in _CARD.findall(text):
            if code in seen:
                continue
            seen.add(code)
            nm = _NAME.search(block)
            title = html.unescape(nm.group(1)).strip() if nm else ""
            if not title:
                continue
            locm = _LOC.search(block)
            location = html.unescape(locm.group(1)).strip() if locm else None
            url = f"{self.host}/jobs/{code}/"
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=code,
                title=title,
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

    @staticmethod
    def _company(text: str) -> str:
        m = _TITLE.search(text)
        return html.unescape(m.group(1)).strip() if m else ""
