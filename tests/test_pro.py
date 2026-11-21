"""Jobmesh Pro — signed key: round-trip, tampering, expiry."""
import os
import time

os.environ.setdefault("SECRET_KEY", "test-secret-please-change")
from jobmesh import pro


def test_roundtrip_valid():
    exp = int(time.time()) + 3600
    k = pro.make_key("cus_123", "sub_abc", exp)
    p = pro.verify_key(k)
    assert p and p["cus"] == "cus_123" and p["sub"] == "sub_abc" and p["exp"] == exp


def test_tampered_signature_rejected():
    k = pro.make_key("cus_123", "sub_abc", int(time.time()) + 3600)
    assert pro.verify_key(k[:-2] + ("aa" if not k.endswith("aa") else "bb")) is None


def test_tampered_payload_rejected():
    k = pro.make_key("cus_123", "sub_abc", int(time.time()) + 3600)
    body, sig = k[3:].split(".", 1)
    forged = "jm_" + body[:-1] + ("A" if body[-1] != "A" else "B") + "." + sig
    assert pro.verify_key(forged) is None


def test_expired_rejected():
    k = pro.make_key("cus_123", "sub_abc", int(time.time()) - 10)
    assert pro.verify_key(k) is None


def test_garbage_rejected():
    for bad in [None, "", "nope", "jm_", "jm_abc", "jm_abc.def"]:
        assert pro.verify_key(bad) is None
