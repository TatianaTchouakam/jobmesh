"""JobBoard.com connector — public per-sector RSS feeds (rate-limited).

JobBoard.com boards publish RSS per sector::

    https://{host}/jobs/rss/?params=SectorIds={n}   -> RSS 2.0, ~20 latest jobs

The feed is rate-limited: most requests return 200, but some return a 503
anti-bot challenge page. We use a browser-style User-Agent, keep cookies across
requests (a Session), and retry a few times per sector; sectors still failing
are skipped. Iterating sectors aggregates the volume and dedupes by link.

robots.txt only disallows technical folders (/Scripts/, /_management/), not
/jobs/rss/. A ``board`` is the host, e.g. "preview.jobboard.com".
"""

from __future__ import annotations

import html
import re
import time

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed
from .base import Connector

TIMEOUT = 25
MAX_SECTORS = 20
RETRIES = 4
# Keep our identity but in the "Mozilla/5.0 (compatible; <bot>; +url)" convention
# that rate-limiters recognise (same as Googlebot's UA shape).
_UA = "Mozilla/5.0 (compatible; JobmeshBot/0.1; +https://github.com/TatianaTchouakam/jobmesh)"

_ITEM = re.compile(r"<item>([\s\S]*?)</item>", re.IGNORECASE)
_SLUG = re.compile(r"/jobs/([a-z0-9][a-z0-9-]*)/?$", re.IGNORECASE)


def _tag(block: str, name: str) -> str | None:
    m = re.search(rf"<{name}[^>]*>([\s\S]*?)</{name}>", block, re.IGNORECASE)
    if not m:
        return None
    return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() or None


class JobBoardComConnector(Connector):
    platform = "jobboardcom"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.host = board.strip().strip("/")
        self.base = f"https://{self.host}"
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = _UA

    def _feed(self, sector: int) -> str | None:
        url = f"{self.base}/jobs/rss/?params=SectorIds%3d{sector}"
        for attempt in range(RETRIES):
            try:
                r = self._session.get(url, timeout=TIMEOUT)
            except requests.RequestException:
                time.sleep(0.8)
                continue
            if r.status_code == 200:
                return r.text  # valid response (may be an empty sector); don't retry
            time.sleep(0.8)  # rate-limited (503 challenge) -> back off and retry
        return None

    def fetch(self) -> list[Job]:
        if not robots_allowed(f"{self.base}/jobs/rss/", self._session):
            return []
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for sector in range(1, MAX_SECTORS + 1):
            text = self._feed(sector)
            if not text:
                continue
            for block in _ITEM.findall(text):
                link = _tag(block, "link")
                title = _tag(block, "title")
                if not link or not title:
                    continue
                m = _SLUG.search(link)
                jid = m.group(1) if m else link
                if jid in seen:
                    continue
                seen.add(jid)
                desc = _tag(block, "description")
                jobs.append(Job(
                    source_platform=self.platform,
                    source_board=self.board,
                    source_job_id=jid,
                    title=title,
                    company="JobBoard.com",
                    location=None,
                    description=html_to_text(desc) if desc else None,
                    source_url=link,
                    apply_url=link,
                    remote=detect_remote(title),
                    posted_at=_tag(block, "pubDate"),
                    dedup_key=make_dedup_key(title, "JobBoard.com", None),
                    first_seen=at,
                    last_checked=at,
                    is_open=True,
                ))
        return jobs
