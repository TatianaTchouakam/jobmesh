"""We Work Remotely connector (job board, remote).

Reads the public We Work Remotely RSS feed (no key):
    https://weworkremotely.com/remote-jobs.rss

RSS <item>s have a title of the form "Company: Position". The `board`
argument is ignored; use "all" in config.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from .base import Connector

FEED = "https://weworkremotely.com/remote-jobs.rss"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 25


class WeWorkRemotelyConnector(Connector):
    platform = "weworkremotely"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        resp = self._session.get(FEED, timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        at = now_iso()
        jobs = []
        for item in root.iter("item"):
            jobs.append(self._to_job(item, at))
        return jobs

    def _to_job(self, item: ET.Element, at: str) -> Job:
        def txt(tag):
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else None

        raw_title = txt("title") or ""
        # "Company: Position" -> company, position
        if ": " in raw_title:
            company, title = raw_title.split(": ", 1)
        else:
            company, title = "Unknown", raw_title or "(untitled)"

        link = txt("link")
        region = txt("region")  # WWR custom element, often absent
        job_id = _id_from_link(link) or link

        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(job_id),
            title=title.strip(), company=company.strip(),
            location=region or "Remote",
            description=html_to_text(txt("description")),
            source_url=link, apply_url=link,
            salary=None,
            employment_type=None,
            workplace_type="remote",
            category=txt("category"),
            remote=True,
            posted_at=txt("pubDate"),
            dedup_key=make_dedup_key(title, company, region),
            first_seen=at, last_checked=at, is_open=True,
        )


def _id_from_link(link: str | None) -> str | None:
    if not link:
        return None
    m = re.search(r"/remote-jobs/([^/?#]+)", link)
    return m.group(1) if m else None
