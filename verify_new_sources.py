#!/usr/bin/env python3
"""Diagnostic: France Travail token — body creds vs HTTP Basic auth."""
from __future__ import annotations
import os, requests
from requests.auth import HTTPBasicAuth

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
cid = (os.getenv("FRANCETRAVAIL_CLIENT_ID") or "").strip()
sec = (os.getenv("FRANCETRAVAIL_CLIENT_SECRET") or "").strip()
scope = "api_offresdemploiv2 o2dsoffre"
print(f"client_id length: {len(cid)}   client_secret length: {len(sec)}")
print(f"client_id starts: {cid[:16]}...   secret starts: {sec[:6]}...\n")

print("== Method A: credentials in POST body ==")
r = requests.post(TOKEN_URL, params={"realm": "/partenaire"},
    data={"grant_type":"client_credentials","client_id":cid,"client_secret":sec,"scope":scope},
    headers={"Content-Type":"application/x-www-form-urlencoded"}, timeout=30)
print(f"  HTTP {r.status_code}  body: {r.text[:300]}")

print("\n== Method B: credentials as HTTP Basic auth ==")
r2 = requests.post(TOKEN_URL, params={"realm": "/partenaire"},
    data={"grant_type":"client_credentials","scope":scope},
    auth=HTTPBasicAuth(cid, sec),
    headers={"Content-Type":"application/x-www-form-urlencoded"}, timeout=30)
print(f"  HTTP {r2.status_code}  body: {r2.text[:300]}")
