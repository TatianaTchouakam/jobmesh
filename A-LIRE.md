# À LIRE — persistance Turso (26/11/2026)

Correctif du point 3 (« Closed detected : 0 »). La base SQLite est désormais une
**réplique locale d'une base Turso** (libSQL) : tirée au démarrage, poussée
après écriture → elle **survit aux redéploiements**. Activée seulement si
`JOBMESH_DB_URL` est défini ; sinon, SQLite local comme avant. Aucun code de
requête n'a changé (un petit adaptateur garde `row["col"]`, `dict(r)`, etc.).

## 1) Tester EN LOCAL d'abord (sur ton Mac, rien en prod)

```bash
cd ~/projects/Vaya/jobmesh
export JOBMESH_DB_URL="libsql://jobmesh-tatianatchouakam.aws-eu-west-1.turso.io"
export JOBMESH_DB_TOKEN="<ton token Turso>"

rm -f jobmesh.db jobmesh.db-*                 # repartir propre
.venv/bin/python -m jobmesh.cli ingest        # écrit dans Turso
.venv/bin/python -m jobmesh.cli stats         # affiche les chiffres
```

Puis **la preuve de persistance** — on efface la base locale et on relit :

```bash
rm -f jobmesh.db jobmesh.db-*
.venv/bin/python -m jobmesh.cli stats
```

Si `stats` **réaffiche les chiffres** alors que le fichier local a été supprimé,
c'est gagné : les données ont été rechargées depuis Turso. Dis-moi le résultat.

## 2) Activer en PROD (seulement après que le test local marche)

Dans le dashboard **Render → Environment**, ajouter :
- `JOBMESH_DB_URL` = l'URL libSQL ci-dessus
- `JOBMESH_DB_TOKEN` = ton token (secret)

puis « Manual Deploy ». Dès lors, le catalogue et l'historique des fermetures
persistent entre les déploiements.

---

# À LIRE — fiabilisation du 26/11/2026 (après-midi)

Après vérification de **jobmesh.world/status**. **Rien poussé** — tu fais `git push`. Tests verts (197).

## Les 3 points traités

1. **Trop de sources en échec au dernier ingest (73).**
   Cause : sur le plan **gratuit** de Render (CPU/mémoire limités), 12 fetchs
   en parallèle provoquent des timeouts. Correctif :
   - **Retries avec backoff** sur les seules erreurs *transitoires* (timeout,
     429, 5xx) — 3 tentatives max, délai progressif. Les 4xx délibérés
     (403/404/410) échouent tout de suite, jamais harcelés. **Aucune
     protection, limite de débit ni robots.txt contournés.**
   - **Concurrence réduite sur Render** (`INGEST_WORKERS=6` dans `render.yaml`).
   Rappel important : un fetch en échec **ne ferme jamais** les offres et
   **ne baisse pas la couverture** — les offres récentes restent indexées.

2. **67/78 (et non 68).** CareerPlug est passé en page « client-rendered »
   (re-vérifié le 26/11 : 0 offre, aucune route publique propre) → non
   réparable proprement, rétrogradé. Tous les chiffres sont alignés sur **67**
   (COVERAGE.md, README, page /status qui lit le registre en direct).

3. **« Closed detected : 0 ».** La base SQLite est recréée à **chaque
   redéploiement** (disque éphémère sur Render gratuit) → aucun historique,
   donc aucune fermeture détectée.
   **Solution recommandée (gratuite, ~10 min) : Turso** (base *libSQL*,
   compatible SQLite — quasi aucun changement de code) :
   - créer une base Turso gratuite → récupérer l'URL + le token ;
   - sur Render : définir `JOBMESH_DB_URL` et `JOBMESH_DB_TOKEN` ;
   - `pip install libsql-experimental`, puis brancher `storage` dessus.
   La base survit alors aux redéploiements → fermetures détectées + historique
   conservé. *Alternative :* `litestream` réplique le SQLite vers un bucket
   gratuit (Cloudflare R2).
   **Non implémenté ici** : il faut d'abord **ton** compte Turso. Dis-moi quand
   c'est créé et je branche le code (petit commit, à ton nom).

## Divers
- **Catalogue en ligne augmenté** : `INGEST_MAX_BOARDS` 1000 → **2000** et
  `INGEST_WORKERS` → **8** (`render.yaml`). Laisse passer plus de `join`
  (~3040 boards au lieu de 2040). Hausse mesurée : sur Render gratuit le
  service s'endort après ~15 min, donc on évite un ingest trop long.
  Le vrai gain viendra de **Turso** (base persistante) qui laissera le
  catalogue s'accumuler entre les runs au lieu de repartir de zéro.
- Binaire `mcp-publisher` ajouté au `.gitignore` (ne pas versionner).

---

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
2. **Page publique `/status`** — couverture **67/78** avec le tableau des
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
   chiffres (193 078 offres ouvertes, entreprises, 67/78 actives).

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
