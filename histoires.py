"""
Fils d'histoire : relier les actus en histoires suivies dans le temps.

À chaque passage, les actus importantes pas encore traitées sont envoyées à l'IA par lots,
dans l'ordre chronologique, avec les histoires existantes les plus proches (par le sens).
L'IA décide pour chacune : épisode d'une histoire existante, début d'une nouvelle histoire,
ou actu isolée. Elle écrit ce que l'épisode change, et met à jour le résumé « où en est-on ».

Publié : docs/data/histoires.json (lu par l'appli)
Mémoire : etat/histoires_vec.json (empreinte moyenne de chaque histoire)
"""
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).parent
FICHIER = RACINE / "docs" / "data" / "histoires.json"
FICHIER_VEC = RACINE / "etat" / "histoires_vec.json"
MAINTENANT = datetime.now(timezone.utc)

TAILLE_LOT = int(os.getenv("HISTOIRES_LOT", "25"))        # actus par requête
LOTS_MAX = int(os.getenv("HISTOIRES_LOTS_MAX", "6"))      # requêtes par passage (rattrapage progressif)
FLAIR_MIN = int(os.getenv("HISTOIRES_FLAIR_MIN", "3"))    # en dessous, l'actu n'est pas suivie
JOURS_ACTIVE = 10                                         # sans nouvel épisode depuis : « en sommeil »
JOURS_OUBLI = 75                                          # sans nouvel épisode depuis : oubliée

CONSIGNE = """Tu es le rédacteur en chef d'une veille IA. Tu suis des HISTOIRES : une affaire PRÉCISE qui connaît plusieurs
épisodes, où chaque épisode est la SUITE DIRECTE du précédent (le même produit précis, le même conflit, le même texte de loi,
la même opération financière, le même procès).

BONNES histoires : « Anthropic contre le Pentagone », « Le projet de loi d'Anthropic sur la sécurité de l'IA »,
« Gemini 4 Argon : de l'annonce à la disponibilité », « La Chine prépare des contrôles à l'export de l'IA »,
« L'introduction en Bourse d'Anthropic », « MiniMax M3.1 : annonce puis publication des poids ».
MAUVAISES histoires (INTERDIT) : une entreprise ou sa gamme (« NVIDIA et son écosystème », « Les activités d'Anthropic »),
un thème (« les agents IA », « la concurrence chinoise »), une catégorie (« partenariats cloud »).
Deux actus sur la même entreprise ne sont PAS la même histoire si elles portent sur des sujets différents
(un nouveau modèle, une levée de fonds et une expérience scientifique d'Anthropic = trois sujets différents).

On te donne des histoires existantes et de nouvelles actus, dans l'ordre chronologique. Pour CHAQUE actu, décide :
- "h_..." : nouvel épisode d'une histoire existante, UNIQUEMENT si c'est la suite directe du même objet précis ;
- "N1", "N2"... : début d'une nouvelle histoire, si l'affaire aura probablement des suites (plusieurs actus de la liste peuvent
  partager la même clé si elles portent sur le même objet précis) ;
- "aucune" : dans le doute, et pour toute actu isolée. C'est le choix par défaut.
Pour chaque rattachement, "fil" = le lien concret avec l'histoire (« même projet de loi », « même modèle Gemini 4 Argon »…).
Si tu ne peux pas écrire un fil précis, choisis "aucune".
"neuf" = UNE phrase : ce que cet épisode change par rapport à l'épisode précédent.
Pour chaque histoire touchée, un résumé « où en est-on » de 2-3 phrases, à jour, qui ne parle QUE de l'objet de l'histoire.
Réponds UNIQUEMENT en JSON :
{"affectations": [{"actu": "id", "histoire": "h_... | N1 | aucune", "fil": "...", "neuf": "..."}],
 "nouvelles": [{"cle": "N1", "titre": "l'objet précis de l'histoire, 8 mots max"}],
 "resumes": [{"histoire": "h_... ou N1", "resume": "..."}]}
N'invente aucun fait : appuie-toi seulement sur ce qui est fourni."""


