"""
Pièce Unique : collecte des promos mode homme, sélection par l'IA, tenues composées de vrais articles.
Lit les boutiques de mode/boutiques.json (Shopify : /products.json), garde les vraies remises (≥ 30 %),
les articles encore disponibles dans au moins deux tailles, puis demande à Gemini de choisir les pièces
fortes et de composer des tenues. Résultat : docs/mode/data.json (lu par docs/mode/index.html).
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "docs" / "mode" / "data.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; PieceUnique/1.0; veille personnelle)", "Accept": "application/json"}
REMISE_MIN = 30
PRIX_MAX_EUR = 200
MAINTENANT = datetime.now(timezone.utc)

EXCLURE = re.compile(r"\b(women'?s?|womens|woman|ladies|femme|dress|skirt|bra|bikini|towel|mug|candle|book|magazine|poster|print|sticker|"
                     r"homeware|incense|fragrance|perfume|gift ?card|cup|vase|keyring|key ring|lighter|ashtray|blanket|pillow|cushion|"
                     r"socks?|underwear|boxer|brief|swim|phone case|airpods|playing cards|frisbee|ball)\b", re.I)
CATEGORIES = [
    ("accessoire", r"\b(cap|hat|beanie|bucket|bag|tote|backpack|belt|scarf|bandana|neckerchief|glove|wallet|casquette|bonnet|sac|ceinture|écharpe)s?\b"),
    ("chaussures", r"\b(shoe|boot|sneaker|trainer|loafer|derby|mule|clog|sandal|chaussure|basket|mocassin)s?\b"),
    ("surchemise", r"\b(overshirt|over shirt|shirt jacket|shacket|surchemise)\b"),
    ("veste", r"\b(jacket|coat|parka|blouson|bomber|anorak|overcoat|trucker|chore|harrington|veste|manteau|puffer|fleece|gilet)s?\b"),
    ("maille", r"\b(knit|knitted|sweater|jumper|cardigan|pull|maille|roll ?neck|turtle ?neck|mock neck)\b"),
    ("sweat", r"\b(sweatshirt|hoodie|hooded|crewneck|crew neck sweat|zip through|sweat)\b"),
    ("chemise", r"\b(shirt|chemise)\b"),
    ("tshirt", r"\b(t-shirt|tee|tshirt|polo|long ?sleeve|henley|vest top|tank)\b"),
    ("pantalon", r"\b(pant|trouser|jean|denim|chino|cargo|jogger|pantalon|fatigue)s?\b"),
    ("short", r"\b(short)s?\b"),
]
FEMME = re.compile(r"\b(women|womens|woman|ladies|female|wmns|dame|damer|kvinde|femme|femmes|her)\b", re.I)
HOMME = re.compile(r"\b(men|mens|man|male|menswear|herre|herrer|homme|hommes)\b", re.I)
TAILLES = re.compile(r"^(size|taille|größe|storlek|størrelse)$", re.I)


def taux_eur():
    try:
        r = requests.get("https://api.frankfurter.app/latest", params={"from": "EUR"}, timeout=20).json()["rates"]
        return {k: 1 / v for k, v in r.items()} | {"EUR": 1.0}
    except Exception as e:
        print(f"  (taux de change indisponibles : {e}, valeurs de secours)", file=sys.stderr)
        return {"EUR": 1.0, "GBP": 1.15, "USD": 0.87, "DKK": 0.134, "SEK": 0.087}


def devise(domaine):
    try:
        return requests.get(f"https://{domaine}/cart.js", headers=UA, timeout=15).json().get("currency") or "EUR"
    except Exception:
        return "EUR"


def produits(b):
    base = f"https://{b['domaine']}"
    chemin = f"/collections/{b['collection']}/products.json" if b.get("collection") else "/products.json"
    tous = []
    for page in range(1, 5):
        try:
            r = requests.get(base + chemin, headers=UA, params={"limit": 250, "page": page}, timeout=30)
            lot = r.json().get("products", []) if r.status_code == 200 else []
        except Exception as e:
            print(f"  ✗ {b['nom']} page {page} : {e}", file=sys.stderr)
            break
        tous += lot
        if len(lot) < 250:
            break
        time.sleep(1)
    return tous


def categorie(p):
    texte = f"{p.get('product_type', '')} {p['title']}"
    for nom, motif in CATEGORIES:
        if re.search(motif, texte, re.I):
            return nom
    return None


def ids_homme(b):
    """Boutique mixte : on ne garde que les produits de la collection homme."""
    for h in ("men", "mens", "herre", "man", "homme", "menswear", "mens-collection", "shop-men"):
        ids = set()
        for page in range(1, 9):
            try:
                r = requests.get(f"https://{b['domaine']}/collections/{h}/products.json", headers=UA, params={"limit": 250, "page": page}, timeout=30)
                lot = r.json().get("products", []) if r.status_code == 200 else []
            except Exception:
                lot = []
            ids |= {x["id"] for x in lot}
            if len(lot) < 250:
                break
        if ids:
            print(f"  {b['nom']} : collection homme « {h} », {len(ids)} produits")
            return ids
    return None


def genre(p):
    tags = p.get("tags", [])
    tags = tags if isinstance(tags, list) else str(tags).split(",")
    texte = f"{' '.join(tags)} {p.get('product_type', '')} {p.get('handle', '').replace('-', ' ')}"
    if FEMME.search(texte) and not HOMME.search(texte):
        return "femme"
    return "homme" if HOMME.search(texte) else None


def analyser(p, b, dev, taux):
    if genre(p) == "femme":
        return None
    if EXCLURE.search(f"{p['title']} {p.get('product_type', '')} {' '.join(p.get('tags', []) if isinstance(p.get('tags'), list) else [p.get('tags', '')])}"):
        return None
    cat = categorie(p)
    if not cat:
        return None
    variantes = p.get("variants", [])
    dispo = [v for v in variantes if v.get("available")]
    if not dispo:
        return None
    v = min(dispo, key=lambda x: float(x["price"]))
    prix, avant = float(v["price"]), float(v.get("compare_at_price") or 0)
    if not avant or avant <= prix:
        return None
    remise = round((1 - prix / avant) * 100)
    if remise < REMISE_MIN:
        return None
    idx = next((i for i, o in enumerate(p.get("options", [])) if TAILLES.match(o.get("name", ""))), None)
    tailles = []
    if idx is not None:
        cle = f"option{idx + 1}"
        tailles = list(dict.fromkeys(x.get(cle) for x in dispo if x.get(cle)))
        if cat != "accessoire" and len(tailles) < 2:
            return None
    images = [i["src"] for i in p.get("images", [])[:3] if i.get("src")]
    if not images:
        return None
    eur = round(prix * taux.get(dev, 1), 2)
    if eur > PRIX_MAX_EUR:
        return None
    return {
        "id": f"{b['domaine'].split('.')[0]}-{p['id']}", "boutique": b["nom"], "domaine": b["domaine"], "origine": b["origine"],
        "marque": p.get("vendor") or b["nom"], "nom": p["title"], "categorie": cat, "type": p.get("product_type", ""),
        "prix": prix, "avant": avant, "devise": dev, "remise": remise, "prix_eur": eur, "avant_eur": round(avant * taux.get(dev, 1), 2),
        "tailles": tailles[:12], "images": images, "lien": f"https://{b['domaine']}/products/{p['handle']}",
        "styles_indice": b.get("styles", []), "description": re.sub(r"<[^>]+>", " ", p.get("body_html") or "")[:300].strip(),
    }


def score(x):
    priorite = {"veste": 3, "maille": 3, "surchemise": 3, "pantalon": 2.6, "chemise": 2.2, "chaussures": 2.4, "sweat": 2, "tshirt": 1, "short": .6, "accessoire": .8}
    prix_bonus = 2 if x["prix_eur"] <= 40 else 1.3 if x["prix_eur"] <= 70 else .7 if x["prix_eur"] <= 110 else 0
    return x["remise"] / 10 + priorite.get(x["categorie"], 1) + prix_bonus + (0.8 if x["origine"] == "UE" else 0)


# --- IA : sélection et tenues ---------------------------------------------

URL = os.getenv("LLM_API_URL", "").strip() or "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
CONSIGNE = """Tu es styliste et chasseur de bonnes affaires pour un homme jeune, au budget serré, qui aime le streetwear,
le workwear, le minimal et le old money (références : Aimé Leon Dore, Carhartt WIP, COS, Ralph Lauren). On te donne des
articles réellement en promo, avec leur prix en euros. Réponds UNIQUEMENT en JSON :
{
 "pieces": [{"id": "...", "styles": ["workwear|streetwear|minimal|oldmoney", ...], "forte": true|false,
             "pourquoi": "1 phrase en français : pourquoi c'est une bonne affaire ou une pièce intéressante"}],
 "coup": "id de la meilleure affaire du jour (belle pièce, grosse remise, prix bas)",
 "tenues": [{"style": "workwear|streetwear|minimal|oldmoney", "nom": "nom court et évocateur", "accroche": "1 phrase",
             "articles": ["id", "id", ...],
             "complements": [{"piece": "ex. : t-shirt blanc épais", "ou": "ex. : Uniqlo U", "prix": "ex. : 20 à 30 €"}],
             "conseils": ["3 conseils concrets pour la porter : proportions, couleurs, chaussures"]}]
}
Règles :
- "pieces" : classe CHAQUE article fourni. "forte" = pièce marquante (belle matière, coupe, coloris) à vrai bon prix.
- "tenues" : 2 tenues par style (8 au total), chacune avec 2 à 4 articles de la liste (différentes catégories : haut, bas,
  couche, chaussures…) qui vont vraiment ensemble (couleurs, matières, esprit). Complète avec 1 à 3 pièces basiques
  abordables qui ne sont pas dans la liste (marques à petits prix : Uniqlo, Arket, Weekday, Dickies, Levi's…).
- Privilégie les prix bas : le lecteur a peu d'argent. N'invente aucun id."""


def demander_ia(candidats):
    cle = os.getenv("LLM_API_KEY", "").strip()
    if not cle:
        return None
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {cle}", "Content-Type": "application/json"})
    lignes = "\n".join(f"{x['id']} | {x['marque']} | {x['nom']} | {x['categorie']} | {x['prix_eur']:.0f} € (−{x['remise']} %) | "
                       f"origine {x['origine']} | indice {','.join(x['styles_indice'])}" for x in candidats)
    modeles = [os.getenv("LLM_MODEL", "").strip()] if os.getenv("LLM_MODEL", "").strip() else \
        ["gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"]
    for m in modeles:
        for essai in range(2):
            try:
                r = s.post(URL, timeout=170, json={"model": m, "temperature": 0.5,
                                                  "messages": [{"role": "system", "content": CONSIGNE}, {"role": "user", "content": lignes}]})
            except requests.RequestException as e:
                print(f"  ({m} : pas de réponse, {type(e).__name__})")
                continue
            if r.status_code != 200:
                print(f"  ({m} : {r.status_code})")
                if r.status_code in (429, 503) and essai == 0:
                    time.sleep(25)
                    continue
                break
            t = r.json()["choices"][0]["message"]["content"]
            t = re.sub(r"```(json)?", "", t)
            try:
                rep = json.loads(t[t.find("{"):t.rfind("}") + 1])
                rep["_modele"] = m
                return rep
            except json.JSONDecodeError:
                print(f"  ({m} : réponse illisible)")
    return None


def main():
    cfg = json.loads((Path(__file__).parent / "boutiques.json").read_text(encoding="utf-8"))["boutiques"]
    taux = taux_eur()
    articles, bilan = [], []
    for b in cfg:
        dev = devise(b["domaine"])
        brut = produits(b)
        if b.get("mixte"):
            par_tag = [p for p in brut if genre(p) == "homme"]
            if len(par_tag) >= max(10, len(brut) // 5):
                brut = par_tag
            else:
                hommes = ids_homme(b)
                garde = [p for p in brut if p["id"] in (hommes or ())]
                if len(garde) >= max(10, len(brut) // 5):
                    brut = garde
        gardes = [a for a in (analyser(p, b, dev, taux) for p in brut) if a]
        print(f"🛍️  {b['nom']:16} {len(brut):4} produits lus, {len(gardes):3} vraies affaires ({dev})")
        bilan.append({"boutique": b["nom"], "lus": len(brut), "gardes": len(gardes), "devise": dev, "origine": b["origine"]})
        articles += gardes
        time.sleep(1)
    # une même pièce dans plusieurs coloris : on garde le meilleur coloris par modèle
    vus, uniques = set(), []
    for a in sorted(articles, key=score, reverse=True):
        cle = (a["marque"].lower(), re.sub(r"\s*[-–(].*$", "", a["nom"].lower()))
        if cle in vus:
            continue
        vus.add(cle)
        uniques.append(a)
    candidats = uniques[:140]
    print(f"→ {len(articles)} affaires, {len(uniques)} modèles distincts, {len(candidats)} envoyés à l'IA")
    rep = demander_ia(candidats) or {}
    par_id = {a["id"]: a for a in uniques}
    for p in rep.get("pieces", []):
        a = par_id.get(p.get("id"))
        if a:
            a["styles"] = [s for s in p.get("styles", []) if s in ("workwear", "streetwear", "minimal", "oldmoney")] or a["styles_indice"]
            a["forte"] = bool(p.get("forte"))
            a["pourquoi"] = (p.get("pourquoi") or "").strip()
    for a in uniques:
        a.setdefault("styles", a["styles_indice"])
        a.setdefault("forte", False)
    tenues = []
    for t in rep.get("tenues", []):
        ids = [i for i in t.get("articles", []) if i in par_id]
        if len(ids) >= 2 and t.get("style") in ("workwear", "streetwear", "minimal", "oldmoney"):
            t["articles"] = ids
            tenues.append(t)
    coup = rep.get("coup") if rep.get("coup") in par_id else (max(uniques, key=score)["id"] if uniques else None)
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps({
        "maj": MAINTENANT.isoformat(), "modele": rep.get("_modele"), "taux": {k: round(v, 4) for k, v in taux.items() if k in ("GBP", "USD", "DKK")},
        "bilan": bilan, "coup": coup, "tenues": tenues, "articles": uniques,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ {len(uniques)} articles, {len(tenues)} tenues, coup du jour : {coup} ({rep.get('_modele')})")


if __name__ == "__main__":
    main()
