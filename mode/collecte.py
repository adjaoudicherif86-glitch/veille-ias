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
from datetime import datetime, timedelta, timezone
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


def boutique_meta(domaine):
    """Devise de base de la boutique (celle de /products.json), pays et livraison en France, d'après /meta.json.
    Attention : /cart.js renvoie la devise du visiteur (USD depuis les serveurs GitHub), pas celle des prix."""
    try:
        m = requests.get(f"https://{domaine}/meta.json", headers=UA, timeout=15).json()
        pays = m.get("ships_to_countries") or []
        return m.get("currency") or "EUR", m.get("country"), ("FR" in pays) if pays else None
    except Exception:
        return "EUR", None, None


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
    images = [i["src"] for i in p.get("images", [])[:6] if i.get("src")]
    if not images:
        return None
    eur = round(prix * taux.get(dev, 1), 2)
    if eur > PRIX_MAX_EUR:
        return None
    return {
        "id": f"{b['domaine'].split('.')[0]}-{p['id']}", "boutique": b["nom"], "domaine": b["domaine"], "origine": b["origine"], "pays": b.get("pays", b["origine"]),
        "marque": p.get("vendor") or b["nom"], "nom": p["title"], "categorie": cat, "type": p.get("product_type", ""),
        "prix": prix, "avant": avant, "devise": dev, "remise": remise, "prix_eur": eur, "avant_eur": round(avant * taux.get(dev, 1), 2),
        "tailles": tailles[:12], "images": images, "lien": f"https://{b['domaine']}/products/{p['handle']}",
        "styles_indice": b.get("styles", []), "description": re.sub(r"<[^>]+>", " ", p.get("body_html") or "")[:300].strip(),
    }


MOIS = MAINTENANT.month
SAISON = "froid" if MOIS in (10, 11, 12, 1, 2, 3) else "chaud" if MOIS in (5, 6, 7, 8) else "mi-saison"
POIDS = {
    "froid": {"veste": 3.4, "maille": 3.4, "surchemise": 2.8, "sweat": 2.6, "pantalon": 2.6, "chaussures": 2.6, "chemise": 2,
              "accessoire": 1.2, "tshirt": .8, "short": -.5},
    "chaud": {"tshirt": 2.6, "short": 2.2, "chemise": 2.6, "pantalon": 2.4, "chaussures": 2.4, "surchemise": 2, "sweat": 1.2,
              "veste": 1, "maille": .6, "accessoire": .8},
    "mi-saison": {"veste": 3, "maille": 2.6, "surchemise": 3, "pantalon": 2.6, "chemise": 2.4, "chaussures": 2.4, "sweat": 2.2,
                  "tshirt": 1.4, "short": .8, "accessoire": .8},
}[SAISON]
BONUS_PAYS = {"FR": 2.5, "UK": 0, "US": -.8}  # autres pays de l'UE : 1.2


def score(x):
    """Rang d'un article : remise, saison, petit prix, et les boutiques françaises puis européennes d'abord."""
    prix_bonus = 2 if x["prix_eur"] <= 40 else 1.3 if x["prix_eur"] <= 70 else .7 if x["prix_eur"] <= 110 else 0
    return x["remise"] / 10 + POIDS.get(x["categorie"], 1) + prix_bonus + BONUS_PAYS.get(x.get("pays"), 1.2)


# --- IA : sélection et tenues ---------------------------------------------

