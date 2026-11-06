"""Connector registry.

Maps a platform name to its connector class. The pipeline uses this to
build connectors from the plain-text config, so adding a platform is:
write the connector, then register it here.
"""

from __future__ import annotations

from .base import Connector
from .greenhouse import GreenhouseConnector

REGISTRY: dict[str, type[Connector]] = {
    GreenhouseConnector.platform: GreenhouseConnector,
    # Roadmap — one line each as they are implemented:
    # "lever": LeverConnector,
    # "ashby": AshbyConnector,
    # "workable": WorkableConnector,
}


def build_connector(platform: str, board: str) -> Connector:
    """Instantiate the connector registered for `platform`."""
    try:
        cls = REGISTRY[platform]
    except KeyError:
        raise ValueError(
            f"No connector registered for platform {platform!r}. "
            f"Known: {', '.join(sorted(REGISTRY)) or '(none)'}"
        )
    return cls(board)


__all__ = ["Connector", "GreenhouseConnector", "REGISTRY", "build_connector"]
