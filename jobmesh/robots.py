"""Polite, honest robots.txt handling shared by the connectors.

Jobmesh identifies itself with a real, contactable User-Agent and obeys
each source's robots.txt for that identity. A missing or unreachable
robots.txt is treated as "allowed" (the web convention); any explicit
Disallow for our agent (or for ``*``) is respected.

Beyond the letter of robots.txt, Jobmesh also declines sources whose
robots.txt blocks job-aggregator crawlers by name (even when a generic
``User-agent: *`` rule would still permit us) — crawling those would go
against the operator's clear intent. Such sources are left out of the
config rather than filtered here; see COVERAGE.md.
"""

from __future__ import annotations

import threading
from urllib.parse import quote, unquote, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests

# Real, identifiable agent with a contact URL (transparency).
USER_AGENT = "JobmeshBot/0.1 (+https://github.com/TatianaTchouakam/jobmesh)"
UA_TOKEN = "JobmeshBot"  # token robots.txt groups are matched against

_cache: dict[str, RobotFileParser | None] = {}
_lock = threading.Lock()


def _parser(origin: str, session: requests.Session) -> RobotFileParser | None:
    with _lock:
        if origin in _cache:
            return _cache[origin]
    rp: RobotFileParser | None = RobotFileParser()
    try:
        r = session.get(f"{origin}/robots.txt", timeout=10)
        if r.status_code >= 400 or not r.text.strip():
            rp = None  # no robots.txt -> allowed by convention
        else:
            rp.parse(r.text.splitlines())
    except Exception:
        rp = None  # unreachable/malformed -> fail open (allow), like major crawlers
    with _lock:
        _cache[origin] = rp
    return rp


def _longest_match_allowed(rp: RobotFileParser, ua_token: str, url: str) -> bool:
    """RFC 9309 decision: the most specific (longest) matching rule wins,
    ties go to Allow. Python's urllib uses first-rule-in-file-order instead,
    which wrongly blocks the common ``Disallow: /`` + ``Allow: /careers/``
    pattern that operators use to expose exactly their public career pages.
    We reuse urllib's fetching, UA-group selection and wildcard matching, and
    only replace the allow/deny decision. Falls back to urllib on any
    internals mismatch."""
    try:
        # Normalise the path exactly as urllib's can_fetch does.
        pr = urlparse(unquote(url))
        norm = quote(urlunparse(("", "", pr.path, pr.params, pr.query, pr.fragment))) or "/"
        # Most specific applicable UA group (named beats the "*" default).
        entry = None
        for e in rp.entries:
            if e.applies_to(ua_token):
                entry = e
                break
        if entry is None:
            entry = rp.default_entry
        if entry is None:
            return True
        best_len, best_allow = -1, True
        for rl in entry.rulelines:
            if rl.applies_to(norm):
                plen = len(rl.path)
                if plen > best_len or (plen == best_len and rl.allowance and not best_allow):
                    best_len, best_allow = plen, rl.allowance
        return best_allow if best_len >= 0 else True
    except Exception:
        return rp.can_fetch(ua_token, url)


def allowed(url: str, session: requests.Session, ua_token: str = UA_TOKEN) -> bool:
    """True if robots.txt permits ``ua_token`` to fetch ``url`` (RFC 9309)."""
    parts = urlparse(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    rp = _parser(origin, session)
    if rp is None:
        return True
    return _longest_match_allowed(rp, ua_token, url)
