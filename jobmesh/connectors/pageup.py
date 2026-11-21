"""PageUp connector — public per-client RSS job feed.

PageUp People hosts each customer on ``careers.pageuppeople.com/{clientId}/``
and publishes a rich public RSS feed at ``/{clientId}/cw/en/rss`` (declared
``application/rss+xml``). Each <item> carries namespaced ``job:`` fields:

    <link>https://careers.pageuppeople.com/513/cw/en/job/701817</link>
    <title>...</title>
    <job:refNo>701817</job:refNo>
    <job:location>Campus|Caulfield campus</job:location>
    <job:workType>Fixed-term (Full-time)</job:workType>
    <job:applyLink>https://secure.dc2.pageuppeople.com/apply/...</job:applyLink>
    <job:category>Academic|Scholarship</job:category>
    <pubDate>Fri, 20 Nov 2026 01:30:00 Z</pubDate>

This public feed avoids the bot-challenged HTML listing entirely. The client
name is not in the feed, so ``board`` is "clientId|Company"
(e.g. "513|Monash University"); with no "|", company falls back. robots.txt
on careers.pageuppeople.com disallows only /api/, /me/ and /jobs/search.
"""

from __future__ import annotations

import re
from email.utils import parsedate_to_datetime

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 25
MAX_JOBS = 1000

_ITEM = re.compile(r"<item\b[^>]*>(.*?)</item>", re.IGNORECASE | re.DOTALL)


def _tag(block: str, name: str) -> str | None:
    m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    val = m.group(1).strip()
    cd = re.match(r"^<!\[CDATA\[(.*?)\]\]>$", val, re.DOTALL)
    if cd:
        val = cd.group(1).strip()
    return val or None


def _unescape(s: str | None) -> str | None:
    if not s:
        return s
    import html
    return html.unescape(s)


def _after_pipe(s: str | None) -> str | None:
    if not s:
        return None
    return s.split("|")[-1].strip() or None


def _date(s: str | None) -> str | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s.replace(" Z", " +0000")).isoformat()
    except (TypeError, ValueError):
        return None


class PageUpConnector(Connector):
    platform = "pageup"

    def __init__(self, board: str, session: requests.Session | None = None):
        client, _, company = board.partition("|")
        super().__init__(client.strip())
        self._company = company.strip() or "PageUp employer"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._url = f"https://careers.pageuppeople.com/{client.strip()}/cw/en/rss"

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        resp = self._session.get(self._url, timeout=TIMEOUT)
        resp.raise_for_status()
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for block in _ITEM.findall(resp.text):
            link = _tag(block, "link")
            ref = _tag(block, "job:refNo") or (link.rsplit("/", 1)[-1] if link else None)
            if not ref or ref in seen:
                continue
            seen.add(ref)
            title = _unescape(_tag(block, "title")) or "(untitled)"
            loc = _after_pipe(_unescape(_tag(block, "job:location")))
            cat = _after_pipe(_unescape(_tag(block, "job:category")))
            work = _unescape(_tag(block, "job:workType"))
            apply_link = _tag(block, "job:applyLink") or link
            desc = _tag(block, "job:description") or _tag(block, "description")
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=str(ref),
                title=title,
                company=self._company,
                location=loc,
                description=html_to_text(desc) if desc else None,
                source_url=link or apply_link,
                apply_url=apply_link,
                employment_type=work,
                category=cat,
                remote=detect_remote(f"{loc or ''} {work or ''} {title}"),
                posted_at=_date(_tag(block, "pubDate")),
                dedup_key=make_dedup_key(title, self._company, loc),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
            if len(jobs) >= MAX_JOBS:
                break
        return jobs
