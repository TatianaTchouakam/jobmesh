"""Deferred heavy migration keeps startup fast.

On the deployed server the heavy migration (country backfill + FTS rebuild)
runs in the background so the server answers immediately; keyword search falls
back to LIKE until the FTS index is ready, then switches to it.
"""
from jobmesh import storage


def _seed(db):
    with storage.session(db) as conn:
        conn.executemany(
            "INSERT INTO jobs(uid,source_platform,source_board,source_job_id,"
            "title,company,location,first_seen,last_checked,last_changed,"
            "country,is_open) VALUES (?,?,?,?,?,?,?,?,?,?,?,1)",
            [(f"u{i}", "gh", "b", str(i), "Data Engineer", f"Co{i}",
              "Berlin, Germany", "2026-11-20", "2026-11-20", "2026-11-20", "DE")
             for i in range(40)])
        conn.commit()


def test_deferred_migration_serves_then_upgrades(tmp_path, monkeypatch):
    db = str(tmp_path / "defer.db")
    _seed(db)                                   # synchronous heavy on first connect
    # Simulate a deploy: forget what this process migrated and turn on deferral.
    storage._MIGRATED.discard(db)
    storage._HEAVY_DONE.discard(db)
    monkeypatch.setattr(storage, "DEFER_HEAVY_MIGRATION", True)

    # Before the background migration runs, search still answers (via LIKE).
    assert not storage._fts_available()
    rows = storage.search(storage.connect(db), limit=10, keyword="data")
    assert rows, "search must work (LIKE) before the FTS index is ready"

    # Running the heavy migration flips it to the FTS path.
    took = storage.run_heavy_migration(db)
    assert took >= 0.0 and storage._fts_available()
    rows2 = storage.search(storage.connect(db), limit=10, keyword="data", country="DE")
    assert rows2
