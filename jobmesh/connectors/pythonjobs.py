"""Python.org Jobs connector (niche job board — Python roles).

Reads the official Python Job Board RSS feed (no key):
    https://www.python.org/jobs/feed/rss/

Item titles are of the form "Job Title: Company" (occasionally
"Job Title, Company"). The `board` argument is ignored; use "all".
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

FEED = "https://www.python.org/jobs/feed/rss/"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


class PythonJobsConnector(Connector):
    platform = "pythonjobs"

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
        cats: list[str] = []
        for child in item:
            name = _local(child.tag)
            if name == "category" and child.text:
                cats.append(child.text.strip())
            elif child.text and child.text.strip() and name not in fields:
                fields[name] = child.text.strip()

        raw = fields.get("title") or "(untitled)"
        title, company = _split_title(raw)
        link = fields.get("link")
        # Categories often carry the location; keep the first as location hint.
        location = cats[0] if cats else None
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(fields.get("guid") or link or raw),
            title=title, company=company, location=location,
            description=html_to_text(fields.get("description")),
            source_url=link, apply_url=link,
            salary=None,
            employment_type=None,
            remote=detect_remote(location) or detect_remote(raw),
            category=None,
            posted_at=fields.get("pubdate"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )


def _split_title(raw: str):
    """'Senior Developer: Acme Inc' -> ('Senior Developer', 'Acme Inc')."""
    for sep in (": ", ", "):
        if sep in raw:
            title, company = raw.rsplit(sep, 1)
            return title.strip(), company.strip()
    return raw.strip(), "Unknown"
