"""Paycom connector -- public job posting pages on paycomonline.net.

Paycom's career portals are client-rendered, but each individual posting page
is served with a full schema.org ``JobPosting`` JSON-LD block at the
robots-allowed route::

    https://www.paycomonline.net/v4/ats/web.php/portal/{key}/jobs/{id}

robots.txt is ``Disallow: /`` with ``Allow: /v4/ats/web.php/portal/`` -- the
posting route is permitted under the RFC 9309 longest-match rule (our shared
robots guard applies it). There is no public listing or sitemap, so a board
carries the portal key and the known posting ids, discovered from the public
URL index::

    {key}:{id1},{id2},...

Each cycle re-reads those pages; a posting that 404s is simply absent (the
pipeline marks it closed -- a 404 never mass-closes a board). New postings are
picked up when the discovered id set is refreshed.
"""

from __future__ import annotations

import requests

from ..models import Job, now_iso
from ..ratelimit import get_limiter
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job

TIMEOUT = 25
BASE = "https://www.paycomonline.net"


def _parse_board(board: str):
    key, _, ids = (board or "").partition(":")
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    return key.strip(), id_list


class PaycomConnector(Connector):
    platform = "paycom"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.key, self.ids = _parse_board(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def _fiche_url(self, jid: str) -> str:
        return f"{BASE}/v4/ats/web.php/portal/{self.key}/jobs/{jid}"

    def fetch(self) -> list[Job]:
        at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        for jid in self.ids:
            url = self._fiche_url(jid)
            if not robots_allowed(url, self._session):
                continue
            try:
                with get_limiter("paycom").slot("paycomonline.net"):
                    r = self._session.get(url, timeout=TIMEOUT)
                if r.status_code == 404:
                    continue                      # posting closed -> absent
                r.raise_for_status()
            except requests.RequestException:
                continue
            postings = parse_jobpostings(r.text)
            if not postings:
                continue
            job = posting_to_job(postings[0], self.platform, self.board, at, url)
            if job is None or jid in seen:
                continue
            job.source_job_id = jid
            seen.add(jid)
            jobs.append(job)
        return jobs
