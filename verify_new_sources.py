#!/usr/bin/env python3
"""Worldwide batch 2 — India, SE Asia, Middle East, Eastern Europe."""
from __future__ import annotations
import sys

CANDIDATES = {
    "greenhouse": [
        "razorpaysoftwareprivatelimited",  # confirmed — India fintech
        "careem", "ziina",                 # confirmed — UAE / Middle East
        "freenow", "showpad",              # confirmed — Europe
        "bolteu", "bolt",                  # Estonia (mobility)
        "cred", "postman", "browserstack", "chargebee", "zeta",   # India
        "vinted", "veriff", "preply",      # Eastern Europe
        "tabby", "tamara",                 # Middle East fintech
    ],
    "lever": [
        "zartis",                          # confirmed — Ireland/EU
        "bitpanda", "groww",
    ],
    "ashby": [
        "pipedrive", "groww", "cred",
    ],
    "smartrecruiters": [
        "Grab",                            # confirmed — SE Asia super-app
        "Shopee",
    ],
}


def main() -> int:
    try:
        from jobmesh.connectors import build_connector
    except Exception as exc:
        print(f"Could not import connectors (run from the repo root): {exc}")
        return 1
    clean = []
    print("Testing worldwide batch 2 (live)…\n")
    for platform, tokens in CANDIDATES.items():
        for token in tokens:
            try:
                n = len(build_connector(platform, token).fetch())
                if n > 0:
                    print(f"  OK  {platform}/{token}: {n} jobs"); clean.append((platform, token, n))
                else:
                    print(f"  --  {platform}/{token}: 0 jobs (valid but empty — skip)")
            except Exception as exc:
                print(f"  XX  {platform}/{token}: {str(exc).splitlines()[0][:90]}")
    print("\n--- KEEP THESE (paste this whole output back) ---")
    if clean:
        for platform, token, n in clean:
            print(f"{platform}: {token}   # {n} jobs")
    else:
        print("(nothing returned jobs — we'll hunt different tokens)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
