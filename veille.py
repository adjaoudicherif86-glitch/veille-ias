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

import primaires
import semantique

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

POIDS_TYPE = {"primaire": 3.5, "officiel": 3.0, "presse": 2.0, "communaute": 2.0, "fr": 1.8, "recherche": 1.2}

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
        collecteur = primaires.COLLECTEURS.get(src.get("kind", "rss"))
        if collecteur:
            try:
                lot = collecteur(src)
                trouves.extend(lot)
                ok.append(src["nom"])
                print(f"  ✓ {src['nom']} : {len(lot)} nouveauté(s) [source primaire]")
            except Exception as e:
                ko.append({"nom": src["nom"], "erreur": str(e)[:160]})
                print(f"  ✗ {src['nom']} : {e}", file=sys.stderr)
            continue
        try:
            r = requests.get(src["url"], headers={"User-Agent": UA}, timeout=25)
            r.raise_for_status()
            flux = feedparser.parse(r.content)
            if not flux.entries and flux.bozo:
                raise ValueError("flux illisible")
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

# --- 2. Le flair : doublons, échos, société, score, explication -----------

def charger_societes():
    d = charger_json(DATA / "societes.json", {"societes": []})["societes"]
    for s in d:
        s["_re"] = re.compile(r"(?:" + s["motifs"] + r")", re.I)
    return sorted(d, key=lambda s: -s["poids"])

SOCIETES = []

def fusionner(anciens, nouveaux):
    par_id = {a["id"]: a for a in anciens}
    for n in nouveaux:
        if n["id"] in par_id:
            # garde l'analyse déjà faite, rafraîchit les champs bruts
            par_id[n["id"]].update({k: n.get(k) for k in ("titre", "extrait", "source", "type", "rubrique", "primaire", "signal", "signal_raison", "societe_force") if k in n})
        else:
            par_id[n["id"]] = n
    limite = MAINTENANT - timedelta(days=JOURS_GARDES)
    return [a for a in par_id.values() if datetime.fromisoformat(a["date"]) >= limite]


MOTS_VIDES = set("the a an and or of to in on for with by from at is are its new how what why this that le la les un une des de du et ou en au aux pour par sur avec dans est son ses ce cette qui que ai ia".split())

def jetons(titre):
    return {m for m in titre_normalise(titre).split() if len(m) > 2 and m not in MOTS_VIDES}

RE_MODELE = re.compile(r"\b([a-z][a-z]{2,}[- ]?v?\d+(?:\.\d+)*)(?![\d%x.])", re.I)
PAS_MODELE = MOTS_VIDES | set("top cuts than over under about only page step part phase level since until".split())

def ids_modeles(titre, debut=False):
    t = titre[:45] if debut else titre
    return {re.sub(r"[- ]", "", m.lower()) for m in RE_MODELE.findall(t)
            if re.split(r"[- ]?v?\d", m.lower())[0] not in PAS_MODELE and not re.search(r"(19|20)\d\d$", m)}

def meme_sujet(a, b, vecteurs=None):
    """Même événement ? Par le sens si les empreintes existent, sinon (et en complément) par le titre."""
    ratio = SequenceMatcher(None, a["_tn"], b["_tn"]).ratio()
    ja, jb = a["_tok"], b["_tok"]
    jac = len(ja & jb) / len(ja | jb) if ja and jb else 0
    if ratio > 0.72 or jac >= 0.5 or (bool(a["_mod"] & b["_mod"]) and jac >= 0.2):
        return True
    if vecteurs and a["id"] in vecteurs and b["id"] in vecteurs:
        c = semantique.cosinus(vecteurs[a["id"]], vecteurs[b["id"]])
        if c >= semantique.SEUIL_FORT:
            return True
        if c >= semantique.SEUIL_MOYEN:
            # zone grise : il faut un indice concret en plus du sens
            meme_soc = a["_soc"] and a["_soc"] == b["_soc"]
            # (des mots banals comme « open » ou « agents » ne suffisent pas)
            if a["_soc"] and b["_soc"] and a["_soc"] != b["_soc"]:
                return False
            return bool(meme_soc or (a["_mod"] & b["_mod"]) or jac >= 0.3)
    return False

