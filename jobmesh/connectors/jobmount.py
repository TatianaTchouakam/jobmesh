"""JobMount connector — public per-category RSS feeds.

JobMount powers municipal/association job boards (e.g. AWC JobNet at
jobnet.wacities.org). Each category page declares an RSS feed in <head>
(``application/rss+xml``) reachable at ``{board}?rss`` and returning up to
100 <item>s:

    <title>Water Resources Specialist I or II</title>
    <link>https://jobnet.wacities.org/career/45340/Water-...?utm...</link>
    <description>City of Port Townsend.\n, Port Townsend <br />...</description>
    <category>Public Works/Maintenance, Water/Wastewater</category>

Company and location live at the head of <description>
("{Company}.\n, {Location} <br />"). ``board`` is "{host}/{category-slug}"
(e.g. "jobnet.wacities.org/public-works-maintenance"); several category
boards for one host dedup in the index. robots.txt disallows only
/admin, /candidate/* and /employer/* — /career/ and ?rss are allowed.
"""

from __future__ import annotations

import html
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
_ID = re.compile(r"/career/(\d+)/")


def _tag(block: str, name: str) -> str | None:
    m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    val = m.group(1).strip()
    cd = re.match(r"^<!\[CDATA\[(.*?)\]\]>$", val, re.DOTALL)
    if cd:
        val = cd.group(1).strip()
    return html.unescape(val).strip() or None


def _company_location(desc: str | None) -> tuple[str, str | None]:
    if not desc:
        return "JobMount employer", None
    head = re.split(r"<br", desc, 1, flags=re.IGNORECASE)[0]
    company, _, loc = head.partition(".\n,")
    if not loc:
        company, _, loc = head.partition(", ")
    company = company.strip().rstrip(".").strip() or "JobMount employer"
    return company, (loc.strip() or None)


def _date(s: str | None) -> str | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s.replace(" Z", " +0000")).isoformat()
    except (TypeError, ValueError):
        return None


class JobMountConnector(Connector):
    platform = "jobmount"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._url = f"https://{board}?rss"

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
            m = _ID.search(link or "")
            jid = m.group(1) if m else (link or "").rsplit("/", 1)[-1]
            if not jid or jid in seen:
                continue
            seen.add(jid)
            title = _tag(block, "title") or "(untitled)"
            company, loc = _company_location(_tag(block, "description"))
            cat = _tag(block, "category")
            url = (link or "").split("?")[0] or link
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=str(jid),
                title=title,
                company=company,
                location=loc,
                description=html_to_text(_tag(block, "description")) if _tag(block, "description") else None,
                source_url=url,
                apply_url=url,
                category=cat,
                remote=detect_remote(f"{loc or ''} {title}"),
                posted_at=_date(_tag(block, "pubDate")),
                dedup_key=make_dedup_key(title, company, loc),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
            if len(jobs) >= MAX_JOBS:
                break
        return jobs
