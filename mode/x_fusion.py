"""
Fusionne les posts lus sur X (export du localStorage « __pu_x », un objet {id: [compte, id, texte, images]}
ou une liste [[compte, id, texte, images], ...]) dans etat/x-brut.json, garde 7 jours.
Usage : python mode/x_fusion.py export.json
Pousser ensuite etat/x-brut.json : le workflow comptes.yml lit les nouveaux posts et met à jour le site.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BRUT = Path(__file__).resolve().parent.parent / "etat" / "x-brut.json"
COMPTES = {"caminotv": "CaminoTV", "fitthemall": "FitThemAll", "sneakerologue": "Sneakerologue"}


def date_id(pid):
    return datetime.fromtimestamp(((int(pid) >> 22) + 1288834974657) / 1000, timezone.utc)


def main(chemin):
    neuf = json.loads(Path(chemin).read_text(encoding="utf-8"))
    neuf = list(neuf.values()) if isinstance(neuf, dict) else neuf
    try:
        brut = json.loads(BRUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        brut = {"posts": []}
    par_id = {p[1]: p for p in brut.get("posts", [])}
    ajoutes = 0
    for compte, pid, texte, images in neuf:
        c = COMPTES.get(str(compte).lower())
        if not c or not str(pid).isdigit() or not texte:
            continue
        ajoutes += pid not in par_id
        par_id[pid] = [c, pid, texte, images[:4]]
    limite = datetime.now(timezone.utc) - timedelta(days=7)
    posts = sorted((p for p in par_id.values() if date_id(p[1]) >= limite), key=lambda p: int(p[1]), reverse=True)
    brut.update({"lu_le": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "posts": posts})
    BRUT.write_text(json.dumps(brut, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"✅ {ajoutes} nouveaux posts, {len(posts)} posts sur 7 jours")


if __name__ == "__main__":
    main(sys.argv[1])
