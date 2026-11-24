"""BrassRing (Kenexa/IBM) connector — token-free, via public job-detail JSON-LD.

A BrassRing careersite (``sjobs.brassring.com/TGnewUI/...``) renders its list as
a SPA (the ``HomeSearch`` route needs the home page's session), and there is no
sitemap. But each job-detail page
(``...HomeWithPreLoad?partnerid={pid}&siteid={sid}&PageType=JobDetails&jobid={id}``)
is server-rendered with a clean schema.org ``JobPosting`` JSON-LD block, and
``sjobs.brassring.com`` serves no robots.txt (allowed by convention). Verified
24/11 on Bechtel (partnerid 26639, siteid 5507).

We enumerate the public job-detail URLs for one employer from the Common Crawl
index (open web, no token) and read each page's JSON-LD. ``board`` is
"partnerid|siteid". robots.txt is honoured on every fetch; JobmeshBot UA.
"""

from __future__ import annotations

import re

import requests

from ..models import now_iso
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job
from .. import ccindex

TIMEOUT = 25
MAX_JOBS = 2000
REQUEST_DELAY = 0.4
HOST = "sjobs.brassring.com"
_JOB_ID = re.compile(r"[?&]jobid=(\d+)", re.IGNORECASE)


class BrassRingConnector(Connector):
    platform = "brassring"

    def __init__(self, board: str, session: requests.Session | None = None,
                 url_source=None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        pid, _, sid = board.partition("|")
        self._pid, self._sid = pid.strip(), sid.strip()
        self._url_source = url_source

    def _discover(self) -> list[str]:
        return ccindex.detail_urls(
            self._session, HOST, "/TGnewUI/Search/home/HomeWithPreLoad",
            must_contain=["PageType=JobDetails", f"partnerid={self._pid}",
                          f"siteid={self._sid}"], limit=MAX_JOBS)

    def fetch(self) -> list:
        src = self._url_source
        urls = (src() if callable(src) else src) if src is not None else self._discover()
        at = now_iso()
        jobs = []
        seen: set[str] = set()
        import time
        for url in urls:
            if not robots_allowed(url, self._session):
                continue
            m = _JOB_ID.search(url)
            jid = m.group(1) if m else url
            try:
                page = self._session.get(url, timeout=TIMEOUT)
                page.raise_for_status()
            except requests.RequestException:
                continue
            for posting in parse_jobpostings(page.text):
                job = posting_to_job(posting, self.platform, self.board, at, url)
                if job is None:
                    continue
                job.source_job_id = jid
                job.source_url = url
                job.apply_url = url
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
            if self._url_source is None:
                time.sleep(REQUEST_DELAY)
        return jobs
