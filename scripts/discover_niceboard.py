#!/usr/bin/env python3
"""Filter candidate Niceboard hosts to the ones with open jobs.

Niceboard uses a wildcard cert, so board subdomains aren't enumerable from
CT logs. Instead, feed this script candidate hosts (bare slugs like
``unitedwayjobbank`` or full custom hosts like ``jobs.forcebrands.com``);
it probes each board's public ``/api/jobs`` endpoint and merges the active
ones into ``config/companies.yaml`` under ``niceboard:``.

    python3 scripts/discover_niceboard.py jobs.example.org myboard ...
    python3 scripts/discover_niceboard.py --file candidates.txt --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "companies.yaml"
UA = "jobmesh-discovery/0.1 (+https://github.com/; polite; contact via repo)"
PARAMS = {
    "company": "all", "jobtype": "[]", "category": "[]", "secondary_category": "[]",
    "tags": "[]", "city": "[]", "state": "[]", "country": "[]",
    "remote_ok": "false", "remote_only": "false", "salary_timeframe": "",
    "salary_min": "", "salary_max": "", "keyword": "", "custom_fields": "{}",
    "limit": 1, "page": 1, "sortby": "newest",
}


def host_for(board: str) -> str:
    return board if "." in board else f"{board}.niceboard.co"


def open_count(session, board: str) -> int | None:
    try:
        r = session.get(f"https://{host_for(board)}/api/jobs", params=PARAMS, timeout=20)
        if r.status_code != 200:
            return None
        return int(r.json().get("count") or 0)
    except Exception:
        return None


def merge_config(boards: list[str]) -> int:
    text = CONFIG.read_text()
    existing = re.findall(r"\nniceboard:\n((?:  - .*\n)+)", text)
    current = re.findall(r"  - (.+)", existing[0]) if existing else []
    merged = sorted({*current, *boards})
    block = (
        "\n# Niceboard (niceboard.co) — public keyless /api/jobs on each hosted board.\n"
        "# board = subdomain slug, OR a full custom host (contains a dot).\n"
        "# grow with scripts/discover_niceboard.py <candidate hosts...>\n"
        "niceboard:\n" + "".join(f"  - {b}\n" for b in merged)
    )
    new = re.sub(r"\n# Niceboard \(niceboard\.co\).*?\nniceboard:\n(?:  - .*\n)+", "\n", text, flags=re.DOTALL)
    new = re.sub(r"\nniceboard:\n(?:  - .*\n)+", "\n", new)
    CONFIG.write_text(new.rstrip() + "\n" + block)
    return len(merged)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("boards", nargs="*", help="candidate slugs or hosts")
    ap.add_argument("--file", help="newline-separated candidates file")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cands = list(args.boards)
    if args.file:
        cands += [l.strip() for l in Path(args.file).read_text().splitlines() if l.strip() and not l.startswith("#")]
    cands = sorted(set(cands))
    if not cands:
        ap.error("give candidate hosts as args or via --file")

    s = requests.Session(); s.headers["User-Agent"] = UA
    active = []
    for b in cands:
        n = open_count(s, b)
        mark = f"{n} jobs" if n else ("no jobs" if n == 0 else "unreachable")
        print(f"  {b}: {mark}", file=sys.stderr)
        if n:
            active.append(b)

    print(f"Active: {len(active)}/{len(cands)} | jobs: see above", file=sys.stderr)
    if args.dry_run:
        print("\n".join(active)); return 0
    total = merge_config(active)
    print(f"Wrote {total} niceboard boards into {CONFIG.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
