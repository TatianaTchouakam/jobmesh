"""Jobmesh Pro billing — Stripe Checkout (subscription) + signed-key issuance.

Phase 1: card (and any method enabled in the Stripe Dashboard) with instant
key delivery. A successful checkout issues a stateless signed Pro key
(jobmesh.pro). SEPA / webhook lifecycle is Phase 2.

Env:
    STRIPE_SECRET_KEY   Stripe secret key (use a TEST key while developing).
    BASE_URL            Public base URL (success/cancel redirects). Optional:
                        falls back to the request's own base URL.
    STRIPE_PRICE_ID     Optional: an existing recurring Price id. If unset, a
                        3 EUR/month price is created inline.
    SECRET_KEY          Signs Pro keys (see jobmesh.pro).
"""

from __future__ import annotations

import html
import json
import os
import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import pro

router = APIRouter()

PRICE_EUR_CENTS = 300          # 3.00 EUR / month
GRACE_DAYS = 2


def _stripe():
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        return None
    try:
        import stripe
    except Exception:
        return None
    stripe.api_key = key
    return stripe


def _base_url(request: Request) -> str:
    return (os.getenv("BASE_URL") or str(request.base_url)).rstrip("/")


@router.post("/pro/checkout")
def pro_checkout(request: Request):
    stripe = _stripe()
    if stripe is None:
        return JSONResponse(
            {"error": "Billing is not configured (STRIPE_SECRET_KEY missing)."},
            status_code=503)
    base = _base_url(request)
    price_id = os.getenv("STRIPE_PRICE_ID")
    line_item = ({"price": price_id, "quantity": 1} if price_id else {
        "price_data": {
            "currency": "eur",
            "unit_amount": PRICE_EUR_CENTS,
            "recurring": {"interval": "month"},
            "product_data": {
                "name": "Jobmesh Premium",
                "description": "CSV export of filtered results + full API access",
            },
        },
        "quantity": 1,
    })
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[line_item],
            success_url=f"{base}/pro/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/?pro=cancelled",
            allow_promotion_codes=True,
        )
    except Exception as exc:  # surface Stripe errors cleanly
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"url": session.url}


@router.post("/pro/checkout-once")
def pro_checkout_once(request: Request):
    """One-off 3 EUR payment (not a subscription). Enables wallet methods such
    as PayPal that aren't cleared for recurring charges yet; the existing
    /pro/success handler issues the same signed Pro key (~30-day validity)."""
    stripe = _stripe()
    if stripe is None:
        return JSONResponse(
            {"error": "Billing is not configured (STRIPE_SECRET_KEY missing)."},
            status_code=503)
    base = _base_url(request)
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "unit_amount": PRICE_EUR_CENTS,
                    "product_data": {
                        "name": "Jobmesh Premium — accès 1 mois",
                        "description": "CSV export of filtered results + full API access",
                    },
                },
                "quantity": 1,
            }],
            success_url=f"{base}/pro/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/?pro=cancelled",
            allow_promotion_codes=True,
        )
    except Exception as exc:  # surface Stripe errors cleanly
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"url": session.url}


@router.get("/pro/success")
def pro_success(session_id: str = Query(...)):
    stripe = _stripe()
    if stripe is None:
        return HTMLResponse(_page("Indisponible", "La facturation n'est pas configurée."),
                            status_code=503)
    try:
        s = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
    except Exception:
        return HTMLResponse(_page("Session introuvable",
                                  "Impossible de retrouver cette session de paiement."),
                            status_code=400)
    sub = s.get("subscription") or {}
    paid = (s.get("payment_status") == "paid"
            or (isinstance(sub, dict) and sub.get("status") in ("active", "trialing")))
    if not paid:
        return HTMLResponse(_page(
            "Paiement en cours",
            "Ton paiement n'est pas encore confirmé (c'est normal avec SEPA : "
            "quelques heures à quelques jours). Ta clé Premium s'affichera une fois "
            "le paiement réglé."))
    exp = int((isinstance(sub, dict) and sub.get("current_period_end"))
              or (time.time() + 35 * 86400)) + GRACE_DAYS * 86400
    key = pro.make_key(str(s.get("customer") or ""),
                       str((isinstance(sub, dict) and sub.get("id")) or ""), exp)
    return HTMLResponse(_success_page(key))


# --- tiny self-contained HTML (no template engine needed) -------------------

def _page(title: str, body: str) -> str:
    return (f"<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title>"
            "<div style=\"font-family:system-ui;max-width:640px;margin:60px auto;"
            "padding:0 20px;line-height:1.6\">"
            f"<h1>{html.escape(title)}</h1><p>{body}</p>"
            "<p><a href=\"/\">&larr; Retour</a></p></div>")


def _success_page(key: str) -> str:
    k = html.escape(key)
    kjs = json.dumps(key)  # safe JS string literal
    body = (
        "<p style=\"font-size:16px;margin:0 0 4px\"><b>Ton acc\u00e8s Premium est actif "
        "\u2713</b></p>"
        "<p style=\"color:#4a5262;margin:0 0 22px\">Ta cl\u00e9 est d\u00e9j\u00e0 "
        "enregistr\u00e9e sur cet appareil \u2014 rien \u00e0 copier.</p>"
        "<div style=\"display:flex;flex-wrap:wrap;gap:12px;margin:0 0 30px\">"
        f"<a href=\"/export.csv?api_key={k}\" "
        "style=\"background:linear-gradient(135deg,#e0a52a,#c4881a);color:#fff;"
        "text-decoration:none;font-weight:800;padding:13px 22px;border-radius:12px\">"
        "\u2b07 T\u00e9l\u00e9charger le CSV maintenant</a>"
        "<a href=\"/\" style=\"background:#f4f4f5;color:#111;text-decoration:none;"
        "font-weight:700;padding:13px 22px;border-radius:12px;border:1px solid #e3e3e6\">"
        "Aller \u00e0 la recherche</a></div>"
        "<p>Ta cl\u00e9 d'API (utile pour l'acc\u00e8s API ou un autre appareil) :</p>"
        f"<pre id=\"prokey\" style=\"background:#f4f4f5;padding:14px;border-radius:8px;"
        f"overflow:auto;user-select:all\">{k}</pre>"
        "<button type=\"button\" id=\"copykey\" style=\"border:1px solid #e3e3e6;"
        "background:#fff;border-radius:8px;padding:8px 14px;font-family:inherit;"
        "font-weight:700;cursor:pointer\">Copier la cl\u00e9</button>"
        "<h3>Comment l'utiliser</h3>"
        "<p>Export CSV de la recherche filtr\u00e9e :</p>"
        f"<pre style=\"background:#f4f4f5;padding:14px;border-radius:8px;overflow:auto\">"
        f"curl -H \"X-API-Key: {k}\" \"/export.csv?keyword=data&location=remote\" -o jobs.csv</pre>"
        "<p>API compl\u00e8te (pagination jusqu'\u00e0 1000 / requ\u00eate) :</p>"
        f"<pre style=\"background:#f4f4f5;padding:14px;border-radius:8px;overflow:auto\">"
        f"/jobs?api_key={k}&limit=1000</pre>"
        "<script>"
        f"try{{localStorage.setItem('jobmesh_pro_key',{kjs});}}catch(e){{}}"
        "var c=document.getElementById('copykey');"
        f"if(c){{c.addEventListener('click',function(){{"
        f"navigator.clipboard.writeText({kjs}).then(function(){{"
        "c.textContent='Copi\u00e9 \u2713';}).catch(function(){});});}}"
        "</script>")
    return _page("Bienvenue sur Jobmesh Premium", body)
