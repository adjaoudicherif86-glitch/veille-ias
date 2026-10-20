# 🐕 Flair : ta veille IA automatique, 100 % gratuite

Flair est un chien de chasse qui part toutes les 4 heures sur une vingtaine de sources (OpenAI, Google DeepMind, Hugging Face, Microsoft, NVIDIA, presse tech, arXiv, Hacker News, r/LocalLLaMA, sources françaises…). Il rapporte les nouveautés, repère les sujets dont tout le monde parle, puis demande à une IA gratuite de t'expliquer chacune : ce que c'est, pourquoi c'est important, comment ça marche, comment l'utiliser et comment l'essayer sur ton PC.

Coût total : 0 €. GitHub Actions fait tourner le chien, GitHub Pages héberge l'appli, et l'API Gemini (Google AI Studio) écrit les explications dans les limites de son offre gratuite.

## Installation en 10 minutes

### 1. Créer le dépôt GitHub
1. Crée un compte sur https://github.com si tu n'en as pas.
2. Clique sur « New repository », nomme-le par exemple `veille-ia`, laisse-le **Public** (GitHub Pages gratuit l'exige pour les comptes gratuits), puis crée-le.
3. Clique sur « uploading an existing file » et glisse **tout le contenu** du dossier décompressé (y compris le dossier caché `.github`). Si ton explorateur cache `.github`, crée le fichier à la main dans GitHub : « Add file » → « Create new file », nomme-le `.github/workflows/veille.yml` et colle son contenu.

### 2. Obtenir une clé API gratuite (pour les explications)
1. Va sur https://aistudio.google.com, connecte-toi avec un compte Google.
2. Clique sur « Get API key » puis « Create API key ». Aucune carte bancaire n'est demandée.
3. Dans ton dépôt GitHub : **Settings → Secrets and variables → Actions → New repository secret**. Nom : `LLM_API_KEY`, valeur : ta clé.

Sans clé, l'appli marche quand même : tu as la collecte, les doublons fusionnés, le score et les filtres, mais pas les explications ni le brief du jour.

À savoir : sur l'offre gratuite de Gemini, Google peut utiliser les données envoyées pour améliorer ses produits. Ici ce ne sont que des titres d'articles publics, donc aucun souci.

### 3. Autoriser le robot à enregistrer ses trouvailles
**Settings → Actions → General → Workflow permissions** → coche « Read and write permissions » → Save.

### 4. Publier l'appli
**Settings → Pages** → Source : « Deploy from a branch » → Branch : `main`, dossier `/docs` → Save.
Ton appli sera à l'adresse `https://TON-PSEUDO.github.io/veille-ia/`.

### 5. Lâcher le chien une première fois
Onglet **Actions** → « Chasse aux nouveautés IA » → « Run workflow ». Après 2 à 5 minutes, recharge ton appli. Ensuite, il repart seul toutes les 4 heures.

## Les trois onglets

**Veille** : en haut, **les 5 sujets à suivre cette semaine**, présélectionnés par le flair du chien puis choisis par l'IA, avec pour chacun pourquoi le suivre et une action concrète. En dessous, le brief du jour et le fil complet. Chaque article présente **la société concernée** (qui elle est, ce qu'elle fait, ses autres actus de la semaine) et explique **pourquoi le chien l'a remonté** (repris par plusieurs sources, nouveau modèle, acteur majeur, open source…). Un filtre « Société » permet de suivre un acteur précis.

**Les IA** : l'annuaire des IA qui comptent (Claude, ChatGPT, Gemini, Grok, Meta AI, Mistral, DeepSeek, Qwen, Ollama et LM Studio). Chaque fiche donne : à quoi elle sert le mieux, comment l'utiliser pas à pas, comment l'avoir sur ton PC, ses forces, ses limites, ses modèles actuels, son activité et son histoire. Les boutons de tâche (coder, local, souveraineté…) mettent en avant les IA adaptées. La rubrique « Dans ta veille » de chaque fiche se remplit toute seule avec les actus qui la concernent.

**Contrôle et pouvoir** : six dossiers sur les craintes de contrôle par l'IA (surveillance, militaire, perte de contrôle, manipulation, concentration du pouvoir, vie privée). Chaque dossier sépare le récit, les faits prouvés (avec leurs sources), ce qui reste spéculatif et les signaux à surveiller. En dessous : la chronologie 2026 d'Anthropic et un fil d'actus dédié, où l'IA analyse chaque article en quatre temps : la crainte, les faits, les inconnues, le niveau de preuve.

## Les sources primaires

En plus de la presse, le chien lit l'info à la source (marquée « Source primaire » dans l'appli) :
- **les notes de version officielles** des API Claude, OpenAI et Gemini : la page est comparée au passage précédent, et seuls les ajouts sont remontés ;
- **les nouvelles versions** des outils clés sur GitHub (Ollama, vLLM, Transformers, Claude Code, Codex, SDK OpenAI, Anthropic et Gemini, Open WebUI, ComfyUI, Unsloth, MLX) ;
- **les modèles qui entrent dans les tendances Hugging Face**, avec le début de leur fiche technique ;
- **les publications de recherche les plus votées** sur Hugging Face Papers.

Dans `sources.json`, ces sources ont un champ `kind` (`page`, `github`, `hf_modeles`, `hf_papiers`). Pour suivre un autre projet GitHub, copie un bloc `github` et change `repo`. Le dossier `etat/` garde la mémoire des pages et des modèles déjà vus : ne le supprime pas.

## Le regroupement par le sens

