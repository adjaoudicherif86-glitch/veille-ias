"""Sondage n°5 : Bershka et Pull&Bear (groupe Inditex, comme Zara) sont-ils lisibles ?"""
import json
import re
from pathlib import Path

import requests

NAV = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
       "Accept-Language": "fr-FR,fr;q=0.9"}
JS = NAV | {"Accept": "application/json"}
res = {}


def get(u, h=NAV):
    try:
        r = requests.get(u, headers=h, timeout=25)
        return r.status_code, r.headers.get("content-type", ""), r.text
    except Exception as e:
        return 0, "", str(e)[:200]


for nom, base, pages in [
    ("bershka", "https://www.bershka.com", ["/fr/", "/fr/homme.html", "/fr/h-man.html"]),
    ("pullandbear", "https://www.pullandbear.com", ["/fr/", "/fr/homme-n6228", "/fr/homme/promotions-n6587"]),
]:
    ids = {}
    for p in pages:
        s, t, txt = get(base + p)
        trouve = {k: re.findall(rf'["\']?{k}["\']?\s*[:=]\s*["\']?(\d{{5,}})', txt)[:5] for k in ("storeId", "catalogId", "catalogue", "store")}
        print(nom.upper(), p, s, t[:30], len(txt), trouve, re.findall(r"itxrest/[^\"' ]{0,120}", txt)[:5])
        for k, v in trouve.items():
            if v:
                ids.setdefault(k, v[0])
    res[nom] = {"ids": ids}
    store, cat = ids.get("storeId") or ids.get("store"), ids.get("catalogId") or ids.get("catalogue")
    essais = []
    if store and cat:
        essais += [f"{base}/itxrest/2/catalog/store/{store}/{cat}/category?languageId=-2&typeCatalog=1&appId=1",
                   f"{base}/itxrest/3/catalog/store/{store}/{cat}/category?languageId=-2&typeCatalog=1&appId=1"]
    essais += [f"{base}/itxrest/2/web/seo/config?appId=1", f"{base}/fr/categories?ajax=true"]
    for u in essais:
        s, t, txt = get(u, JS)
        print(nom.upper(), "API", u.replace(base, ""), s, t[:30], len(txt), txt[:300].replace("\n", " "))
        res[nom][u] = {"statut": s, "taille": len(txt), "debut": txt[:500]}
Path("etat/mode-sondage-5.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
