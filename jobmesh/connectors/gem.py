"""Gem connector — public, keyless GraphQL careers API.

Gem (gem.com) hosts each customer's job board at
``jobs.gem.com/{board}``. The page is JS-rendered, but it reads a public,
unauthenticated GraphQL endpoint on the same origin:

    POST https://jobs.gem.com/api/public/graphql/batch
    body: [{operationName:"JobBoardList", variables:{boardId}, query:...}]

The ``oatsExternalJobPostings`` field returns every public posting with its
title, locations, department, employment and workplace type; the board's
display name comes from ``jobBoardExternal.teamDisplayName``. Each posting's
``extId`` is the slug used in its public URL ``jobs.gem.com/{board}/{extId}``.
No key, no CSRF. jobs.gem.com serves no robots.txt (404 -> allowed); we still
pass every request through the shared robots guard. A board is the vanity
slug (e.g. "nabla-bio").
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key, normalize_workplace
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

ENDPOINT = "https://jobs.gem.com/api/public/graphql/batch"
BASE = "https://jobs.gem.com"
TIMEOUT = 25

_QUERY = (
    "query JobBoardList($boardId: String!) {\n"
    "  oatsExternalJobPostings(boardId: $boardId) {\n"
    "    jobPostings {\n"
    "      id extId title\n"
    "      locations { name city isoCountry isRemote }\n"
    "      job { department { name } locationType employmentType }\n"
    "    }\n"
    "  }\n"
    "  jobBoardExternal(vanityUrlPath: $boardId) { teamDisplayName }\n"
    "}"
)


class GemConnector(Connector):
    platform = "gem"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        if not robots_allowed(ENDPOINT, self._session):
            return []
        payload = [{
            "operationName": "JobBoardList",
            "variables": {"boardId": self.board},
            "query": _QUERY,
        }]
        resp = self._session.post(ENDPOINT, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        entry = data[0] if isinstance(data, list) else data
        d = (entry or {}).get("data") or {}
        posts = ((d.get("oatsExternalJobPostings") or {}).get("jobPostings")) or []
        company = ((d.get("jobBoardExternal") or {}).get("teamDisplayName")
                   or self.board.replace("-", " ").replace("_", " ").title())
        fetched_at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for p in posts:
            job = self._to_job(p, company, fetched_at)
            if job is None or job.source_job_id in seen:
                continue
            seen.add(job.source_job_id)
            jobs.append(job)
        return jobs

    @staticmethod
    def _location(p: dict) -> tuple[str | None, bool]:
        locs = p.get("locations") or []
        remote = any(l.get("isRemote") for l in locs)
        if locs:
            first = locs[0] or {}
            label = first.get("name") or ", ".join(
                x for x in (first.get("city"), first.get("isoCountry")) if x)
            if label:
                return label, remote
        return (("Remote" if remote else None), remote)

    def _to_job(self, p: dict, company: str, fetched_at: str) -> Job | None:
        title = p.get("title")
        if not title:
            return None
        ext = p.get("extId") or p.get("id")
        jid = str(ext)
        location, remote = self._location(p)
        job = p.get("job") or {}
        workplace = normalize_workplace(job.get("locationType"))
        remote = remote or workplace == "remote"
        url = f"{BASE}/{self.board}/{ext}"
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=jid,
            title=title,
            company=company,
            location=location,
            description=None,
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=job.get("employmentType"),
            workplace_type=workplace,
            category=(job.get("department") or {}).get("name"),
            remote=remote or detect_remote(location),
            posted_at=None,
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
