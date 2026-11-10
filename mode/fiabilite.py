"""
Fiabilité des boutiques : avis clients (mode/avis.json, vérifiés à la main) + conditions réelles lues sur chaque boutique
(pages Shopify /policies/refund-policy et /policies/shipping-policy, résumées par l'IA) + pays d'expédition.
Résultat : docs/mode/fiabilite.json, lu par le site. Lancé chaque semaine (workflow mode-fiabilite.yml).
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ICI = Path(__file__).resolve().parent
SORTIE = ICI.parent / "docs" / "mode" / "fiabilite.json"
NAV = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
       "Accept-Language": "fr-FR,fr;q=0.9"}
PAYS = {"FR": "France", "BE": "Belgique", "NL": "Pays-Bas", "DK": "Danemark", "DE": "Allemagne", "IT": "Italie", "ES": "Espagne",
        "SE": "Suède", "PT": "Portugal", "UK": "Royaume-Uni", "GB": "Royaume-Uni", "US": "États-Unis"}
URL = os.getenv("LLM_API_URL", "").strip() or "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

ENSEIGNES = {  # conditions publiques des grandes enseignes (pas de pages Shopify)
    "Zara": {"pays": "FR", "retour": "30 jours, gratuit en magasin, payant par la poste", "livraison": "Gratuite en magasin, payante à domicile sous un certain montant",
             "remboursement": "Sur le moyen de paiement"},
    "Uniqlo": {"pays": "FR", "retour": "30 jours, gratuit en magasin, payant par la poste", "livraison": "Gratuite en magasin, payante à domicile sous un certain montant",
               "remboursement": "Sur le moyen de paiement"},
}


def niveau(a):
    """Verdict simple à partir des avis : fiable, correct, mitigé, prudence, peu d'avis, grande enseigne."""
    if not a:
        return "inconnu"
    if a.get("enseigne"):
        return "enseigne"
    note, nb = a.get("note"), a.get("avis") or 0
    if note is None or nb < 10:
        return "peu"
    if note >= 4.0 and nb >= 50:
        return "fiable"
    if note >= 3.5:
        return "correct"
    if note >= 2.5:
        return "mitige"
    return "prudence"


def charger_avis():
    try:
        return json.loads((ICI / "avis.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"boutiques": {}}


def texte_politique(domaine, nom):
    try:
        r = requests.get(f"https://{domaine}/policies/{nom}", headers=NAV, timeout=20)
        m = re.search(r'shopify-policy__body.*?>(.*)</div>\s*</div>', r.text, re.S)
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1) if m else ""))
        return t.strip()[:3500]
    except Exception:
        return ""


CONSIGNE = """Tu lis les conditions de retour et de livraison d'une boutique de vêtements en ligne. Le client habite en FRANCE.
Réponds UNIQUEMENT en JSON, en français, très court (6 mots max par champ, null si l'info n'y est pas) :
{"retour": "ex. : 14 jours, retour payant", "retour_gratuit": true|false|null, "livraison": "ex. : 7 € en France, 3 à 5 jours",
 "livraison_gratuite_des": "ex. : 100 €" ou null, "remboursement": "argent | avoir seulement | null", "douane": "ex. : droits payés par la boutique" ou null,
 "alerte": "un piège à connaître pour un client français, ou null"}"""


def resumer(nom, retours, livraison):
    cle = os.getenv("LLM_API_KEY", "").strip()
    if not cle or not (retours or livraison):
        return {}
    for modele in ("gemini-flash-lite-latest", "gemini-2.5-flash-lite", "gemini-flash-latest"):
        try:
            r = requests.post(URL, timeout=90, headers={"Authorization": f"Bearer {cle}"}, json={
                "model": modele, "temperature": 0,
                "messages": [{"role": "system", "content": CONSIGNE},
                             {"role": "user", "content": f"BOUTIQUE : {nom}\n\nRETOURS :\n{retours}\n\nLIVRAISON :\n{livraison}"}]})
        except requests.RequestException:
            continue
        if r.status_code == 429:
            time.sleep(20)
            continue
        if r.status_code != 200:
            continue
        t = re.sub(r"```(json)?", "", r.json()["choices"][0]["message"]["content"])
        try:
            return json.loads(t[t.find("{"):t.rfind("}") + 1])
        except json.JSONDecodeError:
            continue
    return {}


def main():
    cfg = json.loads((ICI / "boutiques.json").read_text(encoding="utf-8"))
    avis = charger_avis()
    try:
        ancien = {b["boutique"]: b for b in json.loads(SORTIE.read_text(encoding="utf-8"))["boutiques"]}
    except Exception:
        ancien = {}
    sortie = []
    for b in cfg["boutiques"] + [{"nom": n, "enseigne": True} for n in ENSEIGNES]:
        nom = b["nom"]
        a = avis["boutiques"].get(nom, {})
        fiche = {"boutique": nom, "site": b.get("domaine") or f"{nom.lower()}.com", "niveau": niveau(a), "avis": a or None,
                 "veille": bool(b.get("veille")), "multi": bool(b.get("multi"))}
        if b.get("enseigne"):
            fiche |= ENSEIGNES[nom] | {"pays_nom": "France (magasins)"}
        else:
            pays = b.get("pays") or b.get("origine")
            try:
                m = requests.get(f"https://{b['domaine']}/meta.json", headers=NAV, timeout=15).json()
                pays = {"GB": "UK"}.get(m.get("country"), m.get("country")) or pays
            except Exception:
                pass
            fiche["pays"], fiche["pays_nom"] = pays, PAYS.get(pays, pays)
            fiche["hors_ue"] = pays in ("UK", "GB", "US")
            pol = resumer(nom, texte_politique(b["domaine"], "refund-policy"), texte_politique(b["domaine"], "shipping-policy"))
            if not pol and nom in ancien:  # IA indisponible : on garde la dernière lecture
                pol = {k: ancien[nom].get(k) for k in ("retour", "retour_gratuit", "livraison", "livraison_gratuite_des", "remboursement", "douane", "alerte")}
            fiche |= {k: v for k, v in pol.items() if v not in (None, "", "null")}
            print(f"{'✓' if pol else '·'} {nom:28} {fiche['niveau']:9} {fiche.get('retour', '')} | {fiche.get('livraison', '')}")
            time.sleep(4)
        sortie.append(fiche)
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps({"maj": datetime.now(timezone.utc).isoformat(), "avis_verifies_le": avis.get("verifie_le"),
                                  "ecartees": cfg.get("ecartees", []), "boutiques": sortie}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ {len(sortie)} boutiques")


if __name__ == "__main__":
    main()
