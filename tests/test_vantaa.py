"""Offline test: City of Vantaa open jobs JSON API."""
from jobmesh.connectors.vantaa import VantaaConnector

_ROWS = [
    {"id": 1, "organisaatio": "Kasvatus ja oppiminen", "ammattiala": "Opetusala",
     "tyotehtava": "Tuntiopettaja, Varia", "osoite": "Tennistie 1, 01370 Vantaa",
     "haku_paattyy_pvm": "2026-12-03",
     "linkki": "https://vantaa.rekrytointi.com/paikat/?o=A_RJ&jgid=1&jid=18796"},
    {"id": 2, "organisaatio": "Tekniikka", "ammattiala": "Tekniset",
     "tyotehtava": "Insinööri", "osoite": "Vantaa",
     "linkki": "https://vantaa.rekrytointi.com/paikat/?jid=18800"},
]


class _Resp:
    status_code = 200
    def __init__(self, payload=None, text=""): self._p = payload; self.text = text
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def get(self, url, timeout=None, **k):
        if url.endswith("robots.txt"):
            return _Resp(text="")  # 404/empty -> allowed
        assert url.endswith("/rest/tyopaikat/v1/kaikki")
        return _Resp(payload=_ROWS)


def test_vantaa_maps():
    jobs = VantaaConnector(session=_Session()).fetch()
    assert len(jobs) == 2
    a = jobs[0]
    assert a.source_job_id == "18796"             # jid from URL, not list index
    assert a.title == "Tuntiopettaja, Varia"
    assert a.company == "City of Vantaa"
    assert a.location.startswith("Tennistie")
    assert a.source_url.endswith("jid=18796")
    assert jobs[1].source_job_id == "18800"
