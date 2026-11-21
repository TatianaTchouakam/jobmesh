"""Command-line interface for jobmesh.

Usage:
    python -m jobmesh.cli ingest            # refresh the index from config
    python -m jobmesh.cli search "data engineer" --location remote
    python -m jobmesh.cli stats
"""

from __future__ import annotations

import argparse
import json
import logging

from . import storage
import os

from .config import load_boards
from .pipeline import ingest


def _cmd_ingest(args) -> None:
    boards = load_boards(args.config) if args.config else load_boards()
    # Build-time safety cap (e.g. Render free tier): limit boards per platform.
    # Unset locally -> full ingest. Self-discovering connectors (Dover/Recooty
    # use the 'all' token) are bounded by their own *_MAX_* env vars instead.
    _cap = os.getenv("INGEST_MAX_BOARDS")
    if _cap:
        _n = int(_cap)
        boards = {p: bl[:_n] for p, bl in boards.items()}
    with storage.session(args.db) as conn:
        results = ingest(conn, boards)

    ok = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status == "failure"]
    total_new = sum(r.new for r in ok)
    total_updated = sum(r.updated for r in ok)
    total_closed = sum(r.closed for r in ok)
    total_fetched = sum(r.fetched for r in ok)

    print(
        f"Ingest complete: {len(ok)} boards OK, {len(failed)} failed | "
        f"{total_fetched} jobs seen | {total_new} new, "
        f"{total_updated} updated, {total_closed} closed"
    )
    for r in failed:
        print(f"  ! {r.platform}/{r.board}: {r.error}")


def _cmd_search(args) -> None:
    with storage.session(args.db) as conn:
        rows = storage.search(
            conn,
            keyword=args.keyword,
            company=args.company,
            location=args.location,
            open_only=not args.include_closed,
            limit=args.limit,
            offset=args.offset,
        )
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    if not rows:
        print("No matching jobs.")
        return
    for r in rows:
        tag = "" if r["is_open"] else " [CLOSED]"
        loc = r["location"] or "—"
        print(f"- {r['title']} @ {r['company']} ({loc}){tag}")
        print(f"    {r['apply_url']}")


def _cmd_stats(args) -> None:
    with storage.session(args.db) as conn:
        print(json.dumps(storage.stats(conn), indent=2, ensure_ascii=False))



def _cmd_sources(args) -> None:
    from . import sources as srcreg
    data = srcreg.load_sources()
    try:
        with storage.session(args.db) as conn:
            obp = storage.stats(conn).get("open_by_platform", {})
    except Exception:
        obp = {}
    rows = srcreg.health(obp, data)
    counts = srcreg.status_counts(data)
    if getattr(args, "json", False):
        print(json.dumps({"status_counts": counts, "sources": rows},
                         indent=2, ensure_ascii=False))
        return
    order = {s: i for i, s in enumerate(srcreg.STATUSES)}
    rows.sort(key=lambda r: (order.get(r["status"], 9), r["name"].lower()))
    active = counts.get("ACTIVE", 0)
    total = sum(counts.values())
    print(f"JobMesh source registry — {active}/{total} required platforms ACTIVE (live)\n")
    for r in rows:
        if r["status"] == "ACTIVE":
            live = r["live_open"]
            tail = f"{live} open" if live is not None else "live"
            print(f"  ACTIVE                      {r['name']:<22} {r['connector']:<16} {tail}")
        else:
            print(f"  {r['status']:<27} {r['name']:<22} -> {r['next_action'] or r['reason'] or ''}")
    print("\nStatus summary: " + ", ".join(f"{k}={counts[k]}" for k in srcreg.STATUSES if k in counts))
    print("Only ACTIVE sources run in the daily ingest; the rest are declared, not failed.")



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobmesh", description=__doc__)
    parser.add_argument("--db", default=storage.DEFAULT_DB, help="SQLite path")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="refresh the index from config")
    p_ingest.add_argument("--config", help="path to companies.yaml")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_search = sub.add_parser("search", help="search the index")
    p_search.add_argument("keyword", nargs="?", help="keyword in title/description")
    p_search.add_argument("--company")
    p_search.add_argument("--location")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.add_argument("--offset", type=int, default=0)
    p_search.add_argument("--include-closed", action="store_true")
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=_cmd_search)

    p_stats = sub.add_parser("stats", help="show index statistics")
    p_stats.set_defaults(func=_cmd_stats)

    p_src = sub.add_parser("sources", help="integration status of all required platforms")
    p_src.add_argument("--json", action="store_true", help="machine-readable output")
    p_src.set_defaults(func=_cmd_sources)

    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
