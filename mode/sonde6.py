"""Sondage n°6 : structure des produits Bershka (API catalogue du site, comme Zara)."""
import json
import re
from pathlib import Path

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
     "Accept": "application/json", "Accept-Language": "fr-FR,fr;q=0.9"}
B = "https://www.bershka.com/itxrest/2/catalog/store/44009501/40259533"
arbre = requests.get(f"{B}/category?languageId=-2&typeCatalog=1&appId=1", headers=H, timeout=30).json()
cibles = []


def parcours(noeuds, chemin=""):
    for n in noeuds or []:
        c = f"{chemin} > {n.get('name')}"
        if c.startswith(" > HOMME"):
            print("CAT", n.get("id"), c, n.get("numberOfProducts"))
            if re.search(r"promo|solde|sale|prix|offre|basic|pantalon|pull|veste|sweat", c, re.I):
                cibles.append((n.get("id"), c))
        parcours(n.get("subcategories"), c)


parcours(arbre.get("categories"))
res = {}
for cid, c in cibles[:6]:
    for u in (f"{B}/category/{cid}/product?languageId=-2&appId=1", f"{B}/category/{cid}/product?languageId=-2&appId=1&showProducts=true"):
        try:
            r = requests.get(u, headers=H, timeout=30)
            t = r.text
        except Exception as e:
            print("PROD", cid, e)
            continue
        print("PROD", cid, c, r.status_code, len(t), t[:1500].replace("\n", " "))
        res[f"{cid} {u[-30:]}"] = {"statut": r.status_code, "debut": t[:6000]}
        if r.status_code == 200 and len(t) > 500:
            try:
                d = r.json()
                ids = d.get("productIds") or [p.get("id") for p in d.get("products", [])][:3]
                print("IDS", ids[:10], list(d.keys())[:10])
                if d.get("productIds"):
                    q = ",".join(str(i) for i in d["productIds"][:4])
                    r2 = requests.get(f"{B}/productsArray?productIds={q}&languageId=-2&appId=1", headers=H, timeout=30)
                    print("ARRAY", r2.status_code, r2.text[:3000].replace("\n", " "))
                    res["array"] = r2.text[:20000]
            except Exception as e:
                print("JSON", e)
            break
Path("etat/mode-sondage-6.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
