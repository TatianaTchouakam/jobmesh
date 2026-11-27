"""Spread a large, rate-limited platform across several cycles.

Workday has ~2,200 boards on a few shared clusters that must be fetched
politely (one request per cluster at a time, paced). A full pass at that rate
takes about 3 h, so Workday is optionally split into N stable shards: each
cycle fetches one shard, and every board is refreshed once every N cycles.

The split is deterministic (a hash of the board token), so a board always
lands in the same shard; the shard index advances once per cycle. Enable it
per platform with ``<PLATFORM>_ROTATION_SHARDS`` (e.g. ``WORKDAY_ROTATION_SHARDS=3``);
1 (the default) means no rotation.
"""

from __future__ import annotations

import hashlib
import os


# Built-in defaults so rotation is on in production without an env change.
# The heaviest platforms run a fraction of their boards each cycle, so a full
# cycle stays well under the refresh interval; every board is still refreshed
# once every N cycles. Override per platform with <PLATFORM>_ROTATION_SHARDS
# (1 disables rotation). Chosen for the biggest / slowest platforms:
#   workday ~2,250 boards on rate-limited clusters (paced);
#   join    ~2,950 boards;
#   icims    ~740 boards, each fetched posting-by-posting (slowest per board).
# Greenhouse/SmartRecruiters stay full: one fast API call per board.
_DEFAULT_SHARDS = {"workday": 4, "join": 3, "icims": 3}


def shards_for(platform: str) -> int:
    env = os.getenv(f"{platform.upper()}_ROTATION_SHARDS")
    if env is not None:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    return _DEFAULT_SHARDS.get(platform, 1)


def shard_of(token: str, shards: int) -> int:
    return int(hashlib.md5(token.encode()).hexdigest(), 16) % shards


def apply_rotation(boards: dict[str, list[str]], index: int):
    """Keep only the current shard of each rotated platform.

    Returns ``(boards_to_run, info)``. ``info`` maps each rotated platform to
    ``{shards, current, total_boards, this_cycle}`` for honest reporting on the
    status page. Non-rotated platforms pass through unchanged.
    """
    out: dict[str, list[str]] = {}
    info: dict[str, dict] = {}
    for platform, blist in boards.items():
        shards = shards_for(platform)
        if shards <= 1 or not blist:
            out[platform] = blist
            continue
        cur = index % shards
        kept = [b for b in blist if shard_of(b, shards) == cur]
        out[platform] = kept
        info[platform] = {
            "shards": shards,
            "current": cur,
            "total_boards": len(blist),
            "this_cycle": len(kept),
        }
    return out, info
