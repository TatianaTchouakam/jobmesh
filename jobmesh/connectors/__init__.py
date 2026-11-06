"""Connector registry.

Maps a platform name to its connector class. The pipeline uses this to
build connectors from the plain-text config, so adding a platform is:
write the connector, then register it here.
"""

from __future__ import annotations

from .base import Connector
from .greenhouse import GreenhouseConnector
from .lever import LeverConnector
from .ashby import AshbyConnector
from .workable import WorkableConnector
from .smartrecruiters import SmartRecruitersConnector
from .recruitee import RecruiteeConnector
from .breezy import BreezyConnector

REGISTRY: dict[str, type[Connector]] = {
    GreenhouseConnector.platform: GreenhouseConnector,
    LeverConnector.platform: LeverConnector,
    AshbyConnector.platform: AshbyConnector,
    WorkableConnector.platform: WorkableConnector,
    SmartRecruitersConnector.platform: SmartRecruitersConnector,
    RecruiteeConnector.platform: RecruiteeConnector,
    BreezyConnector.platform: BreezyConnector,
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


__all__ = [
    "Connector",
    "GreenhouseConnector",
    "LeverConnector",
    "AshbyConnector",
    "WorkableConnector",
    "SmartRecruitersConnector",
    "RecruiteeConnector",
    "BreezyConnector",
    "REGISTRY",
    "build_connector",
]
