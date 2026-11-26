"""The ingestion pipeline: fetch -> normalize -> store, per board.

This ties the pieces together and is deliberately defensive: a failure on
one board is logged and skipped, and never closes that board's listings.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

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


_TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def _is_transient(exc: Exception) -> bool:
    """A transient error is worth retrying; a deliberate 4xx (403/404/410) is not."""
    if isinstance(exc, (requests.Timeout, requests.ConnectionError,
                        requests.exceptions.ChunkedEncodingError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in _TRANSIENT_STATUS
    return False


def _fetch_with_retry(platform: str, board: str):
    """Fetch one board, retrying only transient failures with backoff.

    Returns (jobs, None) on success or (None, error) on failure. A constrained
    free-tier host drops a fraction of concurrent requests; a short backoff
    recovers most of them. Deliberate 4xx responses fail immediately and are
    never hammered. No protection, rate-limit or robots rule is bypassed.
    """
    attempts = max(1, int(os.getenv("INGEST_RETRIES", "2")) + 1)
    delay = float(os.getenv("INGEST_RETRY_DELAY", "0.6"))
    last = None
    for i in range(attempts):
        try:
            connector = build_connector(platform, board)
            return connector.fetch(), None
        except Exception as exc:  # network, parse, unknown platform, ...
            last = exc
            if i < attempts - 1 and _is_transient(exc):
                time.sleep(delay * (2 ** i))
                continue
            return None, str(exc)
    return None, str(last)


def ingest_board(conn, platform: str, board: str) -> BoardResult:
    """Run one board end-to-end, recording the outcome in the DB."""
    jobs, error = _fetch_with_retry(platform, board)
    if error is not None:
        storage.log_fetch(conn, platform, board, "failure", error=error)
        log.warning("fetch failed for %s/%s: %s", platform, board, error)
        return BoardResult(platform, board, "failure", error=error)

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
    jobs, error = _fetch_with_retry(platform, board)
    return platform, board, jobs, error


def ingest(conn, boards: dict[str, list[str]]) -> list[BoardResult]:
    """Public entry point: mark an ingest in progress so the UI can show
    'update in progress' and never present partial counts as final, then run
    the actual ingest and clear the flag whatever happens."""
    storage.set_meta(conn, "ingesting", "1")
    try:
        return _run_ingest(conn, boards)
    finally:
        storage.set_meta(conn, "ingesting", "0")


def _run_ingest(conn, boards: dict[str, list[str]]) -> list[BoardResult]:
    """Ingest every board in a {platform: [boards]} mapping.

    Fetches run concurrently, but in **bounded chunks**: only one chunk of
    futures is held in memory at a time, and the DB is committed after each
    chunk. That keeps peak memory low on a small instance and persists
    progress, so an interrupted run (an OOM restart, a redeploy) keeps the
    boards already done instead of losing the whole run. Every DB write stays
    on the calling thread. INGEST_WORKERS tunes concurrency (default 8);
    INGEST_WORKERS=1 is sequential.
    """
    workers = max(1, int(os.getenv("INGEST_WORKERS", "8")))
    tasks = [(p, b) for p, blist in boards.items() for b in blist]
    results: list[BoardResult] = []

    def _store(platform, board, jobs, error):
        if error is not None:
            storage.log_fetch(conn, platform, board, "failure", error=error)
            log.warning("fetch failed for %s/%s: %s", platform, board, error)
            return BoardResult(platform, board, "failure", error=error)
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

    if workers == 1:
        for i, (platform, board) in enumerate(tasks):
            jobs, error = _fetch_with_retry(platform, board)
            results.append(_store(platform, board, jobs, error))
            if (i + 1) % 25 == 0:
                conn.commit()
        conn.commit()
        return results

    chunk = max(workers * 2, 12)   # small chunks keep peak memory low and commit often
    for start in range(0, len(tasks), chunk):
        batch = tasks[start:start + chunk]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_fetch_only, p, b) for p, b in batch]
            for fut in as_completed(futures):
                platform, board, jobs, error = fut.result()
                results.append(_store(platform, board, jobs, error))
        conn.commit()  # persist this chunk; the executor's buffered results free here
    return results
