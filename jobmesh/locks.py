"""A single-host ingest lock.

Prevents two ingests running at the same time on one machine -- the scheduled
background refresh and a manual `jobmesh ingest`, or two web workers that each
start a refresher. Uses an advisory file lock (flock), so it is released
automatically if the process dies. Best-effort: where file locking is not
available, it never blocks ingesting.
"""

from __future__ import annotations

import contextlib
import os
import tempfile

try:  # POSIX only; absent on some platforms
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

_DEFAULT_LOCK = os.path.join(tempfile.gettempdir(), "jobmesh-ingest.lock")


@contextlib.contextmanager
def ingest_lock(path: str = _DEFAULT_LOCK):
    """Yield True if this process took the exclusive ingest lock, else False.

    Non-blocking: if another ingest already holds it, yields False at once so
    the caller can skip this cycle instead of queueing a second ingest.
    """
    if fcntl is None:  # pragma: no cover - non-POSIX fallback
        yield True
        return
    handle = open(path, "w")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:  # pragma: no cover
                pass
    finally:
        handle.close()
