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

sys.path.insert(0, str(Path(__file__).resolve().parent))

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "docs" / "mode" / "data.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; PieceUnique/1.0; veille personnelle)", "Accept": "application/json"}
REMISE_MIN = 30
PRIX_MAX_EUR = 200
# Le style Camino : du streetwear, du workwear, un peu d'old money, pas du sport pur
SPORT = re.compile(r"\b(maillot|football|soccer|replica|(home|away|third) (shirt|jersey|kit)|pre-?match|matchday|fanwear|supporters?|"
                   r"football club|f\.?c\.?|ac milan|inter milan|juventus|fiorentina|psg|paris saint|olympique|real madrid|barcelona|arsenal|"
                   r"chelsea|liverpool|manchester (city|united)|bayern|dortmund|ajax|celtic|nba|nfl|basketball|basket-?ball|tennis|"
                   r"golf(?! ?le ?fleur)|cycling|cyclisme|swim|compression|marathon|training top|gym)\b", re.I)
MARQUES_CONNUES = re.compile(
    r"nike|jordan|adidas|new balance|asics|salomon|puma|reebok|converse|vans|hoka|timberland|clarks|dr\.? ?martens|birkenstock|ugg|"
    r"carhartt|dickies|north face|patagonia|columbia|arc.?teryx|stone island|c\.?p\.? company|st[uü]ssy|ralph lauren|lacoste|tommy|"
    r"levi|\blee\b|wrangler|uniqlo|zara|bershka|pull ?& ?bear|jack ?& ?jones|champion|napapijri|kappa|fila|ellesse|le coq sportif|"
    r"sergio tacchini|lyle ?& ?scott|fred perry|barbour|schott|alpha industries|obey|kangol|new era|eastpak|edwin|gramicci|and wander|"
    r"norse projects|arte antwerp|sixth june|avnier|olaf hussein|daily paper|pop trading|patta|represent|ami paris|a\.?p\.?c|kitsun|"
    r"axel arigato|veja|autry|calvin klein|hugo boss|armor.?lux|saint james|chevignon|teddy smith|kaporal|slip fran|faguo|olow|dagobear|"
    r"kulte|h[ée]las|homecore|carne bollente|dr[oô]le de monsieur|nudie|filling pieces|mizuno|saucony|diadora|karhu|merrell|quiksilver|"
    r"volcom|huf|thrasher|butter goods|polar skate|palace|kith|aim[ée] leon dore|parajumpers|k-?way|comme des gar", re.I)
PLAFONDS = {"chaussures": 130, "veste": 150, "surchemise": 100, "maille": 100}  # au-delà : onglet « Indés & pointu »


def zone(a):
    """principal = ce que Camino mettrait en avant (marque connue, expédié de l'UE, prix accessible) ; sinon « pointu »."""
    connue = a.get("enseigne") or MARQUES_CONNUES.search(f"{a['marque']} {a['nom']} {a['boutique']}")
    abordable = a["prix_eur"] <= PLAFONDS.get(a["categorie"], 90)
    return "principal" if (connue and abordable and a["origine"] == "UE") else "pointu"

PRIX_MAX_NEUF = 160   # onglet « Sans promo » : on reste sur des prix accessibles
JOURS_NEUF = 45
MAINTENANT = datetime.now(timezone.utc)

EXCLURE = re.compile(r"\b(women'?s?|womens|woman|ladies|femme|dress|skirt|bra|bikini|towel|mug|candle|book|magazine|poster|print|sticker|"
                     r"homeware|incense|fragrance|perfume|gift ?card|cup|vase|keyring|key ring|lighter|ashtray|blanket|pillow|cushion|"
                     r"socks?|underwear|boxer|brief|swim|phone case|airpods|playing cards|frisbee|ball|jupe|jupe-culotte|robe|junior|kids?|enfants?|girls?|boys|"
                     r"brassière|legging|soutien-gorge|caleçon|chaussettes?|slip|pyjamas?|pj|nightwear|loungewear)\b", re.I)
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


SOUS_TYPES = [
    ("puffer", r"puffer|doudoune|down\b|padded|quilted|matelass"), ("teddy", r"teddy|varsity|letterman"),
    ("polaire", r"sherpa|fleece|polaire|borg"), ("bomber", r"bomber|ma-?1|aviator|harrington"),
    ("coupe-vent", r"coach|windbreaker|coupe-vent|track jacket|shell"), ("travail", r"chore|worker|work jacket|travail|utility|engineer|coverall"),
    ("veste-denim", r"trucker|denim jacket|veste en (denim|jean)"), ("parka", r"parka|anorak|raincoat|imperm"),
    ("manteau", r"\bcoat|manteau|overcoat|\bmac\b"), ("blazer", r"blazer|suit|costume|tailored"),
    ("gilet", r"gilet|\bvest\b|sans manches|sleeveless"), ("cardigan", r"cardigan"),
    ("col-roule", r"roll ?neck|turtle|col roulé|mock"), ("hoodie", r"hood|capuche"), ("zip", r"\bzip"),
    ("pull", r"knit|sweater|jumper|\bpull|maille"), ("sweat", r"crew|sweatshirt|sweat\b"), ("polo", r"polo"),
    ("manches-longues", r"long ?sleeve|manches longues|\bls\b"), ("tee", r"\btee|t-shirt|tshirt"),
    ("cargo", r"cargo|fatigue|carpenter"), ("jean", r"jean|denim"), ("jogging", r"jogger|sweatpant|track pant|jogging"),
    ("velours", r"cord|velours"), ("chino", r"chino|pleat|trouser|pantalon|pant"), ("flanelle", r"flannel|flanelle|check|carreaux"),
    ("oxford", r"oxford|button.?down"), ("bottes", r"boot|botte"), ("mocassins", r"loafer|mocassin|derby"),
    ("baskets", r"sneaker|trainer|basket|runner"), ("casquette", r"\bcap\b|casquette"), ("bonnet", r"beanie|bonnet"), ("sac", r"bag|tote|sac"),
]


