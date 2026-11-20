"""HiBob connector — public, keyless career-site API.

HiBob ("Bob", hibob.com) hosts each customer's career site at
``{tenant}.careers.hibob.com``; the SPA front end reads a public,
unauthenticated JSON endpoint on the same origin:

    GET https://{tenant}.careers.hibob.com/api/job-ad
    -> {jobAdDetails: [...], filterGroups, jobOpeningMetadata}

The company's display name comes from ``/api/career-site``. Jobs carry
rich HTML sections (description / responsibilities / requirements /
benefits), structured posting locations, workspace type, employment
type and optional pay-transparency salary. A board is the tenant
subdomain prefix (e.g. "hibob-fa0ad69d0cb34a").

The endpoint is unauthenticated but returns 401 unless the request
carries a ``Referer`` from the career site itself, so we send one; the
job data is public and our User-Agent stays the honest JobmeshBot token.
The careers host has no real robots.txt (the SPA serves its shell for
unknown paths -> no rules), and we still pass every request through the
shared robots guard.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key, normalize_workplace
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 20


class HibobConnector(Connector):
    platform = "hibob"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{board}.careers.hibob.com"
        # the careers API returns 401 without a Referer from its own site; the
        # job data is public and our User-Agent stays the honest JobmeshBot one.
        self._headers = {"Referer": f"{self._base}/"}

    def fetch(self) -> list[Job]:
        if not robots_allowed(f"{self._base}/api/job-ad", self._session):
            return []
        fetched_at = now_iso()
        company = self._company_name()
        resp = self._session.get(f"{self._base}/api/job-ad", headers=self._headers, timeout=TIMEOUT)
        resp.raise_for_status()
        rows = (resp.json() or {}).get("jobAdDetails") or []
        return [self._to_job(r, company, fetched_at) for r in rows]

    # -- helpers -------------------------------------------------------

    def _company_name(self) -> str:
        try:
            cs = self._session.get(f"{self._base}/api/career-site", headers=self._headers, timeout=TIMEOUT).json()
            name = cs.get("companyName") or cs.get("name") or cs.get("title")
            if name:
                return str(name)
        except Exception:
            pass
        # fall back to the subdomain prefix without the trailing hash
        slug = self.board.rsplit("-", 1)[0] if "-" in self.board else self.board
        return slug.replace("-", " ").replace("_", " ").strip().title() or self.board

    @staticmethod
    def _location(d: dict) -> str | None:
        locs = d.get("postingLocations") or []
        if locs:
            loc = locs[0] or {}
            parts = []
            if loc.get("showCity") and loc.get("city"):
                parts.append(loc["city"])
            if loc.get("showRegion") and loc.get("region"):
                parts.append(loc["region"])
            if loc.get("country"):
                parts.append(loc["country"])
            label = ", ".join(dict.fromkeys(p for p in parts if p))
            if label:
                return label
            if loc.get("displayValue"):
                return loc["displayValue"]
        return d.get("country") or None

    @staticmethod
    def _salary(d: dict) -> str | None:
        lo, hi = d.get("payTransparencyMinSalary"), d.get("payTransparencyMaxSalary")
        cur = d.get("payTransparencySalaryCurrency") or ""
        period = d.get("payTransparencySalaryPayPeriod")
        unit = f"/{str(period).lower()}" if period else ""
        cur = f"{cur} " if cur else ""
        if lo and hi:
            return f"{cur}{_num(lo)}-{_num(hi)}{unit}".strip()
        if lo or hi:
            return f"{cur}{_num(lo or hi)}{unit}".strip()
        return None

    @staticmethod
    def _description(d: dict) -> str | None:
        chunks = [d.get("description"), d.get("responsibilities"),
                  d.get("requirements"), d.get("benefits")]
        text = "\n\n".join(html_to_text(c) or "" for c in chunks if c).strip()
        return text or None

    def _to_job(self, d: dict, company: str, fetched_at: str) -> Job:
        title = d.get("title") or "(untitled)"
        location = self._location(d)
        jid = str(d.get("id") or title)
        url = f"{self._base}/jobs/{jid}"
        workplace = normalize_workplace(d.get("workspaceType"))
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=jid,
            title=title,
            company=company,
            location=location,
            description=self._description(d),
            source_url=url,
            apply_url=url,
            salary=self._salary(d),
            employment_type=d.get("employmentType"),
            workplace_type=workplace,
            category=d.get("department"),
            remote=(workplace == "remote") or detect_remote(location),
            posted_at=d.get("publishedAt"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )


def _num(raw) -> str:
    try:
        return f"{int(round(float(raw))):,}"
    except (TypeError, ValueError):
        return str(raw)
