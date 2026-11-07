"""Minimal, dependency-free MCP (Model Context Protocol) endpoint.

Exposes Jobmesh search to AI agents over the Streamable-HTTP transport as
plain JSON-RPC 2.0 at `POST /mcp`. An AI client (Claude, an agent, …) that
supports remote MCP can be pointed at `https://<your-site>/mcp` and then
search the live index directly — no account, no scraping, same public data
the website already serves.

Design goals:
  * **No new dependencies** — hand-rolled JSON-RPC over FastAPI.
  * **Cannot break the main site** — it only *adds* two routes, and api.py
    wraps the registration in try/except.

Tools:
  * search_jobs  — search by role/skill, location, country, level, category…
  * index_stats  — headline numbers about the index
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from . import storage

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "jobmesh", "version": "0.1.0"}

TOOLS = [
    {
        "name": "search_jobs",
        "description": (
            "Search the Jobmesh index of open job postings, aggregated from "
            "many public ATS and job boards worldwide. Filter by role/skill "
            "keyword, free-text location, ISO-2 country code, seniority level, "
            "category, or remote-only. Returns matching openings, each with a "
            "link back to its original source."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Role or skill, matched in title/description, e.g. 'data engineer', 'nurse', 'python'."},
                "location": {"type": "string", "description": "Free-text location filter, e.g. 'Berlin'."},
                "country": {"type": "string", "description": "ISO-2 country code, e.g. 'DE', 'NG', 'US'."},
                "level": {"type": "string", "description": "Seniority: Internship, Apprenticeship, Working Student, Junior / Entry, Senior, Lead / Principal, Manager."},
                "category": {"type": "string", "description": "Broad domain, e.g. 'Healthcare', 'Engineering', 'Logistics & Supply Chain'."},
                "remote": {"type": "boolean", "description": "Only remote roles when true."},
                "limit": {"type": "integer", "description": "Max results (1-50, default 15)."},
            },
        },
    },
    {
        "name": "index_stats",
        "description": "Headline numbers about the Jobmesh index: open postings, companies and source platforms.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# -- tool implementations --------------------------------------------------

def _run_search(args: dict, db_path: str) -> str:
    try:
        limit = max(1, min(int(args.get("limit") or 15), 50))
    except (TypeError, ValueError):
        limit = 15
    filters = {
        "keyword": args.get("query") or None,
        "location": args.get("location") or None,
        "country": args.get("country") or None,
        "level": args.get("level") or None,
        "category": args.get("category") or None,
    }
    if args.get("remote"):
        filters["workplace_type"] = "remote"
    with storage.session(db_path) as conn:
        rows = storage.search(conn, limit=limit, **filters)
        total = storage.count(conn, **filters)
    if not rows:
        return f"No open roles matched those filters (0 of {total})."
    out = [f"{total} open roles match — showing {len(rows)}:\n"]
    for r in rows:
        head = r.get("title") or "(untitled)"
        if r.get("company"):
            head += f" @ {r['company']}"
        meta = [x for x in (r.get("location"), r.get("level"),
                            "remote" if r.get("remote") else None) if x]
        if meta:
            head += " — " + ", ".join(meta)
        url = r.get("apply_url") or r.get("source_url")
        out.append(head + (f"\n  {url}" if url else ""))
    return "\n".join(out)


def _run_stats(db_path: str) -> str:
    with storage.session(db_path) as conn:
        s = storage.stats(conn)
    return (
        f"Jobmesh index — {s.get('open_postings', 0):,} open postings, "
        f"{s.get('companies', 0):,} companies, "
        f"{s.get('platforms', 0)} source platforms."
    )


# -- JSON-RPC dispatch -----------------------------------------------------

def _ok(mid: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _handle(msg: dict, db_path: str) -> Optional[dict]:
    """Return a JSON-RPC response for one request, or None for notifications."""
    mid = msg.get("id")
    method = msg.get("method")

    if method == "initialize":
        return _ok(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "search_jobs":
                text = _run_search(args, db_path)
            elif name == "index_stats":
                text = _run_stats(db_path)
            else:
                return _err(mid, -32602, f"Unknown tool: {name}")
        except Exception as exc:  # never 500 inside a tool
            return _ok(mid, {"content": [{"type": "text", "text": f"Error: {exc}"}],
                             "isError": True})
        return _ok(mid, {"content": [{"type": "text", "text": text}]})

    # Any notification (no id) we don't handle is simply acknowledged.
    if mid is None:
        return None
    return _err(mid, -32601, f"Method not found: {method}")


def register_mcp(app, db_path: str) -> None:
    """Add the /mcp routes to a FastAPI app."""

    @app.post("/mcp", include_in_schema=False)
    async def mcp_post(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse(_err(None, -32700, "Parse error"), status_code=400)

        if isinstance(payload, list):
            body: Any = [r for r in (_handle(m, db_path) for m in payload) if r is not None]
            if not body:
                return Response(status_code=202)
        else:
            resp = _handle(payload, db_path)
            if resp is None:
                return Response(status_code=202)
            body = resp

        # Content negotiation: some MCP clients ask for an SSE-framed reply.
        if "text/event-stream" in request.headers.get("accept", ""):
            data = "event: message\ndata: " + json.dumps(body) + "\n\n"
            return Response(content=data, media_type="text/event-stream",
                            headers={"Cache-Control": "no-cache"})
        return JSONResponse(body)

    @app.get("/mcp", include_in_schema=False)
    async def mcp_get():
        # We don't offer a server-initiated SSE stream; POST JSON-RPC instead.
        return JSONResponse(_err(None, -32601, "Use POST JSON-RPC"), status_code=405)
