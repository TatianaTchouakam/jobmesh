"""Generic career-page connector: schema.org JobPosting (JSON-LD).

Most ATS career pages and job-board-software sites embed their openings
as schema.org `JobPosting` JSON-LD. One parser therefore covers many
platforms. The module-level `parse_jobpostings` / `posting_to_job`
helpers are reused by other connectors (e.g. smartjobboard) that fetch
JSON-LD from individual job pages.

A careersite board is the full URL of a server-rendered page that
carries JobPosting JSON-LD (usually an individual job page, since Google
recommends JSON-LD on detail pages, not list pages).
"""

from __future__ import annotations

import hashlib
import json
import re

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = (
    "Mozilla/5.0 (compatible; jobmesh/0.1; +https://github.com/; job index)"
)
TIMEOUT = 25
_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _iter_jobpostings(node):
    """Yield every JobPosting object found anywhere in a parsed JSON-LD node."""
    if isinstance(node, list):
        for item in node:
            yield from _iter_jobpostings(item)
    elif isinstance(node, dict):
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(str(x).lower() == "jobposting" for x in types if x):
            yield node
        for key in ("@graph", "itemListElement", "item", "mainEntity"):
            if key in node:
                yield from _iter_jobpostings(node[key])


def parse_jobpostings(html: str) -> list[dict]:
    """Extract every JobPosting object from a page's JSON-LD blocks."""
    out: list[dict] = []
    for block in _LD_RE.findall(html):
        block = block.strip()
        if not block:
            continue
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        out.extend(_iter_jobpostings(data))
    return out


def _text(value):
    if isinstance(value, dict):
        return value.get("name") or value.get("@value") or value.get("value")
    if isinstance(value, list):
        return ", ".join(x for x in (_text(v) for v in value) if x) or None
    return value


def _location(posting: dict):
    loc = posting.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, dict):
        addr = loc.get("address")
        if isinstance(addr, dict):
            parts = [addr.get("addressLocality"), addr.get("addressRegion"),
                     _text(addr.get("addressCountry"))]
            return ", ".join(x for x in parts if x) or None
        if isinstance(addr, str):
            return addr
        return _text(loc)
    return _text(loc)


def _is_remote(posting: dict, location):
    if str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        return True
    if posting.get("applicantLocationRequirements"):
        return True
    return detect_remote(location)


def _salary(posting: dict):
    bs = posting.get("baseSalary")
    if not isinstance(bs, dict):
        return None
    val = bs.get("value")
    cur = bs.get("currency") or ""
    if isinstance(val, dict):
        amount = val.get("value")
        if amount is None:
            lo, hi = val.get("minValue"), val.get("maxValue")
            amount = f"{lo}-{hi}" if lo or hi else None
        unit = val.get("unitText")
        if amount:
            return " ".join(str(x) for x in (cur, amount, unit) if x).strip() or None
    elif val:
        return f"{cur} {val}".strip()
    return None


def posting_to_job(p: dict, platform: str, board: str, fetched_at: str,
                   page_url: str | None = None) -> Job | None:
    """Map one schema.org JobPosting dict to a jobmesh Job."""
    title = _text(p.get("title")) or _text(p.get("name"))
    if not title:
        return None
    org = p.get("hiringOrganization")
    company = _text(org) or _text(p.get("author")) or board
    location = _location(p)
    url = _text(p.get("url")) or p.get("@id") or page_url or board

    ident = p.get("identifier")
    job_id = _text(ident) or url or page_url or title
    job_id = str(job_id)
    if job_id in (board, ""):
        job_id = hashlib.sha1((board + title).encode()).hexdigest()[:16]

    return Job(
        source_platform=platform,
        source_board=board,
        source_job_id=job_id,
        title=title,
        company=company,
        location=location,
        description=html_to_text(_text(p.get("description"))),
        source_url=url,
        apply_url=_text(p.get("applicationContact")) or url,
        salary=_salary(p),
        employment_type=_text(p.get("employmentType")),
        workplace_type=None,
        category=_text(p.get("occupationalCategory")) or _text(p.get("industry")),
        remote=_is_remote(p, location),
        posted_at=p.get("datePosted"),
        dedup_key=make_dedup_key(title, company, location),
        first_seen=fetched_at,
        last_checked=fetched_at,
        is_open=True,
    )


class CareerSiteConnector(Connector):
    platform = "careersite"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        resp = self._session.get(self.board, timeout=TIMEOUT)
        resp.raise_for_status()
        fetched_at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for posting in parse_jobpostings(resp.text):
            job = posting_to_job(posting, self.platform, self.board,
                                 fetched_at, self.board)
            if job is None or job.source_job_id in seen:
                continue
            seen.add(job.source_job_id)
            jobs.append(job)
        return jobs
