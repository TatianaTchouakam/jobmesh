#!/usr/bin/env python3
"""Local check of candidate ATS tokens before adding them to config."""
from __future__ import annotations
import sys

# Africa-focused batch: fintech, agritech & NGOs on clean public ATS.
# Several slugs confirmed from live job-board URLs; the rest are best guesses.
CANDIDATES = {
    "greenhouse": [
        "paystack", "moniepoint", "pulaio",        # confirmed (Nigeria/Africa)
        "flutterwave", "chippercash", "kuda", "fairmoney", "carbon",
        "interswitch", "jumia",                     # African fintech/e-commerce
        "mkopa", "m-kopa", "apolloagriculture", "sunculture",
        "wasoko", "twigafoods", "komaza",           # agritech / off-grid
        "sama", "mpharma", "yoco", "andela", "tala", "branch",
    ],
    "lever": [
        "andela", "yassir", "sama", "flutterwave",
    ],
    "workable": [
        "evidence-action", "bracinternational",
    ],
    "smartrecruiters": [
        "AmrefHealthAfrica4",                       # confirmed (Amref, Africa health)
    ],
}


def main() -> int:
    try:
        from jobmesh.connectors import build_connector
    except Exception as exc:
        print(f"Could not import connectors (run from the repo root): {exc}")
        return 1
    clean = []
    print("Testing Africa-focused candidate tokens (live)…\n")
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
