"""Taleo connector — Oracle Taleo careersection public job search REST.

Taleo career sites (``{tenant}.taleo.net/careersection/{section}/jobsearch.ftl
?lang=en&portal={portal}``) render their job list through a keyless JSON
endpoint that the careersection's own front end calls:

    POST https://{tenant}.taleo.net/careersection/rest/jobboard/searchjobs
         ?lang=en&portal={portal}
         {... "pageNo": N}
    -> {"requisitionList": [
          {"jobId": "...", "contestNo": "...",
           "column": ["<title>", "[\"Country-State-City\"]", "<date>"],
           "linkedColumn": 0, "locationsColumns": [1]}, ...]}

No login or API key — just the anonymous session cookie set by a GET to the
careersection. 25 rows per page; paginate ``pageNo`` until a short/empty page.
Detail URL: /careersection/{section}/jobdetail.ftl?job={contestNo}

A ``board`` is ``{tenant}|{portal}`` (careersection defaults to "ex"), or
``{tenant}|{section}|{portal}`` when the careersection name differs.
Taleo serves no robots.txt (404) -> fail-open, nothing disallowed.
"""

from __future__ import annotations

import json

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
PAGE_SIZE = 25
MAX_PAGES = 200  # safety cap -> up to 5000 postings/board

_BODY = {
    "multilineEnabled": False,
    "sortingSelection": {"sortBySelectionParam": "1", "ascendingSortingOrder": "false"},
    "fieldData": {"fields": {"KEYWORD": "", "LOCATION": "", "CATEGORY": ""}, "valid": True},
    "filterSelectionParam": {"searchFilterSelections": [
        {"id": "LOCATION", "selectedValues": []},
        {"id": "JOB_FIELD", "selectedValues": []},
        {"id": "JOB_SCHEDULE", "selectedValues": []},
        {"id": "POSTING_DATE", "selectedValues": []}]},
    "advancedSearchFiltersSelectionParam": {"searchFilterSelections": [
        {"id": "LOCATION", "selectedValues": []},
        {"id": "JOB_FIELD", "selectedValues": []},
        {"id": "EMPLOYEE_STATUS", "selectedValues": []},
        {"id": "JOB_SCHEDULE", "selectedValues": []}]},
}


def _parse_location(raw) -> str | None:
    """column location cell is a JSON array string, e.g. '["US-CO-Englewood"]'."""
    if not raw:
        return None
    try:
        vals = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return str(raw).strip() or None
    if isinstance(vals, list):
        vals = [str(v).strip() for v in vals if str(v).strip()]
        return "; ".join(vals) or None
    return str(vals).strip() or None


class TaleoConnector(Connector):
    platform = "taleo"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        parts = [p.strip() for p in board.split("|")]
        if len(parts) == 3:
            self.tenant, self.section, self.portal = parts
        elif len(parts) == 2:
            self.tenant, self.portal = parts
            self.section = "ex"
        else:
            raise ValueError(
                f"taleo board must be 'tenant|portal' or 'tenant|section|portal': {board!r}")
        self.host = f"https://{self.tenant}.taleo.net"
        self._search_url = (f"{self.host}/careersection/rest/jobboard/searchjobs"
                            f"?lang=en&portal={self.portal}")
        self._seed_url = (f"{self.host}/careersection/{self.section}/jobsearch.ftl"
                          f"?lang=en&portal={self.portal}")
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        if not robots_allowed(self._search_url, self._session):
            return []
        # Seed the anonymous session cookie the REST endpoint expects.
        try:
            self._session.get(self._seed_url, timeout=TIMEOUT)
        except requests.RequestException:
            pass
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        # Taleo's REST endpoint 500s unless the request looks like the portal's
        # own AJAX call: X-Requested-With is required; tz/tzname are expected.
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "tz": "GMT+00:00",
            "tzname": "UTC",
            "Referer": self._seed_url,
        }
        for page in range(1, MAX_PAGES + 1):
            body = dict(_BODY, pageNo=page)
            resp = self._session.post(self._search_url, data=json.dumps(body),
                                      headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json() or {}
            rows = data.get("requisitionList") or []
            for row in rows:
                job = self._to_job(row, at)
                if job is not None and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    jobs.append(job)
            if len(rows) < PAGE_SIZE:
                break
        return jobs

    def _to_job(self, row: dict, at: str) -> Job | None:
        jid = row.get("jobId") or row.get("contestNo")
        if jid is None:
            return None
        contest = str(row.get("contestNo") or jid)
        column = row.get("column") or []
        t_idx = row.get("linkedColumn", 0) or 0
        loc_cols = row.get("locationsColumns") or [1]
        l_idx = loc_cols[0] if loc_cols else 1
        title = (column[t_idx] if t_idx < len(column) else "").strip() or "(untitled)"
        location = _parse_location(column[l_idx] if l_idx < len(column) else None)
        # posted date = a remaining cell (not title, not location)
        posted = None
        for i, cell in enumerate(column):
            if i not in (t_idx, l_idx) and cell:
                posted = str(cell).strip()
                break
        url = f"{self.host}/careersection/{self.section}/jobdetail.ftl?job={contest}"
        company = self.tenant.upper()
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(jid),
            title=title,
            company=company,
            location=location,
            description=None,
            source_url=url,
            apply_url=url,
            remote=detect_remote(location),
            posted_at=posted,
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )
