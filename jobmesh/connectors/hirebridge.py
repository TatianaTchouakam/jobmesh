"""HireBridge connector — public career-center job list (server-rendered HTML).

HireBridge career centers live at::

    https://recruit.hirebridge.com/v3/jobs/list.aspx?cid={cid}

The full job list is rendered server-side (no JS, no API key). Each row::

    <a href="/v3/Jobs/JobDetails.aspx?cid=5535&jid=393832&bid=1">Management Internship</a>

robots.txt on recruit.hirebridge.com disallows only /application, /company and
/jobseeker* — the /v3/jobs/ list and /v3/Jobs/JobDetails pages are allowed.

A ``board`` is the numeric client id ``cid`` (e.g. "5535").
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
HOST = "https://recruit.hirebridge.com"

_ROW = re.compile(
    r'href="(/v3/Jobs/JobDetails\.aspx\?cid=\d+&jid=(\d+)&bid=(\d+))"[^>]*>([^<]+)</a>',
    re.IGNORECASE)
_TITLE = re.compile(r"<title>([^<]+)</title>", re.IGNORECASE)


class HireBridgeConnector(Connector):
    platform = "hirebridge"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.cid = board.strip()
        self._url = f"{HOST}/v3/jobs/list.aspx?cid={self.cid}"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        resp = self._session.get(self._url, timeout=TIMEOUT)
        resp.raise_for_status()
        text = resp.text.replace("&amp;", "&")
        company = self._company(text)
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for m in _ROW.finditer(text):
            path, jid, bid, title = m.group(1), m.group(2), m.group(3), m.group(4)
            if jid in seen:
                continue
            seen.add(jid)
            title = html.unescape(title).strip() or "(untitled)"
            url = HOST + path
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=jid,
                title=title,
                company=company,
                location=None,
                description=None,
                source_url=url,
                apply_url=url,
                remote=detect_remote(title),
                posted_at=None,
                dedup_key=make_dedup_key(title, company, None),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
        return jobs

    @staticmethod
    def _company(text: str) -> str:
        m = _TITLE.search(text)
        if not m:
            return ""
        name = html.unescape(m.group(1)).strip()
        name = re.sub(r"\s*Career Center\s*$", "", name, flags=re.IGNORECASE).strip()
        return name
