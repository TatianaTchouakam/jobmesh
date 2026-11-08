#!/usr/bin/env python3
"""Quick, local check of candidate ATS tokens before adding them to config.

Your machine has network access to the job APIs (the build container does
not), so run this HERE, then paste the output back. We'll add to
config/companies.yaml ONLY the tokens that come back ✅ with jobs — so the
fetch_log stays 100% clean.

Usage:
    cd ~/projects/Vaya/jobmesh
    python verify_new_sources.py

Edit CANDIDATES below to try your own tokens too. For BambooHR / HireHive,
a token is the subdomain in a company's careers URL, e.g.
    https://acme.bamboohr.com/careers   -> acme      (bamboohr)
    https://acme.hirehive.com           -> acme      (hirehive)
    https://careers-page.com/acme       -> acme      (manatal)
"""

from __future__ import annotations

import sys

# platform -> list of candidate tokens to test
CANDIDATES = {
    "ashby": ["corma","cogna","carrum-health","ahead-nutrition","quo","quadrature",
              "pairs","infinite","evermore","empathy","earth","credo","cint","alloy",
              "adc","square-enix","revyl","plot-pointe","mozilla","legorafi"],
    "smartrecruiters": ["HenryFordHealthSystem","2SistersFoodGroup","GreinerAG","Greiner",
                        "BradyCorporation","NuSkin","NuSkinEnterprises","AlliedHealthcare"],
    "greenhouse": [],
    "recruitee": [],
}


def main() -> int:
    try:
        from jobmesh.connectors import build_connector
    except Exception as exc:  # pragma: no cover
        print(f"Could not import connectors (run from the repo root): {exc}")
        return 1

    clean: list[tuple[str, str, int]] = []
    print("Testing candidate tokens (live)…\n")
    for platform, tokens in CANDIDATES.items():
        if not tokens:
            print(f"· {platform}: (no candidate token set — skipped)")
            continue
        for token in tokens:
            try:
                jobs = build_connector(platform, token).fetch()
                n = len(jobs)
                if n > 0:
                    print(f"  ✅ {platform}/{token}: {n} jobs")
                    clean.append((platform, token, n))
                else:
                    print(f"  ⚠️  {platform}/{token}: 0 jobs (valid but empty — skip)")
            except Exception as exc:
                msg = str(exc).splitlines()[0][:90]
                print(f"  ❌ {platform}/{token}: {msg}")

    print("\n--- KEEP THESE (paste this whole output back) ---")
    if clean:
        for platform, token, n in clean:
            print(f"{platform}: {token}   # {n} jobs")
    else:
        print("(nothing returned jobs — we'll hunt different tokens)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
