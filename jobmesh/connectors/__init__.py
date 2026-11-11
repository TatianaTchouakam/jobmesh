"""Connector registry.

Maps a platform name to its connector class. The pipeline uses this to
build connectors from the plain-text config, so adding a platform is:
write the connector, then register it here.
"""

from __future__ import annotations

from .base import Connector
# ATS connectors (per-company boards)
from .greenhouse import GreenhouseConnector
from .lever import LeverConnector
from .ashby import AshbyConnector
from .workable import WorkableConnector
from .smartrecruiters import SmartRecruitersConnector
from .recruitee import RecruiteeConnector
from .breezy import BreezyConnector
# Job-board connectors (one feed, many companies)
from .personio import PersonioConnector
from .bamboohr import BambooHrConnector
from .pinpoint import PinpointConnector
from .remotive import RemotiveConnector
from .arbeitnow import ArbeitnowConnector
from .themuse import TheMuseConnector
from .remoteok import RemoteOkConnector
from .jobicy import JobicyConnector
from .himalayas import HimalayasConnector
from .workingnomads import WorkingNomadsConnector
from .weworkremotely import WeWorkRemotelyConnector
from .workday import WorkdayConnector
from .teamtailor import TeamtailorConnector
from .fourdayweek import FourDayWeekConnector
from .jobspresso import JobspressoConnector
from .pythonjobs import PythonJobsConnector
from .joinrise import JoinRiseConnector
from .rippling import RipplingConnector
from .hirehive import HireHiveConnector
from .manatal import ManatalConnector
from .softgarden import SoftgardenConnector
from .oracle import OracleConnector
from .bundesagentur import BundesagenturConnector
from .devitjobs import DevITjobsConnector
from .reliefweb import ReliefWebConnector
from .jobtech import JobTechConnector
from .navno import NavNoConnector
from .francetravail import FranceTravailConnector
from .reed import ReedConnector
# Generalist job boards (free API key, read from the environment)
from .adzuna import AdzunaConnector
from .jooble import JoobleConnector
from .usajobs import UsaJobsConnector

REGISTRY: dict[str, type[Connector]] = {
    GreenhouseConnector.platform: GreenhouseConnector,
    LeverConnector.platform: LeverConnector,
    AshbyConnector.platform: AshbyConnector,
    WorkableConnector.platform: WorkableConnector,
    SmartRecruitersConnector.platform: SmartRecruitersConnector,
    RecruiteeConnector.platform: RecruiteeConnector,
    BreezyConnector.platform: BreezyConnector,
    PersonioConnector.platform: PersonioConnector,
    BambooHrConnector.platform: BambooHrConnector,
    PinpointConnector.platform: PinpointConnector,
    RemotiveConnector.platform: RemotiveConnector,
    ArbeitnowConnector.platform: ArbeitnowConnector,
    TheMuseConnector.platform: TheMuseConnector,
    RemoteOkConnector.platform: RemoteOkConnector,
    JobicyConnector.platform: JobicyConnector,
    HimalayasConnector.platform: HimalayasConnector,
    WorkingNomadsConnector.platform: WorkingNomadsConnector,
    WeWorkRemotelyConnector.platform: WeWorkRemotelyConnector,
    WorkdayConnector.platform: WorkdayConnector,
    TeamtailorConnector.platform: TeamtailorConnector,
    FourDayWeekConnector.platform: FourDayWeekConnector,
    JobspressoConnector.platform: JobspressoConnector,
    PythonJobsConnector.platform: PythonJobsConnector,
    JoinRiseConnector.platform: JoinRiseConnector,
    RipplingConnector.platform: RipplingConnector,
    HireHiveConnector.platform: HireHiveConnector,
    ManatalConnector.platform: ManatalConnector,
    SoftgardenConnector.platform: SoftgardenConnector,
    OracleConnector.platform: OracleConnector,
    BundesagenturConnector.platform: BundesagenturConnector,
    DevITjobsConnector.platform: DevITjobsConnector,
    ReliefWebConnector.platform: ReliefWebConnector,
    JobTechConnector.platform: JobTechConnector,
    NavNoConnector.platform: NavNoConnector,
    FranceTravailConnector.platform: FranceTravailConnector,
    ReedConnector.platform: ReedConnector,
    AdzunaConnector.platform: AdzunaConnector,
    JoobleConnector.platform: JoobleConnector,
    UsaJobsConnector.platform: UsaJobsConnector,
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


__all__ = ["Connector", "REGISTRY", "build_connector"]
