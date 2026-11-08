"""Eightfold connector (ATS / talent platform).

Reads the public, keyless Eightfold careers API:
    GET https://{tenant}.eightfold.ai/api/apply/v2/jobs?domain={domain}&start=&num=

Eightfold powers the careers sites of many LARGE, non-tech employers
(banks, retail, pharma, industrials), so it is a strong all-sectors,
worldwide source. `board` is the tenant, optionally with its domain:
    "fortive"            -> tenant fortive, domain fortive.com
    "paypal:paypal.com"  -> tenant paypal,  domain paypal.com
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25
NUM = 10          # page size
MAX_PAGES = 5     # up to 50 roles per tenant per run


class EightfoldConnector(Connector):
    platform = "eightfold"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        if ":" in board:
            self.tenant, self.domain = board.split(":", 1)
        else:
            self.tenant, self.domain = board, f"{board}.com"
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")

    def fetch(self) -> list[Job]:
        at = now_iso()
        root = f"https://{self.tenant}.eightfold.ai/api/apply/v2/jobs"
        company = self.tenant.replace("-", " ").title()
        jobs: list[Job] = []
        for page in range(MAX_PAGES):
            resp = self._session.get(
                root,
                params={"domain": self.domain, "start": page * NUM, "num": NUM},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            positions = data.get("positions") or []
            if not positions:
                break
            jobs.extend(self._to_job(p, company, at) for p in positions)
            count = data.get("count") or 0
            if (page + 1) * NUM >= count:
                break
        return jobs

    def _to_job(self, p: dict, company: str, at: str) -> Job:
        title = p.get("name") or "(untitled)"
        location = p.get("location")
        if not location:
            locs = p.get("locations")
            if isinstance(locs, list) and locs:
                location = ", ".join(str(x) for x in locs[:2])
        pid = p.get("id") or p.get("position_id")
        url = (p.get("canonicalPositionUrl")
               or f"https://{self.tenant}.eightfold.ai/careers?pid={pid}&domain={self.domain}")
        return Job(
            source_platform=self.platform, source_board=self.tenant,
            source_job_id=str(pid or url or title),
            title=title, company=company, location=location,
            description=html_to_text(p.get("job_description") or p.get("description")),
            source_url=url, apply_url=url,
            salary=None,
            employment_type=p.get("job_type") or p.get("type"),
            category=p.get("department"),
            remote=detect_remote(location),
            posted_at=_ts(p.get("t_create") or p.get("t_update")),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )


def _ts(v):
    """Eightfold timestamps are epoch seconds (sometimes ms)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v > 1e12:
        v /= 1000.0
    return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
