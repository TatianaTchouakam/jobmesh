"""JazzHR connector — career boards on {board}.applytojob.com.

JazzHR hosts each customer's careers page at `{board}.applytojob.com`, where the
list of open roles is server-rendered as `<li class="list-group-item">` rows —
each with the title, apply link (`/apply/{code}/{slug}`) and a location marker.
No token, no JSON API needed; one keyless GET of the board page. A `board` is
the slug before `.applytojob.com` (e.g. "easeinc").
"""

from __future__ import annotations

import html
import re

import requests

from ..models import Job, now_iso
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30

_ITEM = re.compile(r'<li class="list-group-item">(.*?)</li>', re.S)
_LINK = re.compile(
    r'<a\s+href="(https?://[^"]*?/apply/([A-Za-z0-9]+)/[^"]*)"[^>]*>(.*?)</a>', re.S)
_LOC = re.compile(r"fa-map-marker'?></i>\s*([^<]+)", re.S)
_TAGS = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_TAGS.sub("", text)).strip()


class JazzHrConnector(Connector):
    platform = "jazzhr"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._url = f"https://{board}.applytojob.com/"

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        resp = self._session.get(self._url, timeout=TIMEOUT)
        resp.raise_for_status()
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for block in _ITEM.findall(resp.text):
            link = _LINK.search(block)
            if not link:
                continue
            apply_url, code, raw_title = link.group(1), link.group(2), link.group(3)
            title = _clean(raw_title)
            if not title or code in seen:
                continue
            seen.add(code)
            loc = _LOC.search(block)
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=code,
                title=title,
                company=self.board,
                location=_clean(loc.group(1)) if loc else None,
                source_url=apply_url,
                apply_url=apply_url,
            ))
        return jobs
