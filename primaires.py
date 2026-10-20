"""
Sources primaires : l'info à la source, pas la presse qui en parle.

- github      : notes de version des projets clés (releases.atom)
- hf_modeles  : modèles qui entrent dans les tendances Hugging Face (+ leur fiche)
- hf_papiers  : publications de recherche les plus votées sur Hugging Face Papers
- page        : pages de changements officielles, comparées au passage précédent

Chaque collecteur renvoie des sujets au même format que les flux RSS.
L'état (pages déjà vues, modèles déjà vus) est gardé dans le dossier etat/.
"""
import hashlib
import html
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

ETAT = Path(__file__).parent / "etat"
UA = "Mozilla/5.0 (VeilleIA; +https://github.com) primaires"
MAINTENANT = datetime.now(timezone.utc)
LONG_EXTRAIT = 2500

RE_PRERELEASE = re.compile(r"(rc\d*|alpha|beta|\bpre\b|-pre|nightly|dev\d*)", re.I)


def _id(*parts):
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:14]


def _texte(h, limite=LONG_EXTRAIT):
    t = html.unescape(re.sub(r"<[^>]+>", " ", h or ""))
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t).strip()
    return t[:limite] + ("…" if len(t) > limite else "")


def _charger(nom, defaut):
    try:
        return json.loads((ETAT / nom).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return defaut


def _sauver(nom, valeur):
    ETAT.mkdir(parents=True, exist_ok=True)
    (ETAT / nom).write_text(json.dumps(valeur, ensure_ascii=False, indent=1), encoding="utf-8")


def _get(url, **kw):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30, **kw)
    r.raise_for_status()
    return r


def _sujet(src, titre, lien, date, extrait, type_=None, signal=0.0, raison=None):
    return {
        "id": _id(lien, titre),
        "titre": titre[:300],
        "lien": lien,
        "source": src["nom"],
        "type": type_ or src.get("type", "primaire"),
        "rubrique": src.get("rubrique", "veille"),
        "date": date.isoformat(),
        "extrait": extrait,
        "primaire": True,
        "signal": round(signal, 2),
        "signal_raison": raison,
        "societe_force": src.get("societe"),
    }


# --- GitHub : notes de version ----------------------------------------------

def github(src):
    """src : {"repo": "ollama/ollama", "nom": "Ollama", "filtre": "regex optionnelle", "max": 2}"""
    flux = feedparser.parse(_get(f"https://github.com/{src['repo']}/releases.atom").content)
    if flux.bozo and not flux.entries:
        raise ValueError("flux de versions illisible")
    filtre = re.compile(src["filtre"], re.I) if src.get("filtre") else None
    sortie = []
    for e in flux.entries:
        if len(sortie) >= src.get("max", 2):
            break
        version = (e.get("title") or "").strip()
        if not version or RE_PRERELEASE.search(version):
            continue
        t = e.get("updated_parsed") or e.get("published_parsed")
        date = datetime(*t[:6], tzinfo=timezone.utc) if t else MAINTENANT
        if MAINTENANT - date > timedelta(days=10):
            break
        corps = _texte((e.get("content") or [{}])[0].get("value", "") or e.get("summary", ""))
        if filtre and not filtre.search(corps):
            continue
        titre = version if src["nom"].lower() in version.lower() else f"{src['nom']} {version}"
        sortie.append(_sujet(src, titre, e.get("link", f"https://github.com/{src['repo']}/releases"),
                             date, f"Notes de version officielles de {src['nom']} :\n{corps}"))
    return sortie


# --- Hugging Face : modèles en tendance --------------------------------------

