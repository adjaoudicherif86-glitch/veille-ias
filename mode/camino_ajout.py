"""
Ajout manuel de plans Camino (lus dans le navigateur de Chérif, à sa demande) dans docs/mode/camino.json.
Usage : python mode/camino_ajout.py nouveaux.json
nouveaux.json = liste de posts au même format que camino.py :
  {"tweet_id", "url", "date" (ISO), "texte", "liens": [...], "images": [...],
   "pieces": [{"nom", "marque", "prix", "prix_avant", "code", "lien", "etiquette", "categorie", "styles"}]}
On fusionne sans doublon et on garde les 21 derniers jours.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SORTIE = Path(__file__).resolve().parent.parent / "docs" / "mode" / "camino.json"


def main(chemin):
    nouveaux = json.loads(Path(chemin).read_text(encoding="utf-8"))
    try:
        actuel = json.loads(SORTIE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        actuel = {"posts": []}
    maintenant = datetime.now(timezone.utc)
    limite = (maintenant - timedelta(days=21)).isoformat()
    par_id = {p["tweet_id"]: p for p in actuel.get("posts", [])}
    for p in nouveaux:
        if p.get("tweet_id") and p.get("pieces"):
            par_id[p["tweet_id"]] = p
    posts = sorted((p for p in par_id.values() if p["date"] >= limite), key=lambda p: p["date"], reverse=True)
    SORTIE.write_text(json.dumps({"maj": maintenant.isoformat(), "compte": "CaminoTV", "source": "lecture à la demande",
                                  "posts": posts}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✅ {len(nouveaux)} posts ajoutés, {len(posts)} plans Camino en ligne")


if __name__ == "__main__":
    main(sys.argv[1])