Chaque article reçoit une empreinte numérique (embedding) calculée gratuitement par l'API Gemini. Deux articles sur le même événement ont des empreintes proches, même si leurs titres n'ont presque aucun mot en commun : ils deviennent un seul sujet, avec la liste des sources qui en parlent. Au-dessus du seuil fort (`SEUIL_FORT`, 0,90 par défaut), la fusion est automatique ; entre les deux seuils (`SEUIL_MOYEN`, 0,84), il faut en plus un indice concret (même nom de modèle cité, ou mêmes mots-clés). Deux sociétés différentes ne sont jamais fusionnées dans cette zone grise. Les empreintes sont gardées dans `etat/embeddings.json`, et `etat/similarites.json` liste les fusions du dernier passage (avec leur score) et les paires les plus proches restées séparées, pour régler les seuils.

## Les sociétés reconnues

La liste est dans `docs/data/societes.json` : nom, pays, présentation en une phrase, poids (3 = acteur majeur) et les mots qui permettent de la reconnaître. Pour en ajouter une, copie un bloc existant. Pour une société absente de la liste, l'IA rédige elle-même une présentation dans la fiche de l'article.

## Mettre à jour les fiches

Les fiches de l'annuaire (`docs/data/annuaire.json`) et les dossiers (`docs/data/controle.json`) sont des fichiers texte que tu peux modifier directement dans GitHub (icône crayon). Ajoute une IA en copiant le bloc d'une autre fiche. Le champ `mots` liste les mots qui relient la fiche aux actus de ta veille.

## Utiliser l'appli

- La jauge orange à gauche de chaque sujet, c'est le **flair** : de 1 à 5, selon le rang du sujet parmi tous ceux de la période (les 4 % les plus importants ont 5). Le score tient compte du nombre de sources qui en parlent, de la société concernée, du type d'annonce (nouveau modèle, open source, prix, régulation), de la fraîcheur et de l'avis de l'IA. Les témoignages clients et les petites mises à jour techniques sont rétrogradés.
- Le badge **+2 sources** signale un sujet chaud repris par plusieurs médias (les doublons sont fusionnés en un seul sujet).
- Le filtre **Utilisable sur mon PC** ne garde que ce que tu peux faire tourner chez toi (Ollama, LM Studio, modèles open weights, etc.).
- Clique sur un sujet pour ouvrir la fiche complète. Raccourcis clavier : `/` pour chercher, `j` / `k` pour passer au sujet suivant ou précédent, `Échap` pour fermer.
- ☆ pour mettre en favori, puis « Exporter mes favoris » pour obtenir un fichier Markdown (pratique pour Notion, Obsidian ou un compte rendu).
- Les lus et favoris sont gardés dans ton navigateur, pas sur un serveur.

## Personnaliser

**Ajouter ou retirer des sources** : modifie `sources.json`. Ajoute `"rubrique": "controle"` à une source pour l'envoyer dans l'onglet Contrôle et pouvoir. Chaque source a un `nom`, une `url` de flux RSS et un `type` (`officiel`, `presse`, `communaute`, `recherche`, `fr`). Ajoute `"filtre_ia": true` pour un flux généraliste dont tu ne veux que les articles IA, et `"max": 10` pour limiter le nombre d'articles gardés.

Astuce de chasseur : pour surveiller n'importe quel sujet, utilise une recherche Google News en RSS :
`https://news.google.com/rss/search?q=TON+SUJET&hl=fr&gl=FR&ceid=FR:fr`
Par exemple `q=%22Claude+Code%22` ou `q=Ollama+nouveau+mod%C3%A8le`.

**Réglages** (Settings → Secrets and variables → Actions → onglet Variables) :
- `MAX_ANALYSES` : nombre de sujets expliqués par passage (20 par défaut, soit environ 120 par jour).
- `MAX_ANALYSES_CONTROLE` : nombre d'articles de l'onglet Contrôle analysés par passage (8 par défaut).
- `LLM_MODEL` : force un modèle précis. Par défaut, le script choisit tout seul un modèle Gemini Flash disponible.
- `LLM_API_URL` : pour utiliser un autre fournisseur gratuit compatible OpenAI, par exemple Groq (`https://api.groq.com/openai/v1/chat/completions`, clé sur https://console.groq.com) ou OpenRouter (`https://openrouter.ai/api/v1/chat/completions`, avec un modèle gratuit en `:free`).

**Fréquence** : modifie la ligne `cron` dans `.github/workflows/veille.yml` (`"17 */2 * * *"` pour toutes les 2 heures).

## Faire tourner sur ton PC (optionnel)

```bash
pip install -r requirements.txt
# Windows PowerShell : $env:LLM_API_KEY="ta-cle"   |   Mac/Linux : export LLM_API_KEY="ta-cle"
python veille.py
cd docs
python -m http.server 8000
```
Puis ouvre http://localhost:8000 dans ton navigateur.

## En cas de problème

- **L'appli affiche « Le chien n'est pas encore sorti »** : lance le workflow à la main (étape 5) et vérifie qu'il est vert dans l'onglet Actions.
- **Le workflow échoue à l'étape « Enregistrer les trouvailles »** : l'étape 3 (permissions d'écriture) n'a pas été faite.
- **Des sources « en panne »** : c'est normal qu'une ou deux sources refusent de temps en temps (Reddit bloque parfois les serveurs de GitHub). Le chien continue avec les autres. Le détail est dans `docs/data/meta.json`.
- **Plus d'explications IA** : le quota gratuit du jour est atteint. Le script reprend automatiquement au passage suivant. Baisse `MAX_ANALYSES` si ça arrive souvent.
- **Modèle introuvable (erreur 404)** : les noms de modèles Gemini changent. Regarde les modèles gratuits disponibles dans Google AI Studio et mets le bon nom dans la variable `LLM_MODEL`.