URL = os.getenv("LLM_API_URL", "").strip() or "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
CONSIGNE = """Tu es styliste et chasseur de bonnes affaires pour un homme jeune, au budget serré, qui aime le streetwear,
le workwear, le minimal et le old money (références : Aimé Leon Dore, Carhartt WIP, COS, Ralph Lauren). On te donne des
articles réellement en promo, avec leur prix en euros. Réponds UNIQUEMENT en JSON :
{
 "pieces": [{"id": "...", "styles": ["workwear|streetwear|minimal|oldmoney", ...], "forte": true|false,
             "pourquoi": "ton avis en 1 phrase courte, façon média streetwear qui parle à sa commu (tutoiement, direct, sans
                          blabla marketing) : ce qui rend la pièce intéressante à ce prix. Ex. : « Un vrai ripstop Stan Ray à 42 balles, tu
                          le portes cinq ans. »"}],
 "coup": "id de la meilleure affaire du jour (belle pièce, grosse remise, prix bas)",
 "tenues": [{"style": "workwear|streetwear|minimal|oldmoney", "nom": "nom court qui sonne naturel (2 à 4 mots, pas de jeu de mots forcé)",
             "accroche": "1 phrase en tutoiement : pour quelle occasion, quelle vibe",
             "articles": ["id", "id", ...],
             "complements": [{"piece": "ex. : t-shirt blanc épais", "ou": "ex. : Uniqlo U", "prix": "ex. : 20 à 30 €"}],
             "conseils": ["3 conseils concrets pour la porter : proportions, couleurs, chaussures"]}]
}
Règles :
- "pieces" : classe CHAQUE article fourni. "forte" = pièce marquante (belle matière, coupe, coloris) à vrai bon prix.
- "tenues" : 2 tenues par style (8 au total), chacune avec 2 à 4 articles de la liste (différentes catégories : haut, bas,
  couche, chaussures…) qui vont vraiment ensemble (couleurs, matières, esprit). Complète avec 1 à 3 pièces basiques
  abordables qui ne sont pas dans la liste (marques à petits prix : Uniqlo, Kiabi, H&M, Decathlon, Dickies, Levi's, Vans…),
  40 € maximum chacune, jamais de pièces de luxe en complément.
- Privilégie les prix bas : le lecteur a peu d'argent. N'invente aucun id."""


CONTEXTE = f"""
Contexte du jour :
- Saison : {SAISON} ({MAINTENANT.strftime('%d/%m')}). Raisonne comme un acheteur logique : en saison froide, priorité aux
  vestes, maille, sweats, surchemises, pantalons épais et chaussures ; les t-shirts restent utiles en sous-couche mais ne
  sont pas la priorité. Les tenues doivent être portables MAINTENANT (pas de short en hiver).
- Le lecteur vit en France : favorise les boutiques françaises (FR), puis européennes (BE, NL, DK, DE, IT, SE, PT).
  Royaume-Uni (UK) et États-Unis (US) = douane et TVA en plus : au plus UNE pièce UK/US par tenue, et le "coup" doit venir
  de France ou de l'UE."""


def demander_ia(candidats):
    cle = os.getenv("LLM_API_KEY", "").strip()
    if not cle:
        return None
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {cle}", "Content-Type": "application/json"})
    lignes = "\n".join(f"{x['id']} | {x['marque']} | {x['nom']} | {x['categorie']} | {x['prix_eur']:.0f} € (−{x['remise']} %) | "
                       f"expédié de {x.get('pays', x['origine'])} | indice {','.join(x['styles_indice'])}" for x in candidats)
    modeles = [os.getenv("LLM_MODEL", "").strip()] if os.getenv("LLM_MODEL", "").strip() else \
        ["gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"]
    for m in modeles:
        for essai in range(2):
            try:
                r = s.post(URL, timeout=170, json={"model": m, "temperature": 0.5,
                                                  "messages": [{"role": "system", "content": CONSIGNE + CONTEXTE}, {"role": "user", "content": lignes}]})
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


# --- Photos portées : on repère, parmi les photos de la boutique, celle où un mannequin porte l'article ---

API_NATIVE = "https://generativelanguage.googleapis.com/v1beta"
VISION = """Voici des photos de produits de boutiques de vêtements, groupées par article (ARTICLE id, puis ses photos numérotées 0, 1, 2…).
Pour chaque article, indique la photo où une personne PORTE le vêtement en le montrant le mieux (photo portée, de préférence
en pied ou en buste, vêtement bien visible). Si aucune photo ne montre une personne qui porte l'article, mets -1.
Réponds UNIQUEMENT en JSON : {"id de l'article": numéro, ...}"""


def miniature(url):
    import base64
    try:
        r = requests.get(url + ("&" if "?" in url else "?") + "width=320", headers={"User-Agent": UA["User-Agent"]}, timeout=20)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            return {"inline_data": {"mime_type": r.headers["content-type"].split(";")[0], "data": base64.b64encode(r.content).decode()}}
    except Exception:
        pass
    return None


