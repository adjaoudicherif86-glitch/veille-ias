"""
Fusionne les posts lus sur X (export du localStorage « __pu_x », un objet {id: [compte, id, texte, images]}
ou une liste [[compte, id, texte, images], ...]) dans etat/x-brut.json, garde 7 jours.
Usage : python mode/x_fusion.py export.json
Pousser ensuite etat/x-brut.json : le workflow comptes.yml lit les nouveaux posts et met à jour le site.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BRUT = Path(__file__).resolve().parent.parent / "etat" / "x-brut.json"
COMPTES = {"caminotv": "CaminoTV", "fitthemall": "FitThemAll",
           "bershka": "Bershka", "pullandbear": "pullandbear"}
# Recherche ouverte sur tout X : on garde les autres comptes seulement s'ils parlent de ces marques, avec un lien.
MARQUES = re.compile(r"bershka|pull\s*(&|and|n|et)\s*bear|pullandbear|black\s*(friday|week)|uniqlo|zara|carhartt|north\s*face|"
                     r"levi|lacoste|mango|h&m|arket|ralph\s*lauren|jott|columbia|patagonia|tommy|calvin\s*klein|jack\s*&\s*jones|"
                     r"massimo\s*dutti|celio|jules|kiabi|decathlon|zalando|asos", re.I)
MAX_AUTRES = 40  # au plus 25 posts d'autres comptes par lecture : la recherche ouverte est bruyante


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
    autres = 0
    for compte, pid, texte, images in sorted(neuf, key=lambda p: -int(p[1]) if str(p[1]).isdigit() else 0):
        if not str(pid).isdigit() or not texte:
            continue
        c = COMPTES.get(str(compte).lower())
        if not c:
            if not re.fullmatch(r"\w{1,15}", str(compte)) or not MARQUES.search(texte) or "http" not in texte \
                    or (pid not in par_id and autres >= MAX_AUTRES):
                continue
            c = str(compte)
            autres += pid not in par_id
        ajoutes += pid not in par_id
        par_id[pid] = [c, pid, texte, images[:4]]
    limite = datetime.now(timezone.utc) - timedelta(days=7)
    posts = sorted((p for p in par_id.values() if date_id(p[1]) >= limite), key=lambda p: int(p[1]), reverse=True)
    brut.update({"lu_le": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "posts": posts})
    BRUT.write_text(json.dumps(brut, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"✅ {ajoutes} nouveaux posts, {len(posts)} posts sur 7 jours")


if __name__ == "__main__":
    main(sys.argv[1])
