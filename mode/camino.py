"""
Les plans Camino : lit les nouveaux posts du compte X @CaminoTV avec l'API officielle de X (payante à l'usage,
environ 0,005 $ par post lu), garde les bons plans vêtements et chaussures, et les écrit dans docs/mode/camino.json.

- Clé : secret GitHub X_BEARER_TOKEN (sans clé, le script ne fait rien).
- Coût maîtrisé : on ne lit que les posts publiés depuis le dernier passage (since_id), 80 au maximum par passage.
- Les liens de Camino (chck.me) et leurs codes promo sont gardés tels quels : c'est leur travail, ils sont crédités.
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
ETAT = RACINE / "etat" / "camino.json"
SORTIE = RACINE / "docs" / "mode" / "camino.json"
COMPTE = "CaminoTV"
MAX_LECTURES = 80
GARDER_JOURS = 21
API = "https://api.x.com/2"
URL_IA = os.getenv("LLM_API_URL", "").strip() or "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
MAINTENANT = datetime.now(timezone.utc)


def lire_json(f, defaut):
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return defaut


def x_get(chemin, params, jeton):
    r = requests.get(f"{API}{chemin}", params=params, headers={"Authorization": f"Bearer {jeton}"}, timeout=30)
    if r.status_code == 429:
        print("  ⏸ limite de l'API X atteinte, on réessaiera au prochain passage")
        return None
    if r.status_code in (401, 402, 403):
        print(f"  ✗ API X : accès refusé ({r.status_code}) : clé invalide ou crédit épuisé. {r.text[:200]}")
        return None
    r.raise_for_status()
    return r.json()


def nouveaux_posts(jeton, etat):
    if not etat.get("user_id"):
        u = x_get(f"/users/by/username/{COMPTE}", {}, jeton)
        if not u or "data" not in u:
            return []
        etat["user_id"] = u["data"]["id"]
    params = {"max_results": min(100, MAX_LECTURES), "exclude": "retweets",
              "tweet.fields": "created_at,entities,conversation_id,in_reply_to_user_id,attachments",
              "expansions": "attachments.media_keys", "media.fields": "url,preview_image_url,type"}
    if etat.get("since_id"):
        params["since_id"] = etat["since_id"]
    else:  # premier passage : les 3 derniers jours seulement
        params["start_time"] = (MAINTENANT - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    d = x_get(f"/users/{etat['user_id']}/tweets", params, jeton)
    if not d:
        return []
    medias = {m["media_key"]: (m.get("url") or m.get("preview_image_url")) for m in d.get("includes", {}).get("media", [])}
    posts = []
    for t in d.get("data", []):
        liens = [u.get("expanded_url") or u.get("url") for u in (t.get("entities") or {}).get("urls", [])]
        liens = [l for l in liens if l and "x.com/" not in l and "twitter.com/" not in l]
        images = [medias[k] for k in (t.get("attachments") or {}).get("media_keys", []) if medias.get(k)]
        texte = re.sub(r"\s*https://t\.co/\w+", "", t["text"]).strip()
        posts.append({"tweet_id": t["id"], "url": f"https://x.com/{COMPTE}/status/{t['id']}", "date": t["created_at"],
                      "texte": texte, "liens": liens, "images": images[:4], "fil": t.get("conversation_id") != t["id"]})
    if d.get("meta", {}).get("newest_id"):
        etat["since_id"] = d["meta"]["newest_id"]
    print(f"  {len(posts)} nouveaux posts lus sur @{COMPTE}")
    return posts


CONSIGNE = """On te donne des posts du compte X de Camino TV (média streetwear français qui poste des bons plans).
Pour chaque post, dis s'il présente des VÊTEMENTS, CHAUSSURES ou ACCESSOIRES DE MODE HOMME à acheter (garder = true), ou
autre chose (salutations, déco, meubles, high-tech, vêtement femme seul, sans produit : garder = false).
Pour les posts gardés, liste chaque pièce citée avec son prix. Un post peut citer plusieurs pièces (« le + chaud 80 € »).
Réponds UNIQUEMENT en JSON :
{"posts": [{"tweet_id": "...", "garder": true|false,
  "pieces": [{"nom": "nom clair de la pièce", "marque": "ou null", "prix": nombre ou null, "prix_avant": nombre ou null,
              "code": "code promo cité ou null", "lien": "le lien du post qui correspond à cette pièce, ou null",
              "etiquette": "ex. : le + chaud, ou null",
              "categorie": "veste|surchemise|maille|sweat|chemise|tshirt|pantalon|short|chaussures|accessoire",
              "styles": ["workwear|streetwear|minimal|oldmoney"]}]}]}
Recopie les liens exactement. N'invente aucun prix."""


def analyser(posts):
    cle = os.getenv("LLM_API_KEY", "").strip()
    if not cle or not posts:
        return {}
    texte = "\n\n".join(f"POST {p['tweet_id']}\nTEXTE : {p['texte']}\nLIENS : {', '.join(p['liens']) or 'aucun'}" for p in posts)
    for m in ("gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"):
        try:
            r = requests.post(URL_IA, timeout=150, headers={"Authorization": f"Bearer {cle}"}, json={
                "model": m, "temperature": 0, "messages": [{"role": "system", "content": CONSIGNE}, {"role": "user", "content": texte}]})
        except requests.RequestException:
            continue
        if r.status_code == 429:
            time.sleep(25)
            continue
        if r.status_code != 200:
            continue
        t = re.sub(r"```(json)?", "", r.json()["choices"][0]["message"]["content"])
        try:
            return {p["tweet_id"]: p for p in json.loads(t[t.find("{"):t.rfind("}") + 1]).get("posts", []) if p.get("tweet_id")}
        except json.JSONDecodeError:
            continue
    return {}


def main():
    jeton = os.getenv("X_BEARER_TOKEN", "").strip()
    if not jeton:
        print("Pas de clé X_BEARER_TOKEN : les plans Camino ne sont pas lus (voir mode/camino.py).")
        return
    etat = lire_json(ETAT, {})
    sortie = lire_json(SORTIE, {"posts": []})
    posts = nouveaux_posts(jeton, etat)
    lu = analyser(posts)
    gardes = 0
    for p in posts:
        a = lu.get(p["tweet_id"])
        if a and a.get("garder") and a.get("pieces"):
            p["pieces"] = [x for x in a["pieces"] if x.get("nom")]
            sortie["posts"].append(p)
            gardes += 1
    limite = (MAINTENANT - timedelta(days=GARDER_JOURS)).isoformat()
    vus, propres = set(), []
    for p in sorted(sortie["posts"], key=lambda p: p["date"], reverse=True):
        if p["tweet_id"] not in vus and p["date"] >= limite:
            vus.add(p["tweet_id"])
            propres.append(p)
    sortie = {"maj": MAINTENANT.isoformat(), "compte": COMPTE, "posts": propres}
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps(sortie, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ETAT.parent.mkdir(exist_ok=True)
    ETAT.write_text(json.dumps(etat), encoding="utf-8")
    print(f"✅ {gardes} bons plans gardés sur {len(posts)} posts ; {len(propres)} plans Camino en ligne")


if __name__ == "__main__":
    sys.exit(main())
