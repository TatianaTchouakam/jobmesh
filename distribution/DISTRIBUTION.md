# Distribution de l'API Jobmesh — étapes à faire toi-même

Rien n'est publié automatiquement. Ces fichiers sont prêts ; voici comment les
mettre en ligne quand tu veux. Tout utilise l'API **publique et gratuite** de
Jobmesh (`https://jobmesh.world/jobs`), en lecture seule, sans scraping.

## 1. RapidAPI (lister l'API)

Fichier prêt : `distribution/openapi.yaml` (spec OpenAPI 3.0).

1. Crée un compte sur https://rapidapi.com/ → **My APIs** → **Add New API**.
2. Choisis **Import from OpenAPI** et téléverse `distribution/openapi.yaml`.
3. Base URL : `https://jobmesh.world`. Laisse l'endpoint `/jobs` en **public /
   gratuit** (pas de clé). Les feeds `/export.json` et `/export.csv` restent
   réservés Premium (clé Jobmesh).
4. Renseigne la description, la catégorie « Jobs / Data », quelques exemples
   (déjà dans la spec). Publie.

## 2. Apify (actor)

Dossier prêt : `distribution/apify-actor/` (actor + `main.js` qui pagine `/jobs`).

1. Installe le CLI : `npm i -g apify-cli`, puis `apify login`.
2. Dans `distribution/apify-actor/`, lance `apify push`.
3. Sur le Store Apify, mets l'actor en **gratuit** ou au prix que tu veux ;
   il n'appelle que l'API publique de Jobmesh.

## 3. Zapier / Make (automatisations)

Pas de fichier à publier : n'importe qui peut brancher Jobmesh via un module
**Webhooks / HTTP GET** :
- URL : `https://jobmesh.world/jobs?q=data%20engineer&country=DE&limit=50`
- Réponse JSON → champ `results` (titre, entreprise, lieu, lien).

Pour une app Zapier officielle, il faudrait un compte développeur Zapier ; on
peut la préparer plus tard de la même façon (OpenAPI + un trigger « nouvelles
offres »).

## Règles respectées
- API en lecture seule sur des données déjà publiques, dédupliquées, chaque
  offre liée à sa source. Pas de scraping, robots.txt respecté.
