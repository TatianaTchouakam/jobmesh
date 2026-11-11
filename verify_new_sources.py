#!/usr/bin/env python3
"""Test USAJobs — needs USAJOBS_EMAIL and USAJOBS_API_KEY in the env."""
from __future__ import annotations
import os, sys
CANDIDATES = {"usajobs": ["all"]}
def main() -> int:
    if not os.getenv("USAJOBS_EMAIL") or not os.getenv("USAJOBS_API_KEY"):
        print("Set USAJOBS_EMAIL and USAJOBS_API_KEY first."); return 1
    from jobmesh.connectors import build_connector
    clean = []
    print("Testing USAJobs (live)…\n")
    for platform, tokens in CANDIDATES.items():
        for token in tokens:
            try:
                jobs = build_connector(platform, token).fetch(); n=len(jobs)
                if n>0:
                    cities=sum(1 for j in jobs if j.location)
                    print(f"  OK  {platform}/{token}: {n} jobs  ({cities} with a location)")
                    for j in jobs[:3]:
                        print(f"       · {j.title[:45]} — {j.company[:24]} — {j.location}")
                    clean.append((platform,token,n))
                else:
                    print(f"  --  {platform}/{token}: 0 jobs")
            except Exception as exc:
                print(f"  XX  {platform}/{token}: {str(exc).splitlines()[0][:130]}")
    print("\n--- KEEP THESE (paste this whole output back) ---")
    for platform,token,n in clean: print(f"{platform}: {token}   # {n} jobs")
    if not clean: print("(nothing returned)")
    return 0
if __name__=="__main__": sys.exit(main())
