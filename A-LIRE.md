# À LIRE — lot « contrôle technique » du 26/11/2026

Dernier gros lot avant soumission Vaya. **Rien n'a été poussé** — c'est toi qui
fais `git push`, **un seul**, quand tout est validé (voir la fin). Aucune
mention d'IA nulle part. Tests : **197 verts**.

## 1. Critères du challenge → où Jobmesh les remplit → preuve

| Critère | Statut | Preuve (à vérifier en ligne) |
|---|---|---|
| Connecteurs multi-employeurs | ✅ | 90 employeurs réels ajoutés sur 11 connecteurs · `jobmesh.world/status` |
| Champs d'offre complets (titre, entreprise, lieu, lien, date) | ✅ | `jobmesh.world/jobs?q=data&limit=3` |
| Mise à jour automatique | ✅ | cadence **4 h** + verrou · `/status` affiche « prochaine MAJ dans X h » |
| Déduplication | ✅ | `/stats` → `duplicate_open_postings` |
| API de recherche (filtres + pagination) | ✅ | `/jobs` (q, country, remote, level, since, limit/offset) · doc `/api` |
| Handoff + coûts d'exploitation | ✅ | `HANDOFF.md` (coûts à jour ci-dessous) |
| Intégrité (échec ≠ offres fermées) | ✅ | `/status` : raison exacte par plateforme, 67/78 honnête |
| Serveur MCP | ✅ | publié au registre officiel · `POST /mcp` |

## 2. JobSweep vs Jobmesh (chiffres vérifiés uniquement)

> Chiffres Jobmesh = mesurés sur le site live. Chiffres JobSweep = **relevés sur
> sa page Vaya le 26/11** (à reconfirmer) ; « non publié » = pas trouvé en public.

| Point | JobSweep | Jobmesh |
|---|---|---|
| Offres ouvertes | ~1,35 M (page Vaya) | **~121 000** (live, en hausse) |
| Employeurs | ~21 000 (page Vaya) | **~8 250** |
| Plateformes | 76/78 (page Vaya) | **67/78** documentées + raison |
| Fraîcheur | re-check 6–12 h | **4 h**, affichée |
| API REST documentée | ✅ | ✅ `/api` |
| Serveur MCP (registre) | ✅ | ✅ |
| Export CSV **et** JSON | ✅ | ✅ `/export.csv` + `/export.json` |
| Déduplication | ✅ | ✅ |
| Multilingue | EN | **EN/DE/FR** |
| CV-matcher | non publié | ✅ |
| Open source | non publié | ✅ MIT |
| RapidAPI / Apify | ✅ | **préparé** (non publié) — voir `distribution/` |
| Coût | non publié | ~25 $/mois (Standard) + disque |

**Là où on gagne** : fraîcheur affichée par état, intégrité documentée (67/78 +
raison vs 76–78 potentiellement gonflés), multilingue, CV-match, open source,
MCP + API tous deux documentés. **Où on ne peut pas gagner (volume)** : on
compense par la **qualité** (dédupliqué, liens vers la source, filtres utiles).

## 3. Ce qui a changé dans ce lot

- **Infra** : `render.yaml` aligné sur **Standard (2 Go) + disque 10 Go**, build
  court (pip install seul, pas d'ingest au build), cadence **4 h**, caps relevés
  (`INGEST_MAX_BOARDS=3000`, `INGEST_WORKERS=6`).
- **Recherche** : `?q=` reconnu (alias de `keyword`), tri **titre d'abord**.
- **Routes** : `/robots.txt`, `/sitemap.xml`, `/export.json` (feed agences
  paginé, Premium), pages **404/500** propres (HTML pour le navigateur, JSON
  pour l'API). `/health` existait déjà.
- **Mêmes chiffres partout** : accueil et `/status` lisent la même source
  (`/stats`) ; pendant un ingest, les deux affichent **« mise à jour en cours »**
  (plus de chiffres partiels présentés comme finaux).
- **Distribution** : `distribution/` (OpenAPI, actor Apify, how-to FR).

## 4. Chiffres du jour (26/11, live)

~121 000 offres ouvertes · ~8 250 entreprises · 7 581 doublons fusionnés ·
35 plateformes avec offres · 67/78 live. Chiffres live : `jobmesh.world/status`.

## 5. Mémoire & base (à mesurer au prochain ingest Standard)

- Taille de la base, dans le **Shell Render** : `ls -lah /var/data/jobmesh.db`.
- Pic mémoire pendant l'ingest : **Render → Metrics → Memory** (objectif < 1,5 Go
  sur les 2 Go). Avec `INGEST_WORKERS=6` et l'écriture par lots (commit par
  chunk), on reste loin de la limite ; si tu montes les workers, re-regarde ce
  pic. Note le ici après le prochain cycle.

## 6. Variables à régler dans Render (si pas déjà via le blueprint)

`INGEST_INTERVAL_HOURS=4` · `INGEST_MAX_BOARDS=3000` · `INGEST_WORKERS=6` ·
`JOBMESH_DB=/var/data/jobmesh.db` (déjà). Le disque **10 Go** et le plan
**Standard** sont dans `render.yaml` → le blueprint ne les fera pas redescendre.

## 7. À vérifier EN LIGNE après le push

`/` · `/jobs?q=data` · `/status` · `/stats` · `/api` · `/export.csv` ·
`/export.json` · `/mcp` · `/robots.txt` · `/sitemap.xml` · `/health` ·
une page inexistante (doit afficher la page 404 propre).

---

## ⚠️ UN SEUL PUSH

Quand tu as tout relu : **un seul** `git push`. Render redéploiera (build court),
l'ingest de fond remplira `/var/data` à la cadence de 4 h. Ne pousse pas avant
d'être prête.
