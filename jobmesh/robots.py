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

import re

import requests

# Real, identifiable agent with a contact URL (transparency).
USER_AGENT = "JobmeshBot/0.1 (+https://github.com/TatianaTchouakam/jobmesh)"
UA_TOKEN = "JobmeshBot"  # token robots.txt groups are matched against

_WILDCARD_CACHE: dict[str, "re.Pattern"] = {}


def _rule_matches(rule_path: str, norm: str) -> bool:
    """RFC 9309 path matching for one rule line.

    ``*`` matches any run of characters and ``$`` anchors the end. urllib's own
    matcher only does a literal prefix test, so it misses the very common
    ``Allow: */JobBoard/`` style (a leading/embedded wildcard) that operators
    rely on. We honour the wildcards for such patterns and fall back to a plain
    prefix test for ordinary paths.
    """
    # urllib percent-encodes the wildcard metacharacters when it parses the
    # rule (``*`` -> ``%2A``, ``$`` -> ``%24``); restore them so we can honour
    # them. The literal segments stay encoded, matching the encoded ``norm``.
    rule_path = rule_path.replace("%2A", "*").replace("%2a", "*").replace("%24", "$")
    if "*" not in rule_path and "$" not in rule_path:
        return norm.startswith(rule_path)
    rx = _WILDCARD_CACHE.get(rule_path)
    if rx is None:
        out = []
        for ch in rule_path:
            if ch == "*":
                out.append(".*")
            elif ch == "$":
                out.append(r"\Z")
            else:
                out.append(re.escape(ch))
        rx = re.compile("".join(out))
        _WILDCARD_CACHE[rule_path] = rx
    return rx.match(norm) is not None


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
            # Python 3.14+ keeps the "*" group in rp.entries (Entry.applies_to
            # no longer matches it), so look it up explicitly.
            entry = next((e for e in rp.entries if "*" in e.useragents), None)
        if entry is None:
            # Couldn't identify the applicable group via urllib internals
            # (their layout shifts between Python versions, e.g. the "*" group
            # moved in 3.14). Defer to urllib's own canonical decision rather
            # than assuming "allowed", so a blanket Disallow is always honoured.
            return rp.can_fetch(ua_token, url)
        best_len, best_allow = -1, True
        for rl in entry.rulelines:
            if _rule_matches(rl.path, norm):
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
