"""SAP SuccessFactors connector — Career Site Builder (CSB) sites.

SuccessFactors CSB (formerly jobs2web) powers many large employers' career
sites (Boehringer Ingelheim, BASF, E.ON, Fraunhofer, ...). We never touch
the token-gated search API: instead we use the public, robots-permitted
surface each CSB site exposes for Google for Jobs —

  * ``/sitemap.xml`` lists every ``/job/{slug}/{id}/`` detail page, and
  * each detail page server-renders schema.org **microdata** (itemprop):
    datePosted, addressLocality/Region/Country, hiringOrganization,
    title/description — plus clean og:title / og:description.

So this is the shared "sitemap + schema.org JobPosting" recipe, in its
microdata form, with no session token and no DOM scraping. robots.txt on
CSB sites disallows only utility paths (/services/, /applybutton/, ...),
not /job/ or the sitemap. ``board`` is "host|Company"
(e.g. "jobs.boehringer-ingelheim.com|Boehringer Ingelheim").
"""

from __future__ import annotations

import re

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key, normalize_date
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector

TIMEOUT = 30
MAX_JOBS = 300

_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)
_JOB_ID = re.compile(r"/job/[^\"<>\s]*?/(\d+)/?$")
_META = lambda name: re.compile(
    rf'<meta[^>]*itemprop="{name}"[^>]*content="([^"]*)"', re.IGNORECASE)
_OG = lambda name: re.compile(
    rf'<meta[^>]*property="og:{name}"[^>]*content="([^"]*)"', re.IGNORECASE)
_DESC = re.compile(r'class="jobdescription">(.*?)</span>\s*</span>', re.IGNORECASE | re.DOTALL)
_UNESCAPE = __import__("html").unescape


def _meta(html_text: str, name: str) -> str | None:
    m = _META(name).search(html_text)
    return _UNESCAPE(m.group(1)).strip() if m else None


def _og(html_text: str, name: str) -> str | None:
    m = _OG(name).search(html_text)
    return _UNESCAPE(m.group(1)).strip() if m else None


def _clean_date(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = re.sub(r"\s+(UTC|GMT)\s+", " ", raw).strip()
    return normalize_date(raw)


class SuccessFactorsConnector(Connector):
    platform = "successfactors"

    def __init__(self, board: str, session: requests.Session | None = None):
        host, _, company = board.partition("|")
        super().__init__(host.strip())
        self._host = host.strip()
        self._company = company.strip() or host.strip()
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._base = f"https://{self._host}"

    def fetch(self) -> list[Job]:
        sitemap = f"{self._base}/sitemap.xml"
        if not robots_allowed(sitemap, self._session):
            return []
        resp = self._session.get(sitemap, timeout=TIMEOUT)
        resp.raise_for_status()
        urls: list[tuple[str, str]] = []
        seen_ids: set[str] = set()
        for loc in _LOC.findall(resp.text):
            m = _JOB_ID.search(loc)
            if not m:
                continue
            jid = m.group(1)
            if jid not in seen_ids:
                seen_ids.add(jid)
                urls.append((jid, loc))
        at = now_iso()
        jobs: list[Job] = []
        for jid, url in urls[:MAX_JOBS]:
            if not robots_allowed(url, self._session):
                continue
            try:
                page = self._session.get(url, timeout=TIMEOUT)
                page.raise_for_status()
            except requests.RequestException:
                continue
            job = self._to_job(jid, url, page.text, at)
            if job is not None:
                jobs.append(job)
        return jobs

    def _to_job(self, jid: str, url: str, html_text: str, at: str) -> Job | None:
        title = _og(html_text, "title") or _meta(html_text, "title")
        if not title:
            return None
        locality = _meta(html_text, "addressLocality")
        region = _meta(html_text, "addressRegion")
        location = ", ".join(p for p in (locality, region) if p and p.lower() != "null") or None
        m = _DESC.search(html_text)
        desc = html_to_text(m.group(1)) if m else _og(html_text, "description")
        return Job(
            source_platform=self.platform,
            source_board=self.board,
            source_job_id=jid,
            title=title,
            company=self._company,
            location=location,
            description=desc,
            source_url=url,
            apply_url=url,
            remote=detect_remote(f"{location or ''} {title}"),
            posted_at=_clean_date(_meta(html_text, "datePosted")),
            dedup_key=make_dedup_key(title, self._company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )
