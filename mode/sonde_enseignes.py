"""Sonde temporaire : quelles boutiques candidates sont lisibles (Shopify, euros) et combien de pièces en promo ?
Et comment Carhartt WIP expose ses produits."""
import re, json, requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9"}
CANDIDATS = """hanon-shop.com nakedcph.com woodwood.com norsestore.com eu.kith.com faguo-store.com rains.com makia.com
dickieslife.com edwin-europe.com obeyclothing.eu hopaal.com asphalte.com 1083.fr justoverthetop.com picture-organic-clothing.com
maisonlabiche.com communedeparis1871.com edmmond.com twothirds.com allikestore.com titolo.ch uebervart-shop.de grailpoint.com
routeone.co.uk wellgosh.com thegoodneighbour.eu sivasdescalzo.com overkillshop.com bstn.com citadium.com celio.com jules.com
brice.fr bonoboplanet.com kaporal.com lecoqsportif.com champion.com fila.com ellesse.com elementbrand.com vans.fr
schottnyc.eu alphaindustries.com napapijri.fr obey.fr stussy.eu awakenewyork.com newamsterdamsurfassociation.com
sporty-and-rich.com satisfyrunning.com arpenteur.fr outland-denim.com nudiejeans.com levi.com thenorthface.fr
carhartt-wip.com stanray.eu gramicci.com eu.gramicci.com eu.patagonia.com columbiasportswear.fr salomon.com""".split()
ok = []
for d in CANDIDATS:
    try:
        r = requests.get(f"https://{d}/products.json?limit=250", headers=UA, timeout=20)
        if r.status_code != 200 or "products" not in r.text[:200]:
            print(f"{d:40} non ({r.status_code})"); continue
        ps = r.json()["products"]
        promo = sum(1 for p in ps if any(v.get("compare_at_price") and float(v["compare_at_price"] or 0) > float(v["price"]) for v in p["variants"]))
        try:
            dev = requests.get(f"https://{d}/meta.json", headers=UA, timeout=15).json().get("currency")
        except Exception:
            dev = "?"
        print(f"{d:40} SHOPIFY {dev} produits={len(ps)} promo={promo}")
        ok.append(d)
    except Exception as e:
        print(f"{d:40} erreur {type(e).__name__}")
print("LISIBLES", ok)
# Carhartt WIP : liens et API visibles dans la page
r = requests.get("https://www.carhartt-wip.com/fr/", headers=UA, timeout=30)
t = r.text
print("carhartt liens", sorted(set(re.findall(r'href="(/fr/[a-z0-9\-/]+)"', t)))[:80])
print("carhartt api", sorted(set(re.findall(r'https://[a-z0-9\.\-]+/(?:api|graphql|v\d)[^"\' ]{0,60}', t)))[:20])
for k in ("algolia", "commercetools", "salesforce", "shopify", "bigcommerce", "sanity", "graphql", "searchspring", "klevu", "constructor"):
    if k in t.lower(): print("carhartt contient", k)
