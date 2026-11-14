#!/usr/bin/env python3
"""Teste une liste de flux candidats et imprime le nombre d'offres par URL.

Usage:
    python3 scripts/test_feeds.py

Ajoute/retire des lignes dans CANDIDATES. A la fin, un bloc YAML pret a
coller dans config/companies.yaml est imprime pour les flux qui marchent.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jobmesh.connectors import build_connector

# (platform, url) — ajoute les tiens librement.
CANDIDATES: list[tuple[str, str]] = [
    # --- SmartJobBoard : pattern {domaine}/rss (domaines verifies, page clients officielle) ---
    ("jobfeed", "https://jobs.flnonprofits.org/rss"),
    ("jobfeed", "https://www.cleantechrecruits.com/rss"),
    ("jobfeed", "https://www.christiancareercenter.com/rss"),
    ("jobfeed", "https://www.hireveterans.com/rss"),
    ("jobfeed", "https://academiccareers.com/rss"),
    ("jobfeed", "https://apartmentjobs.com/rss"),
    ("jobfeed", "https://chirorecruit.com/rss"),
    ("jobfeed", "https://environmentalcareer.com/rss"),
    ("jobfeed", "https://jobs.acem.org.au/rss"),
    ("jobfeed", "https://jobs.buckrail.com/rss"),
    ("jobfeed", "https://jobs.psychologicalscience.org/rss"),
    ("jobfeed", "https://jobs.thechemicalengineer.com/rss"),
    ("jobfeed", "https://jobs.tribalcollegejournal.org/rss"),
    ("jobfeed", "https://newimmigrantjobs.ca/rss"),
    ("jobfeed", "https://www.datacareer.de/rss"),
    ("jobfeed", "https://www.jobsinchildcare.com/rss"),
]


def main() -> None:
    winners: list[tuple[str, str, int]] = []
    for platform, url in CANDIDATES:
        try:
            n = len(build_connector(platform, url).fetch())
            if n > 0:
                winners.append((platform, url, n))
            print(f"{n:>6}  {platform:9} {url}")
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).splitlines()[0][:80]
            print(f"   ERR  {platform:9} {url}  -> {msg}")

    if winners:
        total = sum(n for _, _, n in winners)
        print(f"\n# --- {len(winners)} flux OK, {total} offres au total ---")
        print("# A coller sous 'jobfeed:' dans config/companies.yaml :")
        for _, url, n in winners:
            print(f'  - "{url}"   # {n} offres')
    else:
        print("\nAucun flux positif. Ajoute d'autres URLs dans CANDIDATES.")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
