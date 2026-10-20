"""
Regroupement par le sens : chaque sujet reçoit une empreinte numérique (embedding)
calculée par l'API Gemini (gratuite). Deux articles sur le même événement ont des
empreintes proches, même si leurs titres n'ont presque aucun mot en commun.

- Les empreintes sont mises en cache dans etat/embeddings.json : un article n'est
  jamais envoyé deux fois.
- Sans clé API, ou si l'API échoue, le robot garde le regroupement par les titres.
- etat/similarites.json liste les paires les plus proches, pour régler les seuils.
"""
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ETAT = Path(__file__).parent / "etat"
CACHE = ETAT / "embeddings.json"
DIMS = 256          # on tronque les empreintes : assez précis, cache léger
LOT = 20            # articles envoyés par requête (quota gratuit par minute)

# Seuils de similarité (cosinus entre -1 et 1)
# Mesuré sur les vraies données (20/10/2026) : un même événement raconté par deux médias
# donne 0,84 à 0,89 ; deux publications différentes peuvent aussi monter à 0,86.
# Donc : au-dessus de SEUIL_FORT, doublon évident ; entre les deux, l'IA tranche.
SEUIL_FORT = float(os.getenv("SEUIL_FORT", "0.93"))
SEUIL_ARBITRAGE = float(os.getenv("SEUIL_ARBITRAGE", "0.80"))
MAX_ARBITRAGES = int(os.getenv("MAX_ARBITRAGES", "40"))  # paires soumises à l'IA par passage

FUSIONS = []  # (cosinus, raison, titre A, titre B), pour vérifier les fusions faites  # même sujet si un indice concret le confirme


def texte_de(it):
    return f"{it['titre']}\n{(it.get('extrait') or '')[:500]}"


def _normaliser(v):
    v = v[:DIMS]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [round(x / n, 5) for x in v]


def _choisir_modele(session, url_base):
    force = os.getenv("LLM_EMBED_MODEL", "").strip()
    if force:
        return force
    try:
        ids = [m["id"].split("/")[-1] for m in session.get(f"{url_base}/models", timeout=20).json().get("data", [])]
        candidats = [i for i in ids if "embedding" in i and "exp" not in i]
        candidats.sort(key=lambda i: (not i.startswith("gemini-embedding"), "preview" in i, i), reverse=False)
        if candidats:
            return candidats[0]
    except Exception as e:
        print(f"  (liste des modèles d'empreinte indisponible : {e})", file=sys.stderr)
    return "gemini-embedding-001"


def empreintes(items, cle, url_chat):
    """Renvoie {id: vecteur normalisé} pour les sujets, en complétant le cache si possible."""
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}
    manquants = [it for it in items if it["id"] not in cache]
    if manquants and cle and "generativelanguage.googleapis.com" in url_chat:
        url_base = url_chat.rsplit("/chat/completions", 1)[0]
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {cle}", "Content-Type": "application/json"})
        modele = _choisir_modele(s, url_base)
        print(f"→ Empreintes de sens : {len(manquants)} sujet(s) avec {modele}")
        faits, essais = 0, 0
        i = 0
        while i < len(manquants):
            lot = manquants[i:i + LOT]
            try:
                r = s.post(f"{url_base}/embeddings", timeout=90,
                           json={"model": modele, "input": [texte_de(it) for it in lot]})
                if r.status_code == 429:
                    essais += 1
                    if essais > 4:
                        print(f"  ⏸ quota d'empreintes atteint ({faits} faites), la suite au prochain passage")
                        break
                    time.sleep(20 * essais)  # on patiente que le quota par minute se libère
                    continue
                r.raise_for_status()
                essais = 0
                for it, d in zip(lot, sorted(r.json()["data"], key=lambda d: d.get("index", 0))):
                    cache[it["id"]] = _normaliser(d["embedding"])
                faits += len(lot)
                i += LOT
                time.sleep(1.5)
            except Exception as e:
                print(f"  ✗ empreintes indisponibles ({e}) : regroupement par les titres", file=sys.stderr)
                break
    elif manquants:
        print("→ Pas d'empreintes de sens (clé Gemini absente) : regroupement par les titres")
    ids = {it["id"] for it in items}
    cache = {k: v for k, v in cache.items() if k in ids}
    ETAT.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    return cache


def cle_paire(a, b):
    return "|".join(sorted((a, b)))


def charger_arbitrages():
    try:
        return json.loads((ETAT / "arbitrages.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def sauver_arbitrages(memo, ids_actuels):
    garde = {k: v for k, v in memo.items() if all(i in ids_actuels for i in k.split("|"))}
    ETAT.mkdir(parents=True, exist_ok=True)
    (ETAT / "arbitrages.json").write_text(json.dumps(garde, indent=0), encoding="utf-8")


def cosinus(a, b):
    return sum(x * y for x, y in zip(a, b))


def releve_similarites(items, vecteurs, n=60):
    """Écrit les paires les plus proches (sources différentes, à moins de 3 jours) pour régler les seuils."""
    paires = []
    vus = [it for it in items if it["id"] in vecteurs]
    for i, a in enumerate(vus):
        da = datetime.fromisoformat(a["date"])
        for b in vus[i + 1:]:
            if a["source"] == b["source"] or abs((datetime.fromisoformat(b["date"]) - da).days) > 3:
                continue
            c = cosinus(vecteurs[a["id"]], vecteurs[b["id"]])
            if c >= 0.70:
                paires.append((round(c, 3), a["titre"][:110], b["titre"][:110]))
    paires.sort(reverse=True)
    choix = paires[:n] + [p for p in paires if 0.78 <= p[0] < 0.88][:40]
    (ETAT / "similarites.json").write_text(
        json.dumps({"seuils": {"doublon": SEUIL_FORT, "arbitrage_ia": SEUIL_ARBITRAGE}, "fusions_du_passage": FUSIONS, "paires_non_fusionnees": choix}, ensure_ascii=False, indent=1),
        encoding="utf-8")
