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
from .config import load_boards
from .pipeline import ingest


def _cmd_ingest(args) -> None:
    boards = load_boards(args.config) if args.config else load_boards()
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

    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
