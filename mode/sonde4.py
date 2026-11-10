"""Sondage n°4 : devise réelle des prix Shopify (base de la boutique ou devise locale ?), API Zara et Uniqlo."""
import json
import re
from pathlib import Path

import requests

NAV = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
       "Accept": "application/json", "Accept-Language": "fr-FR,fr;q=0.9"}
res = {"devises": {}, "zara": {}, "uniqlo": {}}


def j(url, **kw):
    try:
        r = requests.get(url, headers=NAV, timeout=25, **kw)
        return r.status_code, (r.json() if "json" in r.headers.get("content-type", "") else r.text[:300])
    except Exception as e:
        return 0, str(e)[:150]


for d in ["hast.fr", "representclo.com", "leslipfrancais.fr", "stuartslondon.com", "minimum.dk", "olow.fr", "sergiotacchini.com",
          "taylorstitch.com", "lecoqsportif.com", "footdistrict.com"]:
    b = f"https://{d}"
    _, meta = j(f"{b}/meta.json")
    _, p = j(f"{b}/products.json?limit=1")
    prod = (p.get("products") or [{}])[0] if isinstance(p, dict) else {}
    v = (prod.get("variants") or [{}])[0]
    _, c1 = j(f"{b}/cart.js")
    _, c2 = j(f"{b}/cart.js", cookies={"cart_currency": "EUR", "localization": "FR"})
    _, pj = j(f"{b}/products/{prod.get('handle', 'x')}.js", cookies={"cart_currency": "EUR", "localization": "FR"})
    _, pj0 = j(f"{b}/products/{prod.get('handle', 'x')}.js")
    ligne = {
        "meta_devise": meta.get("currency") if isinstance(meta, dict) else None,
        "meta_pays": meta.get("country") if isinstance(meta, dict) else None,
        "livre_FR": ("FR" in (meta.get("ships_to_countries") or [])) if isinstance(meta, dict) else None,
        "products_json_prix": v.get("price"), "cart_sans_cookie": c1.get("currency") if isinstance(c1, dict) else c1,
        "cart_cookie_EUR": c2.get("currency") if isinstance(c2, dict) else c2,
        "produit_js_cookie_EUR": pj.get("price") if isinstance(pj, dict) else None,
        "produit_js_sans": pj0.get("price") if isinstance(pj0, dict) else None,
    }
    res["devises"][d] = ligne
    print("DEV", d, ligne)

# Zara : arbre des catégories, puis les produits d'une catégorie « prix spéciaux / soldes » homme
s, cats = j("https://www.zara.com/fr/fr/categories?ajax=true")
trouve = []


def parcours(noeuds, chemin=""):
    for n in noeuds or []:
        nom = f"{chemin} > {n.get('name', '')}"
        if re.search(r"homme|man", chemin + n.get("name", ""), re.I) and re.search(r"sp[ée]cia|solde|sale|prix|promo|offre", n.get("name", ""), re.I):
            trouve.append((nom, n.get("id"), n.get("redirectCategoryId")))
        parcours(n.get("subcategories"), nom)


if isinstance(cats, dict):
    parcours(cats.get("categories"))
print("ZARA catégories", trouve[:15])
res["zara"]["categories"] = trouve[:30]
for nom, cid, red in trouve[:3]:
    s, pr = j(f"https://www.zara.com/fr/fr/category/{red or cid}/products?ajax=true")
    txt = json.dumps(pr)[:200000] if not isinstance(pr, str) else pr
    res["zara"][str(cid)] = {"statut": s, "nom": nom, "extrait": txt[:3000]}
    print("ZARA", cid, s, nom, "oldPrice" in txt, txt.count('"price"'), txt[:400])

# Uniqlo : plusieurs formes d'appel
for k, u in {
    "a": "https://www.uniqlo.com/fr/api/commerce/v5/fr/products?path=%2C%2C%2C&flagCodes=discount&limit=24&offset=0",
    "b": "https://www.uniqlo.com/fr/api/commerce/v5/fr/products?q=homme&flagCodes=discount&limit=24",
    "c": "https://www.uniqlo.com/fr/api/commerce/v5/fr/products?limit=24&offset=0",
    "d": "https://www.uniqlo.com/fr/api/commerce/v3/fr/products?limit=24&flagCodes=discount",
    "e": "https://www.uniqlo.com/fr/api/commerce/v5/fr/products?genderId=37608&limit=24",
    "f": "https://www.uniqlo.com/fr/api/commerce/v5/fr/products?q=pull&limit=24",
}.items():
    s, r = j(u)
    t = json.dumps(r)[:600] if not isinstance(r, str) else r
    res["uniqlo"][k] = {"statut": s, "extrait": t}
    print("UNIQLO", k, s, t[:500])

Path("etat/mode-sondage-4.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
