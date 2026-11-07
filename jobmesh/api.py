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

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import storage
from . import geo


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


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    """Serve the search page."""
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/stats")
def get_stats() -> dict:
    """Headline numbers about the current index."""
    with storage.session(DB_PATH) as conn:
        return storage.stats(conn)


def _filters(keyword, company, location, platform, workplace_type,
             employment_type, category, country=None) -> dict:
    return {
        "keyword": keyword, "company": company, "location": location,
        "platform": platform, "workplace_type": workplace_type,
        "employment_type": employment_type, "category": category,
        "country": country,
    }


@app.get("/jobs")
def list_jobs(
    keyword: Optional[str] = Query(None, description="match in title/description"),
    company: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    platform: Optional[str] = Query(None, description="filter by source platform"),
    workplace_type: Optional[str] = Query(None, description="remote / hybrid / onsite"),
    employment_type: Optional[str] = Query(None, description="e.g. Full-time, Contract"),
    category: Optional[str] = Query(None, description="broad domain, e.g. Engineering"),
    country: Optional[str] = Query(None, description="ISO-2 country, e.g. DE"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """Search the index with filters and pagination."""
    f = _filters(keyword, company, location, platform, workplace_type,
                 employment_type, category, country)
    with storage.session(DB_PATH) as conn:
        rows = storage.search(conn, limit=limit, offset=offset, **f)
        total = storage.count(conn, **f)
    return {
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": rows,
    }


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
) -> dict:
    """Total plus per-value counts for each filter, given the other filters."""
    f = _filters(keyword, company, location, platform, workplace_type,
                 employment_type, category, country)
    with storage.session(DB_PATH) as conn:
        return storage.facets(conn, **f)
