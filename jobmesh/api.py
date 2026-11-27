"""HTTP API for the job index (FastAPI), plus a small search web page.

Run it with:
    uvicorn jobmesh.api:app --reload

Then open:
    http://127.0.0.1:8000        -> the search page
    http://127.0.0.1:8000/docs   -> interactive API documentation
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, Query, Request, Header
from fastapi.responses import (FileResponse, StreamingResponse, JSONResponse,
                               Response, HTMLResponse, PlainTextResponse)
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import storage
from . import geo
from . import pro

import csv
import io


class FeedbackIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    name: Optional[str] = Field(None, max_length=80)
    lang: Optional[str] = Field(None, max_length=5)

app = FastAPI(
    title="jobmesh API",
    version="0.1.0",
    description="A unified, continuously updated index of job postings.",
)

DB_PATH = storage.DEFAULT_DB

# On the deployed server (self-refresh on) keep startup fast: defer the heavy
# migration (country backfill, FTS rebuild) to the background refresh thread so
# the server answers /health in seconds instead of blocking on a full reindex.
# Keyword search falls back to LIKE until that background migration finishes.
if os.getenv("INGEST_INTERVAL_HOURS"):
    storage.DEFER_HEAVY_MIGRATION = True
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

# Serve the bundled front-end libraries (d3, topojson) and the world map
# locally, so the interactive globe needs no external CDN.
_VENDOR = os.path.join(WEB_DIR, "vendor")
if os.path.isdir(_VENDOR):
    app.mount("/vendor", StaticFiles(directory=_VENDOR), name="vendor")

# Expose the index to AI agents over MCP (POST /mcp). Wrapped so a problem
# in the MCP layer can never stop the main API from starting.
try:
    from .mcp_server import register_mcp
    register_mcp(app, DB_PATH)
except Exception:  # pragma: no cover
    pass

# Jobmesh Pro billing (Stripe Checkout + signed keys). Guarded so a missing
# Stripe config can never stop the API from starting.
try:
    from .billing import router as _billing_router
    app.include_router(_billing_router)
except Exception:  # pragma: no cover
    pass

# Jobmesh Pro billing via PayPal (subscription), alongside Stripe. Same guard:
# a missing PayPal config never stops the API from starting.
try:
    from .paypal import router as _paypal_router
    app.include_router(_paypal_router)
except Exception:  # pragma: no cover
    pass


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    """Serve the search page."""
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/robots.txt", include_in_schema=False)
def robots_txt() -> PlainTextResponse:
    base = os.getenv("BASE_URL", "https://jobmesh.world").rstrip("/")
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml() -> Response:
    # Served straight from disk: the index + gzip url-files are regenerated at
    # the end of each ingest cycle (no per-request computation). Before the
    # first cycle has run we fall back to a small on-demand SEO-only sitemap.
    idx_path = os.path.join(EXPORT_DIR, "sitemap.xml")
    if os.path.exists(idx_path):
        return FileResponse(idx_path, media_type="application/xml")
    base = os.getenv("BASE_URL", "https://jobmesh.world").rstrip("/")
    paths = ["/", "/status", "/api"]
    try:
        with storage.session(DB_PATH) as conn:
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
    except Exception:
        pass
    items = "".join(f"<url><loc>{base}{pth}</loc></url>" for pth in paths)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           f"{items}</urlset>")
    return Response(xml, media_type="application/xml")


@app.get("/sitemap-{n}.xml.gz", include_in_schema=False)
def sitemap_part(n: int) -> Response:
    """Serve a generated gzip url-file straight from disk."""
    path = os.path.join(EXPORT_DIR, f"sitemap-{n}.xml.gz")
    if not os.path.exists(path):
        raise StarletteHTTPException(status_code=404, detail="no such sitemap")
    return FileResponse(path, media_type="application/gzip")


import html as _html
import json as _json

_SEO_COUNTRIES = ["DE", "US", "GB", "FR", "NL", "ES", "IT", "PL", "PT", "SE",
                  "CH", "IE", "CA", "AT", "BE", "IN"]
_SEO_ROLES = [("data-engineer", "data engineer"), ("data-analyst", "data analyst"),
              ("data-scientist", "data scientist"), ("software-engineer", "software engineer"),
              ("product-manager", "product manager"), ("devops-engineer", "devops"),
              ("machine-learning-engineer", "machine learning"), ("backend-engineer", "backend"),
              ("frontend-engineer", "frontend"), ("business-analyst", "business analyst"),
              ("project-manager", "project manager"), ("ux-designer", "designer")]
_SEO_TYPES = ["full-time", "part-time", "contract", "internship", "temporary"]


def _resolve_country_code(seg: str):
    from . import geo
    code = None
    try:
        code = geo.resolve_country(seg)
    except Exception:
        code = None
    if not code and seg and seg.upper() in geo.COUNTRY_NAME:
        code = seg.upper()
    if code and code in geo.COUNTRY_NAME:
        return code, geo.COUNTRY_NAME[code]
    return None, None


def _resolve_employment_type(conn, slug: str):
    want = (slug or "").lower().replace("-", " ").replace("_", " ").strip()
    rows = conn.execute(
        "SELECT DISTINCT employment_type FROM jobs "
        "WHERE employment_type IS NOT NULL AND TRIM(employment_type) != '' "
        "AND is_open = 1").fetchall()
    vals = [r[0] for r in rows]
    for v in vals:
        if v and v.lower().replace("-", " ").replace("_", " ").strip() == want:
            return v
    for v in vals:
        if v and want and want in v.lower():
            return v
    return None


def _seo_page(title: str, h1: str, desc: str, canonical: str, jobs, total: int):
    base = os.getenv("BASE_URL", "https://jobmesh.world").rstrip("/")

    def esc(x):
        return _html.escape(str(x if x is not None else ""))

    elements = []
    for i, j in enumerate(jobs, 1):
        url = j.get("apply_url") or j.get("source_url") or ""
        elements.append({
            "@type": "ListItem", "position": i, "url": url,
            "item": {
                "@type": "JobPosting",
                "title": j.get("title"),
                "hiringOrganization": {"@type": "Organization", "name": j.get("company")},
                "jobLocation": {"@type": "Place", "address": {
                    "@type": "PostalAddress", "addressLocality": j.get("location")}},
                "datePosted": j.get("posted_at"),
                "url": url,
            }})
    ld = _json.dumps({"@context": "https://schema.org", "@type": "ItemList",
                      "itemListElement": elements}, ensure_ascii=False)
    rows_html = "".join(
        f'<li><a href="{esc(j.get("apply_url") or j.get("source_url") or "#")}" rel="nofollow">'
        f'{esc(j.get("title"))}</a><span>{esc(j.get("company"))}</span>'
        f'<span>{esc(j.get("location"))}</span></li>' for j in jobs)
    page = (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)}</title><meta name=description content='{esc(desc)}'>"
        f"<link rel=canonical href='{base}{esc(canonical)}'>"
        f"<script type='application/ld+json'>{ld}</script>"
        "<style>body{font-family:Inter,system-ui,-apple-system,sans-serif;max-width:880px;"
        "margin:0 auto;padding:28px;color:#1c2030;background:#faf8f3}h1{font-size:26px;"
        "letter-spacing:-.02em;margin:.2em 0}ul{list-style:none;padding:0}li{padding:11px 0;"
        "border-bottom:1px solid #ececec}a{color:#c4881a;font-weight:700;text-decoration:none}"
        "span{color:#6b7280;font-size:14px;margin-left:10px}.t{color:#6b7280}</style></head><body>"
        f"<p class=t><a href='/'>Jobmesh</a> — the whole-web job index</p>"
        f"<h1>{esc(h1)}</h1><p class=t>{total:,} open roles</p><ul>{rows_html}</ul>"
        f"<p class=t><a href='/'>Search the full index →</a></p></body></html>")
    return HTMLResponse(page)


def _error_page(code: int, title: str) -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>Jobmesh \u2014 {code}</title><style>"
        "body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;"
        "font-family:Inter,system-ui,-apple-system,sans-serif;background:#faf8f3;color:#1c2030;text-align:center}"
        ".b{max-width:30em;padding:24px}.c{font-size:64px;font-weight:900;letter-spacing:-.03em;color:#c4881a;margin:0}"
        "h1{font-size:20px;margin:.3em 0}a{color:#c4881a;font-weight:700;text-decoration:none}"
        "</style></head><body><div class=b>"
        f"<p class=c>{code}</p><h1>{title}</h1>"
        "<p>Try the <a href='/'>search</a> or the <a href='/status'>status page</a>.</p>"
        "</div></body></html>"
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exc_handler(request: Request, exc: StarletteHTTPException):
    accept = request.headers.get("accept", "")
    if exc.status_code == 404 and "text/html" in accept:
        return HTMLResponse(_error_page(404, "Page not found"), status_code=404)
    return JSONResponse({"error": exc.detail or "error", "status": exc.status_code,
                         "request_id": _req_id(request)}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return HTMLResponse(_error_page(500, "Something went wrong"), status_code=500)
    return JSONResponse({"error": "internal server error", "status": 500,
                         "request_id": _req_id(request)}, status_code=500)


@app.get("/stats")
def get_stats(request: Request):
    """Headline numbers about the current index. A browser (Accept: text/html)
    gets the human status page; API clients get JSON."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        return FileResponse(os.path.join(WEB_DIR, "status.html"))
    with storage.session(DB_PATH) as conn:
        return storage.stats(conn)


