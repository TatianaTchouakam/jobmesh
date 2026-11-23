#!/usr/bin/env python3
"""Find live employers for the platforms that still lack a public tenant.

Several required platforms have no central feed: each employer publishes its
own careers site or feed (Paycor per-client ATOM feeds, talentReef, Talenetic,
CareerSiteCloud and eJobBoard tenants). This script looks those tenants up in
the public Common Crawl URL index, then checks each candidate politely:

  1. robots.txt must allow JobmeshBot on the page that is read;
  2. the page or feed must answer (HTTP 200);
  3. it must have at least one open job.

Nothing is guessed into the config: the script prints what it found, and only
the verified lines are added to config/companies.yaml afterwards.

It is bounded (--max candidates per platform), slow on purpose (one request
per second to Common Crawl) and cached in config/.cc_discovery_cache.json.

Run it on a machine with open network access (your Mac):

    python3 scripts/discover_commoncrawl.py
    python3 scripts/discover_commoncrawl.py --only paycor --max 80

Then paste the whole "KEEP THESE" block back.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jobmesh.robots import USER_AGENT, allowed as robots_allowed  # noqa: E402

CACHE = ROOT / "config" / ".cc_discovery_cache.json"
COLLINFO = "https://index.commoncrawl.org/collinfo.json"

# What to look up in the index, per platform. "hosts" are URL patterns in the
# Common Crawl CDX syntax; "*." matches every subdomain.
TARGETS = {
    "paycor": {"hosts": ["recruitingbypaycor.com/career/*", "newton.newtonsoftware.com/career/*"]},
    "talentreef": {"hosts": ["*.talentreef.com", "*.jobappnetwork.com"]},
    "talenetic": {"hosts": ["*.talenetic.com"]},
    "careersitecloud": {"hosts": ["*.careersitecloud.com"]},
    "ejobboard": {"hosts": ["*.ejobboard.com", "*.ejobboards.com"]},
}

_JOB_HINT = re.compile(r'"@type"\s*:\s*"JobPosting"|<entry\b|<item\b|/job/|/jobs/', re.IGNORECASE)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def save_cache(c: dict) -> None:
    CACHE.write_text(json.dumps(c, indent=1, sort_keys=True))


def latest_indexes(s: requests.Session, n: int) -> list[str]:
    r = s.get(COLLINFO, timeout=30)
    r.raise_for_status()
    return [c["cdx-api"] for c in r.json()[:n]]


def cc_urls(s: requests.Session, api: str, pattern: str, limit: int) -> list[str]:
    params = {"url": pattern, "output": "json", "fl": "url,status", "limit": str(limit), "filter": "status:200"}
    if pattern.startswith("*."):
        params["url"] = pattern[2:]
        params["matchType"] = "domain"
    time.sleep(1.0)  # one request per second to Common Crawl
    try:
        r = s.get(api, params=params, timeout=60)
    except requests.RequestException as exc:
        log(f"   index error: {exc}")
        return []
    if r.status_code == 404:  # no capture for this pattern
        return []
    if r.status_code >= 400:
        log(f"   index HTTP {r.status_code}")
        return []
    out = []
    for line in r.text.splitlines():
        try:
            out.append(json.loads(line)["url"])
        except (ValueError, KeyError):
            pass
    return out


def candidates(platform: str, urls: list[str]) -> list[str]:
    """One candidate per employer: a Paycor clientId, or a tenant host."""
    found: dict[str, None] = {}
    for u in urls:
        p = urlparse(u)
        if platform == "paycor":
            cid = (parse_qs(p.query).get("clientId") or [None])[0]
            if cid and re.fullmatch(r"[0-9a-fA-F]{16,40}", cid):
                found[cid] = None
        else:
            host = p.netloc.lower()
            if host and not host.startswith(("www.", "api.", "cdn.", "static.", "help.", "support.", "blog.")):
                found[host] = None
    return list(found)


def check_paycor(s: requests.Session, cid: str) -> tuple[int, str]:
    from jobmesh.connectors.paycor import PaycorConnector
    try:
        jobs = PaycorConnector(f"{cid}|?", session=s).fetch()
    except Exception as exc:  # noqa: BLE001 — report and move on
        return 0, str(exc).splitlines()[0][:100]
    company = ""
    if jobs and jobs[0].source_url:
        company = urlparse(jobs[0].source_url).netloc
    return len(jobs), company


def check_host(s: requests.Session, host: str) -> tuple[int, str]:
    url = f"https://{host}/"
    if not robots_allowed(url, s):
        return 0, "robots disallows"
    try:
        r = s.get(url, timeout=20, allow_redirects=True)
    except requests.RequestException as exc:
        return 0, str(exc).splitlines()[0][:100]
    if r.status_code != 200:
        return 0, f"HTTP {r.status_code}"
    hints = len(_JOB_HINT.findall(r.text or ""))
    return hints, f"final URL {r.url}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=sorted(TARGETS))
    ap.add_argument("--max", type=int, default=60, help="candidates checked per platform")
    ap.add_argument("--indexes", type=int, default=3, help="how many recent crawls to search")
    args = ap.parse_args()

    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    cache = load_cache()
    apis = latest_indexes(s, args.indexes)
    log(f"Common Crawl indexes: {', '.join(a.rsplit('/', 1)[-1] for a in apis)}")

    keep: list[str] = []
    for platform, spec in TARGETS.items():
        if args.only and platform != args.only:
            continue
        log(f"\n== {platform}")
        urls: list[str] = []
        for api in apis:
            for pattern in spec["hosts"]:
                urls += cc_urls(s, api, pattern, 3000)
        cands = candidates(platform, urls)[: args.max]
        log(f"   {len(urls)} captures, {len(cands)} candidate employers")
        for c in cands:
            key = f"{platform}:{c}"
            if key in cache and time.time() - cache[key]["at"] < 7 * 86400:
                n, note = cache[key]["n"], cache[key]["note"]
            else:
                n, note = check_paycor(s, c) if platform == "paycor" else check_host(s, c)
                cache[key] = {"n": n, "note": note, "at": time.time()}
                save_cache(cache)
                time.sleep(0.5)
            mark = "OK " if n > 0 else "-- "
            log(f"   {mark}{c}  ({n}) {note}")
            if n > 0:
                keep.append(f"{platform}: {c}   # {n} {'jobs' if platform == 'paycor' else 'job hints'} · {note}")

    print("\n--- KEEP THESE (paste this whole output back) ---")
    print("\n".join(keep) if keep else "(nothing found)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
