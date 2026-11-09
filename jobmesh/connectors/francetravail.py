"""France Travail (ex-Pôle emploi) connector — France's public job board.

France's public employment service exposes its official "Offres d'emploi v2"
API. Free, but needs OAuth2 client credentials (self-service, instant, at
https://francetravail.io → create an app, subscribe to "Offres d'emploi v2").
Set them as env vars (never hard-coded):
    FRANCETRAVAIL_CLIENT_ID
    FRANCETRAVAIL_CLIENT_SECRET

Covers ALL sectors across France. `board` is ignored; use "all".
Docs: https://francetravail.io/data/api/offres-emploi
"""

from __future__ import annotations

import os

import requests

from ..models import Job, now_iso
from ..normalize import html_to_text, detect_remote, make_dedup_key
from .base import Connector

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
API = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE = "api_offresdemploiv2 o2dsoffre"
USER_AGENT = "jobmesh/0.1 (+https://github.com/; job index; contact via repo)"
TIMEOUT = 30
RANGE = 150        # France Travail max per request
MAX_PAGES = 7      # bounded: up to ~1,000 most-recent postings per run


def _creds() -> tuple[str, str]:
    cid = os.getenv("FRANCETRAVAIL_CLIENT_ID")
    sec = os.getenv("FRANCETRAVAIL_CLIENT_SECRET")
    if not cid or not sec:
        raise RuntimeError(
            "FRANCETRAVAIL_CLIENT_ID / FRANCETRAVAIL_CLIENT_SECRET not set. "
            "Register free at https://francetravail.io and set them as env vars.")
    return cid, sec


class FranceTravailConnector(Connector):
    platform = "francetravail"

    def __init__(self, board: str = "all", session: requests.Session | None = None):
        super().__init__(board)
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def _token(self) -> str:
        cid, sec = _creds()
        r = self._session.post(
            TOKEN_URL, params={"realm": "/partenaire"},
            data={"grant_type": "client_credentials", "client_id": cid,
                  "client_secret": sec, "scope": SCOPE},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()["access_token"]

    def fetch(self) -> list[Job]:
        at = now_iso()
        token = self._token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        jobs: list[Job] = []
        for page in range(MAX_PAGES):
            start = page * RANGE
            end = start + RANGE - 1
            r = self._session.get(API, params={"range": f"{start}-{end}"},
                                  headers=headers, timeout=TIMEOUT)
            if r.status_code == 204:
                break
            r.raise_for_status()
            res = (r.json() or {}).get("resultats") or []
            if not res:
                break
            jobs.extend(self._to_job(d, at) for d in res)
            if len(res) < RANGE:
                break
        return jobs

    def _to_job(self, d: dict, at: str) -> Job:
        title = d.get("intitule") or "(sans titre)"
        company = (d.get("entreprise") or {}).get("nom") or "Entreprise non précisée"
        location = (d.get("lieuTravail") or {}).get("libelle") or "France"
        if "france" not in location.lower():
            location = location + ", France"
        jid = str(d.get("id") or title)
        url = (d.get("origineOffre") or {}).get("urlOrigine")
        body = html_to_text(d.get("description"))
        return Job(
            source_platform=self.platform, source_board=self.board,
            source_job_id=jid,
            title=title, company=company, location=location, description=body,
            source_url=url, apply_url=url,
            salary=(d.get("salaire") or {}).get("libelle"),
            employment_type=d.get("typeContratLibelle") or d.get("typeContrat"),
            category=d.get("romeLibelle"),
            remote=detect_remote(location),
            posted_at=d.get("dateCreation"),
            dedup_key=make_dedup_key(title, company, location),
            first_seen=at, last_checked=at, is_open=True,
        )
