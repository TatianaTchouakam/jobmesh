"""Teamtailor connector (ATS, popular in the Nordics/Europe).

Each company on Teamtailor exposes a public RSS feed of its open jobs:
    https://{board}.teamtailor.com/jobs.rss

`board` is the company's Teamtailor subdomain. Items carry the standard
RSS tags (title, link, description, pubDate) plus some namespaced extras
(location, department, remote). We read tags by their local name so an
unknown namespace prefix doesn't matter.

Docs: https://support.teamtailor.com (RSS feed how-to)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 25


def _local(tag: str) -> str:
    """Strip any '{namespace}' prefix from an element tag."""
    return tag.rsplit("}", 1)[-1].lower()


class TeamtailorConnector(Connector):
    platform = "teamtailor"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    @property
    def _feed(self) -> str:
        return f"https://{self.board}.teamtailor.com/jobs.rss"

    def fetch(self) -> list[Job]:
        resp = self._session.get(self._feed, timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        at = now_iso()
        company = self._channel_title(root)
        return [self._to_job(item, company, at) for item in root.iter("item")]

    @staticmethod
    def _channel_title(root: ET.Element) -> str | None:
        ch = root.find("channel")
        if ch is not None:
            t = ch.find("title")
            if t is not None and t.text:
                # "Jobs at Acme" -> "Acme"
                return t.text.replace("Jobs at ", "").strip() or None
        return None

    def _to_job(self, item: ET.Element, company: str | None, at: str) -> Job:
        fields: dict[str, str] = {}
        for child in item:
            name = _local(child.tag)
            if child.text and child.text.strip() and name not in fields:
                fields[name] = child.text.strip()

        title = fields.get("title") or "(untitled)"
        link = fields.get("link")
        location = fields.get("location") or fields.get("region")
        remote_flag = fields.get("remote", "")
        remote = (remote_flag.lower() in ("true", "yes", "1")
                  if remote_flag else detect_remote(location))
        job_id = fields.get("guid") or link or title
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(job_id),
            title=title, company=company or self.board,
            location=location,
            description=html_to_text(fields.get("description")),
            source_url=link, apply_url=link,
            salary=None,
            employment_type=None,
            remote=remote,
            category=fields.get("department") or fields.get("division"),
            posted_at=fields.get("pubdate"),
            dedup_key=make_dedup_key(title, company or self.board, location),
            first_seen=at, last_checked=at, is_open=True,
        )
