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
from .recooty import RecootyConnector
from .rippling import RipplingConnector
from .hirehive import HireHiveConnector
from .manatal import ManatalConnector
from .hireology import HireologyConnector
from .hibob import HibobConnector
from .careerplug import CareerPlugConnector
from .jobvite import JobviteConnector
from .zohorecruit import ZohoRecruitConnector
from .freshteam import FreshteamConnector
from .gem import GemConnector
from .deel import DeelConnector
from .exenzo import ExenzoConnector
from .isolvedhire import IsolvedHireConnector
from .jazzhr import JazzHrConnector
from .icims import IcimsConnector
from .phenom import PhenomConnector
from .jobiqo import JobiqoConnector
from .homerun import HomerunConnector
from .jobscore import JobScoreConnector
from .adp import AdpConnector
from .dvinci import DvinciConnector
from .paylocity import PaylocityConnector
from .avature import AvatureConnector
from .pageup import PageUpConnector
from .eightfold import EightfoldConnector
from .softgarden import SoftgardenConnector
from .oracle import OracleConnector
from .bundesagentur import BundesagenturConnector
from .devitjobs import DevITjobsConnector
from .reliefweb import ReliefWebConnector
from .jobtech import JobTechConnector
from .navno import NavNoConnector
from .francetravail import FranceTravailConnector
from .reed import ReedConnector
from .comeet import ComeetConnector
from .careersite import CareerSiteConnector
from .jobfeed import JobFeedConnector
from .smartjobboard import SmartJobBoardConnector
from .join import JoinConnector
from .dover import DoverConnector
from .niceboard import NiceboardConnector
from .polymer import PolymerConnector
from .dayforce import DayforceConnector
from .taleo import TaleoConnector
from .hirebridge import HireBridgeConnector
from .trinet import TriNetConnector
from .trakstar import TrakstarConnector
from .rival import RivalConnector
from .werecruit import WeRecruitConnector
from .firststage import FirstStageConnector
from .hiringthing import HiringThingConnector
from .nodex import NodexConnector
from .talentlyft import TalentLyftConnector
from .recruitcrm import RecruitCrmConnector
from .uncareers import UnCareersConnector
from .artha import ArthaConnector
from .jobboardcom import JobBoardComConnector
from .mycareersfuture import MyCareersFutureConnector
from .eures import EuresConnector
from .jobmount import JobMountConnector
from .catsone import CatsOneConnector
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
    HireologyConnector.platform: HireologyConnector,
    HibobConnector.platform: HibobConnector,
    CareerPlugConnector.platform: CareerPlugConnector,
    JobviteConnector.platform: JobviteConnector,
    ZohoRecruitConnector.platform: ZohoRecruitConnector,
    FreshteamConnector.platform: FreshteamConnector,
    GemConnector.platform: GemConnector,
    DeelConnector.platform: DeelConnector,
    ExenzoConnector.platform: ExenzoConnector,
    IsolvedHireConnector.platform: IsolvedHireConnector,
    JazzHrConnector.platform: JazzHrConnector,
    IcimsConnector.platform: IcimsConnector,
    PhenomConnector.platform: PhenomConnector,
    JobiqoConnector.platform: JobiqoConnector,
    HomerunConnector.platform: HomerunConnector,
    JobScoreConnector.platform: JobScoreConnector,
    AdpConnector.platform: AdpConnector,
    DvinciConnector.platform: DvinciConnector,
    PaylocityConnector.platform: PaylocityConnector,
    AvatureConnector.platform: AvatureConnector,
    PageUpConnector.platform: PageUpConnector,
    EightfoldConnector.platform: EightfoldConnector,
    SoftgardenConnector.platform: SoftgardenConnector,
    OracleConnector.platform: OracleConnector,
    BundesagenturConnector.platform: BundesagenturConnector,
    DevITjobsConnector.platform: DevITjobsConnector,
    ReliefWebConnector.platform: ReliefWebConnector,
    JobTechConnector.platform: JobTechConnector,
    NavNoConnector.platform: NavNoConnector,
    FranceTravailConnector.platform: FranceTravailConnector,
    ReedConnector.platform: ReedConnector,
    ComeetConnector.platform: ComeetConnector,
    CareerSiteConnector.platform: CareerSiteConnector,
    JobFeedConnector.platform: JobFeedConnector,
    SmartJobBoardConnector.platform: SmartJobBoardConnector,
    JoinConnector.platform: JoinConnector,
    DoverConnector.platform: DoverConnector,
    NiceboardConnector.platform: NiceboardConnector,
    RecootyConnector.platform: RecootyConnector,
    PolymerConnector.platform: PolymerConnector,
    DayforceConnector.platform: DayforceConnector,
    CatsOneConnector.platform: CatsOneConnector,
    TaleoConnector.platform: TaleoConnector,
    HireBridgeConnector.platform: HireBridgeConnector,
    TriNetConnector.platform: TriNetConnector,
    TrakstarConnector.platform: TrakstarConnector,
    RivalConnector.platform: RivalConnector,
    WeRecruitConnector.platform: WeRecruitConnector,
    FirstStageConnector.platform: FirstStageConnector,
    HiringThingConnector.platform: HiringThingConnector,
    NodexConnector.platform: NodexConnector,
    TalentLyftConnector.platform: TalentLyftConnector,
    RecruitCrmConnector.platform: RecruitCrmConnector,
    UnCareersConnector.platform: UnCareersConnector,
    ArthaConnector.platform: ArthaConnector,
    JobBoardComConnector.platform: JobBoardComConnector,
    MyCareersFutureConnector.platform: MyCareersFutureConnector,
    EuresConnector.platform: EuresConnector,
    JobMountConnector.platform: JobMountConnector,
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
