"""HTTP API for the job index (FastAPI).

Run it with:
    uvicorn jobmesh.api:app --reload

Then open http://127.0.0.1:8000/docs for interactive, auto-generated
documentation of every endpoint, parameter and response.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Query

from . import storage

app = FastAPI(
    title="jobmesh API",
    version="0.1.0",
    description="A unified, continuously updated index of job postings.",
)

DB_PATH = storage.DEFAULT_DB


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/stats")
def get_stats() -> dict:
    """Headline numbers about the current index."""
    with storage.session(DB_PATH) as conn:
        return storage.stats(conn)


@app.get("/jobs")
def list_jobs(
    keyword: Optional[str] = Query(None, description="match in title/description"),
    company: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    open_only: bool = Query(True, description="exclude closed postings"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """Search the index with filters and pagination."""
    with storage.session(DB_PATH) as conn:
        rows = storage.search(
            conn,
            keyword=keyword,
            company=company,
            location=location,
            open_only=open_only,
            limit=limit,
            offset=offset,
        )
    return {
        "count": len(rows),
        "limit": limit,
        "offset": offset,
        "results": rows,
    }