def regrouper(items, vecteurs=None):
    """Regroupe les articles qui parlent du même sujet (sources différentes) et garde l'historique des échos."""
    items.sort(key=lambda a: (-POIDS_TYPE.get(a["type"], 1), a["date"]))
    for it in items:
        it["_tn"], it["_tok"], it["_mod"] = titre_normalise(it["titre"]), jetons(it["titre"]), ids_modeles(it["titre"])
        soc, _ = detecter_societe(it)
        it["_soc"] = soc["id"] if soc else None
    groupes = []
    for it in items:
        d = datetime.fromisoformat(it["date"])
        for g in groupes:
            chef = g[0]
            if chef.get("rubrique", "veille") != it.get("rubrique", "veille"):
                continue
            if chef.get("primaire") and it.get("primaire") and chef["source"] != it["source"]:
                continue  # deux annonces officielles distinctes ne se fusionnent jamais
            if abs((datetime.fromisoformat(chef["date"]) - d).days) > 3:
                continue
            if any(meme_sujet(it, membre, vecteurs) for membre in g):
                g.append(it)
                break
        else:
            groupes.append([it])
    sortie = []
    for g in groupes:
        chef = g[0]
        echos = {e["lien"]: e for e in chef.get("echos", [])}
        for x in g[1:]:
            for e in [{"source": x["source"], "lien": x["lien"]}] + x.get("echos", []):
                if e["source"] != chef["source"]:
                    echos.setdefault(e["lien"], e)
        chef["echos"] = list(echos.values())
        if not chef.get("analyse"):  # on ne perd pas une explication déjà faite sur un autre article du groupe
            deja = next((x for x in g[1:] if x.get("analyse")), None)
            if deja:
                chef["analyse"] = deja["analyse"]
                chef["local"], chef["categorie"] = deja.get("local"), deja.get("categorie")
        chef["anciens_ids"] = sorted({i for x in g for i in [x["id"]] + x.get("anciens_ids", [])} - {chef["id"]})[-20:]
        sortie.append(chef)
    for it in items:
        for k in ("_tn", "_tok", "_mod", "_soc"):
            it.pop(k, None)
    return sortie


BASE_TYPE = {"primaire": (2.2, "Source primaire"), "officiel": (3.0, "Source officielle"), "presse": (2.2, None), "fr": (2.0, None),
             "communaute": (1.6, None), "recherche": (0.8, None)}
RE_LANCEMENT = re.compile(r"\b(launch\w*|releas\w*|introduc\w*|announc\w*|unveil\w*|debut\w*|rolls? out|now available|lance\w*|dévoil\w*|annonce\w*|présente\w*|sortie)\b", re.I)
RE_OUVERT = re.compile(r"\b(open[- ]?source\w*|open[- ]?weights?|poids ouverts|apache 2\.0|mit license|gguf)\b", re.I)
RE_ARGENT = re.compile(r"\b(raises?|funding|levée|lève|valuation|valoris\w*|ipo|introduction en bourse|acqui\w*|rachat|rachète|billion|milliards?)\b", re.I)
RE_REGLE = re.compile(r"\b(regulat\w*|régulation|ai act|lawsuit|procès|court|tribunal|ban\w*|interdi\w*|export controls?|antitrust|amende|fine[ds]?)\b", re.I)
RE_PRIX = re.compile(r"\b(pric\w*|tarif\w*|prix|free tier|gratuit\w*|cheaper|moins cher)\b", re.I)
RE_NOUVEAU_SUPPORT = re.compile(r"\b(new models?|nouveaux? modèles?|add(ed|s)? support for|now supports?|support for .{0,40}(model|llm)|introduc\w+ .{0,30}model|breaking change|deprecat\w+)\b", re.I)
RE_PAQUET = re.compile(r"^[\w.-]+ v?\d+(\.\d+)*([ab]|rc|dev)?\d*$", re.I)
RE_TEMOIGNAGE = re.compile(r"^(how|comment) .{3,60} (uses?|is using|builds?|is building|answers|scales?|transforms?|utilise)\b"
                           r"|\b(cuts?|boosts?|reduces?|saves?|triples?|doubles?|speeds? up|answers)\b.{0,60}\bwith\b", re.I)


def detecter_societe(it):
    """Renvoie (société, trouvée_dans_le_titre)."""
    titre, texte = it["titre"], f"{it['titre']} {it.get('extrait', '')}"
    if it.get("societe_force"):
        force = next((s for s in SOCIETES if s["id"] == it["societe_force"]), None)
        if force:
            return force, True
    for zone, dans_titre in ((titre, True), (texte, False)):
        for s in SOCIETES:
            if s["_re"].search(zone):
                return s, dans_titre
    return None, False


