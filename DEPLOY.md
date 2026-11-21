# Deploying Jobmesh on Render

Jobmesh is a FastAPI app that serves a SQLite index. On Render the index is
rebuilt by the **build step** on every deploy, so no persistent disk is
needed — each deploy produces a fresh index that the API serves. This is
declared in `render.yaml` (a Render Blueprint).

Live demo: **https://jobmesh.world**

## 1. Service (Blueprint)
Render Dashboard → **New → Blueprint** → pick the `jobmesh` repo. Render reads
`render.yaml` and creates the web service `jobmesh`:
- **Build**: `pip install -r requirements.txt && python -m jobmesh.cli ingest || true`
  (installs deps, then builds the index from every connector).
- **Start**: `uvicorn jobmesh.api:app --host 0.0.0.0 --port $PORT`.

## 2. Instance type
Service → **Compute** → **Starter ($7/mo, 0.5 CPU / 512 MB)** keeps the service
always on (no cold-start spin-down). The **Free** instance also works but sleeps
after ~15 min of inactivity (first request then waits ~50 s).

## 3. Secret env vars (dashboard → the service → Environment)
Declared `sync: false`, i.e. fill them in the dashboard:
- `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID` — Jobmesh Premium tier.
- `BASE_URL` — the service URL, e.g. `https://jobmesh.world`.
- *(optional)* `INGEST_MAX_BOARDS` — cap boards/platform to keep builds fast.
- *(optional)* `JOOBLE_API_KEY`, `REED_API_KEY`, `USAJOBS_API_KEY`,
  `USAJOBS_EMAIL`, `RELIEFWEB_APPNAME` — enable those keyed sources.

`SECRET_KEY` is generated once by Render automatically.

## 4. Refreshing the index
The index is rebuilt on every deploy. To refresh it on demand, trigger a deploy
(push to `main`, or **Manual Deploy → Deploy latest commit**). You can also run
`python -m jobmesh.cli ingest` from the service **Shell** to refresh in place.

## 5. Verify
- `https://jobmesh.world/` — the search page (interactive globe).
- `https://jobmesh.world/docs` — interactive API docs.
- `https://jobmesh.world/stats` — live index snapshot (JSON).
- `https://jobmesh.world/coverage` — platform coverage.

## Notes
- The DB path is controlled by `JOBMESH_DB` (defaults to `jobmesh.db`); unset on
  Render, so it uses the build-time index in the service's working directory.
- Want the index to persist across deploys instead of rebuilding? Add a Render
  **persistent disk** at `/var/data`, set `JOBMESH_DB=/var/data/jobmesh.db`,
  change the build step to `pip install -r requirements.txt` only, and populate
  once from the **Shell** with `python -m jobmesh.cli ingest`. Not required for
  the demo.
