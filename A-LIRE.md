# À LIRE — mise à jour du 26/11/2026

Objectif : sécuriser la victoire Vaya (critères « Automatic updates », preuve
publique, Docker, MCP, intégrité des sources). **Rien n'a été poussé** — c'est
toi qui fais `git push`. Aucune soumission du challenge n'a été faite.

## Ce qui a changé (6 commits, à ton nom)

1. **Mise à jour planifiée** — l'index se rafraîchit tout seul toutes les 6 h
   (variable `INGEST_INTERVAL_HOURS=6`, déjà dans `render.yaml`), avec un
   **verrou** anti-double-ingest. La page d'accueil et `/status` affichent
   « dernière mise à jour il y a X h ». Un fetch en échec reste une erreur de
   fetch, il ne ferme jamais les offres en masse.
2. **Page publique `/status`** — couverture **68/78** avec le tableau des
   plateformes (en ligne / en attente d'accès + **raison** exacte), offres,
   entreprises, doublons, fermetures, dernière MAJ et durée du dernier ingest.
   Liée depuis l'accueil (indicateur « live » cliquable) et le README.
3. **Docker** — `Dockerfile` + `docker-compose.yml` (services **api** et
   **ingest** planifié, volume partagé). `docker compose up --build`.
4. **MCP** — le serveur `/mcp` existait déjà (vérifié : outils `search_jobs`,
   `index_stats`, `source_coverage`) ; ajout d'une section dédiée au README et
   d'un pointeur sur `/status`.
5. **PARTNERSHIPS.md** — **10 e-mails** d'accès, un par plateforme bloquée,
   signés à ton nom (voir ci-dessous).
6. **Chiffres du jour** — COVERAGE.md et le README mis à jour avec les vrais
   chiffres (193 078 offres ouvertes, 28 737 entreprises, 68/78 actives).

## À faire sur ton Mac (dans l'ordre)

```bash
cd ~/projects/Vaya/jobmesh

# 1) lancer les tests (doivent être verts)
.venv/bin/python -m pytest -q

# 2) ingest complet + chiffres du jour (réseau requis, donc sur ton Mac)
.venv/bin/python -m jobmesh.cli ingest
.venv/bin/python -m jobmesh.cli stats        # recopie les chiffres si besoin dans COVERAGE.md

# 3) pousser (déclenche le redéploiement Render)
git push
```

## Vérifier que la mise à jour planifiée tourne (après le push)

- Sur **Render**, la variable `INGEST_INTERVAL_HOURS` doit valoir `6` (elle est
  déjà déclarée dans `render.yaml`).
- Dans les **logs Render** au démarrage, tu dois voir :
  `background index refresh enabled: every 6 h`.
- Le **premier** rafraîchissement planifié a lieu **6 h après** le démarrage
  (le déploiement, lui, fait déjà un ingest). Ensuite, `jobmesh.world/status`
  affiche « Last refreshed … » qui se rapproche après chaque cycle.
- Astuce pour tester vite : mettre temporairement `INGEST_INTERVAL_HOURS=0.1`
  (~6 min) sur Render, vérifier que `/status` bouge, puis remettre `6`.

## Les 10 e-mails à envoyer (toi-même)

Tout est prêt dans **`PARTNERSHIPS.md`** — un e-mail court et signé par
plateforme : Cornerstone (CSOD), BrassRing, UKG/UltiPro, Paycom, talentReef
(déjà contacté — Mitratech), Paradox/Workday, Paycor/Paychex, Talenetic,
CareerSiteCloud, eJobBoard. Avant d'envoyer, vérifie l'adresse/contact actuel
sur le site de chaque éditeur (indiqué à côté de chaque e-mail).

## Rappel sécurité (rapide)

- **Régénérer** la clé secrète **Stripe** et le **secret PayPal** (ils sont
  passés en clair dans le chat), puis remettre les nouvelles valeurs dans Render.

## Et surtout

- **Ne pas** cliquer « Submit for review » sur Vaya tant que tu n'es pas prête.
  Tu as jusqu'au **30 novembre**.
