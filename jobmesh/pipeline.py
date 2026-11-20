"""The ingestion pipeline: fetch -> normalize -> store, per board.

This ties the pieces together and is deliberately defensive: a failure on
one board is logged and skipped, and never closes that board's listings.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _fetch_only(platform: str, board: str):
    """Fetch one board without touching the DB (safe to run in a worker thread)."""
    try:
        connector = build_connector(platform, board)
        return platform, board, connector.fetch(), None
    except Exception as exc:  # network, parse, unknown platform, ...
        return platform, board, None, str(exc)


def ingest(conn, boards: dict[str, list[str]]) -> list[BoardResult]:
    """Ingest every board in a {platform: [boards]} mapping.

    Network fetches (the slow part) run concurrently in a thread pool; every
    database write stays on the calling thread, so the single SQLite
    connection is only ever touched by one thread. Set INGEST_WORKERS to tune
    concurrency (default 12); INGEST_WORKERS=1 restores sequential behaviour.
    """
    workers = max(1, int(os.getenv("INGEST_WORKERS", "12")))
    tasks = [(p, b) for p, blist in boards.items() for b in blist]
    results: list[BoardResult] = []

    if workers == 1:
        for platform, board in tasks:
            results.append(ingest_board(conn, platform, board))
        return results

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch_only, p, b) for p, b in tasks]
        for fut in as_completed(futures):
            platform, board, jobs, error = fut.result()
            if error is not None:
                storage.log_fetch(conn, platform, board, "failure", error=error)
                log.warning("fetch failed for %s/%s: %s", platform, board, error)
                results.append(BoardResult(platform, board, "failure", error=error))
                continue
            counts = storage.upsert_jobs(conn, jobs)
            seen = {job.uid for job in jobs}
            closed = storage.close_absent(conn, platform, board, seen)
            storage.log_fetch(conn, platform, board, "success", job_count=len(jobs))
            log.info(
                "%s/%s: %d fetched (%d new, %d updated, %d closed)",
                platform, board, len(jobs), counts["new"], counts["updated"], closed,
            )
            results.append(BoardResult(
                platform, board, "success", fetched=len(jobs),
                new=counts["new"], updated=counts["updated"], closed=closed,
            ))
    return results
