# Publier l'API Jobmesh sur RapidAPI — guide pas à pas

Objectif : exposer l'API Jobmesh (lecture seule) sur RapidAPI Hub, avec un plan
gratuit et un plan Premium. RapidAPI se place **devant** `https://jobmesh.world`
comme proxy : il gère les clés et les quotas, puis transmet la requête à ton API.

Fichier à importer : `rapidapi/openapi.json` (spec OpenAPI 3.x déjà curée — 14
endpoints publics, serveur = https://jobmesh.world).

---

## 1. Créer le compte et l'API
1. Va sur **rapidapi.com**, crée un compte (ou connecte-toi).
2. En haut à droite : **My APIs** → **Add New API**.
3. Choisis **Import from OpenAPI**, puis téléverse `rapidapi/openapi.json`.
   - Name : `Jobmesh — Job Postings API`
   - Category : `Jobs` (ou `Business`).
4. Vérifie que **Base URL** = `https://jobmesh.world` (onglet *Settings* → *Base URL*).

## 2. Description (à coller dans l'onglet *General*)
**Short description** :
> Live, de-duplicated index of open job postings from dozens of ATS and job boards — one searchable API, every role linking back to its source.

**Long description** : utilise le bloc `info.description` du fichier `openapi.json`
(déjà rédigé : recherche, dédup, fraîcheur `/changes`, couverture `/sources`,
plans, respect de robots.txt).

## 3. Définir les plans (onglet *Plans & Pricing*)
| Plan | Prix | Quota mensuel | Débit (hard limit) | Cap résultats |
|---|---|---|---|---|
| **Basic (Free)** | 0 € | 1 000 requêtes / mois | 240 req/min | 50 résultats/req |
| **Pro (Premium)** | ex. 9,99 €/mois | 100 000 requêtes / mois | 2 400 req/min | 1 000 résultats/req |

- Mets les *hard limits* de débit comme ci-dessus (ils collent à ton API).
- Tu peux ajouter un plan **Ultra** plus cher plus tard (exports .gz, quota plus gros).

## 4. Faire que le plan Premium débloque le cap à 1000 (clé backend)
Ton API lève le cap à 1000 résultats quand elle reçoit l'en-tête `X-API-Key`
(une clé Jobmesh Premium). Sur RapidAPI, injecte cette clé **uniquement** pour le
plan payant :
1. Génère une clé Premium Jobmesh (ta commande habituelle, ex. `python -m jobmesh.cli key ...`).
2. Dans RapidAPI : **Settings → Header Transformations** (ou *Secrets*), ajoute un
   en-tête sortant `X-API-Key: <ta clé>` **conditionné au plan Pro**.
   - Ainsi, les utilisateurs Free n'ont pas la clé (cap 50), les Pro l'ont (cap 1000).
   - Ne mets jamais la clé dans la spec publique ni dans le dépôt.

## 5. Tester puis publier
1. Onglet **Endpoints** → prends `GET /jobs`, mets `keyword=data engineer`,
   `country=DE`, `limit=5` → **Test Endpoint** : tu dois voir un 200 + des offres.
2. Teste aussi `/stats` et `/sources`.
3. Quand c'est bon : **Make Public** (bouton *Publish*).

## 6. Exemples pour la doc RapidAPI (les consommateurs appellent via le proxy)
```bash
# curl
curl --request GET \
  --url 'https://jobmesh.p.rapidapi.com/jobs?keyword=data%20engineer&country=DE&limit=5' \
  --header 'X-RapidAPI-Key: VOTRE_CLE_RAPIDAPI' \
  --header 'X-RapidAPI-Host: jobmesh.p.rapidapi.com'
```
```python
# Python
import requests
r = requests.get(
    "https://jobmesh.p.rapidapi.com/jobs",
    params={"keyword": "data engineer", "country": "DE", "limit": 5},
    headers={"X-RapidAPI-Key": "VOTRE_CLE_RAPIDAPI",
             "X-RapidAPI-Host": "jobmesh.p.rapidapi.com"})
print(r.json()["total"])
```
```javascript
// JavaScript (fetch)
const r = await fetch(
  "https://jobmesh.p.rapidapi.com/jobs?keyword=data+engineer&country=DE&limit=5",
  { headers: { "X-RapidAPI-Key": "VOTRE_CLE_RAPIDAPI",
               "X-RapidAPI-Host": "jobmesh.p.rapidapi.com" } });
const { results } = await r.json();
```
> `jobmesh.p.rapidapi.com` est l'hôte que RapidAPI te donnera après publication ;
> remplace-le par celui affiché sur ta page RapidAPI.

## Notes
- RapidAPI gère lui-même les clés consommateurs et les quotas ; ton rate-limit
  interne (240/2400) reste un filet de sécurité.
- Tu peux régénérer `rapidapi/openapi.json` à tout moment depuis l'API live
  (`/openapi.json`) si tu ajoutes des endpoints.
- Rien à déployer côté serveur pour RapidAPI : c'est de la config sur leur Hub.
