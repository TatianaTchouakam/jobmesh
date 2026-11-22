"""Jobmesh Pro billing — PayPal Subscriptions (alongside Stripe).

A second, independent payment path that mirrors the Stripe one: a PayPal
subscription at 3 EUR/month that, once active, issues the SAME stateless
signed Pro key (jobmesh.pro). Stripe is untouched; this simply adds a PayPal
button next to it.

Flow (no server-side order creation needed):
  1. The browser loads the PayPal SDK with our public client-id and renders
     PayPal Buttons configured with PAYPAL_PLAN_ID (intent=subscription).
  2. PayPal handles approval; onApprove the browser POSTs the subscription id
     to /pro/paypal/verify.
  3. The server confirms the subscription is ACTIVE/APPROVED with PayPal and
     returns a signed Pro key. Webhook lifecycle (cancellations) is Phase 2,
     exactly as on the Stripe side.

Env:
    PAYPAL_CLIENT_ID      PayPal REST app client id (public; sent to browser).
    PAYPAL_CLIENT_SECRET  PayPal REST app secret (server only).
    PAYPAL_PLAN_ID        Billing plan id (3 EUR/month). Create once with
                          `python -m jobmesh.cli paypal-setup`.
    PAYPAL_ENV            "sandbox" (default) or "live".
    SECRET_KEY            Signs Pro keys (see jobmesh.pro).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from . import pro

router = APIRouter()

TIMEOUT = 20
GRACE_DAYS = 2
_ACTIVE = {"ACTIVE", "APPROVED"}


def _api_base() -> str:
    env = (os.getenv("PAYPAL_ENV") or "sandbox").strip().lower()
    return ("https://api-m.paypal.com" if env == "live"
            else "https://api-m.sandbox.paypal.com")


def _creds() -> tuple[str, str] | None:
    cid = os.getenv("PAYPAL_CLIENT_ID")
    sec = os.getenv("PAYPAL_CLIENT_SECRET")
    return (cid, sec) if cid and sec else None


def _config_ok() -> bool:
    return _creds() is not None and bool(os.getenv("PAYPAL_PLAN_ID"))


def _token() -> str | None:
    """OAuth2 client-credentials access token, or None if unconfigured/failed."""
    creds = _creds()
    if creds is None:
        return None
    try:
        r = requests.post(
            f"{_api_base()}/v1/oauth2/token",
            auth=creds,
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("access_token")
    except requests.RequestException:
        return None


def _get_subscription(subscription_id: str, token: str) -> dict | None:
    try:
        r = requests.get(
            f"{_api_base()}/v1/billing/subscriptions/{subscription_id}",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/json"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def _exp_from(sub: dict) -> int:
    """Pro-key expiry: the subscription's next billing time (+ grace), or a
    35-day fallback if PayPal doesn't report one."""
    nxt = (((sub.get("billing_info") or {}).get("next_billing_time")) or "")
    base = None
    if nxt:
        try:
            base = datetime.fromisoformat(nxt.replace("Z", "+00:00")).timestamp()
        except ValueError:
            base = None
    if base is None:
        base = time.time() + 35 * 86400
    return int(base) + GRACE_DAYS * 86400


@router.get("/pro/paypal/config")
def paypal_config():
    """Public config the browser needs to render the PayPal button."""
    if not _config_ok():
        return JSONResponse({"error": "PayPal is not configured."}, status_code=503)
    return {
        "client_id": os.getenv("PAYPAL_CLIENT_ID"),
        "plan_id": os.getenv("PAYPAL_PLAN_ID"),
        "env": (os.getenv("PAYPAL_ENV") or "sandbox").strip().lower(),
    }


@router.post("/pro/paypal/verify")
def paypal_verify(subscription_id: str = Query(..., min_length=3, max_length=64)):
    """Confirm the PayPal subscription is active, then issue a signed Pro key."""
    if not _config_ok():
        return JSONResponse({"error": "PayPal is not configured."}, status_code=503)
    token = _token()
    if token is None:
        return JSONResponse({"error": "Could not reach PayPal."}, status_code=502)
    sub = _get_subscription(subscription_id, token)
    if sub is None:
        return JSONResponse({"error": "Subscription not found."}, status_code=404)
    if str(sub.get("status", "")).upper() not in _ACTIVE:
        return JSONResponse(
            {"error": "Subscription not active yet.", "status": sub.get("status")},
            status_code=402)
    payer = (sub.get("subscriber") or {}).get("payer_id") or ""
    try:
        key = pro.make_key(str(payer), str(sub.get("id") or subscription_id),
                           _exp_from(sub))
    except RuntimeError as exc:  # SECRET_KEY missing
        return JSONResponse({"error": str(exc)}, status_code=503)
    return {"key": key}


# -- one-time plan bootstrap (run once to obtain PAYPAL_PLAN_ID) --------------

def bootstrap_plan(name: str = "Jobmesh Premium",
                   amount_eur: str = "3.00") -> dict:
    """Create a PayPal product + monthly billing plan and return
    {product_id, plan_id}. Run once per environment (sandbox, then live)."""
    token = _token()
    if token is None:
        raise RuntimeError("PayPal credentials missing or unreachable "
                           "(set PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET).")
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    prod = requests.post(f"{_api_base()}/v1/catalogs/products", headers=h, json={
        "name": name, "type": "SERVICE", "category": "SOFTWARE",
    }, timeout=TIMEOUT)
    prod.raise_for_status()
    product_id = prod.json()["id"]
    plan = requests.post(f"{_api_base()}/v1/billing/plans", headers=h, json={
        "product_id": product_id,
        "name": f"{name} — 3 EUR/month",
        "billing_cycles": [{
            "frequency": {"interval_unit": "MONTH", "interval_count": 1},
            "tenure_type": "REGULAR", "sequence": 1, "total_cycles": 0,
            "pricing_scheme": {"fixed_price": {
                "value": amount_eur, "currency_code": "EUR"}},
        }],
        "payment_preferences": {
            "auto_bill_outstanding": True,
            "setup_fee_failure_action": "CONTINUE",
            "payment_failure_threshold": 1,
        },
    }, timeout=TIMEOUT)
    plan.raise_for_status()
    return {"product_id": product_id, "plan_id": plan.json()["id"]}
