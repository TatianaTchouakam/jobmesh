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
        "Disallow: /export.csv\n"
        "Disallow: /export.json\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml() -> Response:
    base = os.getenv("BASE_URL", "https://jobmesh.world").rstrip("/")
    paths = ["/", "/status", "/api"]
    items = "".join(f"<url><loc>{base}{pth}</loc></url>" for pth in paths)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           f"{items}</urlset>")
    return Response(xml, media_type="application/xml")


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
    return JSONResponse({"error": exc.detail or "error", "status": exc.status_code},
                        status_code=exc.status_code)


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return HTMLResponse(_error_page(500, "Something went wrong"), status_code=500)
    return JSONResponse({"error": "internal server error", "status": 500}, status_code=500)


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
    rows = srcreg.health(obp, data)
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
             employment_type, category, country=None, level=None, since=None) -> dict:
    return {
        "keyword": keyword, "company": company, "location": location,
        "platform": platform, "workplace_type": workplace_type,
        "employment_type": employment_type, "category": category,
        "country": country, "level": level, "since": since,
    }


FREE_LIMIT = 50          # max results per request without a Pro key
PRO_LIMIT = 1000         # max results per request with a Pro key
EXPORT_CAP = 5000        # max rows a single CSV export returns


def _pro_payload(api_key, x_api_key):
    """Return the signed-key payload if a valid Pro key is supplied, else None."""
    return pro.verify_key(api_key or x_api_key)


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
                 employment_type, category, country, level, since)
    with storage.session(DB_PATH) as conn:
        rows = storage.search(conn, limit=limit, offset=offset, **f)
        total = storage.count(conn, **f)
    return {
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "pro": is_pro,
        "free_limit": FREE_LIMIT,
        "results": rows,
    }


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
    """Pro-only: download the filtered search as CSV."""
    if _pro_payload(api_key, x_api_key) is None:
        return JSONResponse(
            {"error": "Reserve a Jobmesh Premium: l'export CSV est reserve aux abonnes.",
             "upgrade": "/#pro"},
            status_code=402)
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
            while off < EXPORT_CAP:
                batch = storage.search(conn, limit=min(page, EXPORT_CAP - off),
                                       offset=off, **f)
                if not batch:
                    break
                for r in batch:
                    w.writerow([r.get(src) for _, src in _CSV_COLS])
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)
                if len(batch) < page:
                    break
                off += len(batch)

    return StreamingResponse(
        rows_iter(), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="jobmesh.csv"'})


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
    """Pro-only agency feed: the filtered index as JSON, paginated.

    Same filters as /jobs; walk the whole result set with offset/limit (up to
    EXPORT_CAP rows per page). Each row carries the same fields as /export.csv.
    """
    if _pro_payload(api_key, x_api_key) is None:
        return JSONResponse(
            {"error": "Jobmesh Premium required: the JSON feed is for subscribers.",
             "upgrade": "/#pro"},
            status_code=402)
    f = _filters(keyword or q, company, location, platform, workplace_type,
                 employment_type, category, country, level, since)
    with storage.session(DB_PATH) as conn:
        rows = storage.search(conn, limit=limit, offset=offset, **f)
        total = storage.count(conn, **f)
    results = [{name: r.get(src) for name, src in _CSV_COLS} for r in rows]
    return {"count": len(results), "total": total,
            "limit": limit, "offset": offset, "results": results}


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

        cap = os.getenv("INGEST_MAX_BOARDS")
        while True:
            time.sleep(interval)   # wait first: let the web server boot and serve the on-disk index
            try:
                with ingest_lock() as acquired:
                    if not acquired:
                        log.info("skipping refresh: another ingest is running")
                        continue
                    boards = load_boards()
                    if cap:
                        n = int(cap)
                        boards = {p: bl[:n] for p, bl in boards.items()}
                    started = time.time()
                    with storage.session(DB_PATH) as conn:
                        results = _ingest(conn, boards)
                        storage.record_ingest_run(
                            conn, results, started, time.time())
                log.info("scheduled index refresh complete")
            except Exception as exc:  # pragma: no cover - best effort
                log.warning("scheduled index refresh failed: %s", exc)

    threading.Thread(target=_loop, name="jobmesh-refresher", daemon=True).start()
    log.info("background index refresh enabled: every %s h", raw)
