"""Jobvite connector — public, server-rendered career sites.

Jobvite hosts each customer's career site at ``jobs.jobvite.com/{slug}``.
The listing is server-rendered HTML (no JS needed): each job is a table row
with ``jv-job-list-name`` (title + link to ``.../job/{id}``) and
``jv-job-list-location``. Jobvite serves two URL shapes with the same markup
-- legacy ``/{slug}/search?p=N`` and modern ``/careers/{slug}/jobs`` -- so we
try both and use whichever returns rows. Results paginate 50 per page via
``?p=N``. No API key, no CSRF; the host serves no robots.txt (404 ->
allowed). A board is the company slug (e.g. "nutanix").

Individual job pages carry no JSON-LD, so we take title, location and the
job URL from the listing — enough for an index entry; descriptions are left
to the apply link.
"""

from __future__ import annotations

import re

import requests

from ..models import Job, now_iso
from ..normalize import detect_remote, make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

BASE = "https://jobs.jobvite.com"
TIMEOUT = 25
PAGE_SIZE = 50
MAX_PAGES = 60

_ROW_RE = re.compile(
    r'<td[^>]*class="[^"]*jv-job-list-name[^"]*"[^>]*>\s*'
    r'<a[^>]+href="(?P<href>[^"]+/job/[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
    r'<td[^>]*class="[^"]*jv-job-list-location[^"]*"[^>]*>(?P<loc>.*?)</td>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(raw: str) -> str:
    text = _TAG_RE.sub(" ", raw or "")
    text = (text.replace("&amp;", "&").replace("&nbsp;", " ")
                .replace("&#39;", "'").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", text).strip()


class JobviteConnector(Connector):
    platform = "jobvite"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._company = board.replace("-", " ").replace("_", " ").strip().title() or board

    def fetch(self) -> list[Job]:
        fetched_at = now_iso()
        # Jobvite serves two listing shapes with identical row markup but
        # different paging: legacy /{slug}/search paginates via ?p=N, while
        # modern /careers/{slug}/jobs lists everything on one page and returns
        # nothing if a ?p= param is sent. Try legacy first, then modern.
        for listing, paginated in ((f"{BASE}/{self.board}/search/", True),
                                   (f"{BASE}/careers/{self.board}/jobs", False)):
            if not robots_allowed(listing, self._session):
                continue
            jobs = self._crawl(listing, fetched_at, paginated)
            if jobs:
                return jobs
        return []

    def _crawl(self, listing: str, fetched_at: str, paginated: bool) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()
        page = 1
        while page <= MAX_PAGES:
            params = {"p": page} if paginated else None
            resp = self._session.get(listing, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            rows = list(_ROW_RE.finditer(resp.text))
            if not rows:
                break
            new = 0
            for m in rows:
                job = self._to_job(m, fetched_at)
                if job is None or job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
                new += 1
            if not paginated or len(rows) < PAGE_SIZE or new == 0:
                break
            page += 1
        return jobs

    def _to_job(self, m: re.Match, fetched_at: str) -> Job | None:
        title = _clean(m.group("title"))
        if not title:
            return None
        href = m.group("href").strip()
        jid = href.rstrip("/").rsplit("/job/", 1)[-1]
        url = href if href.startswith("http") else f"{BASE}{href}"
        location = _clean(m.group("loc")) or None
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=jid or title,
            title=title,
            company=self._company,
            location=location,
            description=None,
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=None,
            workplace_type=None,
            category=None,
            remote=detect_remote(location),
            posted_at=None,
            dedup_key=make_dedup_key(title, self._company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
