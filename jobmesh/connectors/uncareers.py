"""UN Careers connector — United Nations official job RSS feed (Inspira).

The UN publishes every opening in a public, keyless RSS 2.0 feed::

    https://careers.un.org/jobfeed

Each <item> carries the title and link; the <description> holds structured
fields as "Key : Value <br>" (Job ID, Level, Job Network, Job Family,
Department/Office, Duty Station). We parse those to recover a real location
(Duty Station), the numeric Job ID, the department and the level.

careers.un.org serves no robots.txt (the path redirects to the home page),
so access is allowed by convention. A ``board`` is the feed host, default
"careers.un.org".
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
# careers.un.org's WAF 403s plain non-browser UAs. We keep our identity
# (JobmeshBot + contact URL) but use the long-standing "Mozilla/5.0
# (compatible; <bot>; +url)" convention that well-behaved crawlers use.
_UA = "Mozilla/5.0 (compatible; JobmeshBot/0.1; +https://github.com/TatianaTchouakam/jobmesh)"
_ID_IN_URL = re.compile(r"/jobSearchDescription/(\d+)", re.IGNORECASE)


def _field(desc: str, key: str) -> str | None:
    # fields look like "Duty Station : NEW YORK <br>"
    m = re.search(re.escape(key) + r"\s*:\s*(.*?)\s*(?:<br\s*/?>|$)", desc, re.IGNORECASE)
    if not m:
        return None
    val = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return val or None


class UnCareersConnector(Connector):
    platform = "uncareers"

    def __init__(self, board: str = "careers.un.org",
                 session: requests.Session | None = None):
        super().__init__(board)
        self.host = board.strip() or "careers.un.org"
        self._url = f"https://{self.host}/jobfeed"
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = _UA

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        resp = self._session.get(self._url, timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = item.findtext("description") or ""
            pub = (item.findtext("pubDate") or "").strip() or None
            if not title or not link:
                continue
            m = _ID_IN_URL.search(link)
            jid = _field(desc, "Job ID") or (m.group(1) if m else link)
            if jid in seen:
                continue
            seen.add(jid)
            duty = _field(desc, "Duty Station")
            location = duty.title() if duty else None
            dept = _field(desc, "Department/Office") or "United Nations"
            level = _field(desc, "Level")
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=str(jid),
                title=title,
                company=dept,
                location=location,
                description=html_to_text(desc),
                source_url=link,
                apply_url=link,
                level=level,
                remote=detect_remote(f"{location or ''} {title}"),
                posted_at=pub,
                dedup_key=make_dedup_key(title, dept, location),
                first_seen=at,
                last_checked=at,
                is_open=True,
            ))
        return jobs
