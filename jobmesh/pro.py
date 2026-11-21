"""Jobmesh Pro — stateless, signed API keys (HMAC-SHA256).

A Pro key is self-verifying: it carries the Stripe customer id, subscription
id and an expiry, signed with SECRET_KEY. Nothing is stored server-side, so
keys survive redeploys on an ephemeral free-tier host. Validation checks the
signature and the expiry; the expiry is set to the paid period's end.

    key = "jm_" + base64url(payload) + "." + base64url(HMAC_SHA256(payload))

Never commit SECRET_KEY; it lives only in the environment.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _secret() -> bytes:
    s = os.getenv("SECRET_KEY")
    if not s:
        raise RuntimeError("SECRET_KEY is not set (required to sign Pro keys).")
    return s.encode()


def _sign(body: str) -> str:
    return _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())


def make_key(customer_id: str, subscription_id: str, exp: int) -> str:
    """Build a signed Pro key valid until `exp` (unix seconds)."""
    payload = {"cus": customer_id, "sub": subscription_id, "exp": int(exp)}
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return f"jm_{body}.{_sign(body)}"


def verify_key(key: str | None, now: int | None = None) -> dict | None:
    """Return the payload if the key is well-formed, correctly signed and not
    expired; otherwise None."""
    if not key or not key.startswith("jm_") or "." not in key:
        return None
    body, sig = key[3:].split(".", 1)
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        payload = json.loads(_unb64(body))
    except Exception:
        return None
    if int(now if now is not None else time.time()) > int(payload.get("exp", 0)):
        return None
    return payload
