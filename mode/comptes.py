"""
« Repéré sur X » : les bons plans relayés par Camino TV et ses concurrents (FitThemAll, Sneakerologue).
Les posts sont lus à la demande dans le navigateur de Chérif puis enregistrés dans etat/x-brut.json.
Ce script les fait lire par l'IA (texte + photo) pour nommer chaque pièce, puis écrit docs/mode/camino.json.
On ne garde que la mode homme (pas le sport pur, les maillots de club, la déco, les parfums, la revente).
Les posts de plus de 5 jours disparaissent du site : une promo relayée sur X ne dure pas.
"""
import base64
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

RACINE = Path(__file__).resolve().parent.parent
BRUT = RACINE / "etat" / "x-brut.json"
SORTIE = RACINE / "docs" / "mode" / "camino.json"
API = "https://generativelanguage.googleapis.com/v1beta"
MAINTENANT = datetime.now(timezone.utc)
JOURS = 5
NOMS = {"CaminoTV": "Camino TV", "FitThemAll": "FitThemAll", "Sneakerologue": "Sneakerologue",
        "Bershka": "Bershka", "pullandbear": "Pull&Bear"}

CONSIGNE = """Tu lis des posts X de bons plans mode : comptes français de relais (Camino TV, FitThemAll),
comptes officiels Bershka et Pull&Bear, et posts d'autres comptes (bons plans Black Friday mode, Bershka, Pull&Bear). Pour ces autres
comptes, "garder" vaut false aussi pour la pub déguisée, les concours, les liens d'affiliation sans prix et les posts
qui ne présentent pas une vraie offre.
Pour chaque POST, avec son texte et sa photo, réponds :
- "garder" : true seulement si le post présente des vêtements, chaussures ou accessoires de mode (homme OU femme) portables au
  quotidien (streetwear, workwear, old money, minimal). PAS DE SNEAKERS : écarte les baskets (Nike, Jordan, adidas, New
  Balance, Asics, Salomon…) ; garde seulement les autres chaussures (mocassins, boots, derbies, Clarks). Si un post mélange
  vêtements et baskets, garde le post mais ne mets pas les baskets dans "pieces". false pour : sport pur (maillot de club ou
  d'équipe, NBA, foot, running technique de compétition), enfant, déco, parfum, bijoux, électroménager,
  livres, revente/spéculation, simple annonce sans prix.
- "pieces" : chaque pièce citée, avec un NOM CLAIR en français (aide-toi de la photo : « pull col camionneur côtelé »,
  « Asics Gel-NYC beige »…), la marque, le prix, l'ancien prix si donné, le code promo, le lien exact du texte qui
  correspond, une étiquette courte si le post en donne une (« le + chaud »), la catégorie et les styles.
Réponds UNIQUEMENT en JSON :
{"posts": [{"id": "...", "garder": true|false, "genre": "homme|femme|mixte (pour qui sont les pièces)", "resume": "1 phrase en français, ton direct, qui dit ce que c'est",
  "pieces": [{"nom": "...", "marque": "... ou null", "prix": nombre ou null, "prix_avant": nombre ou null, "code": "... ou null",
              "lien": "... ou null", "etiquette": "... ou null",
              "categorie": "veste|surchemise|maille|sweat|chemise|tshirt|pantalon|short|chaussures|accessoire",
              "styles": ["streetwear|workwear|minimal|oldmoney"]}]}]}
N'invente aucun prix ni lien."""


def image_b64(media_id):
    try:
        url = media_id if media_id.startswith("http") else f"https://pbs.twimg.com/media/{media_id}?format=jpg&name=small"
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(r.content).decode()}}
    except requests.RequestException:
        pass
    return None


NAV = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
       "Accept-Language": "fr-FR,fr;q=0.9"}


def photo_produit(lien):
    """Post X sans photo lisible : on suit le lien (chck.me, tidd.ly…) et on prend la photo du produit (og:image)."""
    if not lien:
        return None
    try:
        r = requests.get(lien, headers=NAV, timeout=20, allow_redirects=True)
        m = re.search(r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)', r.text) or \
            re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', r.text)
        if m and m.group(1).startswith("http"):
            return m.group(1).replace("&amp;", "&")
    except requests.RequestException:
        pass
    return None


