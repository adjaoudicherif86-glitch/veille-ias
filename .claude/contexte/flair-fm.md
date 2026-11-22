# Flair FM (podcast/)

Épisode quotidien en français, animé par Rocco (personnage original). Workflow `podcast.yml`, cron `41 5 * * *` (après la chasse de 4 h 17 UTC).

## Chaîne de fabrication
1. `redaction.py` : lit `docs/data/` (5 sujets à suivre, histoires, brief) et écrit le script en séquences. Modèles de repli : 2 Flash puis 2 Flash-Lite détectés, puis `gemini-2.5-flash` / `gemini-2.5-flash-lite`. Sur 429/404/400/403/503 ou délai dépassé : modèle suivant.
2. `voix.py` : synthèse Gemini TTS (PCM 16 bits, 24 kHz). Modèle détecté (préférence 3.x puis 2.x) ou forcé par `LLM_TTS_MODEL`. Nouvel essai sur 429 et 5xx.
3. `episode.py` : enregistre séquence par séquence avec un **garde-fou de durée** (~150 mots/min attendus ; hors de 0,6×–1,45×+4 s → réenregistrement, 3 essais max, on garde le plus proche).
4. `sons.py` : jingle, transitions, nappe et filtre « voix radio », tout synthétisé (aucun échantillon externe).
5. Sortie : `podcast/sortie/<date>.mp3` + `episode.json` (dossier ignoré par Git).
6. Workflow : Release `episode-AAAA-MM-JJ` (téléchargement) + étiquette `audio-AAAA-MM-JJ` (commit isolé ne contenant que le MP3, servi par jsDelivr).
7. `publier.py` : ajoute l'épisode à `docs/podcast/episodes.json` (14 gardés) et liste les vieilles étiquettes à supprimer.

## À savoir
- La voix et le jeu de Rocco sont dans `rocco.py` (`VOIX = "Algenib"`, `INTENSITE_RADIO = 0.45`, choisis à l'écoute). Les indications entre crochets se jouent, ne se lisent pas.
- L'audio est servi par jsDelivr et non par les Releases : bon type `audio/mpeg`, lecture à une position, compatible Safari. Ne pas remplacer l'URL `url` par celle des Releases.
- Les MP3 ne vont jamais dans l'historique de `main` (sauf les essais de `docs/podcast/essais/`).
- `essais.py` + `podcast-essais.yml` : extraits de test de plusieurs voix, lancés à la main.
- Test local : `python podcast/episode.py` avec `LLM_API_KEY` ; `publier.py` exige `GITHUB_REPOSITORY`, `TAG` et `TAG_AUDIO`, donc il ne se lance qu'en CI.
