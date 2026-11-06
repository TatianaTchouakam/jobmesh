"""Best-effort mapping of a free-text job location to an ISO-2 country.

Job locations come in every shape ("Santa Clara, CA", "Remote, US",
"Berlin, DE", "Köln", "Anywhere in the World", "2 Locations"). This module
turns them into a country code good enough to light up a globe. It is
deliberately conservative: anything it can't place confidently returns
None (counted as "unknown"), and remote/anywhere strings are reported
separately so they don't masquerade as a country.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

# Strings that mean "no fixed country".
_REMOTE_RE = re.compile(
    r"\b(remote|anywhere|worldwide|work\s*from\s*home|wfh|distributed|global)\b",
    re.I,
)

# US state / territory postal codes -> United States.
_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC", "PR",
}
# Two-letter codes that clash between a US state and a country. For these we
# make a data-driven choice: our "CA/TX/NY…" volume is US tech (California,
# not Canada), while "DE" is overwhelmingly Germany in our feeds. So when a
# last token is one of these COUNTRY-first codes we read it as the country;
# every other US state code reads as the US.
_COUNTRY_FIRST = {
    "DE", "GB", "UK", "FR", "NL", "IE", "ES", "IT", "PL", "PT", "SE", "CH",
    "AT", "BE", "DK", "NO", "FI", "CZ", "RO", "HU", "GR", "SG", "AU", "NZ",
    "JP", "CN", "HK", "KR", "IL", "AE", "ZA", "TR", "UA", "PH", "MY", "VN",
    "TH", "NG", "KE", "EG", "CO", "CL", "LU", "BG", "HR", "SK", "SI", "EE",
    "LT", "LV", "RS", "BR", "AR", "MX",
}

# Country names and ISO codes -> ISO-2. Lowercased keys.
_COUNTRY = {
    "united states": "US", "usa": "US", "u.s.": "US", "u.s.a.": "US",
    "us": "US", "america": "US", "united states of america": "US",
    "united kingdom": "GB", "uk": "GB", "u.k.": "GB", "gb": "GB",
    "britain": "GB", "great britain": "GB", "england": "GB",
    "scotland": "GB", "wales": "GB", "northern ireland": "GB",
    "germany": "DE", "deutschland": "DE", "de": "DE",
    "france": "FR", "fr": "FR",
    "netherlands": "NL", "the netherlands": "NL", "holland": "NL", "nl": "NL",
    "ireland": "IE", "ie": "IE",
    "spain": "ES", "españa": "ES", "espana": "ES", "es": "ES",
    "italy": "IT", "italia": "IT", "it": "IT",
    "poland": "PL", "polska": "PL", "pl": "PL",
    "portugal": "PT", "pt": "PT",
    "sweden": "SE", "se": "SE",
    "switzerland": "CH", "schweiz": "CH", "ch": "CH",
    "austria": "AT", "österreich": "AT", "osterreich": "AT", "at": "AT",
    "belgium": "BE", "belgië": "BE", "be": "BE",
    "denmark": "DK", "dk": "DK",
    "norway": "NO", "no": "NO",
    "finland": "FI", "fi": "FI",
    "czech republic": "CZ", "czechia": "CZ", "cz": "CZ",
    "romania": "RO", "ro": "RO",
    "hungary": "HU", "hu": "HU",
    "greece": "GR", "gr": "GR",
    "canada": "CA", "ca": "CA",
    "mexico": "MX", "méxico": "MX", "mx": "MX",
    "brazil": "BR", "brasil": "BR", "br": "BR",
    "argentina": "AR", "ar": "AR",
    "india": "IN", "in": "IN",
    "singapore": "SG", "sg": "SG",
    "australia": "AU", "au": "AU",
    "new zealand": "NZ", "nz": "NZ",
    "japan": "JP", "jp": "JP",
    "china": "CN", "cn": "CN",
    "hong kong": "HK", "hk": "HK",
    "south korea": "KR", "korea": "KR", "kr": "KR",
    "israel": "IL", "il": "IL",
    "united arab emirates": "AE", "uae": "AE", "dubai": "AE", "ae": "AE",
    "south africa": "ZA", "za": "ZA",
    "turkey": "TR", "türkiye": "TR", "tr": "TR",
    "ukraine": "UA", "ua": "UA",
    "philippines": "PH", "ph": "PH",
    "indonesia": "ID", "id": "ID",
    "malaysia": "MY", "my": "MY",
    "vietnam": "VN", "vn": "VN",
    "thailand": "TH", "th": "TH",
    "nigeria": "NG", "ng": "NG",
    "kenya": "KE", "ke": "KE",
    "egypt": "EG", "eg": "EG",
    "colombia": "CO", "co": "CO",
    "chile": "CL", "cl": "CL",
    "luxembourg": "LU", "lu": "LU",
    "bulgaria": "BG", "bg": "BG",
    "croatia": "HR", "hr": "HR",
    "slovakia": "SK", "sk": "SK",
    "slovenia": "SI", "si": "SI",
    "estonia": "EE", "ee": "EE",
    "lithuania": "LT", "lt": "LT",
    "latvia": "LV", "lv": "LV",
    "serbia": "RS", "rs": "RS",
}

# A few well-known cities -> country, to rescue bare-city locations.
_CITIES = {
    "berlin": "DE", "münchen": "DE", "munich": "DE", "hamburg": "DE",
    "köln": "DE", "cologne": "DE", "frankfurt": "DE", "stuttgart": "DE",
    "hannover": "DE", "düsseldorf": "DE", "bielefeld": "DE", "leipzig": "DE",
    "london": "GB", "manchester": "GB", "edinburgh": "GB",
    "paris": "FR", "lyon": "FR", "amsterdam": "NL", "madrid": "ES",
    "barcelona": "ES", "milan": "IT", "rome": "IT", "dublin": "IE",
    "lisbon": "PT", "warsaw": "PL", "vienna": "AT", "zurich": "CH",
    "stockholm": "SE", "copenhagen": "DK", "oslo": "NO", "helsinki": "FI",
    "new york": "US", "san francisco": "US", "seattle": "US", "austin": "US",
    "boston": "US", "chicago": "US", "los angeles": "US", "toronto": "CA",
    "vancouver": "CA", "bangalore": "IN", "bengaluru": "IN", "mumbai": "IN",
    "singapore": "SG", "sydney": "AU", "melbourne": "AU", "tokyo": "JP",
}


# ISO-2 -> display name, for the globe's labels.
COUNTRY_NAME = {
    "US": "United States", "GB": "United Kingdom", "DE": "Germany",
    "FR": "France", "NL": "Netherlands", "IE": "Ireland", "ES": "Spain",
    "IT": "Italy", "PL": "Poland", "PT": "Portugal", "SE": "Sweden",
    "CH": "Switzerland", "AT": "Austria", "BE": "Belgium", "DK": "Denmark",
    "NO": "Norway", "FI": "Finland", "CZ": "Czechia", "RO": "Romania",
    "HU": "Hungary", "GR": "Greece", "CA": "Canada", "MX": "Mexico",
    "BR": "Brazil", "AR": "Argentina", "IN": "India", "SG": "Singapore",
    "AU": "Australia", "NZ": "New Zealand", "JP": "Japan", "CN": "China",
    "HK": "Hong Kong", "KR": "South Korea", "IL": "Israel",
    "AE": "United Arab Emirates", "ZA": "South Africa", "TR": "Turkey",
    "UA": "Ukraine", "PH": "Philippines", "MY": "Malaysia", "VN": "Vietnam",
    "TH": "Thailand", "NG": "Nigeria", "KE": "Kenya", "EG": "Egypt",
    "CO": "Colombia", "CL": "Chile", "LU": "Luxembourg", "BG": "Bulgaria",
    "HR": "Croatia", "SK": "Slovakia", "SI": "Slovenia", "EE": "Estonia",
    "LT": "Lithuania", "LV": "Latvia", "RS": "Serbia", "ID": "Indonesia",
}


def is_remote(location: Optional[str]) -> bool:
    return bool(location and _REMOTE_RE.search(location))


def country_patterns(code: str) -> list[str]:
    """SQL LIKE patterns that match a location string for this country.

    Used to filter the index by country without a schema change: it unions
    the country's spelled names, its "City, XX" code suffix and known
    cities. Best-effort, mirroring resolve_country's heuristics.
    """
    code = (code or "").upper()
    pats: set[str] = set()
    if not code:
        return []
    pats.add(f"%, {code}")
    pats.add(f"%,{code}")
    for name, c in _COUNTRY.items():
        if c == code and len(name) > 3:
            pats.add(f"%{name}%")
    for city, c in _CITIES.items():
        if c == code:
            pats.add(f"%{city}%")
    if code == "US":
        pats.add("%, USA%")
        for st in _US_STATES:
            # Skip state codes that clash with a country we read as that
            # country (e.g. DE = Delaware vs Germany), to avoid false US hits.
            if st not in _COUNTRY_FIRST:
                pats.add(f"%, {st}")
    return list(pats)


def resolve_country(location: Optional[str]) -> Optional[str]:
    """Return an ISO-2 country code for a location string, or None.

    None means "couldn't place it" (including pure-remote strings).
    """
    if not location:
        return None
    raw = location.strip()
    # Split on commas / slashes / semicolons / pipes.
    parts = [p.strip() for p in re.split(r"[,/;|]", raw) if p.strip()]
    if not parts:
        return None

    # 1) A spelled-out country name anywhere wins (len>2 rules out bare codes).
    for p in parts:
        key = p.lower()
        if key in _COUNTRY and len(key) > 3:
            return _COUNTRY[key]

    last = parts[-1].strip().upper()

    # 2) Last token is a country-first code (DE->Germany, GB, FR, ...).
    if last in _COUNTRY_FIRST:
        return _COUNTRY[last.lower()]

    # 3) Last token is a US state postal code (CA, TX, NY ... -> US).
    if last in _US_STATES:
        return "US"

    # 4) Last token is any other 2-letter country code.
    if len(last) == 2 and last.lower() in _COUNTRY:
        return _COUNTRY[last.lower()]

    # 5) Known city anywhere.
    for p in parts:
        key = p.lower()
        if key in _CITIES:
            return _CITIES[key]

    # 6) A US state code anywhere, as a last resort.
    for p in parts:
        if p.upper() in _US_STATES:
            return "US"

    return None


def aggregate(location_counts: dict[str, int]) -> dict:
    """Turn {location_string: count} into country/remote/unknown totals."""
    by_country: Counter = Counter()
    remote = 0
    unknown = 0
    for loc, n in location_counts.items():
        code = resolve_country(loc)
        if code:
            by_country[code] += n
        elif is_remote(loc):
            remote += n
        else:
            unknown += n
    return {
        "countries": dict(by_country),
        "remote": remote,
        "unknown": unknown,
        "placed": sum(by_country.values()),
    }
