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

> 🚧 **Work in progress** – growing towards the goal of **78 platform types**.

### Current status

- 🌍 **~69,000 open postings** (83,000+ tracked incl. closed) across 6 continents
- 🔌 **31 platform types live** · **3,600+ duplicate postings** grouped by deduplication
- 🏛️ **2 national employment agencies live**: 🇩🇪 Bundesagentur für Arbeit · 🇸🇪 Sweden (JobTech)
- 🏢 **~2,900 companies / boards** worldwide
- ✅ **Official public APIs & feeds (REST / RSS / JSON-LD)** — no blind HTML scraping, no login-walled data
- 📋 Full per-platform status vs the 78 required sources: see **[COVERAGE.md](COVERAGE.md)**

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

Scheduling locally (hourly example):

```bash
# crontab -e
0 * * * * cd /path/to/jobmesh && .venv/bin/python -m jobmesh.cli ingest
```

## Platform coverage

| Category | Status |
|---|---|
| ATS platforms (Greenhouse, SmartRecruiters, Lever, Ashby, Workable, Workday, Oracle, …) | ✅ 16 live of the 58 required |
| Job board platforms (SmartJobBoard, …) | ✅ 1 live of the 20 required — proven on 14 boards |
| National employment agencies (🇩🇪 Bundesagentur für Arbeit, 🇸🇪 Sweden JobTech) | ✅ 2 live |
| Extra sources beyond the required 78 | ✅ 14 (arbeitnow, remote boards, …) |
| Full checklist vs the 78 required platforms | 📋 see **[COVERAGE.md](COVERAGE.md)** |

Most sources are official public **APIs or feeds** (REST / RSS); a few read the
schema.org **JobPosting JSON-LD** that sites publish for Google for Jobs. No blind
HTML scraping, no login-walled data. Growth is additive: a new platform is a new
`Connector` subclass plus one line in the registry.

## Running with Docker (🚧 in progress)

The API and the ingestion job are being containerised for reproducible local
runs and deployment:

```bash
# build the image
docker build -t jobmesh .

# serve the API on http://127.0.0.1:8000/docs
docker run -p 8000:8000 -v $(pwd)/data:/app/data jobmesh

# run one ingestion with the same image
docker run -v $(pwd)/data:/app/data jobmesh python -m jobmesh.cli ingest
```

Planned setup:

- slim Python base image, non-root user, small image size
- the SQLite database stored on a mounted volume, so data survives restarts
- `docker-compose.yml` with two services: `api` (FastAPI) and `ingest` (scheduled refresh)
- image built and tested automatically in CI (GitHub Actions)

## Tests

```bash
python -m pytest -q
```

40+ offline tests cover normalization, the storage logic (change detection,
closing absent postings, and that a failed fetch never closes listings), and
connector field-mapping (Comeet, careersite, jobfeed, SmartJobBoard, …) — all
offline, no network required.

## Roadmap

- [ ] **Docker**: Dockerfile and docker-compose (API + ingest)
- [ ] CI with GitHub Actions: tests and Docker build on every push
- [ ] Run the ingestion as a scheduled container job
- [ ] More connectors toward the **78 required platform types** (status in COVERAGE.md)
- [ ] More national employment agencies
