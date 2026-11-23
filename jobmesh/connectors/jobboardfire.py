"""JobBoardFire connector — niche job boards built on Job Board Fire.

Job Board Fire (jobboardfire.com) is job-board software used by publishers
and communities to run their own branded boards (e.g. Product Marketing
Alliance, Trellis/GreenBiz). Every board ships Google-for-Jobs support, so
each board exposes a ``/sitemap-jobs.xml`` listing its job detail pages, and
every detail page embeds a clean schema.org ``JobPosting`` JSON-LD block
(title, datePosted, hiringOrganization, jobLocation). No key, no cookie, no
CSRF, no anti-bot bypass — just the sitemap and the public detail pages.

The job detail path varies per board (``/jobs/{slug}`` on one, ``/j/{slug}``
on another), so the connector trusts ``sitemap-jobs.xml`` for the URL list
rather than guessing a path. A board is the board host, e.g.
``jobs.productmarketingalliance.com``. robots.txt is honoured per host; the
seeded boards allow ``/`` and only block private zones (/api, /admin,
/employer, ...). Jobmesh links back to each original posting.
"""

from __future__ import annotations

import re

import requests

from ..models import now_iso
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job

TIMEOUT = 25
MAX_JOBS = 1000
_LOC_RE = re.compile(r"<loc>([^<]+)</loc>", re.IGNORECASE)


class JobBoardFireConnector(Connector):
    platform = "jobboardfire"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault(
            "Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        self._session.headers["Accept-Encoding"] = "gzip, deflate"
        host = self.board.replace("https://", "").replace("http://", "").strip("/")
        self._host = host
        self._sitemap = f"https://{host}/sitemap-jobs.xml"

    def _job_urls(self) -> list[str]:
        if not robots_allowed(self._sitemap, self._session):
            return []
        try:
            resp = self._session.get(self._sitemap, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException:
            return []
        urls = [u.strip() for u in _LOC_RE.findall(resp.text)]
        # sitemap-jobs.xml lists only job detail pages; keep them in order.
        seen: set[str] = set()
        out: list[str] = []
        for u in urls:
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out[:MAX_JOBS]

    def fetch(self) -> list:
        at = now_iso()
        jobs = []
        seen: set[str] = set()
        for url in self._job_urls():
            if not robots_allowed(url, self._session):
                continue
            slug = url.rstrip("/").rsplit("/", 1)[-1]
            try:
                page = self._session.get(url, timeout=TIMEOUT)
                page.raise_for_status()
            except requests.RequestException:
                continue
            for posting in parse_jobpostings(page.text):
                job = posting_to_job(posting, self.platform, self.board, at, url)
                if job is None:
                    continue
                job.source_job_id = slug
                job.source_url = url
                job.apply_url = url
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
        return jobs
