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
from .ratelimit import RateLimited, parse_retry_after

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

# Seconds to wait before successive in-cycle retries of a board that
# was rate-limited (HTTP 429). We move on after a 429 and come back to
# the board later in the cycle, never in a burst.
_RL_BACKOFF = [5.0, 15.0, 60.0]


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

    Returns ``(jobs, error, rate_limited)``: on success ``(jobs, None, None)``;
    on a plain failure ``(None, error, None)``; on HTTP 429 ``(None, msg, rl)``
    where ``rl`` is the :class:`RateLimited` (carrying any ``Retry-After``).
    A 429 is **not** retried in place -- the caller sets the board aside and
    comes back to it later in the cycle, so a rate-limited cluster is never
    hammered. Other transient errors get a short local backoff. No protection,
    rate-limit or robots rule is bypassed.
    """
    attempts = max(1, int(os.getenv("INGEST_RETRIES", "2")) + 1)
    delay = float(os.getenv("INGEST_RETRY_DELAY", "0.6"))
    last = None
    for i in range(attempts):
        try:
            connector = build_connector(platform, board)
            return connector.fetch(), None, None
        except RateLimited as rl:
            return None, str(rl), rl
        except requests.HTTPError as exc:
            # A 429 from any connector (shared-host APIs like Greenhouse) is a
            # rate limit: defer the board to later in the cycle instead of
            # retrying in place, so we never burst the host.
            if exc.response is not None and exc.response.status_code == 429:
                rl = RateLimited(retry_after=parse_retry_after(exc.response))
                return None, str(rl), rl
            last = exc
            if i < attempts - 1 and _is_transient(exc):
                time.sleep(delay * (2 ** i))
                continue
            return None, str(exc), None
        except Exception as exc:  # network, parse, unknown platform, ...
            last = exc
            if i < attempts - 1 and _is_transient(exc):
                time.sleep(delay * (2 ** i))
                continue
            return None, str(exc), None
    return None, str(last), None


def ingest_board(conn, platform: str, board: str) -> BoardResult:
    """Run one board end-to-end, recording the outcome in the DB."""
    jobs, error, rl = _fetch_with_retry(platform, board)
    # Single-board path (CLI / direct call): honour a 429 by waiting the
    # backoff (or the server's Retry-After) and retrying, rather than failing.
    attempt = 0
    while rl is not None and attempt < len(_RL_BACKOFF):
        wait = rl.retry_after if rl.retry_after is not None else _RL_BACKOFF[attempt]
        time.sleep(min(wait, 120.0))
        jobs, error, rl = _fetch_with_retry(platform, board)
        attempt += 1
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
    jobs, error, rl = _fetch_with_retry(platform, board)
    return platform, board, jobs, error, rl


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
    deferred: list[tuple[str, str, float | None]] = []  # (platform, board, retry_after)

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
            jobs, error, rl = _fetch_with_retry(platform, board)
            if rl is not None:
                deferred.append((platform, board, rl.retry_after))
            else:
                results.append(_store(platform, board, jobs, error))
            if (i + 1) % 25 == 0:
                conn.commit()
        conn.commit()
        _drain_deferred(conn, deferred, results, _store, workers)
        return results

    chunk = max(workers * 2, 12)   # small chunks keep peak memory low and commit often
    for start in range(0, len(tasks), chunk):
        batch = tasks[start:start + chunk]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_fetch_only, p, b) for p, b in batch]
            for fut in as_completed(futures):
                platform, board, jobs, error, rl = fut.result()
                if rl is not None:
                    deferred.append((platform, board, rl.retry_after))
                else:
                    results.append(_store(platform, board, jobs, error))
        conn.commit()  # persist this chunk; the executor's buffered results free here
    _drain_deferred(conn, deferred, results, _store, workers)
    return results


def _drain_deferred(conn, deferred, results, store, workers):
    """Retry boards that were rate-limited (429), later in the same cycle.

    We move on from a 429 during the main pass and come back here, waiting the
    server's Retry-After (or an exponential backoff) between rounds. Retries
    still go through the per-cluster limiter, so a cluster is paced, never
    bursted. Boards still limited after the last round are recorded as a fetch
    failure (which never closes their listings)."""
    rounds = len(_RL_BACKOFF)
    pending = list(deferred)
    for r in range(rounds):
        if not pending:
            break
        asked = [ra for (_p, _b, ra) in pending if ra]
        wait = max(_RL_BACKOFF[r], min(asked) if asked else 0.0)
        time.sleep(min(wait, 120.0))
        still: list[tuple[str, str, float | None]] = []
        if workers == 1:
            for platform, board, _ra in pending:
                jobs, error, rl = _fetch_with_retry(platform, board)
                if rl is not None:
                    still.append((platform, board, rl.retry_after))
                else:
                    results.append(store(platform, board, jobs, error))
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_fetch_only, p, b) for p, b, _ra in pending]
                for fut in as_completed(futures):
                    platform, board, jobs, error, rl = fut.result()
                    if rl is not None:
                        still.append((platform, board, rl.retry_after))
                    else:
                        results.append(store(platform, board, jobs, error))
        conn.commit()
        pending = still
    for platform, board, _ra in pending:
        msg = "rate limited (HTTP 429) after retries"
        storage.log_fetch(conn, platform, board, "failure", error=msg)
        log.warning("fetch failed for %s/%s: %s", platform, board, msg)
        results.append(BoardResult(platform, board, "failure", error=msg))
    if pending:
        conn.commit()