@app.get("/coverage")
def get_coverage() -> dict:
    """Per-source-platform status: open jobs, boards and last-fetch health."""
    with storage.session(DB_PATH) as conn:
        return storage.coverage(conn)


@app.get("/status", include_in_schema=False)
def status_page() -> FileResponse:
    """Human-readable status / coverage page (proof of what the index holds)."""
    return FileResponse(os.path.join(WEB_DIR, "status.html"))


@app.get("/api", include_in_schema=False)
def api_page() -> FileResponse:
    """Human-readable API reference page."""
    return FileResponse(os.path.join(WEB_DIR, "api.html"))


@app.get("/sources")
def get_sources() -> dict:
    """Full required-platform registry: per-platform status, live open count
    and the exact reason a platform is not yet active. Powers the public
    coverage table (X / 78)."""
    from . import sources as srcreg
    data = srcreg.load_sources()
    with storage.session(DB_PATH) as conn:
        obp = storage.stats(conn).get("open_by_platform", {})
        obb = storage.open_counts_by_board(conn)
        last = storage.last_fetch_by_platform(conn)
    rows = srcreg.health(obp, data, obb)
    _attach_last_read(rows, last)
    counts = srcreg.status_counts(data)
    return {
        "status_counts": counts,
        "statuses": list(srcreg.STATUSES),
        "required_total": sum(counts.values()),
        "active": counts.get("ACTIVE", 0),
        "ats_total": len(data.get("required_ats", [])),
        "boards_total": len(data.get("required_boards", [])),
        "bonus_count": len(srcreg.bonus_sources(data)),
        "sources": rows,
    }


