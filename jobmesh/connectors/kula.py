"""Kula.ai connector — official public RSS feed per company.

Kula's job list is a SPA served from the robots-disallowed /api/ route, but
every Kula career site also publishes an official RSS feed that robots.txt
explicitly permits (``Allow: /``, only ``/api/`` and ``/*/portal`` are
disallowed):

    https://careers.kula.ai/{slug}/feed      ->  application/rss+xml

Each <item> carries namespaced ``job:`` fields:
    <title>...</title>
    <link>https://careers.kula.ai/{slug}/{id}/apply</link>
    <pubDate>...</pubDate>
    <category>...</category>
    <job:employmentType>FULL_TIME</job:employmentType>
    <job:workplace>OFFICE|REMOTE|HYBRID</job:workplace>
    <job:location>\n  City, Country\n  <flags>\n</job:location>

So this is the shared "official RSS feed" recipe, no token, no DOM scraping.
The feed carries no company name, so ``board`` is "slug|Company"
(e.g. "rocketlane|Rocketlane"); with no "|", the slug is used.
"""

from __future__ import annotations

import html
import re
from email.utils import parsedate_to_datetime

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key, normalize_workplace
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 25
MAX_JOBS = 1000

_ITEM = re.compile(r"<item\b[^>]*>(.*?)</item>", re.IGNORECASE | re.DOTALL)
_ID = re.compile(r"/(\d+)/apply")


def _tag(block: str, name: str) -> str | None:
    m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    val = m.group(1).strip()
    cd = re.match(r"^<!\[CDATA\[(.*?)\]\]>$", val, re.DOTALL)
    if cd:
        val = cd.group(1).strip()
    return html.unescape(val).strip() or None


def _location(raw: str | None) -> str | None:
    """job:location is multiline: 'City, Country\\n <flag>\\n <flag>'. Keep line 1."""
    if not raw:
        return None
    for line in raw.splitlines():
        line = line.strip()
        if line and line.lower() not in ("true", "false"):
            return line
    return None


def _date(s: str | None) -> str | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).isoformat()
    except (TypeError, ValueError):
        return None


class KulaConnector(Connector):
    platform = "kula"

    def __init__(self, board: str, session: requests.Session | None = None):
        slug, _, company = board.partition("|")
        super().__init__(slug.strip())
        self._slug = slug.strip()
        self._company = company.strip() or slug.strip().replace("-", " ").title()
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._url = f"https://careers.kula.ai/{self._slug}/feed"

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        resp = self._session.get(self._url, timeout=TIMEOUT)
        resp.raise_for_status()
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for block in _ITEM.findall(resp.text):
            link = _tag(block, "link") or _tag(block, "guid")
            m = _ID.search(link or "")
            jid = m.group(1) if m else (_tag(block, "job:referencenumber") or link)
            if not jid or jid in seen:
                continue
            seen.add(jid)
            title = _tag(block, "title") or "(untitled)"
            loc = _location(_tag(block, "job:location"))
            workplace = _tag(block, "job:workplace")
            desc = _tag(block, "description")
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=str(jid),
                title=title,
                company=self._company,
                location=loc,
                description=html_to_text(desc) if desc else None,
                source_url=link,
                apply_url=link,
                employment_type=_tag(block, "job:employmentType"),
                workplace_type=normalize_workplace(workplace) if workplace else None,
                category=_tag(block, "category"),
                remote=detect_remote(f"{workplace or ''} {loc or ''} {title}"),
                posted_at=_date(_tag(block, "pubDate")),
                dedup_key=make_dedup_key(title, self._company, loc),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
            if len(jobs) >= MAX_JOBS:
                break
        return jobs
