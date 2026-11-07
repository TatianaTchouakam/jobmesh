"""Adzuna connector (job board, free API key).

Reads the public Adzuna Search API:
    https://api.adzuna.com/v1/api/jobs/{country}/search/{page}

Adzuna is a generalist aggregator covering ~20 countries and ALL sectors
(healthcare, trades, logistics, admin, finance, retail, ...), not just
tech. One `board` = one country code, e.g. "za" (South Africa), "de"
(Germany), "gb", "us", "fr", "in". That is how we get worldwide,
all-category coverage from a single connector.

Credentials are READ FROM THE ENVIRONMENT, never hard-coded:
    ADZUNA_APP_ID   and   ADZUNA_APP_KEY
Get them free at https://developer.adzuna.com (sign up -> app id + key).
If the variables are missing, the connector raises a clear error so the
pipeline logs it as a normal fetch failure rather than crashing.
"""

from __future__ import annotations

import os
import time

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API_ROOT = "https://api.adzuna.com/v1/api/jobs"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 25
RESULTS_PER_PAGE = 50      # Adzuna's maximum per page
# Adzuna's FREE tier is ~250 calls/day and ~2,500/month. We deliberately
# keep page depth low (2 pages = up to 100 roles per country per run) so a
# handful of countries per ingest stays well inside the free budget and the
# fetch_log stays clean. Raise this only if you move to a paid Adzuna plan.
MAX_PAGES = 2

# Countries Adzuna serves (used to validate the board token early).
VALID_COUNTRIES = {
    "at", "au", "be", "br", "ca", "ch", "de", "es", "fr", "gb",
    "in", "it", "mx", "nl", "nz", "pl", "sg", "us", "za",
}


def _credentials() -> tuple[str, str]:
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise RuntimeError(
            "Adzuna credentials missing: set ADZUNA_APP_ID and ADZUNA_APP_KEY "
            "(free at https://developer.adzuna.com)."
        )
    return app_id, app_key


class AdzunaConnector(Connector):
    platform = "adzuna"

    def __init__(self, board: str = "gb", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        country = (self.board or "gb").lower().strip()
        if country not in VALID_COUNTRIES:
            raise ValueError(
                f"Adzuna: unknown country code {country!r}. "
                f"Use one of: {', '.join(sorted(VALID_COUNTRIES))}."
            )
        app_id, app_key = _credentials()
        at = now_iso()
        jobs: list[Job] = []
        for page in range(1, MAX_PAGES + 1):
            results = self._get_page(country, page, app_id, app_key)
            if not results:
                break
            jobs.extend(self._to_job(r, country, at) for r in results)
            if len(results) < RESULTS_PER_PAGE:
                break    # last page reached
        return jobs

    def _get_page(self, country: str, page: int, app_id: str, app_key: str) -> list[dict]:
        url = f"{API_ROOT}/{country}/search/{page}"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": RESULTS_PER_PAGE,
            "content-type": "application/json",
        }
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = self._session.get(url, params=params, timeout=TIMEOUT)
                resp.raise_for_status()
                return resp.json().get("results", []) or []
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    def _to_job(self, d: dict, country: str, at: str) -> Job:
        title = d.get("title") or "(untitled)"
        company = ((d.get("company") or {}).get("display_name")) or "Unknown"
        location = (d.get("location") or {}).get("display_name")
        url = d.get("redirect_url")
        category = (d.get("category") or {}).get("label")

        salary = _salary(d.get("salary_min"), d.get("salary_max"))
        employment_type = d.get("contract_time") or d.get("contract_type")

        return Job(
            source_platform=self.platform,
            source_board=country,
            source_job_id=str(d.get("id")),
            title=title,
            company=company,
            location=location,
            description=html_to_text(d.get("description")),
            source_url=url,
            apply_url=url,
            salary=salary,
            employment_type=employment_type,
            category=category,
            remote=detect_remote(" ".join(x for x in (location, title) if x)),
            posted_at=d.get("created"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at,
            last_checked=at,
            is_open=True,
        )


def _salary(lo, hi) -> str | None:
    """Build a readable salary string from Adzuna's min/max numbers."""
    def fmt(v):
        try:
            return f"{int(round(float(v))):,}"
        except (TypeError, ValueError):
            return None
    lo_s, hi_s = fmt(lo), fmt(hi)
    if lo_s and hi_s:
        return lo_s if lo_s == hi_s else f"{lo_s}–{hi_s}"
    return lo_s or hi_s
