"""
Synthèse vocale avec l'API Gemini (modèles TTS). Renvoie du PCM 16 bits mono 24 kHz (numpy int16).
Le modèle est détecté automatiquement (préférence : génération 3.x, puis 2.x), ou forcé avec LLM_TTS_MODEL.
"""
import base64
import os
import sys
import time

import numpy as np
import requests

API = "https://generativelanguage.googleapis.com/v1beta"
_MODELE = []


def _cle():
    cle = os.getenv("LLM_API_KEY", "").strip()
    if not cle:
        raise RuntimeError("LLM_API_KEY absente : impossible de générer la voix")
    return cle


def modele():
    if _MODELE:
        return _MODELE[0]
    force = os.getenv("LLM_TTS_MODEL", "").strip()
    if force:
        _MODELE.append(force)
        return force
    noms = []
    try:
        r = requests.get(f"{API}/models", headers={"x-goog-api-key": _cle()}, params={"pageSize": 1000}, timeout=30)
        noms = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                if "tts" in m["name"] and "generateContent" in m.get("supportedGenerationMethods", ["generateContent"])]
    except Exception as e:
        print(f"  (liste des modèles vocaux indisponible : {e})", file=sys.stderr)
    def rang(n):
        return (0 if n.startswith("gemini-3") else 1, 0 if "flash" in n else 1, n)
    noms.sort(key=rang)
    candidats = noms or ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
    _MODELE.extend(candidats)
    return candidats[0]


def parler(texte, voix, consignes="", tentatives=4):
    """Fait dire `texte` par la voix Gemini `voix`, avec des consignes de jeu (en langage naturel)."""
    prompt = (f"{consignes.strip()}\n\n# TEXTE À DIRE (en français, mot pour mot, sans rien lire d'autre)\n{texte.strip()}"
              if consignes else texte)
    corps = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voix}}},
        },
    }
    modele()
    erreurs = []
    for nom in list(_MODELE):
        for essai in range(tentatives):
            r = requests.post(f"{API}/models/{nom}:generateContent", headers={"x-goog-api-key": _cle()},
                              json=corps, timeout=180)
            if r.status_code == 429:
                attente = 25 * (essai + 1)
                print(f"  ⏸ quota vocal atteint sur {nom}, nouvel essai dans {attente} s")
                time.sleep(attente)
                continue
            if r.status_code in (400, 403, 404):
                erreurs.append(f"{nom} : {r.status_code} {r.text[:200]}")
                break  # modèle indisponible pour cette clé : on essaie le suivant
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            donnees = next(p["inlineData"]["data"] for p in parts if "inlineData" in p)
            if _MODELE[0] != nom:
                _MODELE.remove(nom)
                _MODELE.insert(0, nom)
            return np.frombuffer(base64.b64decode(donnees), dtype="<i2"), nom
        else:
            erreurs.append(f"{nom} : quota épuisé")
    raise RuntimeError("Synthèse vocale impossible :\n  " + "\n  ".join(erreurs))
