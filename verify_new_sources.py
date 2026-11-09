#!/usr/bin/env python3
"""Re-test Bundesagentur after the v6 fix."""
from __future__ import annotations
import sys

CANDIDATES = {"bundesagentur": ["all"]}

def main() -> int:
    from jobmesh.connectors import build_connector
    clean = []
    print("Testing Bundesagentur v6 (live, keyless)…\n")
    for platform, tokens in CANDIDATES.items():
        for token in tokens:
            try:
                jobs = build_connector(platform, token).fetch()
                n = len(jobs)
                if n > 0:
                    cats = {}
                    for j in jobs:
                        c = j.category or "?"; cats[c] = cats.get(c, 0) + 1
                    top = sorted(cats.items(), key=lambda x: -x[1])[:6]
                    locs = sum(1 for j in jobs if j.location and j.location != "Deutschland")
                    print(f"  OK  {platform}/{token}: {n} jobs  ({locs} with a city)")
                    print("       top categories:", ", ".join(f"{c}={k}" for c, k in top))
                    for j in jobs[:3]:
                        print(f"       · {j.title[:45]} — {j.company[:22]} — {j.location}")
                    clean.append((platform, token, n))
                else:
                    print(f"  --  {platform}/{token}: 0 jobs")
            except Exception as exc:
                print(f"  XX  {platform}/{token}: {str(exc).splitlines()[0][:110]}")
    print("\n--- KEEP THESE (paste this whole output back) ---")
    for platform, token, n in clean:
        print(f"{platform}: {token}   # {n} jobs")
    if not clean:
        print("(nothing returned)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
