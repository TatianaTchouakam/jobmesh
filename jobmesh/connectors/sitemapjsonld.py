"""Generic sitemap + schema.org JobPosting (JSON-LD) connector.

Many employer career sites and ATS portals publish a public sitemap of
their job pages, and each job page carries a schema.org ``JobPosting``
JSON-LD block rendered server-side. This connector reads any such
sitemap (plain or gzip, a flat ``urlset`` or a ``sitemapindex``), then
pulls the ``JobPosting`` data from each listed page, reusing the shared
JSON-LD helpers (same recipe as the iCIMS connector, but not tied to one
host). It is keyless and headless, identifies itself as ``JobmeshBot``,
obeys robots.txt for that agent, and fetches at a low rate.

A board is ``"{sitemap_url}|{Company}"``::

    "https://careers.example.com/sitemap.xml|Example Corp"

The company segment is optional. When present it pins the employer name
— career-site sitemaps are usually one company, and some job pages omit
``hiringOrganization`` from their JSON-LD. Without it, the company is
read from each posting::

    "https://careers.example.com/sitemap.xml"

Tunables (environment variables):
    SITEMAP_MAX_JOBS   max job pages fetched per board   (default 300)
    SITEMAP_WORKERS    parallel page fetches             (default 6)
"""

from __future__ import annotations

import gzip
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests

from ..models import Job, now_iso
from ..normalize import make_dedup_key
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job

TIMEOUT = 30
MAX_JOBS = int(os.environ.get("SITEMAP_MAX_JOBS", "300"))
WORKERS = int(os.environ.get("SITEMAP_WORKERS", "6"))
MAX_SUBSITEMAPS = 40

# A loc that is itself a (sub-)sitemap rather than a page.
_SITEMAP_LOC = re.compile(r"\.xml(\.gz)?(\?|$)|sitemap", re.I)
# Loc paths that look like a job/vacancy page (multi-lingual, loose on purpose).
_JOBISH = re.compile(
    r"/(jobs?|careers?|positions?|vacanc(?:y|ies)|openings?|roles?|"
    r"stellen?|emplois?|offres?|empleos?|vagas?)[/\-_0-9]"
    r"|[-/]job-?\d",   # trailing id form, e.g. ...-live-in-carer-job21127
    re.I,
)


def _locs(content: bytes) -> list[str]:
    """Every ``<loc>`` text in a sitemap document (transparently gunzips)."""
    if content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except OSError:
            return []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    out: list[str] = []
    for el in root.iter():
        if el.tag.split("}", 1)[-1].lower() == "loc" and el.text:
            out.append(el.text.strip())
    return out


class SitemapJsonLdConnector(Connector):
    platform = "sitemapjsonld"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        sitemap_url, _, company = board.partition("|")
        self._sitemap_url = sitemap_url.strip()
        self._company = company.strip() or None
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def _page_urls(self) -> list[str]:
        if not robots_allowed(self._sitemap_url, self._session):
            return []
        resp = self._session.get(self._sitemap_url, timeout=TIMEOUT)
        resp.raise_for_status()
        locs = _locs(resp.content)
        pages = [u for u in locs if not _SITEMAP_LOC.search(u)]
        # Root was a sitemap index (or had no direct pages): follow sub-sitemaps.
        if not pages:
            subs = [u for u in locs if _SITEMAP_LOC.search(u)]
            for sub in subs[:MAX_SUBSITEMAPS]:
                try:
                    r = self._session.get(sub, timeout=TIMEOUT)
                    r.raise_for_status()
                except requests.RequestException:
                    continue
                pages.extend(u for u in _locs(r.content) if not _SITEMAP_LOC.search(u))
                if len(pages) >= MAX_JOBS * 4:
                    break
        # De-duplicate, preserving order.
        seen: set[str] = set()
        ordered = [u for u in pages if not (u in seen or seen.add(u))]
        # Prefer job-looking URLs when the sitemap mixes pages; otherwise keep all.
        jobish = [u for u in ordered if _JOBISH.search(u)]
        chosen = jobish or ordered
        return chosen[:MAX_JOBS]

    def _fetch_page(self, url: str, fetched_at: str) -> list[Job]:
        if not robots_allowed(url, self._session):
            return []
        try:
            r = self._session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
        except requests.RequestException:
            return []
        jobs: list[Job] = []
        for p in parse_jobpostings(r.text):
            job = posting_to_job(p, self.platform, self.board, fetched_at, url)
            if job is None:
                continue
            if self._company:
                job.company = self._company
                job.dedup_key = make_dedup_key(job.title, self._company, job.location)
            jobs.append(job)
        return jobs

    def fetch(self) -> list[Job]:
        urls = self._page_urls()
        fetched_at = now_iso()
        jobs: list[Job] = []
        seen: set[str] = set()
        if not urls:
            return jobs
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for page_jobs in pool.map(lambda u: self._fetch_page(u, fetched_at), urls):
                for job in page_jobs:
                    if job.source_job_id in seen:
                        continue
                    seen.add(job.source_job_id)
                    jobs.append(job)
        return jobs
