"""Sonde temporaire : Carhartt WIP (Constructor.io, le moteur de recherche public utilisé par leur site)."""
import re, json, requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9"}
t = requests.get("https://www.carhartt-wip.com/fr/", headers=UA, timeout=30).text
cles = sorted(set(re.findall(r'key_[A-Za-z0-9]{8,}', t)))
print("cles", cles)
print("urls cnstrc", sorted(set(re.findall(r'https://[a-z\.]*cnstrc\.com[^"\'\\\\ ]{0,80}', t)))[:10])
print("chemins", sorted(set(re.findall(r'/fr/[a-z0-9\-]+(?:/[a-z0-9\-]+)?', t)))[:120])
for k in cles[:3]:
    for u in [f"https://ac.cnstrc.com/search/sale?key={k}&section=Products&num_results_per_page=5",
              f"https://ac.cnstrc.com/browse/group_id/sale?key={k}&section=Products&num_results_per_page=5",
              f"https://ac.cnstrc.com/browse/facets?key={k}&section=Products",
              f"https://ac.cnstrc.com/search/veste?key={k}&section=Products&num_results_per_page=3"]:
        try:
            r = requests.get(u, headers=UA, timeout=20)
            print("\n", u.split("?")[0], r.status_code, r.text[:700])
        except Exception as e:
            print(u, e)
