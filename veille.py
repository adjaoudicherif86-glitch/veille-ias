#!/usr/bin/env python3
"""
Veille IA - le chien de chasse.

Collecte les flux RSS de sources IA, supprime les doublons, repère les sujets
chauds (plusieurs sources qui en parlent), attribue un score de "flair",
puis (optionnel, gratuit) demande à un modèle d'IA d'expliquer chaque nouveauté :
ce que c'est, comment ça marche, comment l'utiliser sur son PC.

Variables d'environnement (toutes optionnelles) :
  LLM_API_KEY    clé API (Gemini via Google AI Studio, Groq, OpenRouter...) -> active l'analyse
  LLM_API_URL    endpoint compatible OpenAI (défaut : Gemini)
  LLM_MODEL      nom du modèle (défaut : détection automatique d'un modèle Flash chez Gemini)
  MAX_ANALYSES   nombre d'articles analysés par passage (défaut : 20)
  JOURS_GARDES   nombre de jours d'historique conservés (défaut : 21)
"""
import html
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

import feedparser
import requests

RACINE = Path(__file__).parent
DATA = RACINE / "docs" / "data"
FICHIER_ITEMS = DATA / "items.json"
FICHIER_META = DATA / "meta.json"

LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_API_URL = os.getenv("LLM_API_URL", "").strip() or \
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
MAX_ANALYSES = int(os.getenv("MAX_ANALYSES", "20"))
MAX_ANALYSES_CONTROLE = int(os.getenv("MAX_ANALYSES_CONTROLE", "8"))
JOURS_GARDES = int(os.getenv("JOURS_GARDES", "21"))
PAUSE_LLM = float(os.getenv("PAUSE_LLM", "6"))  # secondes entre deux appels (quotas gratuits)

UA = "Mozilla/5.0 (VeilleIA; +https://github.com) feedparser"
MAINTENANT = datetime.now(timezone.utc)

# --- Vocabulaire du flair -------------------------------------------------

MOTS_IA = re.compile(
    r"\b(ai|a\.i\.|ia|llm|llms|gpt|chatgpt|claude|gemini|llama|mistral|deepseek|qwen|"
    r"openai|anthropic|deepmind|hugging ?face|neural|machine learning|deep learning|"
    r"transformer|diffusion|agent|agents|agentic|copilot|genai|generative|"
    r"intelligence artificielle|modèle de langage|rag|embedding|fine-?tun\w*|inference|"
    r"ollama|gguf|lora|multimodal|reasoning|chatbot)\b", re.I)

BOOSTS = [
    (r"\b(launch\w*|releas\w*|introduc\w*|announc\w*|unveil\w*|lance\w*|dévoil\w*|annonce\w*|sort\w* )\b", 1.5),
    (r"\b(open[- ]?source|open[- ]?weights?|poids ouverts|apache 2\.0|mit license)\b", 1.5),
    (r"\b(gpt-?\d|claude|gemini|llama ?\d|mistral|deepseek|qwen|grok|sora|veo|midjourney|flux)\b", 1.0),
    (r"\b(api|sdk|github|download|télécharg\w*|available|disponible|free|gratuit)\b", 0.7),
    (r"\b(benchmark|state[- ]of[- ]the[- ]art|sota|record|beats|surpasse)\b", 0.7),
    (r"\b(agent\w*|mcp|computer use|coding|code)\b", 0.6),
    (r"\b(regulation|ai act|règlement|lawsuit|procès|ban|interdit)\b", 0.5),
]

LOCAL = re.compile(
    r"\b(ollama|lm ?studio|llama\.cpp|gguf|quantiz\w*|quantif\w*|local(ly)?|en local|"
    r"on[- ]device|open[- ]?weights?|hugging ?face|comfyui|stable diffusion|whisper|"
    r"run on your (pc|laptop|mac)|consumer gpu|rtx|mlx|vllm|jan\.ai|gpt4all|lora)\b", re.I)

CATEGORIES = [
    ("Open source & local", r"\b(open[- ]?source|open[- ]?weights?|ollama|gguf|llama\.cpp|local|hugging ?face|lm ?studio|poids ouverts)\b"),
    ("Modèles", r"\b(model|modèle|gpt-?\d|claude|gemini|llama|mistral|deepseek|qwen|grok|benchmark|reasoning)\b"),
    ("Outils & applis", r"\b(app|tool|outil|plugin|extension|feature|fonctionnalité|api|sdk|agent\w*|copilot|assistant|mcp)\b"),
    ("Recherche", r"\b(paper|arxiv|research|recherche|study|étude|we propose|method)\b"),
    ("Business & régulation", r"\b(funding|raises|lève|valuation|acquisi\w*|rachat|regulation|ai act|lawsuit|procès|ipo|partnership|partenariat|chips?|puces?)\b"),
]

