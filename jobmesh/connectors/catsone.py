"""CATS (catsone.com) connector — the career portal's own public data route.

CATS career portals ({slug}.catsone.com/careers/{portalId}) are a Remix app.
Every portal page has a keyless data twin the front end itself loads:

    GET https://{slug}.catsone.com/careers/{portalId}.data

It returns a Remix "turbo-stream" payload: a flat JSON array where objects
use "_<i>" keys pointing at other array slots. Decoded, the route
"portals/cats-careers/jobs" holds {"data": {"jobs": [{jobId, positionTitle,
city, state, zip, summary, datePosted, ...}]}} — every open job of the portal.

robots.txt on *.catsone.com is `User-agent: * / Disallow:` (everything
allowed). A `board` is "slug|portalId" (e.g. "sau|112762") or a full portal
URL/host path (e.g. "sau.catsone.com/careers/112762").
"""

from __future__ import annotations

import json
import re

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
_SPECIAL = {-5: None, -7: None}  # turbo-stream undefined / null sentinels


def decode_turbo_stream(arr: list):
    """Rebuild the object graph of a Remix single-fetch (turbo-stream) payload."""
    memo: dict[int, object] = {}

    def h(i):
        if isinstance(i, int) and i < 0:
            return _SPECIAL.get(i)
        if i in memo:
            return memo[i]
        v = arr[i]
        if isinstance(v, list):
            # typed values (["D", ...] dates, ["P", ...] promises...) kept raw
            if v and isinstance(v[0], str) and len(v[0]) == 1 and v[0] in "DPSERYZ":
                memo[i] = v
                return v
            out: list = []
            memo[i] = out
            out.extend(h(x) if isinstance(x, int) else x for x in v)
            return out
        if isinstance(v, dict):
            o: dict = {}
            memo[i] = o
            for k, ref in v.items():
                key = arr[int(k[1:])] if k.startswith("_") else k
                o[key] = h(ref) if isinstance(ref, int) else ref
            return o
        memo[i] = v
        return v

    return h(0)


def _parse_board(board: str) -> tuple[str, str]:
    m = re.search(r"([\w-]+)\.catsone\.com/careers/(\d+)", board)
    if m:
        return m.group(1), m.group(2)
    slug, _, pid = board.partition("|")
    return slug.strip(), pid.strip()


class CatsOneConnector(Connector):
    platform = "catsone"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.slug, self.portal_id = _parse_board(board)
        self._base = f"https://{self.slug}.catsone.com/careers/{self.portal_id}"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        url = f"{self._base}.data"
        if not robots_allowed(url, self._session):
            return []
        resp = self._session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        root = decode_turbo_stream(json.loads(resp.text))
        company = self.slug
        jobs_data = None
        for route, payload in (root or {}).items():
            data = (payload or {}).get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                continue
            portal = data.get("portal")
            if isinstance(portal, dict) and portal.get("name"):
                company = portal["name"]
            if route.endswith("/jobs") and isinstance(data.get("jobs"), list):
                jobs_data = data["jobs"]
        if jobs_data is None:
            raise ValueError(f"CATS portal {self._base}: no jobs route in payload")
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for row in jobs_data:
            job = self._to_job(row, company, at)
            if job is not None and job.source_job_id not in seen:
                seen.add(job.source_job_id)
                jobs.append(job)
        return jobs

    def _to_job(self, row: dict, company: str, at: str) -> Job | None:
        jid = row.get("jobId")
        if not jid:
            return None
        title = (row.get("positionTitle") or "").strip() or "(untitled)"
        location = ", ".join(p for p in (row.get("city"), row.get("state")) if p) or None
        url = f"{self._base}/jobs/{jid}"
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(jid),
            title=title,
            company=company,
            location=location,
            description=html_to_text(row.get("summary")),
            source_url=url,
            apply_url=url,
            remote=detect_remote(location),
            posted_at=row.get("datePosted") or row.get("dateCreated"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )
