"""Sonde temporaire : structure d'un produit Carhartt WIP dans Constructor.io."""
import json, requests
K = "key_QG9KK8DOmSUeFblV"
UA = {"User-Agent": "Mozilla/5.0 Chrome/131.0"}
r = requests.get(f"https://ac.cnstrc.com/search/veste?key={K}&section=Products&num_results_per_page=2", headers=UA, timeout=20).json()
res = r["response"]["results"]
print(json.dumps(res[0], ensure_ascii=False)[:3000])
print("GROUPS", json.dumps(r["response"].get("groups", []), ensure_ascii=False)[:2500])
for q in ["", "*", "homme"]:
    u = f"https://ac.cnstrc.com/browse/group_id/all?key={K}&section=Products&num_results_per_page=1"
for g in ["all", "men", "homme", "sale-men", "black-friday", "soldes", "promotions", "mens"]:
    x = requests.get(f"https://ac.cnstrc.com/browse/group_id/{g}?key={K}&section=Products&num_results_per_page=1", headers=UA, timeout=20).json()
    print("browse", g, x["response"].get("total_num_results"))
x = requests.get(f"https://ac.cnstrc.com/browse/groups?key={K}&section=Products", headers=UA, timeout=20)
print("browse/groups", x.status_code, x.text[:3000])
