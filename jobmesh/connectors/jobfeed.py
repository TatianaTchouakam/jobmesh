"""Generic job XML/RSS feed connector.

Many job-board-software platforms (SmartJobBoard, WP Job Manager, and
others) publish every listing in a single public XML or RSS feed. One
parser therefore covers many boards: point it at a feed URL and it
returns every job entry it contains, in one request.

A board is the full feed URL, e.g.
    "https://jobs.example.org/feed"            (RSS <item> entries)
    "https://jobs.example.org/standard.xml"    (<jobs><job> entries)

Both common shapes are handled; XML namespaces and tag case are ignored.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = (
    "Mozilla/5.0 (compatible; jobmesh/0.1; +https://github.com/; job index)"
)
TIMEOUT = 25

# candidate child-tag names (lowercased, namespace-stripped) per field
_FIELD_TAGS = {
    "title": ("title", "jobtitle", "name", "position"),
    "company": ("company", "companyname", "hiringorganization", "employer",
                "organization", "advertiser"),
    "location": ("location", "joblocation", "city", "region", "area", "place"),
    "url": ("url", "link", "joburl", "applyurl", "apply_url", "guid",
            "referenceurl"),
    "description": ("description", "content", "jobdescription", "summary",
                    "encoded"),
    "date": ("datePosted", "dateposted", "pubdate", "date", "posteddate",
             "published"),
    "salary": ("salary", "salaryrange", "compensation", "pay"),
    "employment_type": ("jobtype", "employmenttype", "type", "contracttype",
                        "employment_type"),
    "category": ("category", "department", "jobcategory", "sector",
                 "industry", "function"),
    "job_id": ("referencenumber", "reference", "id", "jobid", "job_id",
               "guid", "jobreference"),
}


def _tag(el) -> str:
    """Local tag name, lowercased, namespace stripped."""
    t = el.tag
    if isinstance(t, str) and "}" in t:
        t = t.split("}", 1)[1]
    return (t or "").lower()


def _first(entry: ET.Element, names: tuple[str, ...]) -> str | None:
    wanted = {n.lower() for n in names}
    for child in entry.iter():
        if child is entry:
            continue
        if _tag(child) in wanted:
            text = (child.text or "").strip()
            if text:
                return text
            # some feeds carry the value in an attribute (e.g. url href)
            for v in child.attrib.values():
                if v and v.strip():
                    return v.strip()
    return None


class JobFeedConnector(Connector):
    platform = "jobfeed"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        resp = self._session.get(self.board, timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        entries = [el for el in root.iter() if _tag(el) in ("item", "job", "entry")]
        fetched_at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for entry in entries:
            job = self._to_job(entry, fetched_at)
            if job is None or job.source_job_id in seen:
                continue
            seen.add(job.source_job_id)
            jobs.append(job)
        return jobs

    def _to_job(self, entry: ET.Element, fetched_at: str) -> Job | None:
        g = lambda f: _first(entry, _FIELD_TAGS[f])
        title = g("title")
        if not title:
            return None
        company = g("company") or self.board
        location = g("location")
        url = g("url")
        job_id = g("job_id") or url or hashlib.sha1(
            (self.board + title + (location or "")).encode()
        ).hexdigest()[:16]

        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(job_id),
            title=title,
            company=company,
            location=location,
            description=html_to_text(g("description")),
            source_url=url,
            apply_url=url,
            salary=g("salary"),
            employment_type=g("employment_type"),
            workplace_type=None,
            category=g("category"),
            remote=detect_remote(location),
            posted_at=g("date"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
