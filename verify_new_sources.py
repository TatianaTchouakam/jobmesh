#!/usr/bin/env python3
"""Re-test The Muse connector from this machine (was blocked server-side)."""
from __future__ import annotations
import sys
CANDIDATES = {"themuse": ["all"]}
def main() -> int:
    from jobmesh.connectors import build_connector
    clean = []
    print("Testing The Muse (live)…\n")
    for platform, tokens in CANDIDATES.items():
        for token in tokens:
            try:
                jobs = build_connector(platform, token).fetch(); n=len(jobs)
                if n>0:
                    print(f"  OK  {platform}/{token}: {n} jobs")
                    for j in jobs[:3]:
                        print(f"       · {j.title[:45]} — {j.company[:22]} — {j.location}")
                    clean.append((platform,token,n))
                else:
                    print(f"  --  {platform}/{token}: 0 jobs")
            except Exception as exc:
                print(f"  XX  {platform}/{token}: {str(exc).splitlines()[0][:120]}")
    print("\n--- KEEP THESE (paste this whole output back) ---")
    for platform,token,n in clean: print(f"{platform}: {token}   # {n} jobs")
    if not clean: print("(nothing returned)")
    return 0
if __name__=="__main__": sys.exit(main())
