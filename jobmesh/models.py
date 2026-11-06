"""Core data model: a single, consistent representation of a job posting.

Every connector, whatever platform it reads from, must return a list of
`Job` objects. Keeping one schema here is what lets the rest of the
system (storage, dedup, search, API) stay platform-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string (used for bookkeeping)."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    """One job posting, normalized across every source platform."""

    # --- Source identity (together these uniquely identify a posting) ---
    source_platform: str          # e.g. "greenhouse", "lever", "ashby"
    source_board: str             # the company's board token, e.g. "gitlab"
    source_job_id: str            # the posting id as given by the platform

    # --- Core fields required by the challenge ---
    title: str
    company: str
    location: Optional[str] = None
    description: Optional[str] = None   # plain text (HTML stripped)
    source_url: Optional[str] = None    # the listing page
    apply_url: Optional[str] = None     # the application page

    # --- Preserved when the source provides them ---
    salary: Optional[str] = None
    employment_type: Optional[str] = None
    remote: Optional[bool] = None
    posted_at: Optional[str] = None     # original posting date (ISO-8601)

    # --- Bookkeeping maintained by jobmesh, not the source ---
    dedup_key: Optional[str] = None     # groups the same role across sources
    first_seen: Optional[str] = None    # first time we indexed this posting
    last_checked: Optional[str] = None  # last successful refresh that saw it
    is_open: bool = True                # False once it disappears from source

    @property
    def uid(self) -> str:
        """Stable unique id for one posting on one board."""
        return f"{self.source_platform}:{self.source_board}:{self.source_job_id}"

    def to_dict(self) -> dict:
        return asdict(self)
