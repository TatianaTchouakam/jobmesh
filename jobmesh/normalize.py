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