THEMES_CONTROLE = [
    ("Surveillance", r"\b(surveillance|facial recognition|reconnaissance faciale|spy\w*|espion\w*|tracking|biometric\w*|biométri\w*)\b"),
    ("Militaire", r"\b(pentagon\w*|military|militaire|weapon\w*|arme\w*|defense|défense|department of war)\b"),
    ("Perte de contrôle", r"\b(safety|sécurité|rogue|shutdown|misalign\w*|incident\w*|jailbreak\w*|sandbox)\b"),
    ("Manipulation", r"\b(deepfake\w*|disinformation|désinformation|influence|election\w*|élection\w*|propaganda)\b"),
    ("Pouvoir et régulation", r"\b(export|regulation|régulation|ai act|court|tribunal|lawsuit|antitrust|ban|government|gouvernement)\b"),
    ("Vie privée", r"\b(privacy|vie privée|personal data|données personnelles|gdpr|rgpd)\b"),
]

POIDS_TYPE = {"officiel": 3.0, "presse": 2.0, "communaute": 2.0, "fr": 1.8, "recherche": 1.2}

# --- Outils ---------------------------------------------------------------

def nettoyer(texte, limite=700):
    texte = html.unescape(re.sub(r"<[^>]+>", " ", texte or ""))
    texte = re.sub(r"\s+", " ", texte).strip()
    return texte[:limite] + ("…" if len(texte) > limite else "")


def date_article(entree):
    for cle in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entree.get(cle)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    return MAINTENANT


