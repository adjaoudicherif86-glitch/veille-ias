"""Sonde temporaire : que voit-on de Pull&Bear, Bershka et Carhartt WIP depuis GitHub Actions ?"""
import re, json, requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9", "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
def voir(u, n=400):
    try:
        r = requests.get(u, headers=UA, timeout=25)
        t = r.text
        print(f"\n=== {u}\n{r.status_code} {r.headers.get('content-type')} len={len(t)} server={r.headers.get('server')}")
        for k in ("storeId", "catalogId", "langId", "bm-verify", "_abck", "Shopify", "shopware", "sw-", "__NEXT_DATA__", "algolia", "magento", "sfcc", "demandware"):
            if k.lower() in t.lower(): print("  contient", k)
        for m in re.findall(r'"?(storeId|catalogId|catalog|store)"?\s*[:=]\s*"?(\d{5,})', t)[:8]: print("  ", m)
        print(t[:n].replace("\n", " "))
        return r
    except Exception as e:
        print("\n===", u, "ERREUR", e)
for u in ["https://www.pullandbear.com/fr/", "https://www.pullandbear.com/fr/homme-n6228",
          "https://www.bershka.com/fr/", "https://www.bershka.com/fr/homme.html",
          "https://www.carhartt-wip.com/fr/", "https://www.carhartt-wip.com/fr/sale",
          "https://www.carhartt-wip.com/products.json", "https://www.carhartt-wip.com/fr/products.json"]:
    voir(u)
