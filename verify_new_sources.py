#!/usr/bin/env python3
"""Test ReliefWeb — needs RELIEFWEB_APPNAME in the env."""
from __future__ import annotations
import os, sys
CANDIDATES = {"reliefweb": ["all"]}
def main() -> int:
    if not os.getenv("RELIEFWEB_APPNAME"):
        print("Set RELIEFWEB_APPNAME first."); return 1
    from jobmesh.connectors import build_connector
    clean = []
    print("Testing ReliefWeb (live)…\n")
    for platform, tokens in CANDIDATES.items():
        for token in tokens:
            try:
                jobs = build_connector(platform, token).fetch(); n=len(jobs)
                if n>0:
                    AFR=("Kenya","Nigeria","Ethiopia","Uganda","Sudan","Somalia","DRC","Congo",
                         "Mali","Niger","Chad","Cameroon","Senegal","Afghanistan","Yemen","Syria",
                         "Bangladesh","Myanmar","Ukraine","Mozambique","Zimbabwe","South Sudan")
                    afr=sum(1 for j in jobs if j.location and any(a in j.location for a in AFR))
                    print(f"  OK  {platform}/{token}: {n} jobs  (~{afr} Afrique/Sud global)")
                    for j in jobs[:3]:
                        print(f"       · {j.title[:42]} — {j.company[:24]} — {j.location}")
                    clean.append((platform,token,n))
                else:
                    print(f"  --  {platform}/{token}: 0 jobs")
            except Exception as exc:
                print(f"  XX  {platform}/{token}: {str(exc).splitlines()[0][:140]}")
    print("\n--- KEEP THESE (paste this whole output back) ---")
    for platform,token,n in clean: print(f"{platform}: {token}   # {n} jobs")
    if not clean: print("(nothing returned)")
    return 0
if __name__=="__main__": sys.exit(main())
