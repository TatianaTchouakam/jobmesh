"""Read public job-detail URLs from the Common Crawl index, without the API.

Some platforms (BrassRing, CSOD) render clean schema.org JobPosting JSON-LD on
each job-detail page but offer no token-free way to *list* the jobs (no sitemap;
the list route needs a session). The public job-detail URLs are, however, part
of the open web and captured by Common Crawl. This module looks them up straight
from the published index on data.commoncrawl.org (cluster.idx + byte-range CDX
shards), bypassing the frequently-overloaded index.commoncrawl.org API.

Everything read here is public. Each caller still checks robots.txt before
fetching a detail page, and keeps a polite pace.
"""

from __future__ import annotations

import gzip
import json
import re
from urllib.parse import urlparse

import requests

COLLINFO = "https://index.commoncrawl.org/collinfo.json"
S3_BASE = "https://data.commoncrawl.org/cc-index/collections/{idx}/indexes/"
TIMEOUT = 60
_CLUSTER: dict[str, list] = {}
_LOC = re.compile(r"<loc>([^<]+)</loc>", re.IGNORECASE)


def latest_index_ids(session: requests.Session, n: int = 2) -> list[str]:
    info = session.get(COLLINFO, timeout=30).json()
    return [c["id"] for c in info[:n]]


def _surt_prefix(host: str, path_prefix: str = "") -> str:
    surt_host = ",".join(reversed(host.split(".")))
    return surt_host + ")" + path_prefix if path_prefix else surt_host


def _cluster(session: requests.Session, idx: str) -> list:
    if idx in _CLUSTER:
        return _CLUSTER[idx]
    url = S3_BASE.format(idx=idx) + "cluster.idx"
    r = session.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    rows = []
    for line in r.text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            try:
                rows.append((parts[0], parts[1], int(parts[2]), int(parts[3])))
            except ValueError:
                pass
    _CLUSTER[idx] = rows
    return rows


def _blocks(rows: list, prefix: str) -> list:
    end = prefix + "\xff"
    out = []
    for i, (key, cdxfile, offset, length) in enumerate(rows):
        nxt = rows[i + 1][0] if i + 1 < len(rows) else "\xff"
        if key < end and nxt > prefix:
            out.append((cdxfile, offset, length))
    return out


def detail_urls(session: requests.Session, host: str, path_prefix: str,
                must_contain: list[str], limit: int = 2000,
                indexes: int = 2) -> list[str]:
    """Public URLs under host+path_prefix whose full URL contains every
    substring in `must_contain` (status 200 captures only)."""
    prefix = _surt_prefix(host, path_prefix)
    seen: set[str] = set()
    out: list[str] = []
    for idx in latest_index_ids(session, indexes):
        base = S3_BASE.format(idx=idx)
        for cdxfile, offset, length in _blocks(_cluster(session, idx), prefix):
            headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
            try:
                r = session.get(base + cdxfile, headers=headers, timeout=TIMEOUT)
            except requests.RequestException:
                continue
            if r.status_code not in (200, 206):
                continue
            try:
                data = gzip.decompress(r.content).decode("utf-8", "replace")
            except OSError:
                continue
            for line in data.splitlines():
                if not line.startswith(prefix):
                    continue
                try:
                    _, _, jtxt = line.split(" ", 2)
                    rec = json.loads(jtxt)
                except (ValueError, KeyError):
                    continue
                if rec.get("status") not in ("200", 200):
                    continue
                u = rec.get("url")
                if not u or u in seen:
                    continue
                if all(s in u for s in must_contain):
                    seen.add(u)
                    out.append(u)
                    if len(out) >= limit:
                        return out
    return out