def sous_type(cat, nom):
    for nom_st, motif in SOUS_TYPES:
        if re.search(motif, nom, re.I):
            return f"{cat}:{nom_st}"
    return f"{cat}:autre"


def analyser(p, b, dev, taux, nouveaute=False):
    """Article en promo (par défaut) ou, avec nouveaute=True, article récent même sans remise."""
    if genre(p) == "femme":
        return None
    if EXCLURE.search(f"{p['title']} {p.get('product_type', '')} {' '.join(p.get('tags', []) if isinstance(p.get('tags'), list) else [p.get('tags', '')])}"):
        return None
    if SPORT.search(f"{p['title']} {p.get('product_type', '')}"):
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
    remise = round((1 - prix / avant) * 100) if avant > prix else 0
    if nouveaute:
        if remise >= REMISE_MIN:  # déjà dans les promos
            return None
        avant = avant if avant > prix else prix
    elif remise < REMISE_MIN:
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
    if eur > (PRIX_MAX_NEUF if nouveaute else PRIX_MAX_EUR):
        return None
    return {
        "id": f"{b['domaine'].split('.')[0]}-{p['id']}", "boutique": b["nom"], "domaine": b["domaine"], "origine": b["origine"], "pays": b.get("pays", b["origine"]),
        "marque": p.get("vendor") or b["nom"], "nom": p["title"], "categorie": cat, "fam": sous_type(cat, p["title"]), "type": p.get("product_type", ""),
        "prix": prix, "avant": avant, "devise": dev, "remise": remise, "prix_eur": eur, "avant_eur": round(avant * taux.get(dev, 1), 2),
        "tailles": tailles[:12], "images": images, "lien": f"https://{b['domaine']}/products/{p['handle']}", "handle": p["handle"],
        "styles_indice": b.get("styles", []), "description": re.sub(r"<[^>]+>", " ", p.get("body_html") or "")[:300].strip(),
        **({"sortie": (p.get("published_at") or p.get("created_at") or "")[:10]} if nouveaute else {}),
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
BONUS_FIAB = {"fiable": .8, "correct": .3, "enseigne": .3, "mitige": -.7, "prudence": -2}


def score(x):
    """Rang d'un article : remise, saison, petit prix, et les boutiques françaises puis européennes d'abord."""
    prix_bonus = 2 if x["prix_eur"] <= 40 else 1.3 if x["prix_eur"] <= 70 else .7 if x["prix_eur"] <= 110 else 0
    return x["remise"] / 10 + POIDS.get(x["categorie"], 1) + prix_bonus + BONUS_PAYS.get(x.get("pays"), 1.2) + BONUS_FIAB.get(x.get("fiab"), 0)


# --- IA : sélection et tenues ---------------------------------------------

URL = os.getenv("LLM_API_URL", "").strip() or "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
RAYONS = {
    "workwear": "vestes de travail, toiles épaisses, denim brut, chore jackets, cargos, bottes (esprit Carhartt WIP, Stan Ray, Dickies)",
    "streetwear": "hoodies lourds, puffers, cargos amples, pièces graphiques, skate, sneakers (esprit Stüssy, Patta, Arte Antwerp)",
    "minimal": "coupes nettes, couleurs neutres, belles matières, sans gros logo (esprit COS, Norse Projects, Uniqlo U)",
    "oldmoney": "maille, polos, chemises oxford, velours côtelé, mocassins, esprit preppy discret (esprit Ralph Lauren, Drake's)",
}
CONSIGNE = """Tu es le sélectionneur d'un média streetwear français (esprit Camino TV). Ton lecteur est un homme jeune, au budget
serré, qui cherche des PÉPITES : des pièces qui ont un vrai intérêt (matière, coupe, marque respectée, détail qui change tout)
à petit prix. Il en a marre des listes de vestes qui se ressemblent toutes.
Ton lecteur suit Camino TV : il veut des marques connues (Nike, Adidas, New Balance, Salomon, Carhartt WIP, Dickies, The North
Face, Levi's, Ralph Lauren, Lacoste, Uniqlo, Stüssy…) et de bonnes marques françaises abordables, à petit prix. Le sport pur
(maillots de foot, tenues de running technique, basket) est hors sujet : note 0.
Référence de goût : ce que relaient Camino TV et FitThemAll sur X. Par exemple : pantalon brossé et pantalon barrel Uniqlo,
half-zip côtelé, polaire Uniqlo ou Columbia, bomber Uniqlo x JW Anderson, surchemise matelassée Uniqlo C, doudounes simples
(Decathlon, Columbia), Air Max 95, Air Force 1, Asics Gel-NYC et Gel-1130, New Balance 1906R et 2002R, Salomon XT-4, Clarks
Gore-Tex, boots Timberland, mocassins Mango, polo adidas rayé, sweat Ralph Lauren, hoodie zippé Carhartt WIP, joggings Nike,
gants et bonnets ACG : des pièces qu'on porte vraiment, à petit prix.
Rayon du jour : {style} — {description}.
On te donne des articles réellement {quoi}, avec leur prix en euros. Réponds UNIQUEMENT en JSON :
{{
 "pieces": [{{"id": "...", "styles": ["workwear|streetwear|minimal|oldmoney", ...], "note": 0 à 10,
             "pourquoi": "si note ≥ 7 : ton avis en 1 phrase courte, tutoiement, direct, sans blabla marketing, qui dit ce que la
                          pièce a de spécial à ce prix. Sinon chaîne vide."}}]{tenues_schema}
}}
Règles :
- Note CHAQUE article, sévèrement : 9-10 = pépite rare ; 7-8 = bonne affaire solide ; 5-6 = correct mais banal ; moins de 5 =
  sans intérêt, hors style du rayon, ou pièce qu'on voit partout. Au plus {max_hauts} articles à 8 ou plus.
- ANTI-DOUBLONS : si plusieurs pièces se ressemblent (même type, même marque, même esprit), une seule peut avoir 8+ ; baisse
  les autres à 6 ou moins. Varie les types de pièces dans tes meilleures notes (veste, maille, pantalon, chaussures…).
- "styles" : le ou les vrais styles de la pièce (pas forcément le rayon).
- Privilégie les prix bas et les marques qui valent le coup d'être découvertes. N'invente aucun id.{tenues_regles}"""
TENUES_SCHEMA = """,
 "tenues": [{"nom": "nom court qui sonne naturel (2 à 4 mots)", "accroche": "1 phrase en tutoiement : pour quelle occasion, quelle vibe",
             "articles": ["id", "id", ...],
             "complements": [{"piece": "ex. : t-shirt blanc épais", "ou": "ex. : Uniqlo U", "prix": "ex. : 20 à 30 €"}],
             "conseils": ["3 conseils concrets pour la porter : proportions, couleurs, chaussures"]}]"""
TENUES_REGLES = """
- "tenues" : 2 tenues dans le style du rayon, chacune avec 2 à 4 articles de la liste (catégories différentes : haut, bas,
  couche, chaussures…) qui vont vraiment ensemble. Complète avec 1 à 3 basiques abordables hors liste (Uniqlo, Kiabi, H&M,
  Decathlon, Dickies, Levi's, Vans…), 40 € maximum chacun."""


CONTEXTE = f"""
Contexte du jour :
- Saison : {SAISON} ({MAINTENANT.strftime('%d/%m')}). Raisonne comme un acheteur logique : en saison froide, priorité aux
  vestes, maille, sweats, surchemises, pantalons épais et chaussures ; les t-shirts restent utiles en sous-couche mais ne
  sont pas la priorité. Les tenues doivent être portables MAINTENANT (pas de short en hiver).
- Le lecteur vit en France : favorise les boutiques françaises (FR), puis européennes. Royaume-Uni (UK) et États-Unis (US) =
  douane et TVA en plus : au plus UNE pièce UK/US par tenue.
- Fiabilité de la boutique (avis clients) : "fiable" et "correct" d'abord ; "mitige" seulement si la pièce vaut vraiment le
  coup ; JAMAIS de pièce "prudence" dans une tenue."""


def ligne(x):
    return (f"{x['id']} | {x['marque']} | {x['nom']} | {x['categorie']} | {x['prix_eur']:.0f} €"
            + (f" (−{x['remise']} %)" if x["remise"] else "") + f" | expédié de {x.get('pays', x['origine'])} | boutique {x.get('fiab', '?')}")


def demander_ia(consigne, candidats):
    cle = os.getenv("LLM_API_KEY", "").strip()
    if not cle or not candidats:
        return None
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {cle}", "Content-Type": "application/json"})
    lignes = "\n".join(ligne(x) for x in candidats)
    modeles = [os.getenv("LLM_MODEL", "").strip()] if os.getenv("LLM_MODEL", "").strip() else \
        ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"]
    for m in modeles:
        for essai in range(2):
            try:
                r = s.post(URL, timeout=150, json={"model": m, "temperature": 0.4,
                                                  "messages": [{"role": "system", "content": consigne + CONTEXTE}, {"role": "user", "content": lignes}]})
            except requests.RequestException as e:
                print(f"  ({m} : pas de réponse, {type(e).__name__})")
                break
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


def varies(articles, n, par_boutique=6, par_fam=5):
    """Les n meilleurs articles (par rang) sans empiler la même boutique ni le même type de pièce."""
    cb, cf, out = {}, {}, []
    for a in articles:
        if cb.get(a["boutique"], 0) >= par_boutique or cf.get(a["fam"], 0) >= par_fam:
            continue
        cb[a["boutique"]] = cb.get(a["boutique"], 0) + 1
        cf[a["fam"]] = cf.get(a["fam"], 0) + 1
        out.append(a)
        if len(out) >= n:
            break
    return out


def appliquer_notes(rep, par_id):
    for p in (rep or {}).get("pieces", []):
        a = par_id.get(p.get("id"))
        try:
            note = float(p.get("note", 0))
        except (TypeError, ValueError):
            note = 0
        if a and note >= a.get("note", -1):
            a["note"] = note
            st = [x for x in p.get("styles", []) if x in RAYONS]
            if st:
                a["styles"] = st
            if (p.get("pourquoi") or "").strip():
                a["pourquoi"] = p["pourquoi"].strip()


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


# --- Le fil, façon Camino : posts courts + fils « le + chaud / le + clean / le − cher » ---------------------------

CONSIGNE_FIL = """Tu tiens le compte d'un média streetwear français qui poste des bons plans, exactement dans l'esprit du Twitter de
Camino TV. Ton ton : parlé, spontané, minuscules, phrases courtes, tutoiement ou « vous » collectif, argot léger mais naturel
(« dar », « ça passe trop bien », « c'est des détails qui tuent », « valeur sûre », « là ça devient pas mal »). Tu parles de la
pièce comme un pote qui s'y connaît : la matière, la coupe, le détail qui change tout, la saison, la taille dispo. Jamais de
blabla marketing, jamais de hashtags, au plus un emoji de temps en temps.

Exemples de ton (à ne pas recopier) :
- « le côté brossé pour la saison là ça passe trop bien »
- « un halfzip avec ce genre d'empiècements c'est des détails qui tuent »
- « il est encore plus à l'aise lui (dispo jusqu'au 2XL) »
- « la bonne polaire, c'est plus que nécessaire là »

On te donne :
1. POSTS : des pièces déjà sélectionnées (promo ou nouveauté). Pour CHACUNE, écris un post de 1 à 2 phrases (25 mots max). Varie
   vraiment les débuts de phrase et les tournures d'un post à l'autre.
   Le prix est déjà affiché sous le post : ne le répète pas, SAUF si la pièce a une « baisse » (là tu peux dire « passe à X €
   au lieu de Y € »). Parle de la pièce, pas de la remise. Si de grandes tailles sont dispo
   (XXL, 2XL, 3XL), dis-le entre parenthèses. Ne répète pas la même formule d'un post à l'autre.
2. FILS : des listes de pièces du même type. Pour chaque liste, écris un titre de fil dans le même ton (ex. : « l'hiver c'est
   bien la saison des polaires »), puis choisis 4 ou 5 pièces DIFFÉRENTES (marques et prix variés) et donne à chacune une
   étiquette courte et unique : « le + chaud », « le + clean », « la − chère », « le + bg », « le + efficace », « le + oversize »,
   « le + solide », « le + original »… accordée au genre du mot (le pull, la veste).

Réponds UNIQUEMENT en JSON :
{"posts": [{"id": "...", "texte": "..."}], "fils": [{"titre": "...", "items": [{"id": "...", "label": "..."}]}]}
N'invente aucun id."""

NOMS_CAT = {"veste": "vestes", "surchemise": "surchemises", "maille": "pulls et cardigans", "sweat": "sweats et hoodies",
            "chemise": "chemises", "tshirt": "t-shirts et polos", "pantalon": "pantalons", "short": "shorts",
            "chaussures": "chaussures", "accessoire": "accessoires"}


def ligne_fil(x):
    grand = [t for t in x.get("tailles", []) if re.search(r"XXL|2XL|3XL|XXXL", str(t), re.I)]
    prix = f"{x['prix_eur']:.0f} €"
    if x.get("baisse_de"):
        prix += f" (baisse : avant {x['baisse_de']:.0f} €)"
    elif x["remise"]:
        prix += f" au lieu de {x['avant_eur']:.0f} € (−{x['remise']} %)"
    else:
        prix += " (prix normal)"
    return (f"{x['id']} | {x['marque']} | {x['nom']} | {prix} | {x['boutique']}"
            + (f" | grandes tailles : {', '.join(grand[:3])}" if grand else "") + (f" | avis : {x['pourquoi']}" if x.get("pourquoi") else ""))


def rediger_fil(posts, groupes):
    """posts : articles à présenter ; groupes : {catégorie: [articles]} pour les fils thématiques."""
    texte = "POSTS :\n" + "\n".join(ligne_fil(x) for x in posts)
    for cat, lot in groupes.items():
        texte += f"\n\nFIL — {NOMS_CAT.get(cat, cat)} :\n" + "\n".join(ligne_fil(x) for x in lot)
    cle = os.getenv("LLM_API_KEY", "").strip()
    if not cle:
        return {}
    for m in ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"]:
        for essai in range(2):
            try:
                r = requests.post(URL, timeout=150, headers={"Authorization": f"Bearer {cle}"}, json={
                    "model": m, "temperature": 0.8,
                    "messages": [{"role": "system", "content": CONSIGNE_FIL + CONTEXTE}, {"role": "user", "content": texte}]})
            except requests.RequestException:
                break
            if r.status_code in (429, 503) and essai == 0:
                time.sleep(25)
                continue
            if r.status_code != 200:
                break
            t = re.sub(r"```(json)?", "", r.json()["choices"][0]["message"]["content"])
            try:
                rep = json.loads(t[t.find("{"):t.rfind("}") + 1])
                rep["_modele"] = m
                return rep
            except json.JSONDecodeError:
                break
    return {}


def construire_fil(uniques, nouveautes, selection, par_id_tout):
    # les posts : la sélection, les baisses de prix, et les meilleures nouveautés
    baisses = sorted((a for a in uniques + nouveautes if a.get("baisse_de") and a.get("fiab") != "prudence"),
                     key=lambda a: a["baisse_de"] - a["prix_eur"], reverse=True)[:6]
    neufs = [a for a in nouveautes if a.get("note", 0) >= 8][:10]
    ids_posts = list(dict.fromkeys([i for i in selection[:24]] + [a["id"] for a in baisses + neufs]))[:36]
    posts, vus_p = [], set()
    for i in ids_posts:  # un seul post par marque et par type de pièce
        a = par_id_tout.get(i)
        if a and (a["marque"].lower(), a.get("fam")) not in vus_p:
            vus_p.add((a["marque"].lower(), a.get("fam")))
            posts.append(a)
    # les fils : 3 catégories de saison avec assez de bonnes pièces, marques variées
    pool = [a for a in uniques + nouveautes if a.get("note", 0) >= 6 and a.get("fiab") != "prudence"]
    groupes = {}
    for cat in sorted({a["categorie"] for a in pool}, key=lambda c: -POIDS.get(c, 1)):
        if POIDS.get(cat, 1) < 2:
            continue
        vus_m, lot = set(), []
        for a in sorted((a for a in pool if a["categorie"] == cat), key=lambda a: (a.get("note", 0), a.get("rang", 0)), reverse=True):
            if a["marque"].lower() in vus_m:
                continue
            vus_m.add(a["marque"].lower())
            lot.append(a)
            if len(lot) >= 12:
                break
        if len(lot) >= 6:
            groupes[cat] = lot
        if len(groupes) >= 3:
            break
    rep = rediger_fil(posts, groupes)
    textes = {p.get("id"): (p.get("texte") or "").strip() for p in rep.get("posts", []) if p.get("id") in par_id_tout}
    sortie_posts = []
    for a in posts:
        t = textes.get(a["id"]) or a.get("pourquoi") or ""
        if t:
            sortie_posts.append({"id": a["id"], "texte": t, "baisse": bool(a.get("baisse_de"))})
    fils = []
    for f in rep.get("fils", []):
        items = [{"id": i["id"], "label": (i.get("label") or "").strip()} for i in f.get("items", []) if i.get("id") in par_id_tout]
        items = list({i["id"]: i for i in items}.values())
        if len(items) >= 3 and (f.get("titre") or "").strip():
            fils.append({"titre": f["titre"].strip(), "items": items[:5]})
    print(f"→ le fil : {len(sortie_posts)} posts, {len(fils)} fils thématiques ({rep.get('_modele')})")
    return {"posts": sortie_posts, "fils": fils}


def suivre_prix(articles):
    """Garde le dernier prix vu de chaque pièce : une baisse d'au moins 5 % devient « passe à X au lieu de Y »."""
    f = RACINE / "etat" / "mode-prix.json"
    try:
        hist = json.loads(f.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        hist = {}
    jour = MAINTENANT.date().isoformat()
    n = 0
    for a in articles:
        h = hist.get(a["id"])
        if h and a["prix"] <= h["p"] * 0.95 and h["d"] < jour:
            a["baisse_de"] = h["e"]
            n += 1
        if not h or h["d"] < jour or a["prix"] < h["p"]:
            hist[a["id"]] = {"p": a["prix"], "e": round(a["prix_eur"]), "d": jour}
    limite = (MAINTENANT - timedelta(days=45)).date().isoformat()
    f.write_text(json.dumps({k: v for k, v in hist.items() if v["d"] >= limite}, separators=(",", ":")), encoding="utf-8")
    print(f"→ suivi des prix : {n} baisses depuis la dernière visite")


def devise_france(domaine):
    """Devise affichée à un visiteur français (marché France de la boutique)."""
    try:
        return requests.get(f"https://{domaine}/cart.js", headers=UA, timeout=15,
                            cookies={"localization": "FR", "cart_currency": "EUR"}).json().get("currency") or "EUR"
    except Exception:
        return None


def verifier_fr(articles, taux):
    """Relit chaque pièce comme un visiteur français, juste avant publication : prix France, remise France, stock.
    Une promo qui n'existe pas en France (fréquent chez les boutiques anglaises) ou qui a disparu est retirée."""
    from concurrent.futures import ThreadPoolExecutor
    par_dom = {}
    for a in articles:
        if a.get("handle") and a.get("domaine"):
            par_dom.setdefault(a["domaine"], []).append(a)
    garde, retire, echec = [], 0, 0
    heure = datetime.now(timezone.utc).isoformat()

    def boutique(dom):
        nonlocal retire, echec
        dev = devise_france(dom)
        ok = []
        for a in par_dom[dom]:
            try:
                r = requests.get(f"https://{dom}/products/{a['handle']}.js", headers=UA, timeout=15,
                                 cookies={"localization": "FR", "cart_currency": "EUR"})
                if r.status_code == 404:
                    retire += 1
                    continue
                d = r.json()
            except Exception:
                echec += 1
                ok.append(a)  # pas de réponse : on garde la lecture du catalogue
                continue
            dispo = [v for v in d.get("variants", []) if v.get("available")]
            if not dispo or not dev:
                retire += 1
                continue
            v = min(dispo, key=lambda x: x.get("price") or 10 ** 9)
            prix, avant = (v.get("price") or 0) / 100, (v.get("compare_at_price") or 0) / 100
            if not prix or avant <= prix or round((1 - prix / avant) * 100) < REMISE_MIN:
                retire += 1
                continue
            t = taux.get(dev, 1)
            a["prix_eur"], a["avant_eur"], a["remise"] = round(prix * t, 2), round(avant * t, 2), round((1 - prix / avant) * 100)
            noms = d.get("options") or []
            noms = [o.get("name") if isinstance(o, dict) else o for o in noms]
            idx = next((i for i, n in enumerate(noms) if n and TAILLES.match(n)), None)
            if idx is not None:
                a["tailles"] = list(dict.fromkeys(x.get(f"option{idx + 1}") for x in dispo if x.get(f"option{idx + 1}")))[:12]
            a["verifie"] = heure
            ok.append(a)
            time.sleep(.15)
        return ok

    with ThreadPoolExecutor(max_workers=12) as ex:
        for lot in ex.map(boutique, list(par_dom)):
            garde += lot
    for a in articles:  # Zara, Uniqlo : lus en direct sur le marché France
        if not a.get("handle"):
            a["verifie"] = heure
            garde.append(a)
    print(f"→ vérification au prix France : {len(garde)} gardées, {retire} retirées (promo absente en France, épuisée ou disparue), {echec} sans réponse")
    return garde


def main():
    cfg = json.loads((Path(__file__).parent / "boutiques.json").read_text(encoding="utf-8"))["boutiques"]
    taux = taux_eur()
    try:
        ancien = json.loads(SORTIE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        ancien = {}
    notes_avant = {a["id"]: a for a in ancien.get("articles", []) + ancien.get("nouveautes", []) if a.get("note") is not None}
    ia_du_jour = bool(os.getenv("FORCE_IA")) or MAINTENANT.hour in (6, 7) or len(notes_avant) < 50
    print(f"Passage {'complet (IA)' if ia_du_jour else 'rapide (prix et stocks, notes de ce matin)'}")
    articles, neufs, bilan = [], [], []
    depuis = (MAINTENANT - timedelta(days=JOURS_NEUF)).isoformat()
    for b in cfg:
        dev, pays_meta, livre_fr = boutique_meta(b["domaine"])
        if livre_fr is False:
            print(f"⛔ {b['nom']:16} ne livre pas la France d'après la boutique : ignorée")
            bilan.append({"boutique": b["nom"], "lus": 0, "gardes": 0, "devise": dev, "origine": b["origine"], "exclue": "ne livre pas la France"})
            continue
        brut = produits(b)
        catalogue = brut if not b.get("collection") else produits(b | {"collection": None})[:500]  # pour les nouveautés
        hommes = None

        def garder_homme(liste):
            nonlocal hommes
            if not b.get("mixte"):
                return liste
            par_tag = [p for p in liste if genre(p) == "homme"]
            if len(par_tag) >= max(10, len(liste) // 5):
                return par_tag
            if hommes is None:
                hommes = ids_homme(b) or set()
            garde = [p for p in liste if p["id"] in hommes]
            return garde if len(garde) >= max(10, len(liste) // 5) else liste

        brut = garder_homme(brut)
        gardes = [a for a in (analyser(p, b, dev, taux) for p in brut) if a]
        recents = [p for p in (catalogue if catalogue is brut else garder_homme(catalogue)) if (p.get("published_at") or "") >= depuis]
        nv = sorted((a for a in (analyser(p, b, dev, taux, nouveaute=True) for p in recents) if a), key=lambda a: a["sortie"], reverse=True)[:14]
        print(f"🛍️  {b['nom']:16} {len(brut):4} produits lus, {len(gardes):3} vraies affaires, {len(nv):2} nouveautés ({dev})")
        bilan.append({"boutique": b["nom"], "lus": len(brut), "gardes": len(gardes), "neufs": len(nv), "devise": dev, "origine": b["origine"]})
        articles += gardes
        neufs += nv
        time.sleep(1)
    # grandes enseignes hors Shopify (Zara, Uniqlo) : remise d'au moins 20 %, ou « prix spécial » Zara à 40 € max
    import enseignes
    for f in (enseignes.zara, enseignes.uniqlo):
        try:
            lot = f(CATEGORIES)
        except Exception as e:
            print(f"  ✗ {f.__name__} : {e}")
            lot = []
        gardes = [a for a in lot if not EXCLURE.search(a["nom"]) and not SPORT.search(a["nom"]) and (a["remise"] >= 20 or (a.get("prix_special") and a["prix_eur"] <= 40))]
        for a in gardes:
            a["fam"] = sous_type(a["categorie"], a["nom"])
        bilan.append({"boutique": f.__name__.capitalize(), "lus": len(lot), "gardes": len(gardes), "devise": "EUR", "origine": "UE"})
        articles += gardes
    # fiabilité de la boutique (avis clients vérifiés, mode/avis.json)
    import fiabilite
    avis = fiabilite.charger_avis()["boutiques"]
    for a in articles + neufs:
        a["fiab"] = fiabilite.niveau(avis.get(a["boutique"]))
    neufs = [a for a in neufs if a["fiab"] != "prudence"]

    # --- anti-similarité : un coloris par modèle, 3 pièces max par marque et par type, 120 max par boutique
    vus, compte, par_b, uniques = set(), {}, {}, []
    for a in sorted(articles, key=score, reverse=True):
        cle = (a["marque"].lower(), re.sub(r"\s*[-–(].*$", "", a["nom"].lower()))
        k = (a["marque"].lower(), a["fam"])
        if cle in vus or compte.get(k, 0) >= 3 or par_b.get(a["boutique"], 0) >= 120:
            continue
        vus.add(cle)
        compte[k] = compte.get(k, 0) + 1
        par_b[a["boutique"]] = par_b.get(a["boutique"], 0) + 1
        uniques.append(a)
    print(f"→ {len(articles)} affaires, {len(uniques)} gardées après tri des doublons et des pièces trop semblables")
    uniques = verifier_fr(uniques, taux)
    for a in uniques:
        a["zone"] = zone(a)
    par_id = {a["id"]: a for a in uniques}
    print(f"→ onglet principal : {sum(a['zone'] == 'principal' for a in uniques)} pièces ; indés et pointu : {sum(a['zone'] == 'pointu' for a in uniques)}")

    # --- l'IA note chaque rayon (sévèrement) et compose 2 tenues par style
    tenues, modele = [], None
    if not ia_du_jour:  # passage rapide : on reprend les notes et les fits de ce matin
        for a in uniques:
            v = notes_avant.get(a["id"])
            if v:
                for k in ("note", "styles", "pourquoi", "porte"):
                    if v.get(k) is not None:
                        a[k] = v[k]
        tenues = [t for t in ancien.get("tenues", []) if all(i in par_id for i in t.get("articles", []))]
        modele = ancien.get("modele")
    for style, description in (RAYONS.items() if ia_du_jour else []):
        cands = varies([a for a in uniques if style in a["styles_indice"] and a["zone"] == "principal"], 70)
        rep = demander_ia(CONSIGNE.format(style=style, description=description, quoi="en promo", max_hauts=14,
                                          tenues_schema=TENUES_SCHEMA, tenues_regles=TENUES_REGLES), cands)
        print(f"  rayon {style} : {len(cands)} candidats, {'noté par ' + rep['_modele'] if rep else 'IA indisponible'}")
        appliquer_notes(rep, par_id)
        for t in (rep or {}).get("tenues", []):
            ids = list(dict.fromkeys(i for i in t.get("articles", []) if i in par_id))
            if len(ids) >= 2 and not any(par_id[i].get("fiab") == "prudence" for i in ids):
                tenues.append(t | {"style": style, "articles": ids})
        modele = (rep or {}).get("_modele") or modele
        time.sleep(6)
    for a in uniques:
        a.setdefault("styles", a["styles_indice"])
        a["forte"] = a.get("note", 0) >= 8
        a["rang"] = round(score(a), 2)

    # --- la sélection : les mieux notées de chaque style, sans deux fois la même marque ni le même type
    selection = []
    for style in RAYONS:
        cm, cf, n = {}, {}, 0
        for a in sorted((x for x in uniques if x.get("note", 0) >= 7 and style in x["styles"] and x["fiab"] != "prudence" and x["zone"] == "principal"),
                        key=lambda x: (x["note"] + {"FR": .9, "UK": -.4, "US": -.8}.get(x["pays"], .4), x["rang"]), reverse=True):
            m = a["marque"].lower()
            hors_ue = a["origine"] != "UE"
            if a["id"] in selection or cm.get(m, 0) >= 2 or cf.get(a["fam"], 0) >= 2 or (hors_ue and cm.get("_hors_ue", 0) >= 4):
                continue
            if hors_ue:
                cm["_hors_ue"] = cm.get("_hors_ue", 0) + 1
            cm[m], cf[a["fam"]], n = cm.get(m, 0) + 1, cf.get(a["fam"], 0) + 1, n + 1
            selection.append(a["id"])
            if n >= 14:
                break
    print(f"→ sélection : {len(selection)} pépites")

    # --- le plan du jour : une pépite de saison, abordable, expédiée de France ou d'UE par une boutique fiable
    eligibles = [a for a in uniques if a["prix_eur"] <= 70 and a["zone"] == "principal" and POIDS.get(a["categorie"], 1) >= 2
                 and a.get("fiab") in ("fiable", "correct", "enseigne") and a["remise"] >= 30]
    coup = max(eligibles or uniques, key=lambda a: a.get("note", 0) * 2 + score(a))["id"] if uniques else None

    # --- sans promo : les sorties récentes, notées par l'IA pour les styles du lecteur
    vus_n, neufs_u = set(), []
    for a in sorted(neufs, key=lambda a: a["sortie"], reverse=True):
        cle = (a["marque"].lower(), re.sub(r"\s*[-–(].*$", "", a["nom"].lower()))
        if cle not in vus_n and a["id"] not in par_id and not SPORT.search(a["nom"]) and MARQUES_CONNUES.search(f"{a['marque']} {a['nom']} {a['boutique']}"):
            vus_n.add(cle)
            neufs_u.append(a)
    cands = varies(neufs_u, 140, par_boutique=6, par_fam=9)
    rep = None
    par_id_n = {a["id"]: a for a in cands}
    if not ia_du_jour:
        for a in cands:
            v = notes_avant.get(a["id"])
            if v:
                for k in ("note", "styles", "pourquoi"):
                    if v.get(k) is not None:
                        a[k] = v[k]
    for i in (range(0, len(cands), 70) if ia_du_jour else []):  # deux petits appels plutôt qu'un gros (plus fiable)
        r = demander_ia(CONSIGNE.format(style="les nouveautés", description="sorties récentes dans les quatre styles du lecteur : streetwear, workwear, minimal, old money",
                                        quoi="sortis ces dernières semaines (sans promo)", max_hauts=15, tenues_schema="", tenues_regles=""), cands[i:i + 70])
        appliquer_notes(r, par_id_n)
        rep = rep or r
        time.sleep(6)
    for a in cands:
        a.setdefault("styles", a["styles_indice"])
    nouveautes = sorted((a for a in cands if a.get("note", 6) >= 6), key=lambda a: (a.get("note", 0), a["sortie"]), reverse=True)[:72]
    print(f"→ sans promo : {len(neufs)} sorties récentes, {len(cands)} montrées à l'IA, {len(nouveautes)} gardées")

    suivre_prix(uniques + nouveautes)
    par_id_tout = {a["id"]: a for a in uniques + nouveautes}
    fil = {"posts": [], "fils": []}  # le fil façon Camino est retiré (Chérif préfère la sélection en grille)
    a_voir = list(dict.fromkeys([i for t in tenues for i in t["articles"]] + ([coup] if coup else []) + selection[:30]
                                + [p["id"] for p in fil["posts"] if p["id"] in par_id]))
    n = photos_portees([par_id_tout[i] for i in a_voir if not par_id_tout[i].get("porte")][:60]) if ia_du_jour else 0
    print(f"📸 {n} photos portées trouvées sur {len(a_voir)} articles vérifiés")
    # première apparition de chaque article : sert à « Ça vient de tomber »
    f_vus = RACINE / "etat" / "mode-vus.json"
    try:
        deja = json.loads(f_vus.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        deja = {}
    premiere = not deja
    jour = MAINTENANT.date().isoformat()
    debut = deja.setdefault("_debut", jour)
    for a in uniques:
        a["vu_le"] = deja.get(a["id"], jour)
        a["nouveau"] = not premiere and a["vu_le"] > debut and a["vu_le"] >= (MAINTENANT - timedelta(days=2)).date().isoformat()
        deja.setdefault(a["id"], jour)
    limite = (MAINTENANT - timedelta(days=60)).date().isoformat()
    f_vus.parent.mkdir(exist_ok=True)
    f_vus.write_text(json.dumps({k: v for k, v in deja.items() if k == "_debut" or v >= limite}, separators=(",", ":")), encoding="utf-8")
    for a in uniques + nouveautes:  # allège le fichier lu par le site (téléphone)
        for k in ("description", "styles_indice", "type", "prix", "avant", "devise", "domaine", "vu_le", "handle"):  # noqa
            a.pop(k, None)
        a["images"] = a["images"][:2] + ([a["porte"]] if a.get("porte") and a["porte"] not in a["images"][:2] else [])
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps({
        "maj": MAINTENANT.isoformat(), "saison": SAISON, "poids": POIDS, "modele": modele, "taux": {k: round(v, 4) for k, v in taux.items() if k in ("GBP", "USD", "DKK")},
        "bilan": bilan, "coup": coup, "selection": selection, "fil": fil, "tenues": tenues, "articles": uniques, "nouveautes": nouveautes,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✅ {len(uniques)} promos, {len(selection)} pépites, {len(nouveautes)} sans promo, {len(tenues)} tenues, plan du jour : {coup} ({modele})")


if __name__ == "__main__":
    main()