def photos_portees(articles):
    cle = os.getenv("LLM_API_KEY", "").strip()
    if not cle or not articles:
        return 0
    trouves = 0
    for i in range(0, len(articles), 6):
        lot = [a for a in articles[i:i + 6] if len(a["images"]) > 1]
        parts = [{"text": VISION}]
        for a in lot:
            parts.append({"text": f"ARTICLE {a['id']} ({a['nom']})"})
            for k, u in enumerate(a["images"][:6]):
                m = miniature(u)
                if m:
                    parts += [{"text": f"photo {k}"}, m]
        if len(parts) <= 1:
            continue
        for modele in ("gemini-flash-lite-latest", "gemini-2.5-flash-lite", "gemini-flash-latest"):
            try:
                r = requests.post(f"{API_NATIVE}/models/{modele}:generateContent", headers={"x-goog-api-key": cle}, timeout=120,
                                  json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}})
            except requests.RequestException:
                continue
            if r.status_code == 429:
                time.sleep(20)
                continue
            if r.status_code != 200:
                continue
            try:
                t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                rep = json.loads(t[t.find("{"):t.rfind("}") + 1])
            except (KeyError, IndexError, json.JSONDecodeError):
                continue
            for a in lot:
                k = rep.get(a["id"])
                if isinstance(k, int) and 0 <= k < len(a["images"]):
                    a["porte"] = a["images"][k]
                    trouves += 1
            break
        time.sleep(4)
    return trouves


def main():
    cfg = json.loads((Path(__file__).parent / "boutiques.json").read_text(encoding="utf-8"))["boutiques"]
    taux = taux_eur()
    articles, bilan = [], []
    for b in cfg:
        dev, pays_meta, livre_fr = boutique_meta(b["domaine"])
        if livre_fr is False:
            print(f"⛔ {b['nom']:16} ne livre pas la France d'après la boutique : ignorée")
            bilan.append({"boutique": b["nom"], "lus": 0, "gardes": 0, "devise": dev, "origine": b["origine"], "exclue": "ne livre pas la France"})
            continue
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
    # variété : pas plus de 16 modèles par boutique dans ce qu'on montre à l'IA
    par_boutique, candidats = {}, []
    for a in uniques:
        if par_boutique.get(a["boutique"], 0) < 16:
            par_boutique[a["boutique"]] = par_boutique.get(a["boutique"], 0) + 1
            candidats.append(a)
    candidats = candidats[:150]
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
    coup = rep.get("coup") if rep.get("coup") in par_id else None
    if (not coup or par_id[coup]["prix_eur"] > 70 or par_id[coup]["origine"] != "UE") and uniques:  # petit budget : le coup du jour reste abordable
        abordables = [a for a in uniques if a["prix_eur"] <= 70 and a["origine"] == "UE" and POIDS.get(a["categorie"], 1) >= 2]
        coup = max(abordables or uniques, key=lambda a: score(a) + (3 if a.get("forte") else 0))["id"]
    a_voir = list(dict.fromkeys([i for t in tenues for i in t["articles"]] + ([coup] if coup else [])
                                 + [a["id"] for a in sorted(uniques, key=score, reverse=True) if a.get("forte")][:40]))
    n = photos_portees([par_id[i] for i in a_voir])
    print(f"📸 {n} photos portées trouvées sur {len(a_voir)} articles vérifiés")
    # première apparition de chaque article : sert à « Ça vient de tomber »
    f_vus = RACINE / "etat" / "mode-vus.json"
    try:
        deja = json.loads(f_vus.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        deja = {}
    premiere = not deja
    jour = MAINTENANT.date().isoformat()
    for a in uniques:
        a["vu_le"] = deja.get(a["id"], jour)
        a["nouveau"] = not premiere and a["vu_le"] >= (MAINTENANT - timedelta(days=2)).date().isoformat()
        deja.setdefault(a["id"], jour)
    limite = (MAINTENANT - timedelta(days=60)).date().isoformat()
    f_vus.parent.mkdir(exist_ok=True)
    f_vus.write_text(json.dumps({k: v for k, v in deja.items() if v >= limite}, separators=(",", ":")), encoding="utf-8")
    for a in uniques:
        a["rang"] = round(score(a), 2)
    for a in uniques:  # allège le fichier lu par le site (téléphone)
        for k in ("description", "styles_indice", "type", "prix", "avant", "devise", "domaine", "vu_le"):
            a.pop(k, None)
        a["images"] = a["images"][:2] + ([a["porte"]] if a.get("porte") and a["porte"] not in a["images"][:2] else [])
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps({
        "maj": MAINTENANT.isoformat(), "saison": SAISON, "poids": POIDS, "modele": rep.get("_modele"), "taux": {k: round(v, 4) for k, v in taux.items() if k in ("GBP", "USD", "DKK")},
        "bilan": bilan, "coup": coup, "tenues": tenues, "articles": uniques,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✅ {len(uniques)} articles, {len(tenues)} tenues, coup du jour : {coup} ({rep.get('_modele')})")


if __name__ == "__main__":
    main()