def lire_lot(lot, cle):
    parts = [{"text": CONSIGNE}]
    for compte, pid, texte, images in lot:
        parts.append({"text": f"POST {pid} (compte {compte}) :\n{texte}"})
        im = image_b64(images[0]) if images else None
        if im:
            parts.append(im)
    for modele in ("gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash"):
        try:
            r = requests.post(f"{API}/models/{modele}:generateContent", headers={"x-goog-api-key": cle}, timeout=90,
                              json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}})
        except requests.RequestException:
            continue
        if r.status_code == 429:
            time.sleep(25)
            continue
        if r.status_code != 200:
            continue
        try:
            t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return {p["id"]: p for p in json.loads(t[t.find("{"):t.rfind("}") + 1]).get("posts", []) if p.get("id")}
        except (KeyError, IndexError, json.JSONDecodeError):
            continue
    return {}


def date_id(pid):
    return datetime.fromtimestamp(((int(pid) >> 22) + 1288834974657) / 1000, timezone.utc).isoformat()


def main():
    cle = os.getenv("LLM_API_KEY", "").strip()
    brut = json.loads(BRUT.read_text(encoding="utf-8"))
    try:
        actuel = json.loads(SORTIE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        actuel = {"posts": []}
    deja = {p["tweet_id"]: p for p in actuel.get("posts", [])}
    ecartes = set(actuel.get("ecartes", []))  # posts déjà lus et écartés : on ne les relit pas
    a_lire = [p for p in brut["posts"] if p[1] not in deja and p[1] not in ecartes
              and date_id(p[1]) >= (MAINTENANT - timedelta(days=JOURS)).isoformat()]
    a_lire.sort(key=lambda p: int(p[1]), reverse=True)
    a_lire = a_lire[:72]  # au plus 12 lots par passage : le reste au prochain
    lus = {}
    debut = time.time()
    for i in range(0, len(a_lire), 6):
        if time.time() - debut > 18 * 60:
            break
        lus |= lire_lot(a_lire[i:i + 6], cle)
        time.sleep(4)
    gardes = 0
    for compte, pid, texte, images in a_lire:
        a = lus.get(pid)
        if a and (not a.get("garder") or not a.get("pieces")):
            ecartes.add(pid)
        if not a or not a.get("garder") or not a.get("pieces"):
            continue
        liens = re.findall(r"https?://\S+", texte)
        deja[pid] = {"compte": compte, "compte_nom": NOMS.get(compte, compte), "tweet_id": pid, "url": f"https://x.com/{compte}/status/{pid}",
                     "date": date_id(pid), "texte": (a.get("resume") or "").strip() or texte[:200], "liens": liens,
                     "images": [m if m.startswith("http") else f"https://pbs.twimg.com/media/{m}?format=jpg&name=medium" for m in images[:2]]
                     or [u for u in [photo_produit(next((x.get("lien") for x in a["pieces"] if x.get("lien")), None) or (liens[0] if liens else None))] if u],
                     "genre": a.get("genre") if a.get("genre") in ("homme", "femme", "mixte") else "homme",
                     "pieces": [x for x in a["pieces"] if x.get("nom")]}
        gardes += 1
    sans = [p for p in deja.values() if not p.get("images")][:30]
    for p in sans:
        u = photo_produit(next((x.get("lien") for x in p.get("pieces", []) if x.get("lien")), None) or (p.get("liens") or [None])[0])
        if u:
            p["images"] = [u]
    if sans:
        print(f"photos rattrapées : {sum(1 for p in sans if p.get('images'))}/{len(sans)}")
    limite = (MAINTENANT - timedelta(days=JOURS)).isoformat()
    posts = sorted((p for p in deja.values() if p["date"] >= limite), key=lambda p: p["date"], reverse=True)
    SORTIE.write_text(json.dumps({"maj": MAINTENANT.isoformat(), "lu_le": brut.get("lu_le"), "comptes": list(NOMS.values()),
                                  "posts": posts, "ecartes": sorted(ecartes, reverse=True)[:600]}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✅ {len(a_lire)} posts lus par l'IA, {gardes} gardés ; {len(posts)} plans en ligne (5 derniers jours)")


if __name__ == "__main__":
    main()
