"""DevITjobs connector (UK IT job board).

Reads the public DevITjobs XML feed (no key):
    https://devitjobs.uk/job_feed.xml

The `board` argument is ignored; use "all". Field names are read
defensively since the feed's exact tags aren't formally documented.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

FEED = "https://devitjobs.uk/job_feed.xml"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 25


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


class DevITjobsConnector(Connector):
    platform = "devitjobs"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        resp = self._session.get(FEED, timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        at = now_iso()
        # jobs may be <job> items anywhere in the feed
        items = [e for e in root.iter() if _local(e.tag) == "job"]
        return [self._to_job(it, at) for it in items]

    def _to_job(self, item: ET.Element, at: str) -> Job:
        f: dict[str, str] = {}
        for child in item:
            name = _local(child.tag)
            if child.text and child.text.strip() and name not in f:
                f[name] = child.text.strip()
        title = f.get("title") or "(untitled)"
        company = f.get("company") or f.get("companyname") or "Unknown"
        location = f.get("location") or f.get("city")
        url = f.get("url") or f.get("link") or f.get("guid") or FEED
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(f.get("guid") or f.get("id") or url or title),
            title=title, company=company, location=location,
            description=html_to_text(f.get("description")),
            source_url=url, apply_url=url,
            salary=f.get("salary"),
            employment_type=f.get("type") or f.get("contracttype"),
            remote=detect_remote(location) or detect_remote(title),
            category=f.get("category"),
            posted_at=f.get("pubdate") or f.get("posteddate") or f.get("date"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
