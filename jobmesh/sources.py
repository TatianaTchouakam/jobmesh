"""Source registry — the integration status of every required platform.

Separates *technical* access (can we read the jobs?) from *commercial* access
(are we allowed to, and has the client connected?). Only ACTIVE sources run in
the daily ingest; the rest are declared with a reason and a next action, never
silently failed and never counted as covered. This is what lets JobMesh report
honestly on all 78 required platforms — see config/sources.yaml.
"""

from __future__ import annotations

import os
from collections import Counter

import yaml

STATUSES = (
    "ACTIVE",
    "API_REQUIRED",
    "PARTNERSHIP_REQUIRED",
    "CLIENT_CONNECTION_REQUIRED",
    "TEMPORARILY_UNAVAILABLE",
    "RETIRED",
)

_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "config", "sources.yaml")


def load_sources(path: str | None = None) -> dict:
    with open(path or _DEFAULT, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    data.setdefault("required_ats", [])
    data.setdefault("required_boards", [])
    data.setdefault("bonus_sources", [])
    return data


def all_required(data: dict | None = None) -> list[dict]:
    data = data or load_sources()
    return list(data["required_ats"]) + list(data["required_boards"])


def bonus_sources(data: dict | None = None) -> list[dict]:
    data = data or load_sources()
    return list(data.get("bonus_sources", []))


def status_counts(data: dict | None = None) -> dict[str, int]:
    return dict(Counter(p["status"] for p in all_required(data)))


def active_connectors(data: dict | None = None) -> set[str]:
    return {p["connector"] for p in all_required(data)
            if p["status"] == "ACTIVE" and p.get("connector")}


def health(open_by_platform: dict[str, int] | None = None,
           data: dict | None = None) -> list[dict]:
    """One row per required platform: status, connector and (for ACTIVE) the
    live open-job count of its connector. open_by_platform is storage.stats()'s
    'open_by_platform' map (connector -> open count); shared connectors (e.g.
    jobfeed) report the connector's total."""
    data = data or load_sources()
    counts = open_by_platform or {}
    rows = []
    counted: set = set()   # connectors already attributed, to avoid double counting
    for p in all_required(data):
        conn = p.get("connector")
        active = p["status"] == "ACTIVE" and conn
        shared = False
        live_open = None
        if active:
            if conn in counted:
                shared = True            # same feed as an earlier platform; count once
            else:
                live_open = counts.get(conn)
                counted.add(conn)
        rows.append({
            "name": p["name"],
            "connector": conn,
            "status": p["status"],
            "live_open": live_open,
            "shared": shared,
            "reason": p.get("reason"),
            "next_action": p.get("next_action"),
        })
    return rows