def _filters(keyword, company, location, platform, workplace_type,
             employment_type, category, country=None, level=None, since=None,
             posted_after=None, seen_within=None, has_salary=False,
             include_closed=False) -> dict:
    return {
        "keyword": keyword, "company": company, "location": location,
        "platform": platform, "workplace_type": workplace_type,
        "employment_type": employment_type, "category": category,
        "country": country, "level": level, "since": since,
        "posted_after": posted_after, "seen_within": seen_within,
        "has_salary": bool(has_salary), "open_only": not bool(include_closed),
    }


FREE_LIMIT = 50          # max results per request without a Pro key
PRO_LIMIT = 1000         # max results per request with a Pro key
EXPORT_CAP = 5000        # max rows per page for the Premium JSON feed
SAMPLE_CAP = 1000        # free sample without a key: the N most recent rows
SAMPLE_NOTE = "Free sample — full export with Jobmesh Premium"
SAMPLE_NOTE_ASCII = "Free sample - full export with Jobmesh Premium"  # latin-1 safe for HTTP headers


def _pro_payload(api_key, x_api_key):
    """Return the signed-key payload if a valid Pro key is supplied, else None."""
    return pro.verify_key(api_key or x_api_key)


# --- Rate limiting, request id and source "last read" ----------------------
import time as _time
import uuid as _uuid
from collections import defaultdict as _defaultdict, deque as _deque

RATE_WINDOW = 60
RATE_FREE = int(os.getenv("RATE_LIMIT_FREE", "240"))      # requests/min without a key
RATE_PRO = int(os.getenv("RATE_LIMIT_PRO", "2400"))       # requests/min with a Premium key
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "1") != "0"
_rl_hits = _defaultdict(_deque)
_RL_INCLUDE = ("/jobs", "/export", "/changes", "/companies", "/suggest",
               "/filter-values", "/stats", "/sources", "/coverage",
               "/facets", "/geo", "/mcp")
_RL_EXCLUDE = ("/jobs/in", "/jobs/role", "/jobs/type")


