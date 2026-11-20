"""Tests for the Comeet connector (keyless hosted-page + uid:token API)."""

import json

from jobmesh.connectors.comeet import ComeetConnector

POSITIONS = [
    {
        "uid": "AC.F50",
        "name": "Account Executive EU",
        "department": "Sales",
        "company_name": "TripleTen",
        "location": {"name": "Poland", "city": "Warszawa", "country": "PL", "is_remote": True},
        "employment_type": "Full-time",
        "experience_level": "Intermediate",
        "workplace_type": "remote",
        "url_comeet_hosted_page": "https://www.comeet.com/jobs/tripleten/98.008/ae/AC.F50",
        "time_updated": "2026-11-18T00:00:00Z",
        "is_internal": False,
    },
    {  # internal posting -> must be skipped
        "uid": "IN.001", "name": "Secret", "company_name": "TripleTen",
        "location": {"name": "HQ"}, "is_internal": True,
    },
]

PAGE = (
    "<html><head><script>"
    "var COMPANY_DATA = {\"name\":\"TripleTen\",\"uid\":\"98.008\"};\n"
    "var COMPANY_POSITIONS_DATA = " + json.dumps(POSITIONS) + ";\n"
    "</script></head></html>"
)


class _Resp:
    def __init__(self, text):
        self.text = text
    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, text):
        self.headers = {}
        self._text = text
        self.calls = []
    def get(self, url, timeout=None, params=None):
        self.calls.append(url)
        return _Resp(self._text)


def test_comeet_hosted_page_keyless():
    conn = ComeetConnector("tripleten/98.008", session=_FakeSession(PAGE))
    jobs = conn.fetch()
    # the internal posting is filtered out -> 1 job
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source_platform == "comeet"
    assert j.source_board == "tripleten/98.008"  # token-free, matches config board
    assert j.source_job_id == "AC.F50"
    assert j.title == "Account Executive EU"
    assert j.company == "TripleTen"
    assert j.location == "Poland"
    assert j.remote is True
    assert j.workplace_type == "remote"
    assert j.category == "Sales"
    assert "tripleten/98.008" in j.source_url
    # the request hit the keyless hosted page, not the token API
    assert sess_called_page(conn)


def sess_called_page(conn):
    return conn._page_path == "tripleten/98.008" and conn.token == ""


def test_comeet_board_parsing_token_mode():
    conn = ComeetConnector("E5.007:TOKEN123:Acme")
    assert conn.uid == "E5.007"
    assert conn.token == "TOKEN123"
    assert conn.company_name == "Acme"
