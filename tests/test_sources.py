"""The source registry must stay consistent with the real connectors + config.

This is the drift guard: every ACTIVE platform must have a real registered
connector, the registry must list exactly the 78 required platforms, and every
status must be one of the six defined states.
"""
import yaml

from jobmesh import sources as srcreg
from jobmesh.connectors import REGISTRY
from jobmesh.config import load_boards

# The official challenge list (verified against vayahq.com, 21/11/2026).
_OFFICIAL_ATS = {
    "ADP","ApplicantPro","Ashby","Avature","BambooHR","BrassRing","Breezy HR",
    "CareerPlug","Comeet","CSOD (Cornerstone)","Dayforce","Deel","Dover",
    "Eightfold AI","FirstStage","Freshteam","Gem.com","GoHire","Greenhouse",
    "HiBob","HireBridge","HireHive","Hireology","HiringThing","iCIMS",
    "iSolvedHire","JazzHR","Jobvite","JOIN.com","Kula.ai","Lever.co","Manatal",
    "Oracle Recruiting","PageUp","Paradox","Paycom","Paycor","Paylocity",
    "Personio","Phenom People","Pinpoint","Polymer","Recooty","Recruitee",
    "Rippling","Rival","SAP SuccessFactors","SmartRecruiters","talentReef",
    "Taleo","Teamtailor","Trakstar","TriNet","UltiPro","WeRecruit","Workable",
    "Workday","Zoho Recruit",
}
_OFFICIAL_BOARDS = {
    "Niceboard","WP Job Manager","JobKit","Jobboardly","Jobiqo","JBoard.io",
    "JobBoardFire","SmartJobBoard","JobBoard.io","Wiley Madgex","Talenetic",
    "JobMount","CareerSiteCloud","JobBoard.com","Artha","jobboardsoftware.com",
    "jobBoardHQ","Nodex","eJobBoard","ejobsitesoftware.com",
}


def test_registry_covers_exactly_the_78():
    data = srcreg.load_sources()
    ats = {p["name"] for p in data["required_ats"]}
    boards = {p["name"] for p in data["required_boards"]}
    assert ats == _OFFICIAL_ATS
    assert boards == _OFFICIAL_BOARDS
    assert len(ats) == 58 and len(boards) == 20


def test_statuses_are_valid():
    for p in srcreg.all_required():
        assert p["status"] in srcreg.STATUSES, p
        if p["status"] != "ACTIVE":
            # non-active sources must carry a reason + next action (handoff)
            assert p.get("reason"), p["name"]
            assert p.get("next_action"), p["name"]


def test_active_sources_have_a_real_connector():
    for conn in srcreg.active_connectors():
        assert conn in REGISTRY, f"ACTIVE source references missing connector: {conn}"


def test_no_inactive_source_is_seeded_for_live_ingest():
    """A platform declared non-ACTIVE must NOT be wired into the live config —
    otherwise the daily ingest would try (and fail) it, contradicting its status."""
    data = srcreg.load_sources()
    inactive_conns = {p["connector"] for p in srcreg.all_required(data)
                      if p["status"] != "ACTIVE" and p.get("connector")}
    seeded = set(load_boards().keys())
    # connectors used ONLY by an inactive platform must not be seeded
    active = srcreg.active_connectors(data)
    for c in inactive_conns:
        if c not in active:                      # not shared with an active platform
            assert c not in seeded, f"inactive connector {c} is seeded in companies.yaml"


def test_active_count_is_67():
    assert srcreg.status_counts().get("ACTIVE") == 67


def test_bonus_sources_are_real_and_seeded():
    """Bonus sources must have a real connector and be actually seeded live
    (non-empty board list) — a bonus with no boards is not a live source."""
    bonus = srcreg.bonus_sources()
    cfg = yaml.safe_load(open("config/companies.yaml"))
    required = srcreg.active_connectors()
    for b in bonus:
        c = b["connector"]
        assert c in REGISTRY, f"bonus references missing connector: {c}"
        assert cfg.get(c), f"bonus {c} is not seeded with any board"
        assert c not in required, f"bonus {c} is actually a required-platform connector"
        assert b["status"] == "ACTIVE"
