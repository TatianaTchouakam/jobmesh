"""Normalization helpers shared by every connector.

These turn messy, source-specific values into the clean, consistent forms
the rest of jobmesh relies on: plain-text descriptions, a remote flag,
and a deduplication key.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Optional

# Matches any HTML tag so we can strip it out.
_TAG_RE = re.compile(r"<[^>]+>")
# Collapses runs of whitespace into a single space.
_WS_RE = re.compile(r"\s+")

# Words that signal a remote role when they appear in the location text.
_REMOTE_HINTS = ("remote", "anywhere", "work from home", "wfh", "distributed")


def html_to_text(raw: Optional[str]) -> Optional[str]:
    """Turn an HTML job description into readable plain text.

    Greenhouse (and others) return descriptions as HTML-entity-encoded
    markup, e.g. "&lt;p&gt;Hello&lt;/p&gt;". We decode entities, drop the
    tags, and tidy the whitespace.
    """
    if not raw:
        return None
    text = html.unescape(raw)          # &lt;p&gt; -> <p>
    text = _TAG_RE.sub(" ", text)      # <p> -> (space)
    text = html.unescape(text)         # decode any entities the tags hid
    text = _WS_RE.sub(" ", text)
    return text.strip() or None


def detect_remote(location: Optional[str]) -> Optional[bool]:
    """Infer whether a role is remote from its location text.

    Returns True/False when the text is informative, or None when there is
    nothing to go on (so we never overwrite a flag the source gave us).
    """
    if not location:
        return None
    low = location.lower()
    if any(hint in low for hint in _REMOTE_HINTS):
        return True
    return False


def _slug(value: str) -> str:
    """Lowercase, accent-stripped, alphanumeric-only form of a string."""
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


def normalize_workplace(raw: Optional[str]) -> Optional[str]:
    """Map varied workplace labels to: 'remote' / 'hybrid' / 'onsite' / None.

    Sources phrase this differently ("Remote", "on-site", "Hybrid",
    "telecommuting"), so we reduce to a small, filterable set.
    """
    if not raw:
        return None
    s = re.sub(r"[^a-z]", "", str(raw).lower())
    if "hybrid" in s:
        return "hybrid"
    if "remote" in s or "telecommut" in s or "anywhere" in s:
        return "remote"
    if "onsite" in s or "inoffice" in s or "office" in s:
        return "onsite"
    return None


def normalize_employment(raw: Optional[str]) -> Optional[str]:
    """Map varied employment-type labels to a clean, consistent form.

    e.g. "FullTime", "full-time", "fulltime_permanent" -> "Full-time".
    Unknown values are kept, title-cased, so nothing is lost.
    """
    if not raw:
        return None
    s = re.sub(r"[^a-z]", "", str(raw).lower())
    if "intern" in s:
        return "Internship"
    if "parttime" in s:
        return "Part-time"
    if "fulltime" in s:
        return "Full-time"
    if "contract" in s or "freelance" in s or "b2b" in s:
        return "Contract"
    if "temp" in s:
        return "Temporary"
    if "volunteer" in s:
        return "Volunteer"
    return str(raw).strip().title()


#: Broad domains, matched in order (first hit wins) against the posting's
#: department/team text and its title. Specific, vocational and non-tech
#: buckets come first; the generic tech buckets (Data & AI, Engineering)
#: come last so a "Sales Engineer" or "Maintenance Technician" lands in the
#: right place. Keywords are English + German, since the index covers DACH.
_CATEGORY_RULES = (
    ("Healthcare", ("nurse", "nursing", "pflege", "pfleger", "krankenpfleger",
                    "arzt", "ärzt", "medical", "clinic", "klinik", "doctor",
                    "physician", "therapist", "therapeut", "care worker",
                    "altenpfleger", "pharma", "apotheke", "dental", "zahn",
                    "hebamme", "sanitäter", "gesundheit")),
    ("Skilled Trades", ("electrician", "elektriker", "elektroniker", "mechanic",
                        "mechaniker", "mechatronik", "mechatronic", "plumber",
                        "installateur", "schlosser", "schweißer", "welder",
                        "technician", "techniker", "fitter", "maintenance",
                        "instandhaltung", "handwerk", "carpenter", "tischler",
                        "maler", "anlagenmechaniker", "monteur")),
    ("Construction", ("construction", "bauleiter", "bauingenieur", "architect",
                      "architekt", "surveyor", "polier", "hochbau", "tiefbau",
                      "baustelle")),
    ("Manufacturing & Production", ("production", "produktion", "fertigung",
                        "manufacturing", "assembly", "montage",
                        "machine operator", "maschinenbediener",
                        "produktionshelfer", "produktionsmitarbeiter",
                        "werker", "schichtleiter", "qualitätssicherung",
                        "quality assurance", "quality control")),
    ("Logistics & Supply Chain", ("logistics", "logistik", "supply chain",
                        "warehouse", "lager", "kommissionier", "fahrer",
                        "driver", "lkw", "disponent", "spedition", "forklift",
                        "stapler", "versand", "shipping", "procurement",
                        "einkauf", "supply")),
    ("Hospitality & Food", ("chef", "koch", "köch", "kitchen", "küche",
                        "restaurant", "hotel", "barista", "waiter", "kellner",
                        "hospitality", "gastronomie", "catering",
                        "housekeeping", "reinigung", "cleaner", "servicekraft",
                        "rezeption")),
    ("Retail", ("verkäufer", "verkäuferin", "sales associate", "store",
                "filiale", "cashier", "kassierer", "retail", "einzelhandel",
                "merchandiser", "shop assistant")),
    ("Education", ("teacher", "lehrer", "trainer", "dozent", "erzieher",
                   "tutor", "professor", "education", "lecturer", "kita",
                   "nachhilfe", "ausbilder", "pädagog")),
    ("Legal", ("legal", "counsel", "compliance", "paralegal", "jurist",
               "rechtsanwalt", "anwalt", "notar")),
    ("Finance & Accounting", ("financ", "accounting", "accountant",
                   "controller", "buchhalt", "fp&a", "treasury", "audit",
                   "steuer", "payroll", "lohn", "banker", "versicherung")),
    ("People & HR", ("human resources", " hr ", "talent", "recruit",
                     "personalreferent", "personalsachbearbeiter",
                     "personalwesen")),
    ("Marketing", ("marketing", "growth", "content", "brand", "seo",
                   "communications", "kommunikation", "social media")),
    ("Sales", ("sales", "account executive", "account manager",
               "business development", "vertrieb", "revenue", "commercial",
               "partnerships", "außendienst")),
    ("Customer Support", ("support", "customer success", "customer service",
                          "help desk", "kundenservice", "kundenbetreuung",
                          "call center", "servicemitarbeiter")),
    ("Administration", ("assistant", "assistenz", "sekretär", "sachbearbeiter",
                        "administration", "verwaltung", "office manager",
                        "empfang", "reception", "data entry")),
    ("Science & Research", ("research scientist", "laboratory", "chemist",
                        "chemiker", "biologist", "biologe", "physicist",
                        "clinical research", "forschung", "laborant",
                        "wissenschaftler")),
    ("Product", ("product manager", "product management", "product owner",
                 "program manager", "produktmanager")),
    ("Design", ("design", "ux", "ui ", "graphic", "creative", "kreativ",
                "art director")),
    ("Data & AI", ("data ", "analytics", "machine learning", " ml ", " ai ",
                   "data scientist", "data engineer", "analyst", "big data",
                   "künstliche intelligenz", " bi ")),
    ("Engineering", ("engineer", "developer", "software", "backend",
                     "frontend", "full stack", "devops", "sre", "platform",
                     "infrastructure", "cyber", "programmer", "entwickler",
                     "informatik")),
)


def normalize_category(department: Optional[str], title: Optional[str]) -> str:
    """Bucket a posting into a broad domain from its department and title.

    Department/team labels are free-text and vary by company, so we match
    keywords against them (and the title as a fallback) to produce a small,
    filterable set. Anything unmatched becomes 'Other'.
    """
    text = f" {(department or '')} {(title or '')} ".lower()
    for label, keywords in _CATEGORY_RULES:
        if any(k in text for k in keywords):
            return label
    return "Other"


# Seniority / experience level, detected from the title (and employment
# type). Ordered: the FIRST bucket whose pattern matches wins, so the
# junior-side buckets (internship, apprenticeship, junior) come first — a
# "Junior Project Manager" should read as Junior, not Manager.
_LEVEL_RULES = (
    ("Internship", r"\bintern(ship)?\b|praktik|praktikant|stagiaire|becari"),
    ("Apprenticeship", r"apprentice|apprenticeship|ausbildung|auszubildende|\bazubi\b|alternan|trainee|graduate (program|scheme|trainee)|duales? stud|dual study"),
    ("Working Student", r"working student|werkstudent|\bétudiant|\betudiant"),
    ("Junior / Entry", r"\bjunior\b|\bjr\b|entry[ -]level|einsteiger|d[ée]butant|\bgraduate\b|\bgrad\b"),
    ("Lead / Principal", r"\blead\b|principal|\bstaff\b|head of|\bhead\b|director|\bvp\b|vice president|chief|leiter|leitung|responsable|teamlead|tech lead"),
    ("Manager", r"manager|\bmgr\b|management|gestionnaire|leitende"),
    ("Senior", r"\bsenior\b|\bsnr\b|\bsr\b|erfahren|confirm[ée]|exp[ée]riment|experienced"),
)


def normalize_level(title: Optional[str],
                    employment_type: Optional[str] = None) -> Optional[str]:
    """Detect a seniority/experience level from the title (and job type).

    Returns one of a small, filterable set (Internship, Apprenticeship,
    Working Student, Junior / Entry, Senior, Lead / Principal, Manager), or
    None when the title carries no clear level signal — most postings don't,
    and those are simply left out of the level facet.
    """
    text = f" {(employment_type or '')} {(title or '')} ".lower()
    for label, pattern in _LEVEL_RULES:
        if re.search(pattern, text):
            return label
    return None


def make_dedup_key(title: str, company: str, location: Optional[str]) -> str:
    """Build a key that groups the *same* opening seen on different sources.

    The same role often appears on a company's ATS and on one or more job
    boards. Matching on (company, title, coarse location) lets us recognize
    those as one opening while keeping genuinely distinct roles separate.
    """
    parts = [_slug(company), _slug(title)]
    if location:
        # Keep only the first location token (city/region) to stay robust to
        # formatting differences like "Berlin, Germany" vs "Berlin".
        first = re.split(r"[,/|]", location)[0]
        parts.append(_slug(first))
    return ":".join(p for p in parts if p)
