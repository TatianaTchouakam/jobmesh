"""Offline tests for the PayPal subscription billing path (no network)."""

import json

from jobmesh import paypal, pro


def _configure(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "cid")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "sec")
    monkeypatch.setenv("PAYPAL_PLAN_ID", "P-123")
    monkeypatch.setenv("PAYPAL_ENV", "sandbox")
    monkeypatch.setenv("SECRET_KEY", "test-signing-secret")


ACTIVE_SUB = {
    "id": "I-SUB123",
    "status": "ACTIVE",
    "subscriber": {"payer_id": "PAYER9"},
    "billing_info": {"next_billing_time": "2099-01-01T00:00:00Z"},
}


def test_config_exposes_public_fields(monkeypatch):
    _configure(monkeypatch)
    cfg = paypal.paypal_config()
    assert cfg["client_id"] == "cid"
    assert cfg["plan_id"] == "P-123"
    assert cfg["env"] == "sandbox"


def test_config_503_when_unconfigured(monkeypatch):
    for k in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_PLAN_ID"):
        monkeypatch.delenv(k, raising=False)
    resp = paypal.paypal_config()
    assert resp.status_code == 503


def test_verify_active_issues_valid_pro_key(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(paypal, "_token", lambda: "tok")
    monkeypatch.setattr(paypal, "_get_subscription", lambda sid, tok: dict(ACTIVE_SUB))
    out = paypal.paypal_verify(subscription_id="I-SUB123")
    assert "key" in out
    # the issued key must verify and decode to the PayPal subscription id
    payload = pro.verify_key(out["key"])
    assert payload is not None
    assert payload["sub"] == "I-SUB123"
    assert payload["cus"] == "PAYER9"


def test_verify_inactive_is_rejected(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(paypal, "_token", lambda: "tok")
    pending = dict(ACTIVE_SUB, status="APPROVAL_PENDING")
    monkeypatch.setattr(paypal, "_get_subscription", lambda sid, tok: pending)
    resp = paypal.paypal_verify(subscription_id="I-SUB123")
    assert resp.status_code == 402


def test_verify_not_found(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(paypal, "_token", lambda: "tok")
    monkeypatch.setattr(paypal, "_get_subscription", lambda sid, tok: None)
    resp = paypal.paypal_verify(subscription_id="I-NOPE")
    assert resp.status_code == 404


def test_verify_503_when_unconfigured(monkeypatch):
    for k in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_PLAN_ID"):
        monkeypatch.delenv(k, raising=False)
    resp = paypal.paypal_verify(subscription_id="I-SUB123")
    assert resp.status_code == 503


def test_exp_uses_next_billing_time(monkeypatch):
    exp = paypal._exp_from(ACTIVE_SUB)
    # 2099 + grace -> comfortably in the future
    assert exp > 4_000_000_000
