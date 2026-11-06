"""The ingestion pipeline: fetch -> normalize -> store, per board.

This ties the pieces together and is deliberately defensive: a failure on
one board is logged and skipped, and never closes that board's listings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import storage
from .connectors import build_connector

log = logging.getLogger("jobmesh.pipeline")


@dataclass
class BoardResult:
    platform: str
    board: str
    status: str                # "success" | "failure"
    fetched: int = 0
    new: int = 0
    updated: int = 0
    closed: int = 0
    error: str | None = None


def ingest_board(conn, platform: str, board: str) -> BoardResult:
    """Run one board end-to-end, recording the outcome in the DB."""
    try:
        connector = build_connector(platform, board)
        jobs = connector.fetch()
    except Exception as exc:  # network, parse, unknown platform, ...
        storage.log_fetch(conn, platform, board, "failure", error=str(exc))
        log.warning("fetch failed for %s/%s: %s", platform, board, exc)
        return BoardResult(platform, board, "failure", error=str(exc))

    counts = storage.upsert_jobs(conn, jobs)
    seen = {job.uid for job in jobs}
    closed = storage.close_absent(conn, platform, board, seen)
    storage.log_fetch(conn, platform, board, "success", job_count=len(jobs))

    log.info(
        "%s/%s: %d fetched (%d new, %d updated, %d closed)",
        platform, board, len(jobs), counts["new"], counts["updated"], closed,
    )
    return BoardResult(
        platform, board, "success", fetched=len(jobs),
        new=counts["new"], updated=counts["updated"], closed=closed,
    )


def ingest(conn, boards: dict[str, list[str]]) -> list[BoardResult]:
    """Run ingestion for every board in a {platform: [boards]} mapping."""
    results: list[BoardResult] = []
    for platform, board_list in boards.items():
        for board in board_list:
            results.append(ingest_board(conn, platform, board))
    return results
