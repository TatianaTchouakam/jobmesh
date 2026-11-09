#!/usr/bin/env python3
"""Worldwide batch — North/South America, South Africa, Russia-adjacent."""
from __future__ import annotations
import sys

CANDIDATES = {
    "greenhouse": [
        "nubank",        # confirmed — Brazil fintech (huge)
        "quintoandar",   # confirmed — Brazil proptech
        "jobber",        # confirmed — Canada
        "openphone",     # confirmed — US/Canada
        "shakepay",      # confirmed — Canada crypto
        "rootstrap",     # confirmed — Uruguay/LatAm
        "takealotcom",   # confirmed — South Africa e-commerce
        "takealotgroup", # confirmed variant — South Africa
        "rappi", "globant", "luno", "nebius",   # guesses: Colombia / Argentina / S.Africa / ex-Russia
    ],
    "lever": [
        "kavak",         # confirmed — Mexico
        "dlocal",        # confirmed — Uruguay payments
        "rappi", "globant",
    ],
    "ashby": [
        "wealthsimple",  # confirmed — Canada fintech
        "ramp", "mercury", "vanta", "deel", "notion",   # big US (likely Ashby)
    ],
}


def main() -> int:
    try:
        from jobmesh.connectors import build_connector
    except Exception as exc:
        print(f"Could not import connectors (run from the repo root): {exc}")
        return 1
    clean = []
    print("Testing worldwide candidate tokens (live)…\n")
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
