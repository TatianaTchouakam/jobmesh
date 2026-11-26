"""Disable rate-limit *enforcement* during the test suite (headers still set),
so the volume of test requests never trips a 429. The dedicated rate-limit
test re-enables it locally with a low limit."""
import jobmesh.api as _api
_api.RATE_LIMIT_ENABLED = False