def hf_modeles(src):
    """Nouveaux venus dans le top des tendances Hugging Face, avec le début de leur fiche."""
    top = src.get("top", 30)
    modeles = _get(f"https://huggingface.co/api/models?sort=trendingScore&limit={top}").json()
    vus = _charger("hf_vus.json", {})
    premier_passage = not vus
    sortie = []
    for rang, m in enumerate(modeles, 1):
        mid = m.get("id") or m.get("modelId")
        if not mid or mid in vus:
            continue
        vus[mid] = MAINTENANT.isoformat()
        cree = m.get("createdAt")
        date = datetime.fromisoformat(cree.replace("Z", "+00:00")) if cree else MAINTENANT
        if MAINTENANT - date > timedelta(days=src.get("age_max_jours", 45)):
            continue  # vieux modèle qui revient en tendance : pas une nouveauté
        if premier_passage and rang > 8:
            continue
        fiche = ""
        try:
            fiche = _texte(_get(f"https://huggingface.co/{mid}/raw/main/README.md").text, 2000)
            fiche = re.sub(r"^---.*?---", "", fiche, flags=re.S).strip()  # retire l'en-tête technique
        except Exception:
            pass
        auteur = mid.split("/")[0]
        infos = (f"Modèle publié par {auteur} sur Hugging Face. Type : {m.get('pipeline_tag') or 'non précisé'}. "
                 f"{m.get('likes', 0)} likes, {m.get('downloads', 0)} téléchargements. "
                 f"N°{rang} des tendances Hugging Face.")
        signal = 2.0 if rang <= 5 else 1.2 if rang <= 15 else 0.6
        sortie.append(_sujet(src, f"En tendance sur Hugging Face : {mid}", f"https://huggingface.co/{mid}",
                             date, f"{infos}\nExtrait de la fiche du modèle :\n{fiche}" if fiche else infos,
                             signal=signal, raison=f"N°{rang} des tendances Hugging Face"))
    # on oublie les modèles vus il y a plus de 60 jours
    limite = (MAINTENANT - timedelta(days=60)).isoformat()
    _sauver("hf_vus.json", {k: v for k, v in vus.items() if v >= limite})
    return sortie


# --- Hugging Face Papers : la recherche qui monte ----------------------------

def hf_papiers(src):
    donnees = _get("https://huggingface.co/api/daily_papers?limit=100").json()
    seuil, jours = src.get("votes_min", 20), src.get("jours", 5)
    retenus = []
    for d in donnees:
        p = d.get("paper") or {}
        votes = p.get("upvotes", 0) or 0
        pub = d.get("publishedAt") or p.get("publishedAt")
        date = datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else MAINTENANT
        if votes < seuil or MAINTENANT - date > timedelta(days=jours):
            continue
        retenus.append((votes, p, date, d))
    retenus.sort(key=lambda x: -x[0])
    sortie = []
    for votes, p, date, d in retenus[: src.get("max", 6)]:
        org = (d.get("organization") or p.get("organization") or {}).get("fullname")
        resume = _texte(p.get("summary") or d.get("summary") or "", 2000)
        tete = f"Publication de recherche{f' de {org}' if org else ''}, {votes} votes sur Hugging Face Papers.\nRésumé des auteurs :\n"
        sortie.append(_sujet(src, p.get("title") or d.get("title") or "Publication",
                             f"https://huggingface.co/papers/{p.get('id')}", date, tete + resume,
                             type_="recherche", signal=min(3.0, math.log2(votes / seuil + 1) * 1.5),
                             raison=f"{votes} votes de chercheurs sur Hugging Face Papers"))
    return sortie


# --- Pages de changements officielles ----------------------------------------

def _extraire_page(h):
    try:
        import trafilatura
        t = trafilatura.extract(h, include_comments=False, include_tables=True, favor_recall=True)
        if t and len(t) > 500:
            return t
    except Exception:
        pass
    h = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<(br|/p|/li|/h\d|/div)[^>]*>", "\n", h, flags=re.I)
    return _texte(h, 10**7)


def page(src):
    """Compare la page à la version du passage précédent et remonte ce qui a été ajouté."""
    texte = _extraire_page(_get(src["url"]).text)
    lignes = [l.strip() for l in texte.splitlines() if len(l.strip()) > 3]
    if len(lignes) < 5:
        raise ValueError("page vide ou générée en JavaScript")
    fichier = f"page_{_id(src['url'])}.json"
    avant = _charger(fichier, None)
    _sauver(fichier, {"url": src["url"], "maj": MAINTENANT.isoformat(), "lignes": lignes})
    if avant is None:
        return []  # premier passage : on mémorise seulement
    connues = set(avant["lignes"])
    nouvelles = [l for l in lignes if l not in connues]
    ajout = "\n".join(nouvelles)
    if len(ajout) < src.get("min_caracteres", 60):
        return []
    extrait = ajout[:LONG_EXTRAIT] + ("…" if len(ajout) > LONG_EXTRAIT else "")
    accroche = next((l for l in nouvelles if len(l) > 25), nouvelles[0])
    return [_sujet(src, f"{src['nom']} : {accroche[:140]}", src["url"], MAINTENANT,
                   f"Ajouts détectés sur la page officielle « {src['nom']} » depuis le dernier passage :\n{extrait}",
                   type_="officiel", signal=1.0, raison="Changement sur une page officielle")]


COLLECTEURS = {"github": github, "hf_modeles": hf_modeles, "hf_papiers": hf_papiers, "page": page}
