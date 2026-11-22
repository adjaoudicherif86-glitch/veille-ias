# Pièce Unique (mode/ → docs/mode/)

Sélection de promos mode homme au style « Camino » (streetwear, workwear, un peu d'old money, marques connues, prix bas, pas de sport).

## Scripts et workflows
| Script | Workflow | Rôle | Écrit |
|---|---|---|---|
| `collecte.py` (+ `enseignes.py`) | `mode.yml`, toutes les heures | Boutiques Shopify de `boutiques.json` (`/products.json`), Zara, Uniqlo, Carhartt WIP. Vraies remises ≥ 30 %, au moins 2 tailles, prix France vérifié, homme uniquement. Notation IA complète à 6 h et 15 h UTC ou si la dernière a plus de 9 h (`FORCE_IA=1` pour forcer). | `docs/mode/data.json`, `etat/mode-vus.json`, `etat/mode-prix.json` |
| `relais.py` | `mode.yml` (échec toléré) | Dealabs (RSS) et LinkDeal, filtrés et classés par l'IA. | `docs/mode/relais.json` |
| `comptes.py` | `comptes.yml`, déclenché par un push de `etat/x-brut.json` | Lit les posts X (texte + photo) avec Gemini, nomme les pièces, garde 5 jours. Au plus 72 posts et 18 min par passage ; posts écartés mémorisés. | `docs/mode/camino.json` |
| `camino.py` | `camino.yml` | Même chose via l'API X officielle, **payante** : ne fait rien sans `X_BEARER_TOKEN`. | `docs/mode/camino.json`, `etat/camino.json` |
| `fiabilite.py` | `mode-fiabilite.yml`, lundi | Avis vérifiés (`avis.json`) + politiques Shopify résumées par l'IA. | `docs/mode/fiabilite.json` |
| `sonde*.py` | `mode-sonde*.yml`, à la main | Explorations ponctuelles (nouvelles boutiques, API d'enseignes). | `etat/mode-sondage-*.json` |

## Relais X (lecture dans le navigateur, sans API payante)
1. Ouvrir une recherche X (`https://x.com/search?q=from%3ACaminoTV%20chck.me%20since%3AAAAA-MM-JJ&f=live`, ou une recherche ouverte sur des marques) dans le navigateur de l'utilisateur, **seulement à sa demande**.
2. Exécuter `mode/x_lecture.js` sur la page : il fait défiler ~35 s et stocke les posts dans le localStorage `__pu_x` (relancer si `encore` vaut true).
3. Exporter ce localStorage dans un fichier JSON, puis `python mode/x_fusion.py export.json` → fusion dans `etat/x-brut.json` (7 jours gardés, filtre comptes / marques / revendeurs).
4. Committer et pousser `etat/x-brut.json` : `comptes.yml` fait le reste.
- Ajout manuel de plans déjà structurés : `python mode/camino_ajout.py nouveaux.json`.

## Règles propres
- Ajouter une boutique : bloc dans `mode/boutiques.json` (`nom`, `domaine`, `origine` ; options `collection`, `mixte`, `multi`, `pays`, `styles`, `veille` : copier un bloc voisin). Tester d'abord avec une sonde si l'API n'est pas Shopify.
- Boutiques qui ne livrent pas la France : ignorées automatiquement.
- `data.json` est allégé pour le téléphone (JSON compact, 2 photos max) : ne pas réintroduire de champs lourds.
- Exclusions (sport, maillots, femme/enfant, pyjamas, déco, parfum, revente) : regex `EXCLURE`, `SPORT`, `MARQUES_CONNUES`, `CATEGORIES` dans `collecte.py`, réutilisées par `relais.py`.
