"""Zoho Recruit connector — public, server-rendered career sites.

Zoho Recruit hosts each customer's career site at
``{tenant}.zohorecruit.com/jobs/Careers``. The listing is a JS app, but the
server HTML embeds every published job as an HTML-entity-encoded JSON object
(fields ``Posting_Title``, ``City``/``State``/``Country``, ``Remote_Job``,
``Job_Type``, ``Industry``, ``Job_Description``, ``Date_Opened``, ``id`` …),
so a plain request returns the full data -- no API key, no CSRF.

Zoho's robots.txt is ``Disallow: /`` with an explicit ``Allow: /jobs/*``,
so ``/jobs/Careers`` is permitted; our shared robots guard enforces that.
A board is the tenant slug (e.g. "thehireboost").
"""

from __future__ import annotations

import html as _html
import json
import re

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 25
_TITLE_KEY = '"Posting_Title"'


def _slugify(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", title or "").strip("-") or "job"


def _extract_jobs(decoded: str) -> list[dict]:
    """Pull each embedded job object out of the decoded page HTML.

    Each job appears as a JSON object whose second key is ``Posting_Title``;
    we locate the enclosing ``{...}`` by brace matching (which tolerates
    braces inside the description) and parse it.
    """
    out: list[dict] = []
    seen_spans: set[int] = set()
    idx = 0
    while True:
        p = decoded.find(_TITLE_KEY, idx)
        if p < 0:
            break
        start = decoded.rfind("{", 0, p)
        idx = p + len(_TITLE_KEY)
        if start < 0 or start in seen_spans:
            continue
        depth = 0
        end = -1
        for j in range(start, len(decoded)):
            c = decoded[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end < 0:
            continue
        seen_spans.add(start)
        try:
            obj = json.loads(decoded[start:end + 1])
        except ValueError:
            continue
        if obj.get("Posting_Title") and obj.get("id"):
            out.append(obj)
    return out


class ZohoRecruitConnector(Connector):
    platform = "zohorecruit"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{board}.zohorecruit.com"
        self._company = board.replace("-", " ").replace("_", " ").strip().title() or board

    def fetch(self) -> list[Job]:
        listing = f"{self._base}/jobs/Careers"
        if not robots_allowed(listing, self._session):
            return []
        resp = self._session.get(listing, timeout=TIMEOUT)
        resp.raise_for_status()
        decoded = _html.unescape(resp.text)
        fetched_at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for obj in _extract_jobs(decoded):
            if obj.get("Publish") is False:
                continue
            jid = str(obj["id"])
            if jid in seen:
                continue
            seen.add(jid)
            jobs.append(self._to_job(obj, jid, fetched_at))
        return jobs

    def _to_job(self, o: dict, jid: str, fetched_at: str) -> Job:
        title = o.get("Posting_Title") or "(untitled)"
        remote = bool(o.get("Remote_Job"))
        loc = ", ".join(x for x in (o.get("City"), o.get("State"), o.get("Country")) if x)
        location = loc or ("Remote" if remote else None)
        url = f"{self._base}/jobs/Careers/{jid}/{_slugify(title)}?source=CareerSite"
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=jid,
            title=title,
            company=self._company,
            location=location,
            description=html_to_text(o.get("Job_Description")),
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=o.get("Job_Type"),
            workplace_type="remote" if remote else None,
            category=o.get("Industry"),
            remote=remote,
            posted_at=o.get("Date_Opened"),
            dedup_key=make_dedup_key(title, self._company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
