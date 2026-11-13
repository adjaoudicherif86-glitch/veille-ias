"""
Les relais : bons plans repérés par d'autres, lus automatiquement à chaque passage.
- Dealabs (communauté française de bons plans) : flux RSS « Mode homme » et « Sneakers ».
- LinkDeal (média mode/streetwear, concurrent de Camino) : les derniers posts de son site lnkd-linkdeal.fr.
L'IA garde ce qui colle au style Camino (streetwear, workwear, un peu d'old money, marques connues, pas cher, pas de sport)
et classe chaque pièce. Résultat : docs/mode/relais.json (les plans Camino lus à la demande restent dans camino.json).
"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collecte import EXCLURE, SPORT, MARQUES_CONNUES, CATEGORIES  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "docs" / "mode" / "relais.json"
NAV = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
       "Accept-Language": "fr-FR,fr;q=0.9"}
MAINTENANT = datetime.now(timezone.utc)
GARDER_JOURS = 5
URL_IA = os.getenv("LLM_API_URL", "").strip() or "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
ENFANT = re.compile(r"\b(fille|enfants?|kids?|junior|bébé|gar[cç]on)\b", re.I)
HORS_MODE = re.compile(r"\b(montre|watch|lunettes|sunglasses|parfum|eau de|bijou|bracelet|collier|valise|portefeuille|ceinture|"
                       r"cravate|chaussettes?|caleçons?|boxers?|slips?|pyjama|maillot de bain)\b", re.I)


def prix_txt(t):
    m = re.search(r"(\d+[.,]?\d*)\s*€", t or "")
    return float(m.group(1).replace(",", ".")) if m else None


def dealabs():
    items = []
    for groupe in ("mode-homme", "sneakers", "mode-femme"):
        try:
            x = requests.get(f"https://www.dealabs.com/rss/groupe/{groupe}", headers=NAV, timeout=30).text
        except Exception as e:
            print(f"  ✗ Dealabs {groupe} : {e}")
            continue
        for it in re.findall(r"<item>(.*?)</item>", x, re.S):
            g = lambda motif: (re.search(motif, it, re.S) or [None, ""])[1]
            titre = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", g(r"<title>(.*?)</title>"))).strip()
            lien = g(r"<link>(.*?)</link>").strip()
            marchand = html.unescape(g(r'<pepper:merchant name="([^"]*)"'))
            prix = prix_txt(g(r'<pepper:merchant[^>]*price="([^"]*)"'))
            image = g(r'<media:content[^>]*url="([^"]+)"').replace("/re/150x150/", "/re/300x300/")
            try:
                date = parsedate_to_datetime(g(r"<pubDate>(.*?)</pubDate>")).astimezone(timezone.utc).isoformat()
            except Exception:
                date = MAINTENANT.isoformat()
            desc = re.sub(r"<[^>]+>", " ", html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", g(r"<description>(.*?)</description>"))))
            if not titre or not lien:
                continue
            items.append({"id": "dealabs-" + lien.rsplit("-", 1)[-1], "source": "Dealabs", "titre": titre, "lien": lien, "marchand": marchand,
                          "prix": prix, "prix_avant": None, "image": image, "date": date, "extrait": re.sub(r"\s+", " ", desc)[:300]})
    print(f"  Dealabs : {len(items)} bons plans lus")
    return items


def linkdeal(pages=2):
    items = []
    for page in range(1, pages + 1):
        try:
            x = requests.get("https://lnkd-linkdeal.fr/" + (f"?page={page}" if page > 1 else ""), headers=NAV, timeout=30).text
        except Exception as e:
            print(f"  ✗ LinkDeal : {e}")
            break
        for href, bloc in re.findall(r'<a[^>]+href="(/go/[^"?]+)\?source=nos_posts"[^>]*>(.*?)</a>', x, re.S):
            alt = html.unescape((re.search(r'alt="([^"]*)"', bloc) or [None, ""])[1]).strip()
            src = re.search(r'url=([^&"]+)&amp;w=640', bloc) or re.search(r'url=([^&"]+)&amp;w=', bloc)
            image = unquote(src.group(1)) if src else ""
            texte = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", bloc))).strip()
            prix = [float(p.replace(",", ".")) for p in re.findall(r"(\d+(?:[.,]\d+)?)\s*€", texte)]
            if not alt or not prix:
                continue
            items.append({"id": "linkdeal-" + href.rsplit("/", 1)[-1], "source": "LinkDeal", "titre": alt, "lien": "https://lnkd-linkdeal.fr" + href,
                          "marchand": None, "prix": prix[0], "prix_avant": prix[1] if len(prix) > 1 and prix[1] > prix[0] else None,
                          "image": image, "date": None, "extrait": texte[:200]})
        time.sleep(1)
    print(f"  LinkDeal : {len(items)} bons plans lus")
    return items


CONSIGNE = """Tu tries des bons plans mode pour des lecteurs (hommes et femmes) qui suivent Camino TV : streetwear, workwear, un peu d'old money, marques
connues (Nike, Adidas, New Balance, Salomon, Carhartt WIP, Dickies, The North Face, Levi's, Ralph Lauren, Lacoste, Uniqlo,
Jack & Jones, Timberland, Le Coq Sportif, Vans, Converse…), petits prix. Pour chaque bon plan, réponds :
garder = true seulement si c'est un vêtement, des chaussures ou un accessoire de mode (bonnet, casquette, sac) pour homme ou
pour femme, dans ce style, à un prix intéressant. false pour : enfant, sport pur (maillot de foot, chaussures de running ou de
basket techniques, tenue de foot), montres, parfums, high-tech, sous-vêtements, chaussettes, pièces de luxe hors budget.
Réponds UNIQUEMENT en JSON : {"items": [{"id": "...", "garder": true|false, "genre": "homme|femme|mixte", "marque": "...", "nom": "nom court et clair en français",
"categorie": "veste|surchemise|maille|sweat|chemise|tshirt|pantalon|short|chaussures|accessoire",
"styles": ["streetwear|workwear|minimal|oldmoney"]}]}"""


def trier(items):
    cle = os.getenv("LLM_API_KEY", "").strip()
    if not cle:
        return {}
    rep = {}
    for i in range(0, len(items), 60):
        lot = items[i:i + 60]
        texte = "\n".join(f"{x['id']} | {x['titre']} | {x['prix'] or '?'} € | {x['marchand'] or x['source']} | {x['extrait'][:120]}" for x in lot)
        for m in ("gemini-flash-lite-latest", "gemini-2.5-flash-lite", "gemini-flash-latest"):
            try:
                r = requests.post(URL_IA, timeout=120, headers={"Authorization": f"Bearer {cle}"}, json={
                    "model": m, "temperature": 0, "messages": [{"role": "system", "content": CONSIGNE}, {"role": "user", "content": texte}]})
            except requests.RequestException:
                continue
            if r.status_code == 429:
                time.sleep(20)
                continue
            if r.status_code != 200:
                continue
            t = re.sub(r"```(json)?", "", r.json()["choices"][0]["message"]["content"])
            try:
                rep |= {x["id"]: x for x in json.loads(t[t.find("{"):t.rfind("}") + 1]).get("items", []) if x.get("id")}
                break
            except json.JSONDecodeError:
                continue
        time.sleep(4)
    return rep


def main():
    try:
        ancien = {x["id"]: x for x in json.loads(SORTIE.read_text(encoding="utf-8")).get("items", [])}
    except (FileNotFoundError, json.JSONDecodeError):
        ancien = {}
    bruts = dealabs() + linkdeal()
    bruts = [x for x in bruts if not ENFANT.search(x["titre"]) and not SPORT.search(x["titre"]) and not EXCLURE.search(x["titre"])
             and not HORS_MODE.search(x["titre"])]
    for x in bruts:  # LinkDeal n'a pas de date : on garde la première fois qu'on l'a vu
        x["date"] = x["date"] or (ancien.get(x["id"]) or {}).get("date") or MAINTENANT.isoformat()
    a_trier = [x for x in bruts if x["id"] not in ancien]
    avis = trier(a_trier)
    gardes = dict(ancien)
    for x in a_trier:
        a = avis.get(x["id"])
        if not a:
            # sans IA : on garde seulement les marques connues
            if MARQUES_CONNUES.search(x["titre"]) and not os.getenv("LLM_API_KEY"):
                gardes[x["id"]] = x | {"categorie": next((c for c, m in CATEGORIES if re.search(m, x["titre"], re.I)), "accessoire"), "styles": []}
            continue
        if a.get("garder"):
            gardes[x["id"]] = x | {"marque": a.get("marque"), "nom": a.get("nom") or x["titre"], "categorie": a.get("categorie"), "styles": a.get("styles", []),
                                   "genre": a.get("genre") or ("femme" if "femme" in x["lien"] else "homme")}
    limite = (MAINTENANT - timedelta(days=GARDER_JOURS)).isoformat()
    vivants = {x["id"] for x in bruts}
    items = sorted((x for x in gardes.values() if x["date"] >= limite and (x["source"] != "LinkDeal" or x["id"] in vivants)),
                   key=lambda x: x["date"], reverse=True)
    SORTIE.write_text(json.dumps({"maj": MAINTENANT.isoformat(), "items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✅ relais : {len(bruts)} lus, {len(a_trier)} nouveaux triés, {len(items)} en ligne "
          f"({sum(x['source'] == 'Dealabs' for x in items)} Dealabs, {sum(x['source'] == 'LinkDeal' for x in items)} LinkDeal)")


if __name__ == "__main__":
    main()
