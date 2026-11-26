"""Workday rotation: deterministic shards, full coverage, honest reporting."""
import json

import pytest

from jobmesh import storage
from jobmesh.rotation import apply_rotation, shard_of, shards_for


def test_workday_rotates_by_default():
    assert shards_for("workday") == 3
    assert shards_for("greenhouse") == 1


def test_env_override(monkeypatch):
    monkeypatch.setenv("WORKDAY_ROTATION_SHARDS", "1")
    assert shards_for("workday") == 1
    monkeypatch.setenv("WORKDAY_ROTATION_SHARDS", "4")
    assert shards_for("workday") == 4


def test_shard_is_stable_and_in_range():
    for tok in ("acme:wd5:X", "beta:wd1:Y", "gamma:wd3:Z"):
        a = shard_of(tok, 3)
        assert 0 <= a < 3
        assert shard_of(tok, 3) == a  # deterministic


def test_rotation_covers_everything_once_per_n_cycles():
    boards = {"workday": [f"co{i}:wd{i%4}:site" for i in range(300)],
              "greenhouse": ["acme", "beta"]}
    seen = set()
    sizes = []
    for cycle in range(3):
        run, info = apply_rotation(boards, cycle)
        # non-rotated platform passes through untouched every cycle
        assert run["greenhouse"] == ["acme", "beta"]
        assert info["workday"]["shards"] == 3
        assert info["workday"]["current"] == cycle % 3
        sizes.append(len(run["workday"]))
        seen |= set(run["workday"])
    assert seen == set(boards["workday"])     # every board fetched once per 3 cycles
    assert sum(sizes) == len(boards["workday"])  # no board in two shards
    # cycle 3 wraps back to shard 0
    run0, _ = apply_rotation(boards, 0)
    run3, _ = apply_rotation(boards, 3)
    assert set(run0["workday"]) == set(run3["workday"])


def test_stats_exposes_rotation(tmp_path):
    db = str(tmp_path / "r.db")
    with storage.session(db) as conn:
        assert storage.stats(conn)["rotation"] is None
        storage.set_meta(conn, "rotation_info",
                         json.dumps({"workday": {"shards": 3, "current": 1,
                                                 "total_boards": 2249,
                                                 "this_cycle": 774}}))
        rot = storage.stats(conn)["rotation"]
        assert rot and rot["workday"]["shards"] == 3
