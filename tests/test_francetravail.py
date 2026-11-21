"""Offline test: France Travail connector (OAuth token + offres search, mapping)."""
from jobmesh.connectors.francetravail import FranceTravailConnector


_OFFRE = {"id": "189FKLM", "intitule": "Développeur Python",
          "entreprise": {"nom": "SNCF"}, "lieuTravail": {"libelle": "Paris"},
          "origineOffre": {"urlOrigine": "https://candidat.francetravail.fr/offres/189FKLM"},
          "description": "Poste de dev", "salaire": {"libelle": "45k€"},
          "typeContratLibelle": "CDI", "romeLibelle": "Études et développement informatique",
          "dateCreation": "2026-11-19T00:00:00Z"}


class _Resp:
    def __init__(self, payload=None, status=200): self._p = payload; self.status_code = status
    def json(self): return self._p
    def raise_for_status(self): pass


class _Session:
    headers = {}
    def post(self, url, params=None, data=None, headers=None, timeout=None, **k):
        assert "access_token" in url
        return _Resp({"access_token": "TOKEN123"})
    def get(self, url, params=None, headers=None, timeout=None, **k):
        assert headers["Authorization"] == "Bearer TOKEN123"
        if params["range"].startswith("0-"):
            return _Resp({"resultats": [_OFFRE]})
        return _Resp(None, status=204)


def test_francetravail_maps(monkeypatch):
    monkeypatch.setenv("FRANCETRAVAIL_CLIENT_ID", "cid")
    monkeypatch.setenv("FRANCETRAVAIL_CLIENT_SECRET", "sec")
    jobs = FranceTravailConnector(session=_Session()).fetch()
    assert len(jobs) == 1
    a = jobs[0]
    assert a.source_job_id == "189FKLM"
    assert a.title == "Développeur Python"
    assert a.company == "SNCF"
    assert a.location == "Paris, France"
    assert a.source_url.endswith("189FKLM")
    assert a.posted_at.startswith("2026-11-19")
