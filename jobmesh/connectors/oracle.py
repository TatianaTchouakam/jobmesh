"""Oracle Recruiting Cloud connector (enterprise ATS).

Oracle's HCM "Candidate Experience" API is public and keyless. Many large,
often non-tech employers run on it (hospitality, retail, banking,
healthcare). Jobs for one career site:

    GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
        ?onlyData=true&expand=requisitionList.secondaryLocations
        &finder=findReqs;siteNumber={site},limit=200,offset=0,sortBy=POSTING_DATES_DESC

A board packs the host and the site code (and an optional company label):

    ejwl.fa.us2.oraclecloud.com:CX              # Marriott
    ejwl.fa.us2.oraclecloud.com:CX:Marriott

The response nests jobs under items[].requisitionList, with TotalJobsCount
for pagination. Field names vary a little between tenants, so the mapping
reads each field from a few likely names.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from .base import Connector

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 30
PAGE = 200
MAX_PAGES = 12


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


class OracleConnector(Connector):
    platform = "oracle"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")
        parts = (board or "").split(":")
        if len(parts) < 2:
            raise ValueError(
                f"Oracle board must be 'host:site[:Company]', got {board!r}")
        self.host, self.site = parts[0], parts[1]
        self.company = parts[2] if len(parts) > 2 and parts[2] else None

    def fetch(self) -> list[Job]:
        at = now_iso()
        jobs: list[Job] = []
        offset = 0
        for _ in range(MAX_PAGES):
            finder = (f"findReqs;siteNumber={self.site},limit={PAGE},"
                      f"offset={offset},sortBy=POSTING_DATES_DESC")
            url = (f"https://{self.host}/hcmRestApi/resources/latest/"
                   f"recruitingCEJobRequisitions")
            resp = self._session.get(
                url,
                params={"onlyData": "true",
                        "expand": "requisitionList.secondaryLocations",
                        "finder": finder},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items") or []
            total = 0
            batch: list[dict] = []
            for it in items:
                batch.extend(it.get("requisitionList") or [])
                total = it.get("TotalJobsCount") or total
            if not batch:
                break
            jobs.extend(self._to_job(j, at) for j in batch)
            offset += PAGE
            if total and offset >= total:
                break
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = _first(d, "Title", "title") or "(untitled)"
        location = _first(d, "PrimaryLocation", "Location", "primaryLocation")
        job_id = _first(d, "Id", "id", "requisitionId") or title
        url = (f"https://{self.host}/hcmUI/CandidateExperience/en/sites/"
               f"{self.site}/job/{job_id}")
        workplace = _first(d, "WorkplaceType", "WorkplaceTypeCode",
                           "RemoteWork")
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(job_id),
            title=title,
            company=self.company or self.site,
            location=location,
            description=None,
            source_url=url, apply_url=url,
            salary=None,
            employment_type=_first(d, "JobSchedule", "ScheduleTypeCode"),
            workplace_type=(workplace if workplace else None),
            category=_first(d, "JobFamily", "Category", "JobFunction"),
            remote=detect_remote(location),
            posted_at=_first(d, "PostedDate", "RequisitionPostDate"),
            dedup_key=make_dedup_key(title, self.company or self.site, location),
            first_seen=at, last_checked=at, is_open=True,
        )
