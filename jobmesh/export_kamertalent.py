"""Daily JSONL export of African, Cameroonian and diaspora postings for KamerTalent.

Read-only: this module opens the index in SQLite read-only mode, and changes
no connector, no rule and no table. It writes one JSON object per line in the
format read by `python -m kamertalent.sources.collecte --importer FILE`.

Usage:
    python -m jobmesh.export_kamertalent                       # -> exports/kamertalent-YYYY-MM-DD.jsonl
    python -m jobmesh.export_kamertalent --out offers.jsonl --db /path/jobmesh.db

What is exported (open postings only):
  * Cameroon: location names Cameroon / Cameroun, a ", CM" suffix, or a Cameroonian city;
  * the rest of Africa: an African country name (EN / FR), its ", XX" ISO-2 suffix, or a capital;
  * diaspora: remote postings explicitly open worldwide, to Africa or to EMEA.
Each posting keeps its original platform (source_id "jobmesh-<platform>"), its
date and its link. Sources excluded on purpose: see EXCLUDED_PLATFORMS.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path
from typing import Iterator, Optional

log = logging.getLogger(__name__)

EXCLUDED_PLATFORMS = {
    "minajobs",   # robots.txt disallows automated access: never exported
    "uncareers",  # KamerTalent reads the official UN feed directly
    "jooble",     # partner API: its terms cover Jobmesh only
    "usajobs",    # US federal jobs, reserved to US citizens
}
# Board placeholders and talent pools are not job offers.
NOT_A_JOB = re.compile(r"(don.?t see what (you.?re|you are) looking for|general application|open application|"
                       r"spontaneous application|candidature spontan|talent pool|talent community|future opportunities)",
                       re.I)

CAMEROON_CITIES = {
    "yaounde", "douala", "bafoussam", "garoua", "maroua", "bamenda", "buea", "bertoua", "ngaoundere",
    "ebolowa", "kousseri", "limbe", "kribi", "kumba", "dschang", "foumban", "nkongsamba", "edea",
}
# ISO-2 -> (ISO-3, names in English and French, capital / main cities)
AFRICA = {
    "CM": ("CMR", ["cameroon", "cameroun"], sorted(CAMEROON_CITIES)),
    "DZ": ("DZA", ["algeria", "algerie"], ["algiers", "alger"]),
    "AO": ("AGO", ["angola"], ["luanda"]),
    "BJ": ("BEN", ["benin"], ["cotonou", "porto-novo"]),
    "BW": ("BWA", ["botswana"], ["gaborone"]),
    "BF": ("BFA", ["burkina faso"], ["ouagadougou"]),
    "BI": ("BDI", ["burundi"], ["bujumbura"]),
    "CV": ("CPV", ["cabo verde", "cape verde", "cap-vert"], ["praia"]),
    "CF": ("CAF", ["central african republic", "republique centrafricaine", "centrafrique"], ["bangui"]),
    "TD": ("TCD", ["chad", "tchad"], ["n'djamena", "ndjamena"]),
    "KM": ("COM", ["comoros", "comores"], ["moroni"]),
    "CG": ("COG", ["republic of the congo", "congo-brazzaville", "republique du congo"], ["brazzaville", "pointe-noire"]),
    "CD": ("COD", ["democratic republic of the congo", "dr congo", "drc", "rdc", "republique democratique du congo"],
           ["kinshasa", "goma", "lubumbashi"]),
    "CI": ("CIV", ["cote d'ivoire", "ivory coast"], ["abidjan", "yamoussoukro"]),
    "DJ": ("DJI", ["djibouti"], []),
    "EG": ("EGY", ["egypt", "egypte"], ["cairo", "le caire"]),
    "GQ": ("GNQ", ["equatorial guinea", "guinee equatoriale"], ["malabo"]),
    "ER": ("ERI", ["eritrea", "erythree"], ["asmara"]),
    "SZ": ("SWZ", ["eswatini", "swaziland"], ["mbabane"]),
    "ET": ("ETH", ["ethiopia", "ethiopie"], ["addis ababa", "addis-abeba"]),
    "GA": ("GAB", ["gabon"], ["libreville"]),
    "GM": ("GMB", ["gambia", "gambie"], ["banjul"]),
    "GH": ("GHA", ["ghana"], ["accra", "kumasi"]),
    "GN": ("GIN", ["guinea", "guinee"], ["conakry"]),
    "GW": ("GNB", ["guinea-bissau", "guinee-bissau"], ["bissau"]),
    "KE": ("KEN", ["kenya"], ["nairobi", "mombasa"]),
    "LS": ("LSO", ["lesotho"], ["maseru"]),
    "LR": ("LBR", ["liberia"], ["monrovia"]),
    "LY": ("LBY", ["libya", "libye"], []),
    "MG": ("MDG", ["madagascar"], ["antananarivo"]),
    "MW": ("MWI", ["malawi"], ["lilongwe", "blantyre"]),
    "ML": ("MLI", ["mali"], ["bamako"]),
    "MR": ("MRT", ["mauritania", "mauritanie"], ["nouakchott"]),
    "MU": ("MUS", ["mauritius", "maurice"], ["port louis"]),
    "MA": ("MAR", ["morocco", "maroc"], ["casablanca", "rabat", "marrakech", "tangier", "tanger"]),
    "MZ": ("MOZ", ["mozambique"], ["maputo"]),
    "NA": ("NAM", ["namibia", "namibie"], ["windhoek"]),
    "NE": ("NER", ["niger"], ["niamey"]),
    "NG": ("NGA", ["nigeria"], ["lagos", "abuja", "port harcourt", "ibadan"]),
    "RW": ("RWA", ["rwanda"], ["kigali"]),
    "ST": ("STP", ["sao tome and principe", "sao tome-et-principe"], []),
    "SN": ("SEN", ["senegal"], ["dakar"]),
    "SC": ("SYC", ["seychelles"], []),
    "SL": ("SLE", ["sierra leone"], ["freetown"]),
    "SO": ("SOM", ["somalia", "somalie"], ["mogadishu"]),
    "ZA": ("ZAF", ["south africa", "afrique du sud"], ["johannesburg", "cape town", "pretoria", "durban"]),
    "SS": ("SSD", ["south sudan", "soudan du sud"], ["juba"]),
    "SD": ("SDN", ["sudan", "soudan"], ["khartoum", "port sudan"]),
    "TZ": ("TZA", ["tanzania", "tanzanie"], ["dar es salaam", "dodoma", "arusha"]),
    "TG": ("TGO", ["togo"], ["lome"]),
    "TN": ("TUN", ["tunisia", "tunisie"], ["tunis"]),
    "UG": ("UGA", ["uganda", "ouganda"], ["kampala"]),
    "ZM": ("ZMB", ["zambia", "zambie"], ["lusaka"]),
    "ZW": ("ZWE", ["zimbabwe"], ["harare"]),
}
# A city name alone can exist elsewhere ("Lagos, Portugal", "Lagos de Moreno, Jalisco").
ELSEWHERE = re.compile(r"\b(portugal|mexico|jalisco|spain|espana|chile|brazil|usa|united states|"
                       r"france|canada|india|philippines|de moreno)\b")
# ", CA" is California, ", GA" Georgia, ", MA" Massachusetts...: for these, only a country name counts.
US_STATE_CLASHES = {"CA", "GA", "MA", "NE", "SC", "SD", "TN"}
REMOTE = re.compile(r"\b(remote|anywhere|worldwide|work from home|home-based|teletravail|a distance)\b")
# "Anywhere" alone means worldwide; "Anywhere in France" or "Anywhere, USA" does not.
OPEN_TO_US = re.compile(r"\b(worldwide|global|africa|afrique|emea|anywhere in the world)\b")
REMOTE_WORDS = re.compile(r"\b(remote|anywhere|home based|home-based|work from home|teletravail|a distance|"
                          r"fully|100|only)\b|[^a-z]+")
NOT_FOR_US = re.compile(r"\b(us only|usa only|united states only|u s only|uk only|eu only|europe only|"
                        r"us based|based in the us|north america|latam|apac|usa|united states|canada|"
                        r"europe|france|belgium|spain|germany|ukraine|poland|portugal|india|"
                        r"anywhere in (?!the world)[a-z]+)\b")


def _plain(text: Optional[str]) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9',\-]+", " ", t)).strip()


def africa_country(location: Optional[str]) -> Optional[str]:
    """ISO-3 code of the African country named in a location string, or None."""
    loc = _plain(location)
    if not loc:
        return None
    found = lambda word: re.search(rf"(^|[ ,;]){re.escape(word)}($|[ ,;])", loc)
    for iso2, (iso3, names, cities) in AFRICA.items():  # 1) a country name is explicit
        if any(found(w) for w in names):
            return iso3
    if not ELSEWHERE.search(loc):                        # 2) a city, unless another country is named
        for iso2, (iso3, names, cities) in AFRICA.items():
            if any(found(w) for w in cities):
                return iso3
    suffix = re.search(r",\s*([a-z]{2})\s*$", loc)
    if suffix and suffix.group(1).upper() in AFRICA and suffix.group(1).upper() not in US_STATE_CLASHES:
        return AFRICA[suffix.group(1).upper()][0]
    return None


def open_to_diaspora(location: Optional[str]) -> bool:
    """Remote posting explicitly open worldwide, to Africa or to EMEA (or "Remote / Anywhere" with nothing else)."""
    loc = _plain(location)
    if not REMOTE.search(loc) or NOT_FOR_US.search(loc):
        return False
    return bool(OPEN_TO_US.search(loc)) or loc.startswith("anywhere") and not REMOTE_WORDS.sub("", loc)


def guess_type(title: str, level: Optional[str], employment: Optional[str]) -> str:
    t = _plain(f"{title} {level or ''} {employment or ''}")
    if re.search(r"\b(intern|internship|stage|stagiaire|trainee)\b", t):
        return "stage"
    if re.search(r"\b(volunteer|volontaire|volontariat|unv)\b", t):
        return "volontariat"
    if re.search(r"\b(consultant|consultancy|consultance|contract)\b", t):
        return "consultance"
    return "emploi"


def _iso_date(value: Optional[str]) -> Optional[str]:
    if value and re.match(r"\d{4}-\d{2}-\d{2}", value):
        return value[:10]
    return None


def to_kamertalent(row: dict) -> Optional[dict]:
    """One Jobmesh row -> one KamerTalent offer (dict), or None if out of scope."""
    platform = row["source_platform"]
    if platform in EXCLUDED_PLATFORMS or not row.get("is_open", 1):
        return None
    link = row.get("source_url") or row.get("apply_url")
    if not link or not row.get("title") or NOT_A_JOB.search(row["title"]):
        return None
    country = africa_country(row.get("location"))
    diaspora = country is None and open_to_diaspora(row.get("location"))
    if not country and not diaspora:
        return None
    return {
        "source_id": f"jobmesh-{platform}",
        "source_ref": f"{row['source_board']}:{row['source_job_id']}",
        "titre": row["title"].strip(),
        "lien": link,
        "organisation": row.get("company"),
        "description": (row.get("description") or "")[:4000] or None,
        "pays_iso3": country,
        # remote: keep the stated scope so readers see who can apply ("À distance · Anywhere in the World")
        "ville": ((row.get("location") or "")[:120] or None) if country
                 else f"À distance · {(row.get('location') or '').strip()[:100]}",
        "type_offre": guess_type(row["title"], row.get("level"), row.get("employment_type")),
        "date_publication": _iso_date(row.get("posted_at")),  # the source's own date, never invented
        "date_limite": None,
        "retour_au_pays": False,
        "competences": [],
    }


def rows(db_path: str) -> Iterator[dict]:
    uri = f"file:{Path(db_path).resolve()}?mode=ro"  # read-only: the index is never modified
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield from (dict(r) for r in conn.execute("SELECT * FROM jobs WHERE is_open = 1"))
    finally:
        conn.close()


def export(db_path: str, out: Path) -> dict[str, int]:
    out.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    seen: set[str] = set()
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows(db_path):
            offer = to_kamertalent(row)
            if not offer or offer["lien"] in seen:  # one line per link
                continue
            seen.add(offer["lien"])
            f.write(json.dumps(offer, ensure_ascii=False) + "\n")
            counts[offer["source_id"]] = counts.get(offer["source_id"], 0) + 1
    tmp.replace(out)  # the file appears complete or not at all
    return counts


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="Export African / Cameroonian / diaspora postings for KamerTalent")
    ap.add_argument("--db", default=os.getenv("JOBMESH_DB", "jobmesh.db"))
    ap.add_argument("--out", type=Path, default=Path("exports") / f"kamertalent-{date.today().isoformat()}.jsonl")
    args = ap.parse_args(argv)
    counts = export(args.db, args.out)
    log.info("exported %d postings to %s: %s", sum(counts.values()), args.out, counts)


if __name__ == "__main__":
    main()
