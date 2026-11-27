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


# -- sitemap (generated after each cycle, served from disk) ---------------

_SITEMAP_MAX_URLS = 50000   # sitemaps.org per-file limit


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _seo_paths(conn) -> list[str]:
    """SEO landing-page paths that currently have at least one open job.

    Uses the indexed country column and the FTS keyword counts, so this is
    cheap even on a large index."""
    from .api import (_SEO_COUNTRIES, _SEO_ROLES, _SEO_TYPES,
                      _resolve_employment_type)
    paths: list[str] = ["/", "/status", "/api"]
    for code in _SEO_COUNTRIES:
        if storage.count(conn, country=code, open_only=True) > 0:
            paths.append(f"/jobs/in/{code.lower()}")
    for slug, kw in _SEO_ROLES:
        if storage.count(conn, keyword=kw, open_only=True) > 0:
            paths.append(f"/jobs/role/{slug}")
    for slug in _SEO_TYPES:
        et = _resolve_employment_type(conn, slug)
        if et and storage.count(conn, employment_type=et, open_only=True) > 0:
            paths.append(f"/jobs/type/{slug}")
    return paths


def write_sitemaps(db_path: str, out_dir: str, base_url: str) -> int:
    """Generate a gzip sitemap set (index + sitemap-N.xml.gz of <=50k URLs).

    Streams open-job UIDs from one cursor, so memory stays bounded whatever
    the catalogue size. Writes temp files and renames, so a crawler never sees
    a half-written sitemap. Returns the number of job URLs written."""
    os.makedirs(out_dir, exist_ok=True)
    base = base_url.rstrip("/")
    files: list[str] = []
    written = 0

    def _open(idx: int):
        name = f"sitemap-{idx}.xml.gz"
        gz = gzip.open(os.path.join(out_dir, name + ".tmp"), "wt", encoding="utf-8")
        gz.write('<?xml version="1.0" encoding="UTF-8"?>'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        return name, gz

    with storage.session(db_path) as conn:
        seo = _seo_paths(conn)
        idx = 1
        name, gz = _open(idx)
        files.append(name)
        in_file = 0
        for pth in seo:
            gz.write(f"<url><loc>{base}{pth}</loc></url>")
            in_file += 1
        cur = conn.execute("SELECT uid FROM jobs WHERE is_open = 1")
        while True:
            batch = cur.fetchmany(5000)
            if not batch:
                break
            for (uid,) in batch:
                if in_file >= _SITEMAP_MAX_URLS:
                    gz.write("</urlset>")
                    gz.close()
                    os.replace(os.path.join(out_dir, name + ".tmp"),
                               os.path.join(out_dir, name))
                    idx += 1
                    name, gz = _open(idx)
                    files.append(name)
                    in_file = 0
                gz.write(f"<url><loc>{base}/jobs/{_xml_escape(uid)}</loc></url>")
                in_file += 1
                written += 1
        gz.write("</urlset>")
        gz.close()
        os.replace(os.path.join(out_dir, name + ".tmp"),
                   os.path.join(out_dir, name))

    # Sitemap index pointing at every file.
    from .models import now_iso
    lastmod = now_iso()
    idx_tmp = os.path.join(out_dir, "sitemap.xml.tmp")
    with open(idx_tmp, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>'
                 '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        for name in files:
            fh.write(f"<sitemap><loc>{base}/{name}</loc>"
                     f"<lastmod>{lastmod}</lastmod></sitemap>")
        fh.write("</sitemapindex>")
    os.replace(idx_tmp, os.path.join(out_dir, "sitemap.xml"))
    return written
