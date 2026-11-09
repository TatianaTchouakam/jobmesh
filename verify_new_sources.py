#!/usr/bin/env python3
"""Worldwide batch 3 — Japan/Korea, Australia/NZ, Nordics/N. Europe."""
from __future__ import annotations
import sys

CANDIDATES = {
    "greenhouse": [
        "mercari", "appier",                       # confirmed — Japan / Taiwan
        "klarna", "spotify", "pleo", "supermetrics", "cognite", "kahoot",
        "truecaller", "einride", "northvolt",      # Nordics / N. Europe
        "canva", "airwallex", "rokt", "immutable", "go1", "employmenthero",  # Australia
        "coupang", "moloco", "krafton", "smartnews",   # Korea / Japan
    ],
    "lever": [
        "canva", "deputy",
    ],
    "ashby": [
        "sendbird", "moloco",
    ],
    "workable": [
        "mercari",
    ],
}


def main() -> int:
    try:
        from jobmesh.connectors import build_connector
    except Exception as exc:
        print(f"Could not import connectors (run from the repo root): {exc}")
        return 1
    clean = []
    print("Testing worldwide batch 3 (live)…\n")
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
