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
NOMS = {"CaminoTV": "Camino TV", "FitThemAll": "FitThemAll", "Sneakerologue": "Sneakerologue"}

CONSIGNE = """Tu lis des posts X de comptes français de bons plans mode (Camino TV, FitThemAll, Sneakerologue).
Pour chaque POST, avec son texte et sa photo, réponds :
- "garder" : true seulement si le post présente des vêtements, chaussures ou accessoires de mode (homme OU femme) portables au
  quotidien (streetwear, workwear, old money, minimal, sneakers lifestyle). false pour : sport pur (maillot de club ou
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
        r = requests.get(f"https://pbs.twimg.com/media/{media_id}?format=jpg&name=small", timeout=20)
        if r.status_code == 200:
            return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(r.content).decode()}}
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
            r = requests.post(f"{API}/models/{modele}:generateContent", headers={"x-goog-api-key": cle}, timeout=150,
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
    a_lire = [p for p in brut["posts"] if p[1] not in deja and date_id(p[1]) >= (MAINTENANT - timedelta(days=JOURS)).isoformat()]
    lus = {}
    for i in range(0, len(a_lire), 6):
        lus |= lire_lot(a_lire[i:i + 6], cle)
        time.sleep(5)
    gardes = 0
    for compte, pid, texte, images in a_lire:
        a = lus.get(pid)
        if not a or not a.get("garder") or not a.get("pieces"):
            continue
        liens = re.findall(r"https?://\S+", texte)
        deja[pid] = {"compte": compte, "compte_nom": NOMS.get(compte, compte), "tweet_id": pid, "url": f"https://x.com/{compte}/status/{pid}",
                     "date": date_id(pid), "texte": (a.get("resume") or "").strip() or texte[:200], "liens": liens,
                     "images": [f"https://pbs.twimg.com/media/{m}?format=jpg&name=medium" for m in images[:2]],
                     "genre": a.get("genre") if a.get("genre") in ("homme", "femme", "mixte") else "homme",
                     "pieces": [x for x in a["pieces"] if x.get("nom")]}
        gardes += 1
    limite = (MAINTENANT - timedelta(days=JOURS)).isoformat()
    posts = sorted((p for p in deja.values() if p["date"] >= limite), key=lambda p: p["date"], reverse=True)
    SORTIE.write_text(json.dumps({"maj": MAINTENANT.isoformat(), "lu_le": brut.get("lu_le"), "comptes": list(NOMS.values()),
                                  "posts": posts}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✅ {len(a_lire)} posts lus par l'IA, {gardes} gardés ; {len(posts)} plans en ligne (5 derniers jours)")


if __name__ == "__main__":
    main()
