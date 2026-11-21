# Deploying Jobmesh on Render

Jobmesh is a FastAPI app that serves a SQLite index. On Render we keep the
index on a **persistent disk** so it survives restarts and redeploys, and
(optionally) refresh it on a schedule from the web service itself.

Everything below is declared in `render.yaml` (a Render Blueprint); the only
manual steps are creating the service, setting a few secret env vars, and
populating the index once.

## 1. Prerequisites
- A Render account on a **paid instance type** (a persistent disk requires it).
- This repo pushed to GitHub (already connected to your Render account).
- Your secrets ready (Stripe keys, etc.) — they are set in the dashboard,
  never committed. `.env` is git-ignored.

## 2. Create the service from the Blueprint
1. Render Dashboard → **New** → **Blueprint**.
2. Pick the `jobmesh` repo. Render reads `render.yaml` and proposes a **web
   service** named `jobmesh` with a 3 GB disk at `/var/data`.
3. Apply. The first build runs `pip install -r requirements.txt` and starts
   `uvicorn jobmesh.api:app`.

`JOBMESH_DB=/var/data/jobmesh.db` and a generated `SECRET_KEY` are set
automatically from the Blueprint.

## 3. Set the secret env vars (dashboard → the service → Environment)
Set these (they are declared with `sync: false`, i.e. "fill in the dashboard"):
- `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID` — for the Jobmesh Premium tier.
- `BASE_URL` — the service URL, e.g. `https://jobmesh.onrender.com` (set it
  after the first deploy, once Render has assigned the URL).
- *(optional)* `JOOBLE_API_KEY`, `REED_API_KEY`, `USAJOBS_API_KEY`,
  `USAJOBS_EMAIL`, `RELIEFWEB_APPNAME` — only if you want those keyed sources.

## 4. Populate the index once (the disk starts empty)
The persistent disk is empty on first boot, so build the index once:
1. Dashboard → the service → **Shell**.
2. Run a full ingest (writes to `/var/data/jobmesh.db`):
   ```
   python -m jobmesh.cli ingest
   ```
   This takes a while (thousands of boards). For a quick first demo, cap it:
   ```
   INGEST_MAX_BOARDS=25 python -m jobmesh.cli ingest
   ```
   then run the full ingest later.
3. Check it: `python -m jobmesh.cli stats`.

The index now persists across restarts and redeploys.

## 5. Keep it fresh automatically (optional)
Set `INGEST_INTERVAL_HOURS` (e.g. `12`) in the dashboard. The web service then
re-ingests in a background thread on that cadence — this is the challenge's
"automatic updates on a schedule". WAL mode makes the background write safe
while the API keeps serving reads. Add `INGEST_MAX_BOARDS` to keep each run
light on a small instance.

## 6. Verify
- `https://<your-service>.onrender.com/` — the search page (interactive globe).
- `https://<your-service>.onrender.com/docs` — interactive API docs.
- `POST https://<your-service>.onrender.com/mcp` — the MCP endpoint for agents.

## Notes
- **Free tier instead of a disk?** Remove the `disk:` block and set `plan: free`;
  the index then lives on the ephemeral filesystem and is rebuilt by the build
  step (`... && python -m jobmesh.cli ingest`). Simpler, but the index resets on
  every restart. The disk (paid) is recommended for a stable demo.
- The DB path is controlled entirely by `JOBMESH_DB`; nothing else changes
  between local and deployed runs.
