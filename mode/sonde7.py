"""Sondage n°7 : Dealabs (RSS), site LinkDeal, boutiques UE multimarques (marques connues), prix France via /products/x.js."""
import json, re
from pathlib import Path
import requests
NAV = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "fr-FR,fr;q=0.9"}
JS = NAV | {"Accept": "application/json"}
res = {}
def get(u, h=NAV, **kw):
    try:
        r = requests.get(u, headers=h, timeout=25, **kw); return r.status_code, r.headers.get("content-type",""), r.text
    except Exception as e:
        return 0, "", str(e)[:150]
# 1. Dealabs
for u in ["https://www.dealabs.com/rss/groupe/mode-accessoires", "https://www.dealabs.com/rss/hot", "https://www.dealabs.com/rss/groupe/mode-homme",
          "https://www.dealabs.com/rss/groupe/sneakers", "https://www.dealabs.com/groupe/mode-accessoires"]:
    s, t, x = get(u)
    titres = re.findall(r"<title>(.*?)</title>", x)[:8]
    print("DEALABS", u, s, t[:30], len(x), titres)
    res[u] = {"statut": s, "titres": titres, "debut": x[:3000]}
# 2. LinkDeal
for u in ["https://lnkd-linkdeal.fr", "https://lnkd-linkdeal.fr/products.json?limit=5"]:
    s, t, x = get(u)
    print("LINKDEAL", u, s, t[:30], len(x), re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x))[:600])
    res[u] = {"statut": s, "debut": x[:5000]}
# 3. Boutiques UE multimarques
cands = ["allikestore.com", "asphaltgold.com", "43einhalb.com", "thegoodwillout.com", "uebervart-shop.de", "eu.kith.com", "sneakavenue.com",
         "titolo.ch", "sneakers76.com", "footdistrict.com", "lafuria.fr", "shinzo.paris", "the-next-door.fr", "wethenew.com", "basket4ballers.com",
         "hhv.de", "sivasdescalzo.com", "naked-copenhagen.com", "sns.se", "einhalb.com", "afew-store.com", "overkillshop.com", "solebox.com", "bstn.com",
         "kickz.com", "snipes.com", "courir.com", "jdsports.fr", "zalando.fr", "asos.com", "laboutiqueofficielle.com", "citadium.com", "printemps.com",
         "carhartt-wip.com", "thenorthface.fr", "dickieslife.com", "levi.com", "lacoste.com", "ralphlauren.fr", "tommy.com"]
MARQUES = r"nike|jordan|adidas|new balance|asics|salomon|carhartt|north face|stussy|stüssy|arc.?teryx|patagonia|levi|dickies|ralph|lacoste|puma|converse|vans|timberland|clarks"
for d in cands:
    s, t, x = get(f"https://{d}/products.json?limit=250", JS)
    ok = s == 200 and x.strip().startswith("{")
    info = {"statut": s}
    if ok:
        try:
            p = json.loads(x).get("products", [])
            rem = [q for q in p for v in q.get("variants", [])[:1] if v.get("compare_at_price") and float(v["compare_at_price"]) > float(v["price"])]
            info |= {"produits": len(p), "remises": len(rem), "marques_connues": sum(1 for q in rem if re.search(MARQUES, (q.get("vendor") or "") + " " + q["title"], re.I)),
                     "exemples": [f"{q.get('vendor')} | {q['title'][:40]}" for q in rem[:4]]}
            sm, _, xm = get(f"https://{d}/meta.json", JS)
            if sm == 200: m = json.loads(xm); info |= {"devise": m.get("currency"), "pays": m.get("country"), "livre_FR": "FR" in (m.get("ships_to_countries") or [])}
            for c in ("sale", "outlet", "men-sale", "mens-sale", "sale-men", "herren-sale", "soldes"):
                sc, _, xc = get(f"https://{d}/collections/{c}/products.json?limit=250", JS)
                if sc == 200 and xc.strip().startswith("{") and json.loads(xc).get("products"):
                    info["collection_soldes"] = (c, len(json.loads(xc)["products"])); break
        except Exception as e:
            info["erreur"] = str(e)[:100]
    print("BOUTIQUE", d, info)
    res[d] = info
# 4. Prix France : products.json vs /products/x.js avec cookies FR, sur des boutiques UK actuelles
for d in ["stuartslondon.com", "goodhoodstore.com", "urbanindustry.co.uk", "stanray.com"]:
    s, t, x = get(f"https://{d}/products.json?limit=3", JS)
    try:
        p = json.loads(x)["products"][0]; h = p["handle"]; v = p["variants"][0]
        s2, _, x2 = get(f"https://{d}/products/{h}.js", JS, cookies={"localization": "FR", "cart_currency": "EUR"})
        s3, _, x3 = get(f"https://{d}/products/{h}.js?currency=EUR", JS)
        j2 = json.loads(x2) if s2 == 200 else {}; j3 = json.loads(x3) if s3 == 200 else {}
        print("PRIXFR", d, h, "json:", v["price"], v.get("compare_at_price"), "| js cookieFR:", j2.get("price"), j2.get("compare_at_price"), "| js ?currency:", j3.get("price"), j3.get("compare_at_price"))
    except Exception as e:
        print("PRIXFR", d, "erreur", str(e)[:100])
Path("etat/mode-sondage-7.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