def _charger(chemin, defaut):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return defaut


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [round(x / n, 5) for x in v]


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def _titre(it):
    return (it.get("analyse") or {}).get("titre_fr") or it["titre"]


def _resume(it):
    a = it.get("analyse") or {}
    return (a.get("a_retenir") or a.get("resume") or it.get("extrait") or "")[:260]


def _eligible(it):
    return it.get("rubrique") in ("veille", "controle") and (it.get("flair", 0) >= FLAIR_MIN or it.get("echos"))


def suivre(items, vecteurs, demander):
    """demander(consigne, message) -> dict JSON ou None. Met à jour items[*]['histoire'] et histoires.json."""
    donnees = _charger(FICHIER, {"histoires": []})
    hist = {h["id"]: h for h in donnees["histoires"]}
    hvec = _charger(FICHIER_VEC, {})
    par_id = {it["id"]: it for it in items}

    # les sujets fusionnés gardent l'histoire de l'article qu'ils ont absorbé
    rattache = {ep["id"]: h["id"] for h in hist.values() for ep in h["episodes"]}
    for it in items:
        if not it.get("histoire"):
            for ancien in it.get("anciens_ids", []):
                if ancien in rattache:
                    it["histoire"], it["histoire_vu"] = rattache[ancien], True
                    break

    a_traiter = sorted([it for it in items if not it.get("histoire_vu") and _eligible(it)], key=lambda i: i["date"])
    traites = 0
    if demander and a_traiter:
        print(f"🧵 Fils d'histoire : {len(a_traiter)} actu(s) à rattacher, {len(hist)} histoire(s) suivie(s)")
    for n_lot in range(LOTS_MAX):
        lot = a_traiter[n_lot * TAILLE_LOT:(n_lot + 1) * TAILLE_LOT]
        if not lot or not demander:
            break
        candidates = _histoires_candidates(lot, hist, hvec, vecteurs)
        message = "HISTOIRES EXISTANTES :\n" + ("\n".join(
            f"- {h['id']} | {h['titre']} | dernier épisode {h['maj'][:10]} : {h['episodes'][-1]['titre']} | où en est-on : {h['resume']}"
            for h in candidates) or "(aucune pour l'instant)")
        message += "\n\nNOUVELLES ACTUS (ordre chronologique) :\n" + "\n".join(
            f"- {it['id']} | {it['date'][:10]} | {it['source']} | {_titre(it)} | {_resume(it)}" for it in lot)
        rep = demander(CONSIGNE, message)
        if not rep:
            break
        _appliquer(rep, lot, hist, hvec, vecteurs, par_id, {h["id"] for h in candidates})
        for it in lot:
            it["histoire_vu"] = True
        traites += len(lot)

    # statut, oubli, liens items -> histoires
    limite_oubli = (MAINTENANT - timedelta(days=JOURS_OUBLI)).isoformat()
    for hid in [k for k, h in hist.items() if h["maj"] < limite_oubli]:
        hist.pop(hid); hvec.pop(hid, None)
    for h in hist.values():
        h["statut"] = "active" if h["maj"] >= (MAINTENANT - timedelta(days=JOURS_ACTIVE)).isoformat() else "en sommeil"
        h["episodes"].sort(key=lambda e: e["date"])
        for ep in h["episodes"]:
            if ep["id"] in par_id:
                par_id[ep["id"]]["histoire"] = h["id"]
    for it in items:
        if it.get("histoire") and it["histoire"] not in hist:
            it.pop("histoire")

    liste = sorted(hist.values(), key=lambda h: h["maj"], reverse=True)
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps({"maj": MAINTENANT.isoformat(), "histoires": liste}, ensure_ascii=False, indent=1), encoding="utf-8")
    FICHIER_VEC.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_VEC.write_text(json.dumps(hvec, separators=(",", ":")), encoding="utf-8")
    if traites:
        suivies = sum(1 for h in liste if len(h["episodes"]) >= 2)
        print(f"   → {traites} actu(s) traitée(s) ; {suivies} histoire(s) à plusieurs épisodes ; {len(REFUS)} rattachement(s) refusé(s) par le garde-fou")


