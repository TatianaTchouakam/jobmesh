#!/usr/bin/env python3
"""Classify board fetch failures by cause and list dead boards to prune.

Runs the real connector for each board (same code path as the ingest) and
buckets the outcome: ok / 404 / 410 / 429 / timeout / conn / 403 / 5xx /
parse / other. A board that returns 404/410 is "dead" (its listing is gone)
and a candidate for removal from config/companies.yaml.

Usage:
    python3 scripts/diagnose_boards.py --platforms greenhouse,lever,ashby --max 400
    python3 scripts/diagnose_boards.py --all --workers 8 > report.txt

It only reads; it never edits config. Dead boards are printed (and written to
--out as JSON) so a human can review before pruning.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from jobmesh.config import load_boards  # noqa: E402
from jobmesh.connectors import build_connector  # noqa: E402
from jobmesh.ratelimit import RateLimited  # noqa: E402


def classify(exc: Exception | None) -> str:
    if exc is None:
        return "ok"
    if isinstance(exc, RateLimited):
        return "429"
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.ConnectionError):
        return "conn"
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return str(exc.response.status_code)
    msg = str(exc).lower()
    for code in ("404", "410", "403", "429", "500", "502", "503", "504"):
        if code in msg:
            return code
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "connect" in msg or "resolve" in msg or "ssl" in msg:
        return "conn"
    if "json" in msg or "parse" in msg or "empty" in msg:
        return "parse"
    return "other"


DEAD = {"404", "410"}


def check(platform: str, board: str):
    try:
        jobs = build_connector(platform, board).fetch()
        return platform, board, "ok", len(jobs)
    except Exception as exc:  # noqa: BLE001
        return platform, board, classify(exc), 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--platforms", help="comma-separated platform names")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--max", type=int, default=0, help="cap boards per platform")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    boards = load_boards()
    if not args.all:
        want = set((args.platforms or "").split(","))
        boards = {p: b for p, b in boards.items() if p in want}
    tasks = []
    for p, blist in boards.items():
        bl = blist[: args.max] if args.max else blist
        tasks += [(p, b) for b in bl]

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(lambda t: check(*t), tasks):
            results.append(r)

    by_cause = Counter(r[2] for r in results)
    by_plat_cause = Counter((r[0], r[2]) for r in results)
    dead = [(p, b) for p, b, c, _ in results if c in DEAD]

    print(f"checked {len(results)} boards")
    print("by cause:", dict(by_cause))
    print("\ndead (404/410) by platform:",
          dict(Counter(p for p, _ in dead)))
    for (p, c), n in sorted(by_plat_cause.items()):
        if c not in ("ok",):
            print(f"  {p:<16} {c:<8} {n}")
    if args.out:
        json.dump({"dead": dead,
                   "by_cause": dict(by_cause)}, open(args.out, "w"))
        print(f"\ndead boards written to {args.out}")


if __name__ == "__main__":
    main()
