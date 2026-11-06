"""Jobspresso connector (job board, curated remote roles).

Jobspresso runs on WP Job Manager, which publishes a public job feed:
    https://jobspresso.co/?feed=job_feed

Items carry the standard RSS tags plus WP Job Manager's namespaced extras
(company, location, job_type). We read tags by local name so the
namespace prefix doesn't matter. The `board` argument is ignored; use
"all" in config.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

FEED = "https://jobspresso.co/?feed=job_feed"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 25


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


class JobspressoConnector(Connector):
    platform = "jobspresso"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        resp = self._session.get(FEED, timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        at = now_iso()
        return [self._to_job(item, at) for item in root.iter("item")]

    def _to_job(self, item: ET.Element, at: str) -> Job:
        fields: dict[str, str] = {}
        for child in item:
            name = _local(child.tag)
            if child.text and child.text.strip() and name not in fields:
                fields[name] = child.text.strip()

        title = fields.get("title") or "(untitled)"
        link = fields.get("link")
        company = fields.get("company") or "Unknown"
        location = fields.get("location") or None
        job_id = fields.get("guid") or link or title
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(job_id),
            title=title, company=company, location=location,
            description=html_to_text(fields.get("description")),
            source_url=link, apply_url=link,
            salary=None,
            employment_type=fields.get("job_type"),
            remote=detect_remote(location) or True,   # Jobspresso is remote-only
            category=fields.get("job_category") or fields.get("category"),
            posted_at=fields.get("pubdate"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
