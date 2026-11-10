"""Sondage n°3 : fiabilité (Trustpilot, politiques Shopify), grandes enseignes (Uniqlo, Zara, Adidas, Mango…),
marques françaises sur Shopify. Résultat : etat/mode-sondage-3.json"""
import json
import re
from pathlib import Path

import requests

NAV = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
       "Accept-Language": "fr-FR,fr;q=0.9"}
JS = NAV | {"Accept": "application/json"}
res = {"trustpilot": {}, "politiques": {}, "enseignes": {}, "shopify_fr": {}}


def get(url, h=NAV, **kw):
    try:
        return requests.get(url, headers=h, timeout=25, **kw)
    except Exception as e:
        return e


# 1. Trustpilot
boutiques = json.loads(Path("mode/boutiques.json").read_text())["boutiques"]
for b in boutiques[:45]:
    dom = b["domaine"].removeprefix("www.").removeprefix("eu.")
    r = get(f"https://fr.trustpilot.com/review/{dom}")
    if isinstance(r, Exception):
        res["trustpilot"][dom] = str(r)[:80]
        continue
    t = r.text
    note = re.search(r'"trustScore"\s*:\s*([\d.]+)', t) or re.search(r'"ratingValue"\s*:\s*"?([\d.]+)', t)
    nb = re.search(r'"numberOfReviews"\s*:\s*(\d+)', t) or re.search(r'"reviewCount"\s*:\s*"?(\d+)', t)
    res["trustpilot"][dom] = {"statut": r.status_code, "note": note and note.group(1), "avis": nb and nb.group(1), "taille": len(t)}
    print("TP", dom, res["trustpilot"][dom])

# 2. Politiques Shopify (retours, livraison)
for b in boutiques[:8]:
    for pol in ("refund-policy", "shipping-policy"):
        r = get(f"https://{b['domaine']}/policies/{pol}")
        if isinstance(r, Exception):
            continue
        m = re.search(r'shopify-policy__body.*?>(.*?)</div>\s*</div>', r.text, re.S)
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1) if m else ""))[:400]
        res["politiques"][f"{b['domaine']} {pol}"] = {"statut": r.status_code, "texte": txt}
        print("POL", b["domaine"], pol, r.status_code, txt[:120])

# 3. Grandes enseignes
essais = {
    "uniqlo_v5_discount": "https://www.uniqlo.com/fr/api/commerce/v5/fr/products?flagCodes=discount&limit=24&offset=0&httpFailure=true",
    "uniqlo_v5_men_sale": "https://www.uniqlo.com/fr/api/commerce/v5/fr/products?path=%2C%2C%2C&genderId=men&flagCodes=discount&limit=24",
    "uniqlo_page": "https://www.uniqlo.com/fr/fr/men/sale",
    "zara_categories": "https://www.zara.com/fr/fr/categories?ajax=true",
    "zara_page": "https://www.zara.com/fr/fr/homme-special-prices-l806.html",
    "adidas_api": "https://www.adidas.fr/api/plp/content-engine?query=hommes-outlet",
    "adidas_page": "https://www.adidas.fr/hommes-outlet",
    "mango_api": "https://shop.mango.com/services/productlist/products/FR/he/sections_he_rebajas/?pageNum=1",
    "pullbear_page": "https://www.pullandbear.com/fr/homme/promotions-n6587",
    "hm_page": "https://www2.hm.com/fr_fr/homme/offres/prix-bas.html",
    "nike_api": "https://api.nike.com/cic/browse/v2?queryid=products&anonymousId=x&country=fr&endpoint=%2Fproduct_feed%2Frollup_threads%2Fv2%3Ffilter%3Dmarketplace(FR)%26filter%3Dlanguage(fr)%26filter%3DemployeePrice(true)%26filter%3DattributeIds(0f64ecc7-d624-4e91-b171-b83a03dd8550%2C5b21a62a-0503-400c-8336-3ccfbff2a684)%26anchor%3D0%26consumerChannelId%3Dd9a5bc42-4b9c-4976-858a-f159cf99c647%26count%3D24",
    "decathlon_page": "https://www.decathlon.fr/homme/soldes",
    "kiabi_page": "https://www.kiabi.com/homme-promos_200058",
    "celio_page": "https://www.celio.com/fr-fr/promotions",
}
for k, u in essais.items():
    r = get(u, JS if "api" in k or "ajax" in u or "services" in u else NAV)
    if isinstance(r, Exception):
        res["enseignes"][k] = {"erreur": str(r)[:120]}
    else:
        t = r.text
        res["enseignes"][k] = {"statut": r.status_code, "type": r.headers.get("content-type", ""), "taille": len(t), "debut": t[:300],
                               "prix": len(re.findall(r'"(?:price|salePrice|currentPrice|promoPrice)"', t)), "jsonld": t.count("application/ld+json")}
    print("ENS", k, {x: y for x, y in res["enseignes"][k].items() if x != "debut"})

# 4. Marques et boutiques françaises (ou très accessibles) sur Shopify
fr = ["lyleandscott.com", "bensherman.com", "sergiotacchini.com", "ellesse.fr", "kappa.fr", "wethenew.com", "basket4ballers.com",
      "footdistrict.com", "sneakers76.com", "hopaal.com", "loom.fr", "1083.fr", "leslipfrancais.fr", "balibaris.com",
      "maisonstandards.com", "edmmondstudios.com", "cuissedegrenouille.com", "olow.fr", "pompeiibrand.com", "kaporal.com",
      "teddysmith.com", "japanrags.com", "dagobear.com", "bleu-de-chauffe.com", "laboutiqueofficielle.com", "kulte.fr",
      "nozbone.com", "chevignon.fr", "oxbow.com", "letempsdescerises.fr", "schott-nyc.fr", "commune-de-paris.fr",
      "maison-montagut.com", "armorlux.com", "le-mont-saint-michel.fr", "saint-james.fr", "lepetitbateau.fr", "hast.fr",
      "jagvi.com", "atelier-tuffery.com", "le-vestiaire-masculin.fr", "pigalle-paris.com", "maisonkitsune.com",
      "lebonmarche.com", "printemps.com", "newbalance.fr", "vans.fr", "puma.com", "champion.fr", "eu.huf.com",
      "neweracap.eu", "eu.obeyclothing.com", "eastpak.com", "reebok.eu", "fila.fr", "umbro.fr", "lecoqsportif.com",
      "ellesse.co.uk", "kangol.com", "dickies.fr", "wrangler.fr", "lee.com", "levi.com", "jackjones.com"]
for d in fr:
    ok = None
    for base in (f"https://{d}", f"https://www.{d}"):
        r = get(f"{base}/products.json?limit=250", JS)
        try:
            if not isinstance(r, Exception) and r.status_code == 200:
                p = r.json().get("products")
                if p is not None:
                    rem = sum(1 for x in p for v in x.get("variants", [])[:1] if v.get("compare_at_price") and float(v["compare_at_price"]) > float(v["price"]))
                    dev = None
                    try:
                        dev = get(f"{base}/cart.js", JS).json().get("currency")
                    except Exception:
                        pass
                    ok = {"base": base, "produits": len(p), "remises": rem, "devise": dev}
                    break
        except Exception:
            pass
    res["shopify_fr"][d] = ok
    print("FR", d, ok)

Path("etat/mode-sondage-3.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
