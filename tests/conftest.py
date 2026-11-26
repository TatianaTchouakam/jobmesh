import os as _os
# Neutralize cluster rate-limit pacing during tests (the dedicated ratelimit
# tests construct their own ClusterLimiter with explicit intervals).
_os.environ.setdefault("CLUSTER_MIN_INTERVAL", "0")
_os.environ.setdefault("CLUSTER_MAX_PARALLEL", "32")
try:
    import jobmesh.ratelimit as _rl
    _rl.reset_limiters()
except Exception:
    pass
"""Disable rate-limit *enforcement* during the test suite (headers still set),
so the volume of test requests never trips a 429. The dedicated rate-limit
test re-enables it locally with a low limit."""
import jobmesh.api as _api
_api.RATE_LIMIT_ENABLED = False
