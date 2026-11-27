"""Per-cluster rate limiting for platforms that share a few host clusters.

Some ATS host thousands of tenants on a handful of shared clusters and
rate-limit by client IP *per cluster* (Workday's ``wd1``/``wd3``/``wd5`` ...;
Oracle, iCIMS and SmartRecruiters behave similarly). Fetching one cluster
from several workers at once trips HTTP 429. This limiter keeps our traffic
inside the host's own limits -- it never bypasses one:

* at most **one in-flight request per cluster** (serialized);
* at least ``min_interval`` seconds between consecutive requests to the same
  cluster;
* at most ``max_parallel_clusters`` clusters hit at the same time.

It is process-global and thread-safe, so every worker shares the same pacing.
A 429 is surfaced as :class:`RateLimited` (with the server's ``Retry-After``
when given) so the pipeline can set the board aside and pick it up later in
the cycle instead of hammering -- never a burst.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from email.utils import parsedate_to_datetime


class RateLimited(Exception):
    """A host answered HTTP 429.

    ``retry_after`` is the number of seconds the server asked us to wait
    (parsed from the ``Retry-After`` header), or ``None`` when it didn't say.
    """

    def __init__(self, message: str = "rate limited (HTTP 429)",
                 retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def parse_retry_after(resp) -> float | None:
    """Seconds to wait from a response's ``Retry-After`` header, or ``None``.

    Handles both the delta-seconds form (``Retry-After: 30``) and the
    HTTP-date form (``Retry-After: Wed, 21 Oct 2026 07:28:00 GMT``).
    """
    try:
        raw = resp.headers.get("Retry-After")
    except AttributeError:
        return None
    if not raw:
        return None
    raw = raw.strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        import datetime
        dt = parsedate_to_datetime(raw)
        if dt is None:
            return None
        now = datetime.datetime.now(dt.tzinfo)
        return max(0.0, (dt - now).total_seconds())
    except (TypeError, ValueError):
        return None


class ClusterLimiter:
    """Serialize and pace requests per cluster, capping parallel clusters."""

    def __init__(self, min_interval: float = 1.5, max_parallel_clusters: int = 2):
        self.min_interval = max(0.0, float(min_interval))
        self._sem = threading.BoundedSemaphore(max(1, int(max_parallel_clusters)))
        self._registry_lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}

    def _cluster_lock(self, key: str) -> threading.Lock:
        with self._registry_lock:
            lk = self._locks.get(key)
            if lk is None:
                lk = threading.Lock()
                self._locks[key] = lk
            return lk

    @contextmanager
    def slot(self, cluster_key: str):
        """Hold a polite slot for one request to ``cluster_key``.

        Acquires the cluster's lock (one request at a time), waits out the
        minimum interval since the last request to this cluster, then takes a
        global parallel-cluster slot for the duration of the request.
        """
        lock = self._cluster_lock(cluster_key)
        lock.acquire()
        try:
            wait = self._last.get(cluster_key, 0.0) + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._sem.acquire()
            try:
                self._last[cluster_key] = time.monotonic()
                yield
            finally:
                self._sem.release()
        finally:
            lock.release()


# Per-platform default pacing (seconds between same-host requests). Page-per-job
# platforms (CareerPlug) use a lighter pace than Workday's cluster API.
_DEFAULT_INTERVALS = {"workday": 1.5, "careerplug": 0.4, "paylocity": 1.0}

_LIMITERS: dict[str, ClusterLimiter] = {}
_LIMITERS_LOCK = threading.Lock()


def get_limiter(name: str) -> ClusterLimiter:
    """Return the process-global limiter for ``name`` (one per platform).

    Tunable from the environment: ``<NAME>_MIN_INTERVAL`` /
    ``<NAME>_MAX_PARALLEL_CLUSTERS`` (falling back to ``CLUSTER_MIN_INTERVAL`` /
    ``CLUSTER_MAX_PARALLEL``). Defaults: 1.5 s between same-cluster requests,
    at most 2 clusters in parallel.
    """
    with _LIMITERS_LOCK:
        lim = _LIMITERS.get(name)
        if lim is None:
            up = name.upper()
            mi = float(os.getenv(f"{up}_MIN_INTERVAL",
                                 os.getenv("CLUSTER_MIN_INTERVAL",
                                           str(_DEFAULT_INTERVALS.get(name, 1.5)))))
            mp = int(os.getenv(f"{up}_MAX_PARALLEL_CLUSTERS",
                               os.getenv("CLUSTER_MAX_PARALLEL", "2")))
            lim = ClusterLimiter(mi, mp)
            _LIMITERS[name] = lim
        return lim


_HOST_POOLS: dict[str, threading.BoundedSemaphore] = {}
_HOST_DEFAULTS = {"greenhouse": 4}


def host_semaphore(name: str) -> threading.BoundedSemaphore:
    """A per-host concurrency cap for tolerant shared-host APIs.

    Unlike the strict per-cluster limiter (one request at a time), this allows
    a few concurrent requests to one host -- enough to stay fast while keeping
    us under the host's burst limit, so we stop tripping 429 at the source.
    Tunable via ``<NAME>_MAX_CONCURRENT``.
    """
    with _LIMITERS_LOCK:
        sem = _HOST_POOLS.get(name)
        if sem is None:
            n = int(os.getenv(f"{name.upper()}_MAX_CONCURRENT",
                              str(_HOST_DEFAULTS.get(name, 4))))
            sem = threading.BoundedSemaphore(max(1, n))
            _HOST_POOLS[name] = sem
        return sem


def reset_limiters() -> None:
    """Drop all cached limiters (tests only)."""
    with _LIMITERS_LOCK:
        _LIMITERS.clear()
        _HOST_POOLS.clear()
