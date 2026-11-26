"""Pre-generated gzip exports of the full open index.

Written to disk after each ingest cycle so the bulk-download routes serve a
static file instead of streaming the whole table on every request. Rows are
streamed from one cursor, so memory stays bounded regardless of catalogue size.
"""
from __future__ import annotations

import csv
import gzip
import json
import os

from . import storage


def write_gz_exports(db_path: str, out_dir: str, cols, limit: int | None = None) -> int:
    """Write jobs.ndjson.gz and jobs.csv.gz (all open postings) into out_dir.

    Returns the row count. Writes to temp files and renames, so a reader never
    sees a half-written export. `limit` caps rows (for tests); None = all.
    """
    os.makedirs(out_dir, exist_ok=True)
    nd_final = os.path.join(out_dir, "jobs.ndjson.gz")
    csv_final = os.path.join(out_dir, "jobs.csv.gz")
    nd_tmp, csv_tmp = nd_final + ".tmp", csv_final + ".tmp"
    header = [c for c, _ in cols]
    n = 0
    with storage.session(db_path) as conn:
        cur = conn.execute(
            "SELECT * FROM jobs WHERE is_open = 1 "
            "ORDER BY COALESCE(posted_at, first_seen) DESC")
        with gzip.open(nd_tmp, "wt", encoding="utf-8") as ndf, \
             gzip.open(csv_tmp, "wt", encoding="utf-8", newline="") as cf:
            w = csv.writer(cf)
            w.writerow(header)
            for row in cur:
                r = dict(row)
                ndf.write(json.dumps({name: r.get(src) for name, src in cols},
                                     ensure_ascii=False) + "\n")
                w.writerow([r.get(src) for _, src in cols])
                n += 1
                if limit and n >= limit:
                    break
    os.replace(nd_tmp, nd_final)
    os.replace(csv_tmp, csv_final)
    return n
