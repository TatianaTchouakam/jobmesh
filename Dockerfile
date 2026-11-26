# Jobmesh — API image (also used for the scheduled ingest service).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    JOBMESH_DB=/data/jobmesh.db

WORKDIR /app

# Install dependencies first so the layer caches across code changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p /data

EXPOSE 8000

# Serve the API. The index lives on a mounted volume at /data (JOBMESH_DB),
# so it persists across restarts and is shared with the ingest service.
CMD ["sh", "-c", "uvicorn jobmesh.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
