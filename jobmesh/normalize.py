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
#: department/team text and its title.
_CATEGORY_RULES = (
    ("Data & AI", ("data", "analytics", "machine learning", " ml ", "ai ",
                   "scientist", "analyst")),
    ("Engineering", ("engineer", "developer", "software", "backend",
                     "frontend", "full stack", "devops", "sre", "platform",
                     "infrastructure", "security", "qa", "programmer")),
    ("Design", ("design", "ux", "ui ", "researcher", "creative")),
    ("Product", ("product manager", "product management", "product owner",
                 "program manager")),
    ("Sales", ("sales", "account executive", "account manager",
               "business development", "revenue", "commercial", "partnerships")),
    ("Marketing", ("marketing", "growth", "content", "brand", "seo",
                   "communications", "social media")),
    ("Finance", ("finance", "accounting", "accountant", "controller",
                 "fp&a", "treasury", "audit")),
    ("People & HR", ("people", "human resources", " hr ", "talent",
                     "recruit", "recruiter")),
    ("Operations", ("operations", " ops", "logistics", "supply",
                    "procurement", "facilities")),
    ("Customer Support", ("support", "customer success", "customer service",
                          "help desk")),
    ("Legal", ("legal", "counsel", "compliance", "paralegal")),
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
