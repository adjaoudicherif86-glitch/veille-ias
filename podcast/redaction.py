"""
Écrit le script de l'épisode du jour à partir des données de Flair (5 à suivre, histoires, brief),
découpé en séquences jouées séparément.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import rocco

RACINE = Path(__file__).resolve().parent.parent
DATA = RACINE / "docs" / "data"
URL = os.getenv("LLM_API_URL", "").strip() or "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def _json(nom, defaut):
    try:
        return json.loads((DATA / nom).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return defaut


def date_parlee(d):
    return f"{JOURS[d.weekday()]} {'premier' if d.day == 1 else d.day} {MOIS[d.month - 1]}"


def vraie_source(it):
    """Pour un article venu d'une recherche Google News, le vrai média est à la fin du titre (« … - Reuters »)."""
    if "news.google.com" in it.get("lien", "") and " - " in it["titre"]:
        return it["titre"].rsplit(" - ", 1)[1].strip()
    if it.get("primaire"):
        return f"{it['source']} (source officielle)"
    return it["source"]


def matiere(maintenant):
    """Rassemble ce dont parlera l'épisode."""
    meta, items = _json("meta.json", {}), {i["id"]: i for i in _json("items.json", [])}
    hist = _json("histoires.json", {"histoires": []})["histoires"]
    sujets = []
    for t in (meta.get("top5") or {}).get("items", []):
        it = items.get(t["id"])
        if not it:
            continue
        a = it.get("analyse") or {}
        sujets.append({
            "id": it["id"], "titre": a.get("titre_fr") or it["titre"], "source": vraie_source(it), "lien": it["lien"],
            "date": it["date"][:10], "a_retenir": a.get("a_retenir", ""), "resume": a.get("resume") or it.get("extrait", "")[:500],
            "pourquoi": t.get("pourquoi") or a.get("pourquoi", ""), "a_faire": t.get("a_faire", ""),
            "societe": (a.get("societe") or {}).get("nom", ""), "nb_sources": 1 + len({e["source"] for e in it.get("echos", [])}),
        })
    limite = (maintenant - timedelta(days=3)).isoformat()
    feuilleton = None
    for h in sorted(hist, key=lambda h: h["maj"], reverse=True):
        recents = [e for e in h["episodes"] if e["date"] >= limite]
        if 2 <= len(h["episodes"]) <= 40 and recents and not any(e["id"] in {s["id"] for s in sujets} for e in recents):
            feuilleton = {"id": h["id"], "titre": h["titre"], "ou_en_est": h.get("resume", ""),
                          "derniers": [{"date": e["date"][:10], "titre": e["titre"], "neuf": e.get("neuf", "")} for e in h["episodes"][-3:]]}
            break
    return {"date": date_parlee(maintenant), "sujets": sujets, "feuilleton": feuilleton,
            "brief": meta.get("brief") or {}}


CONSIGNE = """Tu écris le script de « Flair FM », le flash quotidien de l'actualité de l'intelligence artificielle,
présenté par Rocco. Durée visée : environ {minutes} minutes à l'oral, soit {mots} mots au total.

{regles}

Structure, en séquences séparées (chacune sera enregistrée à part puis montée) :
1. "intro" (60 à 80 mots) : « Flair FM, bonjour, c'est Rocco », la date, et un teaser qui donne envie.
2. un "sujet" par actu fournie, dans l'ordre (90 à 120 mots chacun). Varie les entrées en matière d'un sujet à l'autre.
3. "histoire" (80 à 110 mots), seulement si un feuilleton est fourni : rappel de l'épisode précédent, puis ce qui a bougé.
4. "fin" (50 à 70 mots) : une idée concrète à tester, puis la formule de fin de Rocco.

Réponds UNIQUEMENT en JSON : {{"titre": "titre de l'épisode, 8 mots max, accrocheur", "sequences": [{{"type": "intro|sujet|histoire|fin", "ref": "id du sujet ou de l'histoire (vide pour intro et fin)", "texte": "..."}}]}}"""


def _modeles(session):
    """Modèles candidats, du meilleur au plus économe : on passe au suivant si le quota gratuit est atteint."""
    force = os.getenv("LLM_MODEL", "").strip()
    if force:
        return [force]
    if "generativelanguage.googleapis.com" not in URL:
        return ["llama-3.3-70b-versatile"]
    try:
        ids = [m["id"].split("/")[-1] for m in session.get(URL.replace("/chat/completions", "/models"), timeout=20).json()["data"]]
    except Exception:
        ids = []
    texte = [i for i in ids if not any(x in i for x in ("tts", "image", "live", "embedding", "audio", "robotics", "omni", "computer"))]
    stables = lambda motif: sorted([i for i in texte if motif(i) and "preview" not in i and "exp" not in i], reverse=True)
    flash = stables(lambda i: "flash" in i and "lite" not in i)
    lite = stables(lambda i: "flash-lite" in i)
    ordre = flash[:2] + lite[:2] + ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    return list(dict.fromkeys(ordre))


def ecrire(maintenant=None, minutes=5):
    maintenant = maintenant or datetime.now(timezone.utc)
    m = matiere(maintenant)
    if not m["sujets"]:
        raise RuntimeError("Pas de sujets dans les 5 à suivre : rien à raconter")
    cle = os.getenv("LLM_API_KEY", "").strip()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {cle}", "Content-Type": "application/json"})
    candidats = _modeles(s)
    consigne = CONSIGNE.format(minutes=minutes, mots=minutes * 150, regles=rocco.REGLES_ECRITURE)
    message = "MATIÈRE DE L'ÉPISODE (JSON) :\n" + json.dumps(m, ensure_ascii=False, indent=1)
    essais = [(m, k) for m in candidats for k in range(2)]
    for modele, k in essais:
        try:
            r = s.post(URL, timeout=150, json={"model": modele, "temperature": 0.8,
                                              "messages": [{"role": "system", "content": consigne}, {"role": "user", "content": message}]})
        except requests.RequestException as e:
            print(f"   ({modele} : pas de réponse, {type(e).__name__} ; on passe à la suite)")
            continue
        if r.status_code in (429, 404, 400, 403, 503):
            print(f"   ({modele} : {r.status_code}, {'nouvel essai' if k == 0 else 'modèle suivant'})")
            if r.status_code in (429, 503) and k == 0:
                time.sleep(30)
            continue
        r.raise_for_status()
        texte = r.json()["choices"][0]["message"]["content"]
        try:
            texte = re.sub(r"```(json)?", "", texte)
            script = json.loads(texte[texte.find("{"):texte.rfind("}") + 1])
            seq = [x for x in script.get("sequences", []) if x.get("texte", "").strip() and x.get("type") in rocco.INTENTIONS]
            if len(seq) >= 3:
                script["sequences"] = seq
                script["modele"], script["matiere"] = modele, m
                return script
        except (json.JSONDecodeError, AttributeError):
            pass
    raise RuntimeError(f"Aucun modèle n'a pu écrire le script (essayés : {', '.join(candidats)})")