def _api_path(path: str) -> bool:
    for e in _RL_EXCLUDE:
        if path == e or path.startswith(e + "/"):
            return False
    for i in _RL_INCLUDE:
        if path == i or path.startswith(i + "/"):
            return True
    return False


def _req_id(request) -> str:
    return getattr(getattr(request, "state", None), "request_id", None) or _uuid.uuid4().hex[:16]


def _attach_last_read(rows, last):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for row in rows:
        ts = last.get(row.get("connector"))
        row["last_read"] = ts
        hrs = None
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                hrs = round((now - dt).total_seconds() / 3600, 1)
            except Exception:
                hrs = None
        row["last_read_hours_ago"] = hrs


@app.middleware("http")
async def _rate_limit_mw(request: Request, call_next):
    rid = request.headers.get("x-request-id") or _uuid.uuid4().hex[:16]
    request.state.request_id = rid
    if not _api_path(request.url.path):
        resp = await call_next(request)
        resp.headers["X-Request-Id"] = rid
        return resp
    key = request.headers.get("x-api-key") or request.query_params.get("api_key")
    is_pro = bool(key) and _pro_payload(key, key) is not None
    ident = ("k:" + key) if is_pro else ("ip:" + (request.client.host if request.client else "?"))
    limit = RATE_PRO if is_pro else RATE_FREE
    now = _time.time()
    dq = _rl_hits[ident]
    while dq and dq[0] <= now - RATE_WINDOW:
        dq.popleft()
    if RATE_LIMIT_ENABLED and len(dq) >= limit:
        reset = int(dq[0] + RATE_WINDOW)
        resp = JSONResponse(
            {"error": "rate limit exceeded", "request_id": rid,
             "limit": limit, "window_seconds": RATE_WINDOW}, status_code=429)
        resp.headers["X-RateLimit-Limit"] = str(limit)
        resp.headers["X-RateLimit-Remaining"] = "0"
        resp.headers["X-RateLimit-Reset"] = str(reset)
        resp.headers["Retry-After"] = str(max(1, reset - int(now)))
        resp.headers["X-Request-Id"] = rid
        return resp
    dq.append(now)
    resp = await call_next(request)
    resp.headers["X-RateLimit-Limit"] = str(limit)
    resp.headers["X-RateLimit-Remaining"] = str(max(0, limit - len(dq)))
    resp.headers["X-RateLimit-Reset"] = str(int(now + RATE_WINDOW))
    resp.headers["X-Request-Id"] = rid
    return resp


