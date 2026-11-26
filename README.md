# jobmesh

**A unified, continuously updated index of job postings.**

Jobs are scattered across company career pages, applicant tracking systems
(ATS), and independent job boards. The same opening often appears on several
sites, in different formats, and listings go stale — links break and closed
roles linger in search results.

`jobmesh` pulls listings from many source platforms into **one consistent,
searchable, de-duplicated dataset**, keeps it fresh on a schedule, and serves
it through a documented API. Each job links back to its original posting.

**Live demo:** [jobmesh.world](https://jobmesh.world)

**Live status & coverage:** [jobmesh.world/status](https://jobmesh.world/status) — real-time index numbers, last-refresh time, and the full X / 78 platform checklist with the reason any platform is not yet live.

**MCP server (for AI agents):** listed on the official [MCP Registry](https://registry.modelcontextprotocol.io) as `io.github.TatianaTchouakam/jobmesh`. Any MCP client can connect to `https://jobmesh.world/mcp` and call `search_jobs`, `index_stats` and `source_coverage`.

> 🚧 **Work in progress** – growing towards the goal of **78 platform types**.

### Current status

- 🌍 **~193,000 open postings** (270,000+ tracked incl. closed) across 6 continents
- 🔌 **67 of the 78 required platforms live** · **18,000+ duplicate postings** grouped by deduplication
- 🏛️ **2 national employment agencies live**: 🇩🇪 Bundesagentur für Arbeit · 🇸🇪 Sweden (JobTech)
- 🏢 **~28,700 companies · ~6,700 boards** worldwide
- ✅ **Official public APIs & feeds (REST / RSS / JSON-LD)** — no blind HTML scraping, no login-walled data
- 📋 Full per-platform status vs the 78 required sources: see **[COVERAGE.md](COVERAGE.md)**
- 📦 Running, operating costs & dependencies: see **[HANDOFF.md](HANDOFF.md)**


### Jobmesh at a glance

Numbers are measured live; see [/status](https://jobmesh.world/status) for the
current figures.

| | Jobmesh |
|---|---|
| Open postings | ~121k (live, growing) · see [/status](https://jobmesh.world/status) |
| Platforms | 67 / 78 live, each with the exact reason if not |
| Refresh | every 4 h, shown per state |
| Search API | ✅ documented at [/api](https://jobmesh.world/api) |
| MCP server | ✅ official MCP Registry |
| CSV **and** JSON feed | ✅ `/export.csv` + `/export.json` |
| Deduplicated | ✅ |
| Languages | EN / DE / FR |
| Open source | ✅ MIT |

Every role links back to its original posting; only public APIs and feeds are
used, robots.txt is honoured, and a failed fetch is never counted as closed jobs.

### Features

- Search bar with filters (keyword, location, remote, **posting date**)
- **CV matching**: rank jobs against your CV
- **AI endpoint (MCP)** so AI assistants can query the index
- Interactive globe, **trilingual** interface (EN / DE / FR)
- Mobile-friendly pagination

---

## Why it's built this way

The design goal is simple: **adding a new platform should mean writing one
small file, and nothing else.** Everything downstream — storage, change
detection, deduplication, search, API — works on a single normalized `Job`
model, so it never needs to know which platform a job came from.

```
            config/companies.yaml          (~2,900 companies/boards, 31 platform types)
                      │
          ┌───────────▼────────────┐
          │       connectors        │   one per platform
          │ ATS · job boards · feeds│   each returns Job objects
          │ 2 national agencies     │
          └───────────┬────────────┘
                      │  normalize (HTML→text, remote flag, dedup key)
          ┌───────────▼────────────┐
          │        pipeline         │   fetch → upsert → close absent
          └───────────┬────────────┘
                      │
          ┌───────────▼────────────┐
          │     storage (SQLite)    │   first_seen · last_checked ·
          │                         │   change detection · fetch log
          └───────────┬────────────┘
                      │
            ┌─────────┴─────────┐
            │ CLI          API  │   search / stats  ·  FastAPI + /docs
            └───────────────────┘
```

## Project layout

```
jobmesh/
├── jobmesh/
│   ├── models.py            # the Job schema shared by everything
│   ├── normalize.py         # HTML→text, remote detection, dedup key
│   ├── connectors/
│   │   ├── base.py          # the Connector contract
│   │   └── ...              # one small file per platform (35+ and growing)
│   ├── storage.py           # SQLite: upsert, change detection, closing
│   ├── pipeline.py          # fetch → normalize → store, per board
│   ├── config.py            # reads config/companies.yaml
│   ├── cli.py               # ingest / search / stats
│   └── api.py               # FastAPI service with auto docs
├── config/companies.yaml    # the boards to index
├── tests/                   # offline unit tests
├── Dockerfile               # container image (planned)
├── docker-compose.yml       # API + scheduled ingest (planned)
└── requirements.txt
```

## Quick start

```bash
# 1. Set up an isolated environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Build the index from the boards in config/companies.yaml
python -m jobmesh.cli ingest

# 3. Search it
python -m jobmesh.cli search "data engineer" --location remote
python -m jobmesh.cli stats

# 4. Or serve the API (interactive docs at http://127.0.0.1:8000/docs)
uvicorn jobmesh.api:app --reload
```

Example API call:

```bash
curl "http://127.0.0.1:8000/jobs?keyword=python&location=remote&limit=5"
```

## What each job record contains

| Field | Notes |
|---|---|
| `title`, `company`, `location`, `description` | core fields, always populated when the source provides them |
| `source_url`, `apply_url` | link back to the original posting / application page |
| `salary`, `employment_type`, `remote`, `posted_at` | preserved when the source exposes them |
| `first_seen`, `last_checked` | when the posting was first indexed and last confirmed live |
| `is_open` | set to `false` automatically when a posting disappears from a successful fetch |
| `dedup_key` | groups the same opening seen across multiple sources |

## Keeping the index current

`jobmesh ingest` is designed to run repeatedly (e.g. a scheduled job):

- **New** postings are inserted; **changed** postings are updated and
  stamped; **unchanged** ones only have `last_checked` refreshed.
- A posting that is no longer returned by a **successful** fetch is marked
  closed — not deleted, so history is kept.
- A **failed** fetch (timeout, network error) is recorded in a fetch log and
  **never** closes that board's listings. A broken request is treated as a
  fetch failure, not as "every job has closed".

**Automatic refresh (deployed).** Set `INGEST_INTERVAL_HOURS` (the Render
blueprint ships `6`) and the running app re-ingests on that cadence from a
background thread — no external scheduler needed. A single-host advisory lock
means a manual `jobmesh ingest` and the scheduled refresh never run at the same
time. The home page and **[/status](https://jobmesh.world/status)** show how long
ago the index was last refreshed, the last run's duration, and any sources that
failed that run.

Scheduling locally (hourly example):

```bash
# crontab -e
0 * * * * cd /path/to/jobmesh && .venv/bin/python -m jobmesh.cli ingest
```

## Platform coverage

| Category | Status |
|---|---|
| ATS platforms (Greenhouse, SmartRecruiters, Lever, Ashby, Workable, Workday, Oracle, …) | ✅ 50 live of the 58 required |
| Job board platforms (SmartJobBoard, Niceboard, JobBoardFire, Artha, …) | ✅ 17 live of the 20 required |
| National employment agencies (🇩🇪 Bundesagentur für Arbeit, 🇸🇪 Sweden JobTech) | ✅ 2 live |
| Extra sources beyond the required 78 | ✅ 36 bonus (arbeitnow, remote boards, national feeds, …) |
| Full checklist vs the 78 required platforms | 📋 see **[COVERAGE.md](COVERAGE.md)** |

Most sources are official public **APIs or feeds** (REST / RSS); a few read the
schema.org **JobPosting JSON-LD** that sites publish for Google for Jobs. No blind
HTML scraping, no login-walled data. Growth is additive: a new platform is a new
`Connector` subclass plus one line in the registry.

## Running with Docker

Two services share one index volume: `api` (website + REST API + MCP) and
`ingest` (scheduled refresh, every 6h by default).

```bash
# build both images and start everything
docker compose up --build

# then open:
#   http://localhost:8000          the search site
#   http://localhost:8000/status   live coverage (X / 78) and freshness
#   http://localhost:8000/docs     interactive API docs
```

The SQLite index lives on a named volume (`jobmesh-data`, mounted at `/data`),
so it survives restarts and is shared between the two services. Change the
refresh cadence with `INGEST_INTERVAL_SECONDS` (default `21600` = 6h) and cap
work per run with `INGEST_MAX_BOARDS`.

To run just the API, or a one-off ingest, with the single image:

```bash
docker build -t jobmesh .
docker run -p 8000:8000 -v jobmesh-data:/data jobmesh
docker run -v jobmesh-data:/data jobmesh python -m jobmesh.cli ingest
```

## AI agents (MCP)

Jobmesh ships a built-in **MCP server** (Model Context Protocol), so AI
assistants and agents can query the live index directly — no account, no
scraping, the same public data the website serves.

- **Endpoint:** `POST https://jobmesh.world/mcp` — JSON-RPC 2.0 over
  Streamable-HTTP.
- **Tools:** `search_jobs` (role/skill, location, ISO-2 country, level,
  category, remote), `index_stats`, `source_coverage`.
- **No extra dependencies**, and registration is guarded so the MCP layer can
  never stop the main API from starting.

Check it is live:

```bash
curl -s https://jobmesh.world/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Point any MCP-capable client at the endpoint URL and it can search the index on
the user's behalf. A plain `GET /mcp` returns a short description and the tool
list.

**Listed in the official MCP Registry.** The manifest is `server.json`
(remote, Streamable-HTTP). Publish it once, as the repo owner, so MCP clients
can discover Jobmesh:

```bash
# the publisher CLI: see modelcontextprotocol.io/registry/quickstart
mcp-publisher login github     # GitHub auth → namespace io.github.<you>/jobmesh
mcp-publisher publish          # pushes server.json to registry.modelcontextprotocol.io
```

The remote server must stay publicly reachable at `https://jobmesh.world/mcp`
(it is). To tie the registry name to the domain instead of a GitHub namespace,
use DNS authentication and rename to `world.jobmesh/jobmesh`.

## Tests

```bash
python -m pytest -q
```

40+ offline tests cover normalization, the storage logic (change detection,
closing absent postings, and that a failed fetch never closes listings), and
connector field-mapping (Comeet, careersite, jobfeed, SmartJobBoard, …) — all
offline, no network required.

## Roadmap

- [x] **Docker**: Dockerfile and docker-compose (API + ingest)
- [ ] CI with GitHub Actions: tests and Docker build on every push
- [x] Run the ingestion as a scheduled container job
- [ ] More connectors toward the **78 required platform types** (status in COVERAGE.md)
- [ ] More national employment agencies