def titre_normalise(t):
    t = re.sub(r"\s+-\s+[^-]{2,40}$", "", t)  # retire " - NomDuJournal" (Google News)
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def charger_json(chemin, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return defaut

# --- 1. La chasse : collecte des flux --------------------------------------

def chasser(sources):
    trouves, ok, ko = [], [], []
    for src in sources:
        try:
            r = requests.get(src["url"], headers={"User-Agent": UA}, timeout=25)
            r.raise_for_status()
            flux = feedparser.parse(r.content)
            if not flux.entries:
                raise ValueError("flux vide ou illisible")
        except Exception as e:  # une source en panne ne bloque jamais les autres
            ko.append({"nom": src["nom"], "erreur": str(e)[:160]})
            print(f"  ✗ {src['nom']} : {e}", file=sys.stderr)
            continue
        garde = 0
        for e in flux.entries:
            if garde >= src.get("max", 25):
                break
            titre = nettoyer(e.get("title", ""), 300)
            lien = e.get("link", "")
            if not titre or not lien:
                continue
            resume = nettoyer(e.get("summary", "") or e.get("description", ""))
            if src.get("filtre_ia") and not MOTS_IA.search(f"{titre} {resume}"):
                continue
            trouves.append({
                "id": hashlib.sha1(lien.encode()).hexdigest()[:14],
                "titre": titre,
                "lien": lien,
                "source": src["nom"],
                "type": src.get("type", "presse"),
                "rubrique": src.get("rubrique", "veille"),
                "date": date_article(e).isoformat(),
                "extrait": resume,
            })
            garde += 1
        ok.append(src["nom"])
        print(f"  ✓ {src['nom']} : {garde} articles")
    return trouves, ok, ko

# --- 2. Le flair : doublons, échos, score, catégories ----------------------

def fusionner(anciens, nouveaux):
    par_id = {a["id"]: a for a in anciens}
    for n in nouveaux:
        if n["id"] in par_id:
            # garde l'analyse déjà faite, rafraîchit les champs bruts
            par_id[n["id"]].update({k: n.get(k) for k in ("titre", "extrait", "source", "type", "rubrique")})
        else:
            par_id[n["id"]] = n
    limite = MAINTENANT - timedelta(days=JOURS_GARDES)
    return [a for a in par_id.values() if datetime.fromisoformat(a["date"]) >= limite]


def regrouper(items):
    """Regroupe les articles qui parlent du même sujet (sources différentes)."""
    items.sort(key=lambda a: (-POIDS_TYPE.get(a["type"], 1), a["date"]))
    groupes = []
    for it in items:
        tn = titre_normalise(it["titre"])
        d = datetime.fromisoformat(it["date"])
        place = False
        for g in groupes:
            chef = g[0]
            if chef.get("rubrique", "veille") != it.get("rubrique", "veille"):
                continue
            if abs((datetime.fromisoformat(chef["date"]) - d).days) > 3:
                continue
            if SequenceMatcher(None, tn, chef["_tn"]).ratio() > 0.72:
                g.append(it)
                place = True
                break
        it["_tn"] = tn
        if not place:
            groupes.append([it])
    sortie = []
    for g in groupes:
        chef = g[0]
        chef["echos"] = [{"source": x["source"], "lien": x["lien"]} for x in g[1:] if x["source"] != chef["source"]]
        sortie.append(chef)
    for it in items:
        it.pop("_tn", None)
    return sortie


def flairer(it):
    texte = f"{it['titre']} {it['extrait']}"
    score = POIDS_TYPE.get(it["type"], 1.5)
    for motif, poids in BOOSTS:
        if re.search(motif, texte, re.I):
            score += poids
    score += 1.5 * min(len(it.get("echos", [])), 4)
    age_h = (MAINTENANT - datetime.fromisoformat(it["date"])).total_seconds() / 3600
    score -= min(age_h / 48, 2.5)
    it["score"] = round(score, 2)
    if not it.get("analyse"):
        it["local"] = bool(LOCAL.search(texte))
        it["categorie"] = next((nom for nom, m in CATEGORIES if re.search(m, texte, re.I)), "Actualité")
        if it["type"] == "recherche":
            it["categorie"] = "Recherche"
        if it.get("rubrique") == "controle":
            it["categorie"] = next((nom for nom, m in THEMES_CONTROLE if re.search(m, texte, re.I)), "Pouvoir et régulation")
    # flair de 1 à 5 : l'analyse IA, si présente, a le dernier mot
    flair = max(1, min(5, round(score / 1.8)))
    if it.get("analyse", {}).get("importance"):
        flair = round((flair + 2 * int(it["analyse"]["importance"])) / 3)
    it["flair"] = max(1, min(5, flair))
    return it

# --- 3. L'explication : analyse par un modèle d'IA gratuit ------------------

CONSIGNE = """Tu es un analyste de veille IA pour un professionnel francophone.
On te donne une actualité. Réponds UNIQUEMENT avec un objet JSON valide (pas de ```), avec ces clés :
{
 "titre_fr": "titre clair en français, 12 mots max",
 "resume": "2-3 phrases : de quoi il s'agit concrètement",
 "pourquoi": "1-2 phrases : pourquoi c'est important pour un pro",
 "comment_ca_marche": "3-5 phrases de vulgarisation technique du principe",
 "utiliser": ["étape concrète 1", "étape 2", "..."],
 "sur_mon_pc": "comment l'essayer sur un PC (outil, config matérielle mini) ou 'Pas en local : service en ligne uniquement' ",
 "local": true ou false (utilisable localement sur un PC ?),
 "niveau": "débutant" | "intermédiaire" | "avancé",
 "categorie": "Modèles" | "Outils & applis" | "Open source & local" | "Recherche" | "Business & régulation" | "Actualité",
 "importance": 1 à 5 (5 = changement majeur à connaître absolument),
 "tags": ["3 à 5 mots-clés"]
}
N'invente aucun fait, aucun chiffre, aucun lien. Si l'extrait ne permet pas de savoir, dis-le honnêtement ("à vérifier sur la source")."""


CONSIGNE_CONTROLE = """Tu es un analyste rigoureux qui aide un lecteur francophone à y voir clair
dans les craintes de contrôle de la société par l'IA (surveillance, militaire, manipulation, perte de contrôle,
concentration du pouvoir, vie privée). On te donne une actualité. Sépare toujours la peur des faits.
Réponds UNIQUEMENT avec un objet JSON valide (pas de ```), avec ces clés :
{
 "titre_fr": "titre clair en français, 12 mots max",
 "resume": "2-3 phrases factuelles : ce qui s'est passé",
 "la_crainte": "la lecture inquiète ou complotiste que ce sujet alimente, formulée honnêtement en 1-2 phrases",
 "les_faits": "ce que l'article établit réellement, sans extrapoler",
 "inconnues": "ce qu'on ne sait pas encore ou ce qui reste à vérifier",
 "preuve": "documente" | "plausible" | "speculatif" (niveau de preuve de la crainte au vu de CET article),
 "a_surveiller": "le prochain signal concret à guetter",
 "categorie": "Surveillance" | "Militaire" | "Perte de contrôle" | "Manipulation" | "Pouvoir et régulation" | "Vie privée",
 "importance": 1 à 5,
 "tags": ["3 à 5 mots-clés"]
}
N'invente aucun fait, aucun chiffre, aucun nom. Si l'extrait est trop maigre, dis-le dans "inconnues"."""


def choisir_modele(session):
    if LLM_MODEL:
        return LLM_MODEL
    if "generativelanguage.googleapis.com" in LLM_API_URL:
        try:
            r = session.get(LLM_API_URL.replace("/chat/completions", "/models"), timeout=20)
            ids = [m["id"].split("/")[-1] for m in r.json().get("data", [])]
            for motif in ("flash-lite", "flash"):
                candidats = sorted([i for i in ids if motif in i and "preview" not in i
                                    and "image" not in i and "tts" not in i and "live" not in i], reverse=True)
                if candidats:
                    return candidats[0]
        except Exception as e:
            print(f"  (détection du modèle impossible : {e})", file=sys.stderr)
        return "gemini-2.5-flash-lite"
    return "llama-3.3-70b-versatile"  # défaut raisonnable pour Groq


def appeler_llm(session, modele, systeme, message, temperature=0.2):
    r = session.post(LLM_API_URL, timeout=90, json={
        "model": modele,
        "temperature": temperature,
        "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": message}],
    })
    if r.status_code == 429:
        raise RuntimeError("quota gratuit atteint pour aujourd'hui (429)")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def extraire_json(texte):
    texte = re.sub(r"```(json)?", "", texte).strip()
    debut, fin = texte.find("{"), texte.rfind("}")
    return json.loads(texte[debut:fin + 1])


