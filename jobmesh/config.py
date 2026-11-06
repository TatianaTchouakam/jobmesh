"""Load the list of boards to index from config/companies.yaml."""

from __future__ import annotations

import os
from typing import Dict, List

import yaml

DEFAULT_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "companies.yaml"
)


def load_boards(path: str = DEFAULT_CONFIG) -> Dict[str, List[str]]:
    """Return a {platform: [board, ...]} mapping from the YAML config."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    boards: Dict[str, List[str]] = {}
    for platform, entries in data.items():
        if not entries:
            continue
        boards[str(platform)] = [str(e).strip() for e in entries if str(e).strip()]
    return boards