def noter(it):
    titre, texte = it["titre"], f"{it['titre']} {it.get('extrait', '')}"
    base, raison = BASE_TYPE.get(it["type"], (1.5, None))
    score, raisons = base, ([raison] if raison else [])
    soc, dans_titre = detecter_societe(it)
    it["societe"] = soc["id"] if soc else None
    if soc:
        score += {3: 1.5, 2: 1.0, 1: 0.5}[soc["poids"]] * (1 if dans_titre else 0.4)
        if soc["poids"] == 3 and dans_titre:
            raisons.append(f"Acteur majeur : {soc['nom']}")
    lance = RE_LANCEMENT.search(titre)
    if (lance and ids_modeles(titre)) or (it["type"] == "officiel" and ids_modeles(titre, debut=True)):
        score += 2.5; raisons.append("Nouveau modèle ou nouvelle version")
    elif lance:
        score += 1.2; raisons.append("Lancement ou annonce")
    if RE_OUVERT.search(texte):
        score += 1.5; raisons.append("Utilisable librement (open source)")
    if RE_ARGENT.search(titre):
        score += 0.8; raisons.append("Argent, levée ou rachat")
    if RE_REGLE.search(titre):
        score += 0.8; raisons.append("Régulation ou justice")
    if RE_PRIX.search(titre):
        score += 0.6; raisons.append("Prix ou accès")
    if it.get("signal"):
        score += it["signal"]
        if it.get("signal_raison"):
            raisons.append(it["signal_raison"])
    if it.get("primaire") and RE_NOUVEAU_SUPPORT.search(it.get("extrait", "")):
        score += 1.5; raisons.append("Nouvelle fonctionnalité ou nouveau modèle pris en charge")
    n = len({e["source"] for e in it.get("echos", [])})
    if n:
        score += 1.6 * min(n, 5); raisons.insert(0, f"Repris par {n + 1} sources")
    if RE_PAQUET.match(titre.strip()) and not it.get("primaire"):
        score -= 2.5
    if RE_TEMOIGNAGE.match(titre.strip()):
        score -= 1.2
    imp = it.get("analyse", {}).get("importance")
    if imp:
        score += (int(imp) - 3) * 1.2
        if int(imp) >= 4:
            raisons.append(f"Jugé important par l'IA ({imp}/5)")
    age_h = (MAINTENANT - datetime.fromisoformat(it["date"])).total_seconds() / 3600
    score -= min(age_h / 36, 3)
    it["score"] = round(score, 2)
    it["raisons"] = raisons[:4]
    if not it.get("analyse"):
        it["local"] = bool(LOCAL.search(texte))
        it["categorie"] = next((nom for nom, m in CATEGORIES if re.search(m, texte, re.I)), "Actualité")
        if it["type"] == "recherche":
            it["categorie"] = "Recherche"
        if it.get("rubrique") == "controle":
            it["categorie"] = next((nom for nom, m in THEMES_CONTROLE if re.search(m, texte, re.I)), "Pouvoir et régulation")
    return it


def flairer(items):
    """Score de chaque sujet puis flair de 1 à 5 selon son rang dans sa rubrique (top 4 % = 5)."""
    for it in items:
        noter(it)
    for rub in ("veille", "controle"):
        groupe = sorted([i for i in items if i.get("rubrique", "veille") == rub], key=lambda i: -i["score"])
        n = max(len(groupe), 1)
        for rang, it in enumerate(groupe):
            p = rang / n
            it["flair"] = 5 if p < .04 else 4 if p < .12 else 3 if p < .30 else 2 if p < .60 else 1
    return items

# --- 3. L'explication : analyse par un modèle d'IA gratuit ------------------

