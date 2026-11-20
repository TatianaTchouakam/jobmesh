#!/usr/bin/env python3
"""Discover active JOIN (join.com) company boards for jobmesh.

JOIN publishes a public sitemap of ~10k companies, but only a subset
have open jobs at any moment. This script samples the sitemap, checks
which companies currently have open jobs (by parsing each company
page's server-rendered ``__NEXT_DATA__``), and writes the active slugs
into ``config/companies.yaml`` under the ``join:`` key.

It is deliberately *bounded* and *cached* so it never hammers JOIN:
  * ``--max`` caps how many companies are probed in one run.
  * ``--spread`` tests an even spread across the whole sitemap
    (default) instead of only the first N alphabetical entries.
  * a small JSON cache (``config/.join_discovery_cache.json``) records
    when each slug was last checked, so re-runs skip the recently seen.

Run it on a machine with open network access (e.g. your Mac):

    python3 scripts/discover_join.py --max 500 --workers 8

Then review the diff and commit config/companies.yaml.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "companies.yaml"
CACHE = ROOT / "config" / ".join_discovery_cache.json"

SITEMAP = "https://join.com/companies/sitemap.xml"
COMPANY = "https://join.com/companies/{slug}"
USER_AGENT = "jobmesh-discovery/0.1 (+https://github.com/; polite; contact via repo)"

_SLUG_RE = re.compile(r"<loc>https://join\.com/companies/([^<]+)</loc>")
_NEXT_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def fetch_slugs(session: requests.Session) -> list[str]:
    r = session.get(SITEMAP, timeout=30)
    r.raise_for_status()
    return _SLUG_RE.findall(r.text)


def open_jobs(session: requests.Session, slug: str) -> int | None:
    """Return the number of open jobs on a company page, or None on error."""
    try:
        r = session.get(COMPANY.format(slug=slug), timeout=20)
        if r.status_code != 200:
            return None
        m = _NEXT_RE.search(r.text)
        if not m:
            return None
        pd = (
            json.loads(m.group(1))
            .get("props", {})
            .get("pageProps", {})
            .get("pageData", {})
        )
        return len((pd.get("jobs") or {}).get("items") or [])
    except Exception:
        return None


def load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text())
        except Exception:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))


def update_config_join(active: list[str]) -> int:
    """Merge active slugs into the ``join:`` block of companies.yaml.

    Keeps every other platform block untouched; preserves existing join
    slugs and adds the newly discovered ones (sorted, de-duplicated).
    """
    text = CONFIG.read_text()
    existing = re.findall(r"\njoin:\n((?:  - .*\n)+)", text)
    current = []
    if existing:
        current = re.findall(r"  - (.+)", existing[0])
    merged = sorted({*current, *active})
    block = (
        "\n# JOIN (join.com) — public keyless Next.js career pages; board = slug\n"
        "# maintained by scripts/discover_join.py (bounded sitemap discovery)\n"
        "join:\n" + "".join(f"  - {s}\n" for s in merged)
    )
    # remove any existing join: block (with or without our comment header)
    new = re.sub(
        r"\n# JOIN \(join\.com\).*?\njoin:\n(?:  - .*\n)+", "\n", text, flags=re.DOTALL
    )
    new = re.sub(r"\njoin:\n(?:  - .*\n)+", "\n", new)
    CONFIG.write_text(new.rstrip() + "\n" + block)
    return len(merged)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=500, help="max companies to probe this run")
    ap.add_argument("--workers", type=int, default=8, help="concurrent requests (be polite)")
    ap.add_argument("--min-jobs", type=int, default=1, help="min open jobs to count as active")
    ap.add_argument("--spread", action="store_true", default=True, help="even spread across sitemap")
    ap.add_argument("--all", action="store_true", help="probe the whole sitemap (ignores --max)")
    ap.add_argument("--recheck-days", type=float, default=7.0, help="skip slugs checked within N days")
    ap.add_argument("--dry-run", action="store_true", help="don't write config, just report")
    args = ap.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    log("Fetching company sitemap…")
    slugs = fetch_slugs(session)
    log(f"  {len(slugs)} companies in sitemap")

    cache = load_cache()
    now = time.time()
    fresh = {s for s, v in cache.items()
             if now - v.get("checked_at", 0) < args.recheck_days * 86400}

    candidates = [s for s in slugs if s not in fresh]
    if not args.all:
        n = min(args.max, len(candidates))
        if args.spread and len(candidates) > n and n > 0:
            step = len(candidates) / n
            candidates = [candidates[int(i * step)] for i in range(n)]
        else:
            candidates = candidates[:n]
    log(f"  probing {len(candidates)} companies ({len(fresh)} skipped as recently checked)")

    active: list[str] = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(open_jobs, session, s): s for s in candidates}
        for fut in as_completed(futs):
            slug = futs[fut]
            n = fut.result()
            done += 1
            if n is not None:
                cache[slug] = {"checked_at": now, "open_jobs": n}
                if n >= args.min_jobs:
                    active.append(slug)
            if done % 50 == 0:
                log(f"    {done}/{len(candidates)} checked, {len(active)} active so far")

    # all currently-active slugs we know of (this run + still-fresh cache hits)
    known_active = sorted({
        s for s, v in cache.items() if v.get("open_jobs", 0) >= args.min_jobs
    })
    log(f"Active this run: {len(active)} | total active known: {len(known_active)}")

    save_cache(cache)
    if args.dry_run:
        log("Dry run — config not written. Active slugs:")
        print("\n".join(known_active))
        return 0

    total = update_config_join(known_active)
    log(f"Wrote {total} join boards into {CONFIG.relative_to(ROOT)}")
    log("Review the diff, then run ingest and commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
