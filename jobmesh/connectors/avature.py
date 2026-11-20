"""Avature connector — public RSS job feed.

Avature hosts each customer's career site at ``{tenant}.avature.net``. The
interactive ``/careers/SearchJobs`` page sits behind a bot-detection
challenge (HTTP 202 to non-browser clients), but Avature also publishes a
plain RSS syndication feed that is meant for machines and is not challenged:

    GET https://{tenant}.avature.net/careers/SearchJobs/feed/

Each ``<item>`` carries the job title, a link to its public
``/careers/JobDetail/{slug}/{id}`` page and a publish date. The feed is
keyless and robots-allowed (``Allow: /careers``). It returns the most recent
~20 postings (there is no public pagination), which is enough to index the
board. A board is the tenant slug (e.g. "delta").
"""

from __future__ import annotations

import html as _html
import re

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 25
_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL | re.IGNORECASE)
_TITLE_RE = re.compile(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", re.DOTALL | re.IGNORECASE)
_LINK_RE = re.compile(r"<link>\s*(.*?)\s*</link>", re.DOTALL | re.IGNORECASE)
_GUID_RE = re.compile(r"<guid[^>]*>\s*(.*?)\s*</guid>", re.DOTALL | re.IGNORECASE)
_DATE_RE = re.compile(r"<pubDate>\s*(.*?)\s*</pubDate>", re.DOTALL | re.IGNORECASE)
_ID_RE = re.compile(r"/JobDetail/[^/]+/(\d+)")


def _text(raw: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(raw or "")).strip()


class AvatureConnector(Connector):
    platform = "avature"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{board}.avature.net"
        self._company = board.replace("-", " ").replace("_", " ").title()

    def fetch(self) -> list[Job]:
        feed = f"{self._base}/careers/SearchJobs/feed/"
        if not robots_allowed(feed, self._session):
            return []
        resp = self._session.get(feed, timeout=TIMEOUT)
        resp.raise_for_status()
        fetched_at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for m in _ITEM_RE.finditer(resp.text):
            job = self._to_job(m.group(1), fetched_at)
            if job is None or job.source_job_id in seen:
                continue
            seen.add(job.source_job_id)
            jobs.append(job)
        return jobs

    def _to_job(self, item: str, fetched_at: str) -> Job | None:
        tm = _TITLE_RE.search(item)
        title = _text(tm.group(1)) if tm else ""
        if not title:
            return None
        lm = _LINK_RE.search(item) or _GUID_RE.search(item)
        url = _text(lm.group(1)) if lm else self._base
        idm = _ID_RE.search(url)
        jid = idm.group(1) if idm else url
        dm = _DATE_RE.search(item)
        posted = _text(dm.group(1)) if dm else None
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(jid),
            title=title,
            company=self._company,
            location=None,
            description=None,
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=None,
            workplace_type=None,
            category=None,
            remote=detect_remote(title),
            posted_at=posted,
            dedup_key=make_dedup_key(title, self._company, None),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