CONSIGNE = """Tu es un analyste de veille IA pour un professionnel francophone.
On te donne une actualité. Réponds UNIQUEMENT avec un objet JSON valide (pas de ```), avec ces clés :
{
 "titre_fr": "titre clair en français, 12 mots max",
 "societe": {"nom": "la société principale concernée", "presentation": "1-2 phrases : qui elle est et ce qu'elle fait, pour un lecteur qui ne la connaît pas"},
 "a_retenir": "LA phrase à retenir, simple et concrète",
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
        soc = next((x for x in SOCIETES if x["id"] == it.get("societe")), None)
        info_soc = f"Société repérée : {soc['nom']} ({soc['presentation']})\n" if soc else ""
        nature = ("Nature : SOURCE PRIMAIRE (texte officiel ou fiche technique). Appuie-toi précisément sur ce texte, "
                  "c'est lui qui fait foi.\n") if it.get("primaire") else ""
        msg = f"{info_soc}{nature}Source : {it['source']} ({it['type']})\nDate : {it['date'][:10]}\nTitre : {it['titre']}\nExtrait : {it['extrait'] or '(aucun)'}\nLien : {it['lien']}"
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

def top_semaine(items, llm, ancien):
    """Les 5 sujets à suivre cette semaine : présélection par le flair, choix final par l'IA."""
    semaine = [i for i in items if i.get("rubrique") != "controle"
               and (MAINTENANT - datetime.fromisoformat(i["date"])) < timedelta(days=7)]
    semaine.sort(key=lambda i: -i["score"])
    cands, par_soc = [], {}
    for it in semaine:
        cle = it.get("societe") or it["id"]
        if par_soc.get(cle, 0) >= 2:
            continue
        par_soc[cle] = par_soc.get(cle, 0) + 1
        cands.append(it)
        if len(cands) >= 15:
            break
    ids = {i["id"] for i in cands}
    if ancien and ancien.get("par_ia") and (MAINTENANT - datetime.fromisoformat(ancien["maj"])) < timedelta(hours=12) \
            and all(x["id"] in {i["id"] for i in items} for x in ancien.get("items", [])):
        return ancien
    diversifies, vus = [], set()
    for it in cands:
        if (it.get("societe") or it["id"]) not in vus:
            vus.add(it.get("societe") or it["id"]); diversifies.append(it)
    if llm and cands:
        session, modele = llm
        liste = "\n".join(
            f"[{i['id']}] {i['date'][:10]} | {i['source']} | société : {i.get('societe') or '?'} | "
            f"{i.get('analyse', {}).get('titre_fr') or i['titre']} | {i.get('analyse', {}).get('resume', '')[:220]}"
            for i in cands)
        consigne = ("Tu es le rédacteur en chef d'une veille IA pour un professionnel francophone. "
                    "Parmi ces sujets de la semaine, choisis les 5 qu'il doit VRAIMENT suivre (impact concret, nouveauté réelle, "
                    "pas de doublon, pas de sujet mineur). Classe-les du plus important au moins important. "
                    "Réponds UNIQUEMENT en JSON : {\"top\": [{\"id\": \"identifiant entre crochets\", "
                    "\"pourquoi\": \"1-2 phrases : pourquoi le suivre cette semaine\", "
                    "\"a_faire\": \"une action concrète (tester, lire, surveiller…)\"}]}. N'invente rien.")
        try:
            rep = extraire_json(appeler_llm(session, modele, consigne, liste, 0.3))
            choix = [x for x in rep.get("top", []) if x.get("id") in ids][:5]
            if len(choix) >= 3:
                return {"maj": MAINTENANT.isoformat(), "par_ia": True,
                        "items": [{"id": x["id"], "pourquoi": x.get("pourquoi", ""), "a_faire": x.get("a_faire", "")} for x in choix]}
        except Exception as e:
            print(f"  (top 5 par l'IA impossible : {e})", file=sys.stderr)
    return {"maj": MAINTENANT.isoformat(), "par_ia": False,
            "items": [{"id": i["id"], "pourquoi": (i.get("analyse") or {}).get("pourquoi", ""), "a_faire": ""} for i in diversifies[:5]]}

# --- Programme principal ---------------------------------------------------

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    sources = charger_json(RACINE / "sources.json", {"sources": []})["sources"]
    print(f"🐕 La chasse commence : {len(sources)} sources")
    nouveaux, ok, ko = chasser(sources)
    anciens = charger_json(FICHIER_ITEMS, [])
    SOCIETES[:] = charger_societes()
    items = fusionner(anciens, nouveaux)
    vecteurs = semantique.empreintes(items, LLM_API_KEY, LLM_API_URL)
    avant = len(items)
    items = flairer(regrouper(items, vecteurs))
    print(f"🧩 Regroupement : {avant} articles → {len(items)} sujets distincts")
    try:
        semantique.releve_similarites(items, vecteurs)
    except Exception as e:
        print(f"  (relevé des similarités impossible : {e})", file=sys.stderr)
    llm = analyser(items)
    items = flairer(items)  # re-score avec l'importance donnée par l'IA
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
        "top5": top_semaine(items, llm, meta_ancienne.get("top5")),
    }
    FICHIER_ITEMS.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    FICHIER_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"🦴 Rapporté : {len(items)} sujets ({meta['analyses']} expliqués), {len(ko)} source(s) en panne.")


if __name__ == "__main__":
    main()
