"""Scheduled refresher: when the first ingest should run after boot.

Regression: _loop used to sleep(interval) before the first ingest, so every
redeploy reset the clock and in production the ingest never ran. The first
ingest must instead start soon after boot when the index is missing or stale.
"""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-please-change")
from datetime import datetime, timezone, timedelta
from jobmesh import api

H = 3600.0


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_no_prior_ingest_runs_soon():
    # never ingested -> wait only the short initial delay
    assert api._initial_refresh_wait(4 * H, "") == api.INGEST_INITIAL_DELAY
    assert api._initial_refresh_wait(4 * H, None) == api.INGEST_INITIAL_DELAY


def test_stale_index_runs_soon():
    old = _iso(datetime.now(timezone.utc) - timedelta(hours=10))
    assert api._initial_refresh_wait(4 * H, old) == api.INGEST_INITIAL_DELAY


def test_recent_index_waits_remaining_interval():
    recent = _iso(datetime.now(timezone.utc) - timedelta(minutes=10))
    w = api._initial_refresh_wait(4 * H, recent)
    # waits the rest of the interval, never less than the initial delay
    assert api.INGEST_INITIAL_DELAY < w <= 4 * H
    assert abs(w - (4 * H - 10 * 60)) < 5


def test_bad_timestamp_runs_soon():
    assert api._initial_refresh_wait(4 * H, "not-a-date") == api.INGEST_INITIAL_DELAY
