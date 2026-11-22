"""Offline tests for the KamerTalent export: scope, exclusions, format, read-only."""
import json

from jobmesh import storage
from jobmesh.export_kamertalent import africa_country, export, open_to_diaspora, to_kamertalent
from jobmesh.models import Job


def _job(job_id, location, platform="greenhouse", title="Data Analyst", **kw):
    return Job(source_platform=platform, source_board="acme", source_job_id=job_id, title=title,
               company="Acme", location=location, source_url=f"https://boards.example.com/acme/{job_id}", **kw)


def test_country_detection():
    assert africa_country("Douala, Cameroon") == "CMR"
    assert africa_country("Yaoundé") == "CMR"
    assert africa_country("Lagos, NG") == "NGA"
    assert africa_country("Abidjan, Côte d'Ivoire") == "CIV"
    assert africa_country("Malabo, Equatorial Guinea") == "GNQ"
    assert africa_country("San Francisco, CA") is None      # California, not Canada nor Africa
    assert africa_country("Atlanta, GA") is None            # Georgia, not Gabon
    assert africa_country("Alexandria, VA") is None
    assert africa_country("Berlin") is None
    assert africa_country("Lagos de Moreno, Jalisco") is None   # seen in the real index
    assert africa_country("Lagos, Portugal") is None
    assert africa_country("Remote, India; Remote, Kenya; Remote, Lagos, Nigeria") == "KEN"
    assert africa_country("Cameroon - Remote") == "CMR"
    assert africa_country("Dakar, Dakar Region, sn") == "SEN"


def test_diaspora_only_when_explicitly_open():
    assert open_to_diaspora("Remote - Worldwide")
    assert open_to_diaspora("Remote (EMEA)")
    assert open_to_diaspora("Remote, Africa")
    assert not open_to_diaspora("Remote - US only")
    assert not open_to_diaspora("Remote")                   # no stated scope: not exported
    assert not open_to_diaspora("Paris, France")


def test_exclusions_and_format():
    row = _job("1", "Douala, Cameroon", posted_at="2026-11-20T09:00:00Z").to_dict()
    o = to_kamertalent({**row, "is_open": 1})
    assert o["source_id"] == "jobmesh-greenhouse" and o["source_ref"] == "acme:1"
    assert o["pays_iso3"] == "CMR" and o["date_publication"] == "2026-11-20" and o["date_limite"] is None
    assert o["lien"] == "https://boards.example.com/acme/1"
    for excluded in ("minajobs", "uncareers", "jooble", "usajobs"):
        assert to_kamertalent({**_job("2", "Douala", platform=excluded).to_dict(), "is_open": 1}) is None
    assert to_kamertalent({**row, "is_open": 0}) is None
    stage = to_kamertalent({**_job("3", "Accra, Ghana", title="Finance Intern").to_dict(), "is_open": 1})
    assert stage["type_offre"] == "stage"
    d = to_kamertalent({**_job("4", "Remote - Worldwide").to_dict(), "is_open": 1})
    assert d["pays_iso3"] is None and d["ville"] == "À distance · Remote - Worldwide"
    for filler in ("Don’t see what you’re looking for?", "Don't see what you are looking for?",
                   "Talent Pool: Future Opportunities", "General Application"):
        assert to_kamertalent({**_job("5", "Remote - Worldwide", title=filler).to_dict(), "is_open": 1}) is None


def test_export_file_read_only(tmp_path):
    db = str(tmp_path / "t.db")
    with storage.session(db) as conn:
        storage.upsert_jobs(conn, [_job("1", "Douala, Cameroon"), _job("2", "Berlin"),
                                   _job("3", "Nairobi, Kenya"), _job("4", "Remote - US only")])
    out = tmp_path / "exports" / "k.jsonl"
    counts = export(db, out)
    lines = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert counts == {"jobmesh-greenhouse": 2} and {l["pays_iso3"] for l in lines} == {"CMR", "KEN"}
    assert set(lines[0]) == {"source_id", "source_ref", "titre", "lien", "organisation", "description", "pays_iso3",
                             "ville", "type_offre", "date_publication", "date_limite", "retour_au_pays",
                             "competences"}
