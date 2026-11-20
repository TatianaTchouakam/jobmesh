"""Comeet (Spark Hire Recruit) connector — public, keyless.

Two board formats are supported:

* ``"company/uid"`` (preferred) reads the Comeet-hosted careers page
  ``https://www.comeet.com/jobs/{company}/{uid}``. The page embeds every
  published position as a ``COMPANY_POSITIONS_DATA`` JSON array, so one
  request lists them all with no token. Example: ``"tripleten/98.008"``.

* ``"uid:token[:Company Name]"`` reads the public Careers API
  ``https://www.comeet.co/careers-api/2.0/company/{uid}/positions`` (the
  same uid/token a careers page embeds). Kept for boards that only expose
  the pair.

robots.txt on comeet.com allows /jobs/ and /careers-api/.
"""

from __future__ import annotations

import json
import re

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

API_ROOT = "https://www.comeet.co/careers-api/2.0/company"
PAGE_ROOT = "https://www.comeet.com/jobs"
USER_AGENT = "JobmeshBot/0.1 (+https://github.com/TatianaTchouakam/jobmesh)"
TIMEOUT = 20

# The hosted page writes the outer array/object, each terminated by ``];``/``};``.
_POS_RE = re.compile(r"COMPANY_POSITIONS_DATA\s*=\s*(\[.*?\])\s*;", re.DOTALL)


def _strip_token(url: str | None) -> str | None:
    """Drop a ?token=... (or &token=...) query so we never store the token."""
    if not url:
        return url
    for sep in ("?token=", "&token="):
        if sep in url:
            head, _, tail = url.partition(sep)
            rest = tail.split("&", 1)
            kept = rest[1] if len(rest) > 1 else ""
            return head + (("?" + kept) if (sep == "?token=" and kept) else "")
    return url


class ComeetConnector(Connector):
    platform = "comeet"

    def __init__(self, board: str, session: requests.Session | None = None):
        super().__init__(board)
        self.company_name = None
        if ":" in board:  # uid:token[:Company Name] -> careers API
            parts = board.split(":", 2)
            self.uid = parts[0]
            self.token = parts[1] if len(parts) > 1 else ""
            self.company_name = parts[2] if len(parts) > 2 else None
            self._page_path = None
            self._board_id = self.uid  # token-free id for storage
        else:  # "company/uid" -> keyless hosted page
            self.token = ""
            self._page_path = board.strip("/")
            self.uid = self._page_path.split("/")[-1]
            self._board_id = self._page_path  # == config board, matches close_absent
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch(self) -> list[Job]:
        positions = self._get_positions()
        fetched_at = now_iso()
        company = (
            self.company_name
            or (positions[0].get("company_name") if positions else None)
            or self.uid
        )
        return [
            self._to_job(p, company, fetched_at)
            for p in positions
            if not p.get("is_internal")
        ]

    def _get_positions(self) -> list[dict]:
        if self.token:  # careers API (uid:token)
            resp = self._session.get(
                f"{API_ROOT}/{self.uid}/positions",
                params={"token": self.token, "details": "true"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data.get("positions") or data.get("data") or []
            return data or []
        # keyless hosted page: parse embedded COMPANY_POSITIONS_DATA
        resp = self._session.get(f"{PAGE_ROOT}/{self._page_path}", timeout=TIMEOUT)
        resp.raise_for_status()
        m = _POS_RE.search(resp.text)
        if not m:
            return []
        return json.loads(m.group(1))

    @staticmethod
    def _description(data: dict) -> str | None:
        details = data.get("details")
        if isinstance(details, list):
            chunks = []
            for section in details:
                if not isinstance(section, dict):
                    continue
                name = section.get("name")
                value = section.get("value")
                if value:
                    chunks.append(f"{name}\n{value}" if name else str(value))
            if chunks:
                return html_to_text("\n\n".join(chunks))
        return html_to_text(data.get("description"))

    def _to_job(self, data: dict, company: str, fetched_at: str) -> Job:
        loc = data.get("location") or {}
        if isinstance(loc, dict):
            location = loc.get("name") or ", ".join(
                x for x in (loc.get("city"), loc.get("state"), loc.get("country")) if x
            ) or None
            is_remote = bool(loc.get("is_remote"))
        else:
            location = loc or None
            is_remote = False

        title = data.get("name") or "(untitled)"
        url = (
            _strip_token(data.get("url_comeet_hosted_page"))
            or _strip_token(data.get("url_active_page"))
            or _strip_token(data.get("url"))
            or _strip_token(data.get("position_url"))
        )
        workplace = (data.get("workplace_type") or "").lower() or None
        remote = is_remote or workplace == "remote" or bool(detect_remote(location))

        return Job(
            source_platform=self.platform,
            source_board=self._board_id,
            source_job_id=str(data.get("uid") or data.get("id") or title),
            title=title,
            company=company,
            location=location,
            description=self._description(data),
            source_url=url,
            apply_url=url,
            salary=None,
            employment_type=data.get("employment_type") or data.get("position_type"),
            workplace_type=workplace,
            category=data.get("department"),
            level=data.get("experience_level"),
            remote=remote,
            posted_at=data.get("time_updated") or data.get("time_created"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=fetched_at,
            last_checked=fetched_at,
            is_open=True,
        )
