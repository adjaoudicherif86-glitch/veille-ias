# Pièges déjà rencontrés (tirés de l'historique Git)

**Regroupement des articles (semantique.py, veille.py)**
- Un seuil de similarité seul ne suffit pas : même événement = 0,84–0,89, mais deux papiers différents peuvent atteindre 0,86. D'où : fusion directe ≥ 0,93, arbitrage IA entre 0,80 et 0,93, décisions mémorisées dans `etat/arbitrages.json`.
- Comparer à tous les membres d'un groupe crée des **fusions en chaîne** : toujours comparer au sujet principal du groupe.
- « Même société » ne justifie pas une fusion ; deux annonces officielles distinctes ne fusionnent jamais.
- Empreinte manquante (quota) : fusion seulement si les titres sont quasi identiques, sinon fusions abusives.
- Réglage des seuils : regarder `etat/similarites.json` (chaque fusion avec score et raison), pas deviner.

**Histoires (histoires.py)**
- Sans consignes strictes, l'IA faisait d'une entreprise ou d'un thème une « histoire ». Chaque rattachement doit citer un fil concret et ressembler (≥ 0,72) à un épisode récent, sinon actu isolée.

**Quotas Gemini**
- Empreintes : lots de 20, puis attente 20/40/60 s sur 429 ; le reste au passage suivant.
- Les appels longs dépassent parfois le délai ou renvoient 5xx : `try/except requests.RequestException`, modèle suivant, `timeout` ≤ 150 s.

**Voix (Flair FM)**
- Le TTS répète ou improvise parfois : contrôler la durée attendue et réenregistrer (garde-fou dans `episode.py`).

**GitHub Actions**
- GitHub **saute beaucoup de passages planifiés** : `mode.yml` tourne toutes les heures pour en obtenir un toutes les 2–3 h, et la notation IA se relance si elle date de plus de 9 h.
- Plusieurs robots poussent sur `main` : boucle `git pull --rebase origin main && git push` (3 essais). `veille.yml` fait encore un `git push` simple.
- `git add` d'un fichier absent fait échouer l'étape : utiliser `[ -f "$f" ] && git add "$f"`.
- Un job trop long est tué : traiter par lots limités avec un chronomètre interne (ex. `comptes.py` : 72 posts, 18 min, `timeout-minutes: 30`).

**Pièce Unique**
- La date de début des nouveautés ne doit être fixée qu'une fois (`setdefault("_debut", …)`), sinon tout redevient « nouveau ».
- Prix et devise : lire la devise réelle de la boutique et vérifier le prix sur le marché France ; une promo affichée ailleurs peut ne pas exister en France.
- Photos Dealabs : seul le format 300x300 existe.
- Fichier du site trop lourd sur téléphone : JSON compact, champs inutiles retirés.
