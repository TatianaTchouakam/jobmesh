"""Africarrieres connector — pan-African Francophone/multilingual job board.

Africarrieres (africarrieres.com) indexes jobs across African countries, with
per-country / per-language sitemaps (``/sitemap-{cc}-{lang}.xml``, e.g.
``sitemap-cm-fr.xml`` for Cameroon in French). Each job detail page
``/{country}/{lang}/emplois/{slug}`` embeds a clean schema.org ``JobPosting``
JSON-LD block (title, datePosted, hiringOrganization, a full PostalAddress
with addressLocality + addressCountry). No key, no cookie, no CSRF.

robots.txt explicitly welcomes citing search robots (``Content-Signal:
search=yes``, ``Allow: /`` for ``*``) and only blocks AI-training and
SEO-data-resale crawlers; it does not block citing job indexers. Jobmesh
links back to each original posting, so it fits both the letter and the
stated spirit ("on garde les robots qui citent"). The ``*`` group's private
zones (/dashboard, /employeur, /connexion, ...) are honoured by our robots
layer. A board is the ``{cc}-{lang}`` sitemap code (e.g. "cm-fr").
"""

from __future__ import annotations

import re

import requests

from ..models import now_iso
from ..robots import allowed as robots_allowed, USER_AGENT
from .base import Connector
from .careersite import parse_jobpostings, posting_to_job

TIMEOUT = 25
MAX_JOBS = 600
HOST = "https://africarrieres.com"
# Job detail URLs look like /{country}/{lang}/emplois/{slug} (one slug segment).
_JOB_URL_RE = re.compile(r"/emplois/[^/]+$", re.IGNORECASE)
_LOC_RE = re.compile(r"<loc>([^<]+)</loc>", re.IGNORECASE)


class AfricarrieresConnector(Connector):
    platform = "africarrieres"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault(
            "Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        self._session.headers.setdefault("Accept-Language", "fr-FR,fr;q=0.9,en;q=0.8")
        self._session.headers["Accept-Encoding"] = "gzip, deflate"
        self._sitemap = f"{HOST}/sitemap-{self.board}.xml"

    def _job_urls(self) -> list[str]:
        if not robots_allowed(self._sitemap, self._session):
            return []
        try:
            resp = self._session.get(self._sitemap, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException:
            return []
        urls = [u.strip() for u in _LOC_RE.findall(resp.text)]
        return [u for u in urls if _JOB_URL_RE.search(u)][:MAX_JOBS]

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
                # Stable per-job id from the URL slug (JSON-LD identifier is not
                # reliably unique across postings).
                job.source_job_id = slug
                job.source_url = url
                job.apply_url = url
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
        return jobs
