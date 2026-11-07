"""Tests for the MCP (/mcp) JSON-RPC endpoint."""

from __future__ import annotations

import os
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jobmesh import storage
from jobmesh.models import Job
from jobmesh.mcp_server import register_mcp


def _client_with_data():
    db = tempfile.mktemp(suffix=".db")
    with storage.session(db) as c:
        storage.upsert_jobs(c, [
            Job("greenhouse", "acme", "1", "Senior Data Engineer", "Acme", "Berlin"),
            Job("lever", "beta", "2", "Junior Data Analyst", "Beta", "Lagos"),
        ])
    app = FastAPI()
    register_mcp(app, db)
    return TestClient(app), db


def test_mcp_initialize_and_tools_list():
    client, db = _client_with_data()
    try:
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1,
                                      "method": "initialize", "params": {}})
        assert r.status_code == 200
        assert r.json()["result"]["serverInfo"]["name"] == "jobmesh"

        r2 = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in r2.json()["result"]["tools"]}
        assert {"search_jobs", "index_stats"} <= names
    finally:
        os.remove(db)


def test_mcp_search_respects_filters():
    client, db = _client_with_data()
    try:
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                      "params": {"name": "search_jobs",
                                                 "arguments": {"query": "data"}}})
        text = r.json()["result"]["content"][0]["text"]
        assert "Data Engineer" in text and "Data Analyst" in text

        r2 = client.post("/mcp", json={"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                       "params": {"name": "search_jobs",
                                                  "arguments": {"level": "Junior / Entry"}}})
        t2 = r2.json()["result"]["content"][0]["text"]
        assert "Data Analyst" in t2 and "Senior Data Engineer" not in t2
    finally:
        os.remove(db)


def test_mcp_stats_and_unknown_tool():
    client, db = _client_with_data()
    try:
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                                      "params": {"name": "index_stats", "arguments": {}}})
        assert "open postings" in r.json()["result"]["content"][0]["text"]

        r2 = client.post("/mcp", json={"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                                       "params": {"name": "nope", "arguments": {}}})
        assert "error" in r2.json()
    finally:
        os.remove(db)


def test_mcp_notification_and_get():
    client, db = _client_with_data()
    try:
        # A notification (no id) is acknowledged with 202 and no body.
        r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert r.status_code == 202
        # GET is not an SSE stream here.
        assert client.get("/mcp").status_code == 405
    finally:
        os.remove(db)