def analyser(items):
    if not LLM_API_KEY:
        print("→ Pas de LLM_API_KEY : collecte seule, sans explications IA.")
        return None
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"})
    modele = choisir_modele(session)
    print(f"→ Analyse avec le modèle : {modele}")
    sans = sorted([i for i in items if not i.get("analyse")], key=lambda i: -i["score"])
    a_faire = [i for i in sans if i.get("rubrique") != "controle"][:MAX_ANALYSES] + \
              [i for i in sans if i.get("rubrique") == "controle"][:MAX_ANALYSES_CONTROLE]
    for n, it in enumerate(a_faire, 1):
        msg = f"Source : {it['source']} ({it['type']})\nDate : {it['date'][:10]}\nTitre : {it['titre']}\nExtrait : {it['extrait'] or '(aucun)'}\nLien : {it['lien']}"
        try:
            consigne = CONSIGNE_CONTROLE if it.get("rubrique") == "controle" else CONSIGNE
            a = extraire_json(appeler_llm(session, modele, consigne, msg))
            a["importance"] = max(1, min(5, int(a.get("importance", 3))))
            it["analyse"] = a
            it["local"] = bool(a.get("local", it.get("local")))
            it["categorie"] = a.get("categorie") or it.get("categorie")
            print(f"  ✓ [{n}/{len(a_faire)}] {it['titre'][:70]}")
        except RuntimeError as e:
            print(f"  ⏸ {e} — on reprendra au prochain passage.")
            break
        except Exception as e:
            print(f"  ✗ analyse ratée ({e}) : {it['titre'][:60]}", file=sys.stderr)
        time.sleep(PAUSE_LLM)
    return session, modele


def brief_du_jour(items, llm):
    if not llm:
        return None
    session, modele = llm
    recents = [i for i in items if i.get("rubrique") != "controle" and (MAINTENANT - datetime.fromisoformat(i["date"])) < timedelta(hours=36)]
    top = sorted(recents, key=lambda i: -i["score"])[:12]
    if not top:
        return None
    liste = "\n".join(f"- [{i['source']}] {i.get('analyse', {}).get('titre_fr') or i['titre']}" for i in top)
    consigne = ("Tu rédiges le brief de veille IA du jour pour un professionnel francophone. "
                "Réponds UNIQUEMENT en JSON : {\"titre\": \"accroche de 10 mots max\", "
                "\"texte\": \"4-6 phrases qui relient les tendances du jour\", "
                "\"a_tester\": [\"2-3 actions concrètes à faire cette semaine\"]}. N'invente rien au-delà de la liste.")
    try:
        return extraire_json(appeler_llm(session, modele, consigne, liste, 0.4))
    except Exception as e:
        print(f"  (brief non généré : {e})", file=sys.stderr)
        return None

# --- Programme principal ---------------------------------------------------

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    sources = charger_json(RACINE / "sources.json", {"sources": []})["sources"]
    print(f"🐕 La chasse commence : {len(sources)} sources")
    nouveaux, ok, ko = chasser(sources)
    anciens = charger_json(FICHIER_ITEMS, [])
    items = regrouper(fusionner(anciens, nouveaux))
    items = [flairer(i) for i in items]
    llm = analyser(items)
    items = [flairer(i) for i in items]  # re-score avec l'importance donnée par l'IA
    items.sort(key=lambda i: i["date"], reverse=True)

    meta_ancienne = charger_json(FICHIER_META, {})
    brief = brief_du_jour(items, llm) or meta_ancienne.get("brief")
    meta = {
        "maj": MAINTENANT.isoformat(),
        "sources_ok": ok,
        "sources_ko": ko,
        "total": len(items),
        "analyses": sum(1 for i in items if i.get("analyse")),
        "brief": brief,
    }
    FICHIER_ITEMS.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    FICHIER_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"🦴 Rapporté : {len(items)} sujets ({meta['analyses']} expliqués), {len(ko)} source(s) en panne.")


if __name__ == "__main__":
    main()
