"""Sondage : quelles boutiques exposent leurs produits (Shopify /products.json) et leurs soldes ?
Et la clé Gemini peut-elle générer des images ? Résultat dans etat/mode-sondage.json."""
import json, os, sys
from pathlib import Path
import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; PieceUnique/0.1; veille personnelle)", "Accept": "application/json"}
BOUTIQUES = [
  "representclo.com", "stuartslondon.com", "kestin.co", "universalworks.co.uk", "olive-clothing.com", "serviceworks.co",
  "dailypaperclothing.com", "arte-antwerp.com", "uskees.com", "percivalclothing.com", "stanray.com", "aimeleondore.com",
  "thefrankieshop.com", "colorfulstandard.com", "portugueseflannel.com", "drakes.com", "knowledgecotton.com",
  "bonnegueule.fr", "asphalte.com", "faguo-store.com", "maisonlabiche.com", "debonnefacture.fr", "lelaboureur.fr",
  "norseprojects.com", "foret.dk", "nn07.com", "kardo-india.com", "dickieslife.com", "edwin-europe.com",
  "hast.fr", "lesdeux.com", "samsoe.com", "minimum.dk", "outlandish.fr", "saintjames.com", "armorlux.com",
  "beamsplus.com", "garbstore.com", "goodhoodstore.com", "hollandandholland.com", "nigelcabourn.com",
  "workwearoutlet.co.uk", "taylorstitch.com", "buckmason.com", "nowmanifest.com", "lecolonel.fr",
]
COLLECTIONS = ["sale", "outlet", "soldes", "mens-sale", "men-sale", "sale-men", "archive-sale", "promotions", "black-friday", "last-chance"]

def essai(url):
    try:
        r = requests.get(url, headers=UA, timeout=20)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
            return r.json().get("products", None)
        return None
    except Exception:
        return None

res = []
for d in BOUTIQUES:
    base = f"https://{d}"
    tous = essai(f"{base}/products.json?limit=250")
    ligne = {"boutique": d, "shopify": tous is not None, "produits": len(tous or []), "soldes": None, "remises_dans_tout": 0, "devise": None}
    if tous:
        ligne["remises_dans_tout"] = sum(1 for p in tous for v in p.get("variants", [])[:1] if v.get("compare_at_price") and float(v["compare_at_price"]) > float(v["price"]))
        for c in COLLECTIONS:
            s = essai(f"{base}/collections/{c}/products.json?limit=250")
            if s:
                remis = [p for p in s for v in p.get("variants", [])[:1] if v.get("compare_at_price") and float(v["compare_at_price"]) > float(v["price"])]
                ligne["soldes"] = {"collection": c, "produits": len(s), "remises": len(remis),
                                   "exemple": [{"titre": p["title"], "prix": p["variants"][0]["price"], "avant": p["variants"][0].get("compare_at_price"),
                                                "image": (p.get("images") or [{}])[0].get("src")} for p in remis[:2]]}
                break
        try:
            m = requests.get(f"{base}/cart.js", headers=UA, timeout=15).json()
            ligne["devise"] = m.get("currency")
        except Exception:
            pass
    print(f"{'✓' if ligne['shopify'] else '✗'} {d:28} produits={ligne['produits']:3} remisés={ligne['remises_dans_tout']:3} soldes={ligne['soldes'] and (ligne['soldes']['collection'], ligne['soldes']['remises'])} devise={ligne['devise']}")
    res.append(ligne)

# Gemini : modèles capables de produire des images
images = []
cle = os.getenv("LLM_API_KEY", "").strip()
if cle:
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": cle}, params={"pageSize": 1000}, timeout=30)
        noms = [m["name"].split("/")[-1] for m in r.json().get("models", [])]
        images = [n for n in noms if "image" in n or "imagen" in n]
        print("Modèles d'image :", images)
        for n in [x for x in images if "gemini" in x][:3]:
            corps = {"contents": [{"parts": [{"text": "A simple product photo of a plain grey crewneck sweatshirt on a white background."}]}],
                     "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
            t = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{n}:generateContent", headers={"x-goog-api-key": cle}, json=corps, timeout=120)
            ok = t.status_code == 200 and any("inlineData" in p for c in t.json().get("candidates", []) for p in c.get("content", {}).get("parts", []))
            print(f"  essai {n} : {t.status_code} {'IMAGE OK' if ok else t.text[:200]}")
            images.append({"modele": n, "statut": t.status_code, "image": ok})
    except Exception as e:
        print("Gemini :", e)

Path("etat").mkdir(exist_ok=True)
Path("etat/mode-sondage.json").write_text(json.dumps({"boutiques": res, "images": images}, ensure_ascii=False, indent=1), encoding="utf-8")
