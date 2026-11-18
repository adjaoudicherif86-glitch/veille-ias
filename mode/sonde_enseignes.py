"""Sonde temporaire : champs cachés (prix FR) et URL produit Carhartt WIP."""
import json, requests
K = "key_QG9KK8DOmSUeFblV"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36", "Accept-Language": "fr-FR"}
for g in ["black-friday", "homme-promos-hiver", "homme-promos-ete"]:
    r = requests.get(f"https://ac.cnstrc.com/browse/group_id/{g}?key={K}&section=Products&num_results_per_page=3&fmt_options%5Bshow_hidden_fields%5D=true", headers=UA, timeout=20).json()
    for x in r["response"]["results"][:2]:
        d = x["data"]
        print(g, {k: v for k, v in d.items() if "price" in k.lower() or k in ("url", "product_title", "group_ids", "attr_main_category_url", "sku")})
d = r["response"]["results"][0]["data"]
for u in [f"https://www.carhartt-wip.com/fr/{d['url']}", f"https://www.carhartt-wip.com/fr/p/{d['url']}",
          f"https://www.carhartt-wip.com/fr/{(d.get('attr_main_category_url') or ['x'])[0]}/{d['url']}", f"https://www.carhartt-wip.com/fr/products/{d['url']}"]:
    try:
        s = requests.get(u, headers=UA, timeout=25, allow_redirects=True)
        print("URL", s.status_code, u, "->", s.url, ("product_title" in s.text or d["product_title"] in s.text))
    except Exception as e:
        print("URL", u, e)
