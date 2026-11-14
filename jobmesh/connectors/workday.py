"""Workday connector (enterprise ATS).

Workday powers the careers sites of many large companies (NVIDIA,
Salesforce, and thousands more). Each site exposes an undocumented but
public, no-auth JSON endpoint — the "CXS" API — used by the careers page
itself:

    POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}

A Workday board has three parts — the tenant, the datacenter shard
(wd1, wd3, wd5, wd12, ...), and the career-site id — so the config token
packs them together, with an optional display name:

    tenant:wd5:NVIDIAExternalCareerSite
    tenant:wd5:NVIDIAExternalCareerSite:NVIDIA   # 4th part = company label

The list response pages 20 at a time (larger limits return an empty page),
so we walk `offset` up to `total`. We index at the listing level (title,
location, link, req id) and skip the per-job detail request, which would
mean one extra HTTP call per posting.

The CXS API often returns an empty / non-JSON body when the request looks
unlike the careers page's own fetch (missing Origin/Referer) or when a
burst of requests trips bot-protection. So we send the same headers the
page sends and retry a few times on an empty/non-JSON response before
giving up, so a transient block is ridden out rather than logged as a
parse error.
"""

from __future__ import annotations

import time

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 25
PAGE = 20          # Workday caps the page size at 20.
MAX_PAGES = 15     # Safety cap: at most 300 postings per board per run.


class WorkdayConnector(Connector):
    platform = "workday"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.tenant, self.wd, self.site, self.company = _parse_board(board)
        self._session = session or requests.Session()
        base = f"https://{self.tenant}.{self.wd}.myworkdayjobs.com"
        # Send the same headers the careers page sends; the CXS API tends to
        # return an empty body to requests without a matching Origin/Referer.
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-US",
            "Content-Type": "application/json",
            "Origin": base,
            "Referer": f"{base}/en-US/{self.site}",
            "X-Requested-With": "XMLHttpRequest",
        })

    @property
    def _base(self) -> str:
        return f"https://{self.tenant}.{self.wd}.myworkdayjobs.com"

    def fetch(self) -> list[Job]:
        url = f"{self._base}/wday/cxs/{self.tenant}/{self.site}/jobs"
        at = now_iso()
        jobs: list[Job] = []
        offset = 0
        for _ in range(MAX_PAGES):
            data = self._post_page(url, offset)
            batch = data.get("jobPostings") or []
            if not batch:
                break
            jobs.extend(self._to_job(j, at) for j in batch)
            offset += PAGE
            if offset >= (data.get("total") or 0):
                break
        return jobs

    def _post_page(self, url: str, offset: int) -> dict:
        """POST one page, retrying on an empty / non-JSON body.

        Workday sometimes answers a 200 with an empty or HTML body (bot
        protection, or a burst of requests). We back off and retry a few
        times; only then do we raise, so the pipeline logs a real failure
        instead of a confusing JSON parse error.
        """
        body = {"appliedFacets": {}, "limit": PAGE,
                "offset": offset, "searchText": ""}
        for attempt in range(3):
            resp = self._session.post(url, json=body, timeout=TIMEOUT)
            resp.raise_for_status()
            try:
                return resp.json()
            except ValueError:
                # empty / non-JSON body (bot-protection or transient) -> retry
                time.sleep(2.0 * (attempt + 1))
        raise RuntimeError(
            f"Workday returned an empty/non-JSON body after retries: {url}"
        )

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("title") or "(untitled)"
        path = d.get("externalPath") or ""
        location = d.get("locationsText") or None
        # Human-facing careers URL for this posting.
        url = f"{self._base}/en-US/{self.site}{path}" if path else self._base
        # req id lives in bulletFields on most sites; else fall back to path.
        bullets = d.get("bulletFields") or []
        job_id = (bullets[0] if bullets else None) or path or title
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(job_id),
            title=title, company=self.company, location=location,
            description=None,           # listing-level only (no detail call)
            source_url=url, apply_url=url,
            salary=None,
            employment_type=None,
            remote=detect_remote(location),
            posted_at=None,             # Workday gives a localized label, not a date
            dedup_key=make_dedup_key(title, self.company, location),
            first_seen=at, last_checked=at, is_open=True,
        )


def _parse_board(board: str):
    """Split 'tenant:wd5:site[:Company]' into its parts.

    The optional 4th segment is a friendly company name; without it we
    title-case the tenant.
    """
    parts = (board or "").split(":")
    if len(parts) < 3:
        raise ValueError(
            f"Workday board must be 'tenant:wdN:site[:Company]', got {board!r}"
        )
    tenant, wd, site = parts[0], parts[1], parts[2]
    company = parts[3] if len(parts) > 3 and parts[3] else tenant.title()
    return tenant, wd, site, company
