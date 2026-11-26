# Jobmesh — Handoff

Everything a new team needs to run, operate and extend Jobmesh.
See also: [README.md](README.md) (architecture & quickstart) and
[COVERAGE.md](COVERAGE.md) (platform coverage checklist).

## Stack

- **Backend:** Python 3.12 · FastAPI + Uvicorn · SQLite · requests · PyYAML
- **Frontend:** one static `jobmesh/web/index.html`, no build step; libraries
  are vendored locally in `jobmesh/web/vendor/` (d3, topojson-client, pdf.js +
  worker, countries-110m.json) — **no CDN, no npm**.
- **Connectors:** 45 connector modules, 35 active source platforms (config in
  `config/companies.yaml`).

## Deployment

- **Host:** Render — one **Standard web service** (2 GB RAM, always on) with a **10 GB persistent disk** at `/var/data`, auto-deploys from GitHub `main`.
- **Build:** `pip install -r requirements.txt` (the index is **not** rebuilt at build; a background thread ingests at runtime onto the disk).
- **Start:** `uvicorn jobmesh.api:app --host 0.0.0.0 --port $PORT`
- **Database:** `jobmesh.db` (SQLite) lives on the **persistent disk** (`JOBMESH_DB=/var/data/jobmesh.db`), so the index **survives redeploys**; a background thread refreshes it every `INGEST_INTERVAL_HOURS` (4) with per-chunk commits.
- **Domain:** `jobmesh.world` (registrar IONOS) → DNS pointed at Render.
- **Keep-alive:** a free **UptimeRobot** monitor pings the service every 5 min
  so the free instance does not spin down (avoids cold-start latency).

### Run it locally / take over
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m jobmesh.cli ingest        # build the index
uvicorn jobmesh.api:app --reload    # serve API + UI at http://127.0.0.1:8000
python -m pytest -q                 # 40+ offline tests
```
Keep the index fresh automatically: set `INGEST_INTERVAL_HOURS` (the Render
blueprint ships `6`) and the app re-ingests on that cadence from a background
thread, guarded by a single-host lock. `/status` and the home page show the
last refresh. A fetch failure is logged, never treated as all-jobs-closed.
(An external cron / Render Cron Job works too.)
**Add a platform** = one `Connector` subclass + one line in
`config/companies.yaml` (details in README).

## Operating costs

| Item | Plan | Cost |
|---|---|---|
| Hosting (Render web service) | Standard, 2 GB, always on | **≈ $25 / month** |
| Persistent disk (Render, 10 GB) | $0.25 / GB·month | **≈ $2.5 / month** |
| Domain `jobmesh.world` (IONOS) | Annual | **≈ €10–15 / year** |

> It also runs on the **Free** plan (512 MB): set `INGEST_WORKERS=2` and
> `INGEST_MAX_BOARDS` low so the ingest fits; the only trade-off is a smaller
> catalogue. The Standard plan is only for a bigger index and headroom.
| Data providers | Public APIs / feeds | **$0** |
| **Total** | | **≈ $0 / month + domain** |

Optional upgrade: Render **Starter ≈ $7/month** removes the free-tier
cold-start entirely (not required — UptimeRobot already mitigates it).

## External service & data dependencies

- **Runtime services:** Render (hosting), IONOS (domain/DNS), UptimeRobot
  (uptime ping). No paid third-party data provider.
- **Data sources:** each platform's **public API or RSS/XML feed**, or the
  schema.org `JobPosting` JSON-LD that sites publish for Google for Jobs. No
  login-walled data, no scraping behind authentication.
- **No key needed for the core:** the large majority of connectors
  (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, Personio,
  Workday, BambooHR, Oracle, Rippling, Teamtailor, Eightfold, Breezy, HireHive,
  Pinpoint, and the `jobfeed` engine for SmartJobBoard / WP Job Manager) use
  **public, keyless** endpoints.
- **Optional free API keys** (set as Render environment variables) that unlock
  extra bonus sources — all free tiers, none required for core coverage:

  | Env var(s) | Source |
  |---|---|
  | `JOOBLE_API_KEY` | Jooble |
  | `REED_API_KEY` | Reed (UK) |
  | `USAJOBS_EMAIL`, `USAJOBS_API_KEY` | USAJobs (US gov) |
  | `RELIEFWEB_APPNAME` | ReliefWeb |
  | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Adzuna (free tier is 25 test calls — not used in production) |
  | `FRANCETRAVAIL_CLIENT_ID`, `FRANCETRAVAIL_CLIENT_SECRET` | France Travail (not currently wired) |

- **Tunables** (env vars, optional): `SMARTJOBBOARD_MAX_JOBS`,
  `SMARTJOBBOARD_WORKERS` — caps for the SmartJobBoard sitemap crawler.

## Where things live

| Path | What |
|---|---|
| `jobmesh/connectors/` | one module per platform (+ `base.py`, `__init__.py` registry) |
| `config/companies.yaml` | the boards/companies to index, grouped by platform |
| `jobmesh/pipeline.py` · `storage.py` | fetch → normalize → upsert → close-absent, SQLite |
| `jobmesh/api.py` · `mcp_server.py` | FastAPI service + MCP endpoint |
| `jobmesh/web/` | the single-file frontend + vendored libs |
| `scripts/test_feeds.py` | validate new SmartJobBoard / WP Job Manager feeds |
| `tests/` | offline unit tests (no network) |