@app.get("/jobs")
def list_jobs(
    keyword: Optional[str] = Query(None, description="match in title/description"),
    q: Optional[str] = Query(None, description="alias for keyword"),
    company: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    platform: Optional[str] = Query(None, description="filter by source platform"),
    workplace_type: Optional[str] = Query(None, description="remote / hybrid / onsite"),
    employment_type: Optional[str] = Query(None, description="e.g. Full-time, Contract"),
    category: Optional[str] = Query(None, description="broad domain, e.g. Engineering"),
    country: Optional[str] = Query(None, description="ISO-2 country, e.g. DE"),
    level: Optional[str] = Query(None, description="seniority, e.g. Internship, Junior / Entry, Senior"),
    since: Optional[str] = Query(None, description="only jobs posted within the last N days"),
    posted_after: Optional[str] = Query(None, description="jobs posted on/after YYYY-MM-DD"),
    seen_within: Optional[int] = Query(None, ge=1, description="first seen within the last N days"),
    has_salary: bool = Query(False, description="only jobs that list a salary"),
    include_closed: bool = Query(False, description="include closed postings (is_open=false)"),
    limit: int = Query(30, ge=1, le=PRO_LIMIT),
    offset: int = Query(0, ge=0),
    api_key: Optional[str] = Query(None, description="Jobmesh Premium API key"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> dict:
    """Search the index with filters and pagination."""
    keyword = keyword or q
    is_pro = _pro_payload(api_key, x_api_key) is not None
    if not is_pro:
        limit = min(limit, FREE_LIMIT)
    f = _filters(keyword, company, location, platform, workplace_type,
                 employment_type, category, country, level, since,
                 posted_after, seen_within, has_salary, include_closed)
    with storage.session(DB_PATH) as conn:
        rows = storage.search(conn, limit=limit, offset=offset, **f)
        total = storage.count(conn, **f)
    capped = total > storage.COUNT_CAP
    if capped:
        total = storage.COUNT_CAP
    return {
        "count": len(rows),
        "total": total,
        "total_capped": capped,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < total,
        "pro": is_pro,
        "free_limit": FREE_LIMIT,
        "results": rows,
    }


@app.get("/jobs/by-url")
def job_by_url(url: str = Query(..., description="source_url or apply_url")) -> dict:
    """One posting by its source or apply URL."""
    with storage.session(DB_PATH) as conn:
        job = storage.get_job_by_url(conn, url)
    if not job:
        raise StarletteHTTPException(status_code=404, detail="job not found")
    return job


@app.get("/jobs/{uid}")
def job_by_id(uid: str) -> dict:
    """One posting by its uid."""
    with storage.session(DB_PATH) as conn:
        job = storage.get_job(conn, uid)
    if not job:
        raise StarletteHTTPException(status_code=404, detail="job not found")
    return job


@app.get("/companies")
def companies(
    q: Optional[str] = Query(None, description="filter by employer name"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    include_closed: bool = Query(False),
) -> dict:
    """Employers with their open-job counts, most first."""
    with storage.session(DB_PATH) as conn:
        total, rows = storage.list_companies(
            conn, limit=limit, offset=offset, q=q, open_only=not include_closed)
    return {"count": len(rows), "total": total, "limit": limit, "offset": offset,
            "has_more": offset + len(rows) < total, "data": rows}


@app.get("/companies/{company}")
def company_detail(
    company: str,
    limit: int = Query(50, ge=1, le=FREE_LIMIT),
    offset: int = Query(0, ge=0),
) -> dict:
    """A single employer: open-job count and its most recent postings."""
    f = _filters(None, company, None, None, None, None, None)
    with storage.session(DB_PATH) as conn:
        total = storage.count(conn, **f)
        rows = storage.search(conn, limit=limit, offset=offset, **f)
    if total == 0:
        raise StarletteHTTPException(status_code=404, detail="company not found")
    return {"company": company, "open_jobs": total, "count": len(rows),
            "limit": limit, "offset": offset,
            "has_more": offset + len(rows) < total, "results": rows}


@app.get("/filter-values")
def get_filter_values(include_closed: bool = Query(False)) -> dict:
    """Distinct values (with counts) for each filter field."""
    with storage.session(DB_PATH) as conn:
        return storage.filter_values(conn, open_only=not include_closed)


@app.get("/suggest")
def get_suggest(q: str = Query(..., min_length=1),
                limit: int = Query(10, ge=1, le=25)) -> dict:
    """Prefix-first title and company suggestions."""
    with storage.session(DB_PATH) as conn:
        return {"query": q, "suggestions": storage.suggest(conn, q, limit=limit)}


@app.get("/changes")
def changes(
    since: Optional[str] = Query(None, description="cursor: last_changed from a previous page"),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    """New, modified and closed postings since a cursor (ascending by change time)."""
    with storage.session(DB_PATH) as conn:
        rows, cursor = storage.changes_since(conn, since=since, limit=limit)
    data = [{
        "change_type": storage.change_type(r),
        "is_open": bool(r.get("is_open")),
        "uid": r.get("uid"),
        "title": r.get("title"),
        "company": r.get("company"),
        "location": r.get("location"),
        "source_url": r.get("source_url"),
        "apply_url": r.get("apply_url"),
        "last_changed": r.get("last_changed"),
    } for r in rows]
    return {"count": len(data), "cursor": cursor,
            "has_more": len(data) == limit, "data": data}


@app.get("/jobs/in/{country}", response_class=HTMLResponse)
def seo_country(country: str):
    code, name = _resolve_country_code(country)
    if not code:
        raise StarletteHTTPException(status_code=404, detail="unknown country")
    f = {"country": code, "open_only": True}
    with storage.session(DB_PATH) as conn:
        total = storage.count(conn, **f)
        jobs = storage.search(conn, limit=100, offset=0, **f)
    if total == 0:
        raise StarletteHTTPException(status_code=404, detail="no jobs for this country")
    return _seo_page(f"Jobs in {name} — Jobmesh", f"Jobs in {name}",
                     f"Open jobs in {name}, indexed from company career pages and job boards.",
                     f"/jobs/in/{code.lower()}", jobs, total)


@app.get("/jobs/in/{country}/{city}", response_class=HTMLResponse)
def seo_country_city(country: str, city: str):
    code, name = _resolve_country_code(country)
    if not code:
        raise StarletteHTTPException(status_code=404, detail="unknown country")
    city_name = city.replace("-", " ").strip()
    f = {"country": code, "location": city_name, "open_only": True}
    with storage.session(DB_PATH) as conn:
        total = storage.count(conn, **f)
        jobs = storage.search(conn, limit=100, offset=0, **f)
    if total == 0:
        raise StarletteHTTPException(status_code=404, detail="no jobs for this city")
    disp = city_name.title()
    return _seo_page(f"Jobs in {disp}, {name} — Jobmesh", f"Jobs in {disp}, {name}",
                     f"Open jobs in {disp}, {name}.",
                     f"/jobs/in/{code.lower()}/{city}", jobs, total)


@app.get("/jobs/role/{role}", response_class=HTMLResponse)
def seo_role(role: str):
    kw = role.replace("-", " ").strip()
    if not kw:
        raise StarletteHTTPException(status_code=404, detail="unknown role")
    f = {"keyword": kw, "open_only": True}
    with storage.session(DB_PATH) as conn:
        total = storage.count(conn, **f)
        jobs = storage.search(conn, limit=100, offset=0, **f)
    if total == 0:
        raise StarletteHTTPException(status_code=404, detail="no jobs for this role")
    disp = kw.title()
    return _seo_page(f"{disp} jobs — Jobmesh", f"{disp} jobs",
                     f"Open {disp} roles indexed from across the web.",
                     f"/jobs/role/{role}", jobs, total)


@app.get("/jobs/type/{contract}", response_class=HTMLResponse)
def seo_type(contract: str):
    with storage.session(DB_PATH) as conn:
        et = _resolve_employment_type(conn, contract)
        if not et:
            raise StarletteHTTPException(status_code=404, detail="unknown contract type")
        f = {"employment_type": et, "open_only": True}
        total = storage.count(conn, **f)
        jobs = storage.search(conn, limit=100, offset=0, **f)
    if total == 0:
        raise StarletteHTTPException(status_code=404, detail="no jobs for this type")
    disp = contract.replace("-", " ").title()
    return _seo_page(f"{disp} jobs — Jobmesh", f"{disp} jobs",
                     f"Open {disp} positions from company career pages and job boards.",
                     f"/jobs/type/{contract}", jobs, total)


# Mapping: CSV column -> job row field
_CSV_COLS = [
    ("title", "title"), ("company", "company"), ("location", "location"),
    ("platform", "source_platform"), ("category", "category"),
    ("employment_type", "employment_type"), ("workplace_type", "workplace_type"),
    ("remote", "remote"), ("level", "level"), ("posted_at", "posted_at"),
    ("source_url", "source_url"), ("apply_url", "apply_url"),
]


@app.get("/export.csv")
def export_csv(
    keyword: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    workplace_type: Optional[str] = Query(None),
    employment_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    api_key: Optional[str] = Query(None, description="Jobmesh Premium API key"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Filtered search as CSV.

    Without a key: a free sample of the most recent SAMPLE_CAP rows (same
    filters as /jobs), flagged with an X-Jobmesh-Sample header. With a valid
    Jobmesh Premium key: the full filtered set.
    """
    is_pro = _pro_payload(api_key, x_api_key) is not None
    cap = None if is_pro else SAMPLE_CAP
    f = _filters(keyword, company, location, platform, workplace_type,
                 employment_type, category, country, level, since)
    header = [c for c, _ in _CSV_COLS]

    def rows_iter():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header)
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        with storage.session(DB_PATH) as conn:
            off, page = 0, 500
            while cap is None or off < cap:
                page_size = page if cap is None else min(page, cap - off)
                batch = storage.search(conn, limit=page_size, offset=off, **f)
                if not batch:
                    break
                for r in batch:
                    w.writerow([r.get(src) for _, src in _CSV_COLS])
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)
                if len(batch) < page_size:
                    break
                off += len(batch)

    headers = {"Content-Disposition": 'attachment; filename="jobmesh.csv"'}
    if not is_pro:
        headers["X-Jobmesh-Sample"] = "true"
        headers["X-Jobmesh-Note"] = SAMPLE_NOTE_ASCII
    return StreamingResponse(rows_iter(), media_type="text/csv", headers=headers)


@app.get("/export.json")
def export_json(
    keyword: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="alias for keyword"),
    company: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    workplace_type: Optional[str] = Query(None),
    employment_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=EXPORT_CAP),
    offset: int = Query(0, ge=0),
    api_key: Optional[str] = Query(None, description="Jobmesh Premium API key"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Filtered index as JSON (agency feed).

    Without a key: a free sample of the most recent SAMPLE_CAP rows (same
    filters as /jobs), with sample/note fields. With a valid Jobmesh Premium
    key: the full feed, paginated with offset/limit (up to EXPORT_CAP per page).
    """
    is_pro = _pro_payload(api_key, x_api_key) is not None
    f = _filters(keyword or q, company, location, platform, workplace_type,
                 employment_type, category, country, level, since)
    if not is_pro:
        # free sample: the most recent SAMPLE_CAP rows, same filters as /jobs
        limit = min(limit, SAMPLE_CAP)
        offset = 0
    with storage.session(DB_PATH) as conn:
        rows = storage.search(conn, limit=limit, offset=offset, **f)
        total = storage.count(conn, **f)
    results = [{name: r.get(src) for name, src in _CSV_COLS} for r in rows]
    payload = {"count": len(results), "total": total,
               "limit": limit, "offset": offset, "pro": is_pro, "results": results}
    if not is_pro:
        payload["sample"] = True
        payload["sample_limit"] = SAMPLE_CAP
        payload["note"] = SAMPLE_NOTE
    return payload


EXPORT_DIR = os.getenv("JOBMESH_EXPORT_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(DB_PATH)) or ".", "export")


def _serve_gz(name: str, media: str, api_key, x_api_key):
    from fastapi.responses import FileResponse
    if _pro_payload(api_key, x_api_key) is None:
        return JSONResponse(
            {"error": "Jobmesh Premium required: the bulk .gz export is for subscribers.",
             "upgrade": "/#pro"}, status_code=402)
    path = os.path.join(EXPORT_DIR, name)
    if not os.path.exists(path):
        return JSONResponse(
            {"error": "export not generated yet; it is built after the next ingest cycle"},
            status_code=503)
    return FileResponse(path, media_type=media, filename=name)


@app.get("/export/jobs.ndjson.gz")
def export_ndjson_gz(
    api_key: Optional[str] = Query(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Premium: the full open index as gzipped NDJSON (one JSON per line),
    regenerated after each ingest cycle."""
    return _serve_gz("jobs.ndjson.gz", "application/gzip", api_key, x_api_key)


@app.get("/export/jobs.csv.gz")
def export_csv_gz(
    api_key: Optional[str] = Query(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Premium: the full open index as gzipped CSV, regenerated after each
    ingest cycle."""
    return _serve_gz("jobs.csv.gz", "application/gzip", api_key, x_api_key)


@app.get("/feedback")
def get_feedback(limit: int = Query(30, ge=1, le=100)) -> dict:
    """Most recent visitor feedback."""
    with storage.session(DB_PATH) as conn:
        return {"results": storage.list_feedback(conn, limit=limit)}


@app.post("/feedback")
def post_feedback(body: FeedbackIn) -> dict:
    """Store one visitor feedback entry."""
    with storage.session(DB_PATH) as conn:
        entry = storage.add_feedback(conn, body.message, body.name, body.lang)
    return {"ok": True, "entry": entry}


@app.get("/geo")
def get_geo() -> dict:
    """Open-posting counts grouped by (best-effort) country, for the globe."""
    with storage.session(DB_PATH) as conn:
        counts = storage.location_counts(conn)
    return geo.aggregate(counts)


@app.get("/facets")
def get_facets(
    keyword: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    workplace_type: Optional[str] = Query(None),
    employment_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
) -> dict:
    """Total plus per-value counts for each filter, given the other filters."""
    f = _filters(keyword, company, location, platform, workplace_type,
                 employment_type, category, country, level, since)
    with storage.session(DB_PATH) as conn:
        return storage.facets(conn, **f)


# --- Optional background index refresh -------------------------------------
# When INGEST_INTERVAL_HOURS is set, a daemon thread re-ingests every N hours
# so the deployed index updates itself on a schedule. WAL (see storage.connect)
# makes the concurrent background write + API reads safe. Off unless the env
# var is set, so local runs and tests are unaffected.
@app.on_event("startup")
def _clear_ingesting_flag() -> None:
    """Clear a stale in-progress flag left by a previous crash."""
    try:
        with storage.session(DB_PATH) as conn:
            storage.set_meta(conn, "ingesting", "0")
    except Exception:
        pass


_UNSET = object()
INGEST_INITIAL_DELAY = float(os.getenv("INGEST_INITIAL_DELAY_SECONDS", "180"))


def _initial_refresh_wait(interval: float, last_finished_iso=_UNSET) -> float:
    """Seconds to wait before the FIRST scheduled ingest.

    Short (INGEST_INITIAL_DELAY, ~3 min so the booted server answers first) when
    the index was never built or is older than one interval; otherwise the time
    left until the current interval elapses. Read from the persisted
    last_ingest_finished so a redeploy does not reset the clock and leave the
    index never refreshed.
    """
    import time as _t
    from datetime import datetime, timezone
    raw = last_finished_iso
    if raw is _UNSET:
        try:
            with storage.session(DB_PATH) as conn:
                raw = storage.get_meta(conn, "last_ingest_finished")
        except Exception:
            raw = None
    if not raw:
        return INGEST_INITIAL_DELAY
    try:
        last = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
    except Exception:
        return INGEST_INITIAL_DELAY
    elapsed = _t.time() - last
    if elapsed >= interval:
        return INGEST_INITIAL_DELAY
    return max(INGEST_INITIAL_DELAY, interval - elapsed)


@app.on_event("startup")
def _maybe_start_refresher() -> None:
    import logging
    import threading
    import time

    raw = os.getenv("INGEST_INTERVAL_HOURS")
    if not raw:
        return
    try:
        interval = float(raw) * 3600.0
    except ValueError:
        return
    if interval <= 0:
        return

    log = logging.getLogger("jobmesh.refresher")

    def _loop() -> None:
        from .config import load_boards
        from .pipeline import ingest as _ingest
        from .locks import ingest_lock

        # Heavy migration runs here, off the startup path: the server is already
        # answering /health and serving LIKE search. Search switches to the FTS
        # index as soon as this returns.
        try:
            took = storage.run_heavy_migration(DB_PATH)
            if took:
                log.info("index ready (heavy migration %.1fs)", took)
        except Exception as exc:
            log.warning("heavy migration failed: %s", exc)

        cap = os.getenv("INGEST_MAX_BOARDS")
        # First ingest soon after boot when the index is missing or stale,
        # otherwise wait out the rest of the interval. Computed from the
        # persisted last_ingest_finished, so a redeploy no longer resets the
        # clock and skips the ingest forever.
        first_wait = _initial_refresh_wait(interval)
        log.info("first scheduled index refresh in ~%d s", int(first_wait))
        time.sleep(first_wait)
        while True:
            try:
                with ingest_lock() as acquired:
                    if acquired:
                        boards = load_boards()
                        if cap:
                            n = int(cap)
                            boards = {p: bl[:n] for p, bl in boards.items()}
                        started = time.time()
                        with storage.session(DB_PATH) as conn:
                            from .rotation import apply_rotation
                            import json as _json
                            idx = int(storage.get_meta(conn, "rotation_index", "0") or "0")
                            run_boards, rot_info = apply_rotation(boards, idx)
                            storage.set_meta(conn, "rotation_index", str(idx + 1))
                            storage.set_meta(conn, "rotation_info", _json.dumps(rot_info))
                            results = _ingest(conn, run_boards)
                            storage.record_ingest_run(
                                conn, results, started, time.time())
                            # Refresh query-planner stats and the headline-stats
                            # cache so /stats and search stay fast after a cycle.
                            try:
                                conn.execute("PRAGMA optimize")
                            except Exception:
                                pass
                            storage.refresh_stats_cache(conn)
                        try:
                            from .exportfiles import write_gz_exports, write_sitemaps
                            write_gz_exports(DB_PATH, EXPORT_DIR, _CSV_COLS)
                            base_url = os.getenv("BASE_URL", "https://jobmesh.world")
                            write_sitemaps(DB_PATH, EXPORT_DIR, base_url)
                            log.info("gz exports + sitemaps regenerated")
                        except Exception as gz_exc:
                            log.warning("gz export generation failed: %s", gz_exc)
                        log.info("scheduled index refresh complete")
                    else:
                        log.info("skipping refresh: another ingest is running")
            except Exception as exc:  # pragma: no cover - best effort
                log.warning("scheduled index refresh failed: %s", exc)
            time.sleep(interval)

    threading.Thread(target=_loop, name="jobmesh-refresher", daemon=True).start()
    log.info("background index refresh enabled: every %s h", raw)