def _histoires_candidates(lot, hist, hvec, vecteurs, maxi=18):
    """Les histoires les plus proches (par le sens) des actus du lot, plus les plus récentes."""
    scores = {}
    for it in lot:
        v = vecteurs.get(it["id"]) if vecteurs else None
        if not v:
            continue
        for hid, hv in hvec.items():
            if hid in hist:
                c = _cos(v, hv)
                if c >= 0.62:
                    scores[hid] = max(scores.get(hid, 0), c)
    choix = [hist[h] for h, _ in sorted(scores.items(), key=lambda x: -x[1])[:maxi]]
    recentes = sorted((h for h in hist.values() if h not in choix and h["statut"] == "active"), key=lambda h: h["maj"], reverse=True)
    return choix + recentes[:max(0, min(8, maxi - len(choix)))]


REFUS = []
SEUIL_PROCHE = float(os.getenv("HISTOIRES_SEUIL", "0.72"))


def _assez_proche(it, h, vecteurs):
    """Garde-fou : l'actu doit ressembler (par le sens) à au moins un épisode récent de l'histoire."""
    if not vecteurs or it["id"] not in vecteurs or not h["episodes"]:
        return True
    v = vecteurs[it["id"]]
    proches = [_cos(v, vecteurs[e["id"]]) for e in h["episodes"][-4:] if e["id"] in vecteurs]
    return not proches or max(proches) >= SEUIL_PROCHE


def _ajouter_vec(hvec, hid, v, n):
    if not v:
        return
    ancien = hvec.get(hid)
    hvec[hid] = _norm([a * n + b for a, b in zip(ancien, v)]) if ancien else _norm(v)


def _appliquer(rep, lot, hist, hvec, vecteurs, par_id, autorisees):
    ids_lot = {it["id"] for it in lot}
    nouvelles = {}
    for n in rep.get("nouvelles", []):
        cle, titre = str(n.get("cle", "")), (n.get("titre") or "").strip()
        if cle and titre:
            hid = "h_" + hashlib.sha1(f"{titre}{MAINTENANT.isoformat()}".encode()).hexdigest()[:10]
            nouvelles[cle] = hid
            hist[hid] = {"id": hid, "titre": titre[:90], "resume": "", "creee": MAINTENANT.isoformat(),
                         "maj": "", "episodes": [], "statut": "active", "societes": []}
    for a in rep.get("affectations", []):
        iid, cible = a.get("actu"), str(a.get("histoire", "aucune"))
        if iid not in ids_lot:
            continue
        hid = nouvelles.get(cible) or (cible if cible in autorisees and cible in hist else None)
        if not hid or len((a.get("fil") or "").strip()) < 6:
            continue
        it, h = par_id[iid], hist[hid]
        if not _assez_proche(it, h, vecteurs):
            REFUS.append((it["titre"][:80], h["titre"]))
            continue
        if any(ep["id"] == iid for ep in h["episodes"]):
            continue
        h["episodes"].append({
            "id": iid, "date": it["date"], "titre": _titre(it), "neuf": (a.get("neuf") or "").strip()[:300],
            "fil": (a.get("fil") or "").strip()[:140],
            "source": it["source"], "lien": it["lien"], "nb_sources": 1 + len({e["source"] for e in it.get("echos", [])}),
            "primaire": bool(it.get("primaire")),
        })
        h["maj"] = max(h["maj"] or it["date"], it["date"])
        if it.get("societe") and it["societe"] not in h["societes"]:
            h["societes"].append(it["societe"])
        it["histoire"] = hid
        _ajouter_vec(hvec, hid, vecteurs.get(iid) if vecteurs else None, len(h["episodes"]) - 1)
    for r in rep.get("resumes", []):
        hid = nouvelles.get(str(r.get("histoire"))) or r.get("histoire")
        if hid in hist and r.get("resume"):
            hist[hid]["resume"] = r["resume"].strip()[:600]
    for hid in list(nouvelles.values()):  # histoire annoncée mais sans épisode valide : on l'abandonne
        if not hist[hid]["episodes"]:
            hist.pop(hid)
