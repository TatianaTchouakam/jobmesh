"""ADP Workforce Now connector — public Career Center job feed.

An ADP Workforce Now career centre exposes a keyless, public JSON feed that
client websites embed directly (the `/public/` path is intended for exactly
this):

    GET https://workforcenow.adp.com/mascsr/default/careercenter/public/events/
        staffing/v1/job-requisitions?cid={cid}&ccId={ccId}&lang=en_US
    -> {"jobRequisitions": [ ... ], "meta": {"totalNumber": N}}

The two IDs come from a company's Career Center URL (`cid` + `ccId`). A `board`
is "cid|ccId|Company Name" (the company name is optional and only used for
display, since the feed does not name the employer per requisition).
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

HOST = "https://workforcenow.adp.com"
API = (HOST + "/mascsr/default/careercenter/public/events/staffing/v1/"
       "job-requisitions")
DETAIL = HOST + "/mascsr/default/mdf/recruitment/recruitment.html"
TIMEOUT = 30


class AdpConnector(Connector):
    platform = "adp"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        parts = board.split("|")
        self._cid = parts[0]
        self._ccid = parts[1] if len(parts) > 1 else ""
        self._company = parts[2] if len(parts) > 2 and parts[2] else self._cid
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        if not robots_allowed(API, self._session):
            return []
        params = {"cid": self._cid, "ccId": self._ccid, "lang": "en_US",
                  "timeZoneId": "America/New_York"}
        resp = self._session.get(API, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        reqs = data.get("jobRequisitions") if isinstance(data, dict) else None
        if not isinstance(reqs, list):
            return []
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for r in reqs:
            job = self._to_job(r, at)
            if job is not None and job.source_job_id not in seen:
                seen.add(job.source_job_id)
                jobs.append(job)
        return jobs

    def _to_job(self, r: dict, at: str) -> Job | None:
        jid = r.get("itemID") or r.get("clientRequisitionID")
        if not jid:
            return None
        location = None
        rls = r.get("requisitionLocations") or []
        if rls:
            nc = (rls[0].get("nameCode") or {}).get("shortName")
            if nc and nc.strip():
                location = nc.strip()
            else:
                addr = rls[0].get("address") or {}
                parts = [addr.get("cityName"),
                         (addr.get("countrySubdivisionLevel1") or {}).get("codeValue")]
                location = ", ".join(p for p in parts if p) or None
        url = (f"{DETAIL}?cid={self._cid}&ccId={self._ccid}&lang=en_US"
               f"&selectedMenuKey=CurrentOpenings&jobId={jid}")
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=str(jid),
            title=r.get("requisitionTitle") or "(untitled)",
            company=self._company,
            location=location,
            source_url=url,
            apply_url=url,
            employment_type=(r.get("workLevelCode") or {}).get("shortName"),
            posted_at=r.get("postDate"),
        )
