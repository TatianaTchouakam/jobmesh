"""Paylocity connector — public, keyless recruiting boards.

Every Paylocity recruiting customer runs a public careers board at a
predictable URL:

    https://recruiting.paylocity.com/Recruiting/Jobs/All/{companyId}

where ``companyId`` is the board's GUID. The page is server-rendered and
embeds the complete job list as JSON in a ``window.pageData = {...};``
assignment — one GET returns every open posting (title, location,
department, published date, remote flag), with no key and no login.

A ``board`` is the company GUID (e.g. "0005a0af-b8ae-4a24-9ae3-458109fffbda").
Individual postings live at ``/Recruiting/Jobs/Details/{JobId}`` and the
apply page at ``/Recruiting/Jobs/Apply/{JobId}`` — links we store but never
fetch. robots.txt on recruiting.paylocity.com is 404 (no restriction); every
request still passes the shared robots guard with an honest User-Agent.
"""

from __future__ import annotations

import json

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text
from ..robots import allowed as robots_allowed, USER_AGENT
from ..ratelimit import get_limiter, parse_retry_after, RateLimited
from .base import Connector

ORIGIN = "https://recruiting.paylocity.com"
TIMEOUT = 30


def _extract_pagedata(html: str) -> dict | None:
    """Return the parsed ``window.pageData`` object, or None.

    Uses a string-aware brace scanner so a brace inside a description or
    address value can never unbalance the match.
    """
    i = html.find("window.pageData")
    if i == -1:
        return None
    i = html.find("{", i)
    if i == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(i, len(html)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[i:j + 1])
                    except json.JSONDecodeError:
                        return None
    return None


def _location(job: dict) -> str | None:
    loc = job.get("JobLocation")
    if isinstance(loc, dict):
        parts = [loc.get("City"), loc.get("State"), loc.get("Country")]
        text = ", ".join(p for p in parts if p)
        if text:
            return text
    name = job.get("LocationName")
    return name or None


class PaylocityConnector(Connector):
    platform = "paylocity"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._url = f"{ORIGIN}/Recruiting/Jobs/All/{board}"

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._url, self._session):
            return []
        # Every board is on the shared recruiting.paylocity.com host, which
        # rate-limits by IP. Pace through the shared limiter and surface a 429
        # so the pipeline retries this board later in the cycle (no burst).
        with get_limiter("paylocity").slot("recruiting.paylocity.com"):
            resp = self._session.get(self._url, timeout=TIMEOUT)
        if resp.status_code == 429:
            raise RateLimited(retry_after=parse_retry_after(resp))
        resp.raise_for_status()
        data = _extract_pagedata(resp.text)
        if not data:
            return []                      # empty / "Job Not Found" board
        company = data.get("ModuleTitle") or self.board
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for j in data.get("Jobs", []) or []:
            jid = j.get("JobId")
            if jid is None:
                continue
            jid = str(jid)
            if jid in seen:
                continue
            seen.add(jid)
            jobs.append(Job(
                source_platform=self.platform,
                source_board=self.board,
                source_job_id=jid,
                title=j.get("JobTitle") or "(untitled)",
                company=company,
                location=_location(j),
                description=html_to_text(j.get("Description")),
                source_url=f"{ORIGIN}/Recruiting/Jobs/Details/{jid}",
                apply_url=f"{ORIGIN}/Recruiting/Jobs/Apply/{jid}",
                category=j.get("HiringDepartment"),
                remote=bool(j.get("IsRemote")),
                posted_at=j.get("PublishedDate"),
            ))
        return jobs
