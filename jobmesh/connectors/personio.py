"""Personio connector (ATS, strong in Germany/DACH).

Reads the public Personio careers XML feed (no key):
    https://{company}.jobs.personio.de/xml

Root element is <workzag-jobs> with repeated <position> elements. The job
description is split across <jobDescriptions>/<jobDescription> blocks.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, make_dedup_key
from .base import Connector

USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25


class PersonioConnector(Connector):
    platform = "personio"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        url = f"https://{self.board}.jobs.personio.de/xml"
        resp = self._session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        company = self.board.replace("-", " ").title()
        at = now_iso()
        return [self._to_job(p, company, at) for p in root.iter("position")]

    def _to_job(self, p: ET.Element, company: str, at: str) -> Job:
        def txt(tag):
            el = p.find(tag)
            return el.text.strip() if el is not None and el.text else None

        job_id = txt("id") or ""
        title = txt("name") or "(untitled)"
        location = txt("office")
        department = txt("department") or txt("recruitingCategory")
        schedule = txt("schedule")
        employment = txt("employmentType")

        # description: join every <jobDescription>/<value>
        parts = []
        for jd in p.iter("jobDescription"):
            v = jd.find("value")
            if v is not None and v.text:
                parts.append(v.text)
        description = html_to_text(" ".join(parts)) if parts else None

        url = f"https://{self.board}.jobs.personio.de/job/{job_id}" if job_id else None

        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=str(job_id),
            title=title, company=company, location=location,
            description=description,
            source_url=url, apply_url=url,
            salary=None,
            employment_type=schedule or employment,
            workplace_type=None,
            category=department,
            remote=None,
            posted_at=txt("createdAt"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
