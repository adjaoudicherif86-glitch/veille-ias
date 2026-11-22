# CLAUDE.md : veille-ias

Un seul dépôt, trois produits gratuits qui tournent sur GitHub Actions et sont publiés par GitHub Pages (`main`, dossier `/docs`) :

- **Flair** : veille IA (collecte → IA → regroupement → histoires), site `docs/index.html`.
- **Flair FM** : podcast quotidien lu par « Rocco », construit à partir des données de Flair, onglet du même site.
- **Pièce Unique** : promos mode homme et relais de bons plans (dont X), site `docs/mode/index.html`.

Tout est en Python 3.12, sans framework ni tests automatisés. Code, commentaires, commits et textes du site sont **en français**.

## Comment les parties s'enchaînent

```
sources.json ─► veille.py (toutes les 4 h, veille.yml)
                 ├─ primaires.py   notes de version, GitHub, Hugging Face
                 ├─ semantique.py  empreintes Gemini + arbitrage IA des doublons (zone 0,80–0,93)
                 ├─ analyse IA, brief du jour, 5 sujets à suivre
                 └─ histoires.py   rattache les actus à des histoires suivies
               ─► docs/data/items.json, meta.json, histoires.json  (+ mémoire dans etat/)

docs/data/* ─► podcast/episode.py (6 h 41 Paris, podcast.yml) ─► MP3 en Release + docs/podcast/episodes.json

mode/boutiques.json ─► mode/collecte.py + relais.py (toutes les heures, mode.yml) ─► docs/mode/data.json, relais.json
navigateur X ─► x_lecture.js ─► x_fusion.py ─► etat/x-brut.json (push) ─► comptes.yml ─► docs/mode/camino.json
```

Détails par partie :
- Flair FM : @.claude/contexte/flair-fm.md
- Pièce Unique (et relais X) : @.claude/contexte/piece-unique.md
- Pièges déjà rencontrés : @.claude/contexte/pieges.md

## Commandes locales

Syntaxe bash (Git Bash) ; sous PowerShell, les jokers `mode/*.py` ne sont pas développés.

```bash
pip install -r requirements.txt                        # Flair (feedparser, requests, trafilatura)
pip install requests numpy scipy lameenc               # Flair FM ; Pièce Unique n'a besoin que de requests
python -m py_compile veille.py histoires.py semantique.py primaires.py mode/*.py podcast/*.py   # vérification minimale, à lancer après toute modif
python veille.py                                       # sans LLM_API_KEY : collecte + regroupement par titres, sans IA
python mode/collecte.py                                # promos (FORCE_IA=1 pour forcer la notation IA)
python podcast/episode.py                              # épisode dans podcast/sortie/ (ignoré par Git), clé obligatoire
cd docs && python -m http.server 8000                  # site sur http://localhost:8000 et /mode/
```

- Clé en local : `$env:LLM_API_KEY="..."` (PowerShell), jamais écrite dans un fichier du dépôt.
- Lancer un script en local **réécrit les fichiers de données** : vérifier le résultat, puis `git restore docs/ etat/` avant de committer du code.
- Après une modif du site : ouvrir la page, contrôler la console du navigateur et l'affichage mobile (largeur 375 px).

## Règles du projet

**Gemini et quotas (offre gratuite)**
- Appels via l'endpoint compatible OpenAI `generativelanguage.googleapis.com/v1beta/openai/chat/completions`, clé `LLM_API_KEY`. `LLM_API_URL` et `LLM_MODEL` permettent de changer de fournisseur ou de modèle.
- Toujours une **liste de modèles de repli** (ex. `gemini-flash-latest` → `gemini-flash-lite-latest` → `gemini-2.5-flash-lite`) : sur 429/503, modèle suivant ou nouvel essai avec pause ; jamais un seul nom de modèle codé en dur.
- Un script doit **finir proprement sans clé ou quota épuisé** (sauter l'étape IA, garder les données précédentes), jamais planter le workflow.
- Respecter les pauses entre appels (`PAUSE_LLM`, lots de 20 pour les empreintes) et les plafonds (`MAX_ANALYSES`, `MAX_ARBITRAGES`, `HISTOIRES_LOTS_MAX`).
- Les noms de modèles Gemini changent souvent : préférer la détection automatique (`/models`) ou les alias `-latest`.

**Secrets** : uniquement dans les secrets GitHub (`LLM_API_KEY`, `X_BEARER_TOKEN`) ou des variables d'environnement locales. Jamais dans le code, un JSON, un commit ou un log.

**Données**
- Générés par les robots, **ne pas modifier à la main** : `docs/data/items.json`, `meta.json`, `histoires.json`, `docs/mode/data.json`, `relais.json`, `camino.json`, `fiabilite.json`, `docs/podcast/episodes.json`, et tout `etat/` (mémoire : ne jamais le vider).
- Éditables à la main (configuration) : `sources.json`, `docs/data/societes.json`, `annuaire.json`, `controle.json`, `mode/boutiques.json`, `mode/avis.json`, `docs/mode/blackfriday.json`.
- JSON écrits en UTF-8 avec `ensure_ascii=False`.

**Style du site**
- HTML/CSS/JS vanilla dans un seul fichier par site, aucun framework ni étape de build. Seules ressources externes : Google Fonts.
- Flair : variables CSS `--fond`, `--encre`, `--blaze` (orange), `--foret` (vert)… avec thème sombre ; polices Bricolage Grotesque (titres) et Atkinson Hyperlegible (texte).
- Pièce Unique : style média streetwear noir et blanc, `--sticker` jaune, `--rouge`, police Archivo.
- Réutiliser les variables existantes, garder le mobile d'abord, textes en français simple.

**Git** : les robots poussent sur `main` plusieurs fois par heure. Toujours `git pull --rebase origin main` juste avant `git push`. Messages de commit au format `Partie : ce qui change` (ex. `Pièce Unique : …`, `Flair FM : …`, `Regroupement : …`).

## Ne jamais faire

- Mettre une clé ou un jeton dans le dépôt, ou l'afficher dans un `print`.
- Modifier à la main un fichier généré, ou committer les données réécrites par un lancement local.
- Supprimer ou réinitialiser `etat/` (cache d'empreintes, arbitrages, pages déjà vues, prix suivis).
- `git push --force` sur `main` (seule exception existante : les étiquettes `audio-*` du podcast, poussées par le workflow).
- Ajouter un service payant, une dépendance lourde ou un framework front : le projet doit rester à 0 €. L'API X (`mode/camino.py`) est payante et reste désactivée tant qu'il n'y a pas de clé.
- Retirer un garde-fou (repli de modèle, plafond par passage, `timeout-minutes`, contrôle de durée des voix) pour « aller plus vite ».
- Supprimer les crédits des sources relayées (liens et codes promo Camino gardés tels quels).
