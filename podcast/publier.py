"""Ajoute l'épisode fabriqué au catalogue docs/podcast/episodes.json (les 14 derniers), avec l'adresse
du fichier dans les Releases GitHub. Affiche les tags d'épisodes trop anciens, à supprimer."""
import json
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CATALOGUE = RACINE / "docs" / "podcast" / "episodes.json"
GARDER = 14

ep = json.loads((Path(__file__).parent / "sortie" / "episode.json").read_text(encoding="utf-8"))
depot = os.environ["GITHUB_REPOSITORY"]
tag = os.environ["TAG"]
ep["tag"] = tag
ep["url"] = f"https://github.com/{depot}/releases/download/{tag}/{ep['fichier']}"
try:
    cat = json.loads(CATALOGUE.read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError):
    cat = {"episodes": []}
cat["episodes"] = [ep] + [e for e in cat["episodes"] if e["tag"] != tag]
for vieux in cat["episodes"][GARDER:]:
    print(vieux["tag"])
cat["episodes"] = cat["episodes"][:GARDER]
CATALOGUE.parent.mkdir(parents=True, exist_ok=True)
CATALOGUE.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
