"""
Fabrique l'épisode du jour de Flair FM : script (redaction.py), voix séquence par séquence (voix.py),
montage (sons.py). Résultat : podcast/sortie/<date>.mp3 et podcast/sortie/episode.json.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import redaction  # noqa: E402
import rocco  # noqa: E402
import sons  # noqa: E402
import voix  # noqa: E402

SORTIE = Path(__file__).resolve().parent / "sortie"


def main():
    maintenant = datetime.now(timezone.utc)
    SORTIE.mkdir(exist_ok=True)
    print("✍️  Écriture du script…")
    script = redaction.ecrire(maintenant)
    seqs = script["sequences"]
    print(f"   « {script.get('titre')} » : {len(seqs)} séquences, {sum(len(x['texte'].split()) for x in seqs)} mots ({script['modele']})")
    enregistrees, modele_voix = [], None
    for k, x in enumerate(seqs, 1):
        consignes = rocco.PROFIL + "\n" + rocco.INTENTIONS[x["type"]]
        pcm, modele_voix = voix.parler(x["texte"], rocco.VOIX, consignes)
        print(f"🎙️  {k}/{len(seqs)} {x['type']} : {len(pcm) / 24000:.1f} s")
        enregistrees.append((x["type"], pcm))
    mix = sons.monter_episode(enregistrees, rocco.INTENSITE_RADIO)
    nom = f"flair-fm-{maintenant:%Y-%m-%d}.mp3"
    sons.en_mp3(mix, SORTIE / nom, debit=64)
    duree = round(len(mix) / sons.SR)
    m = script["matiere"]
    sujets = [{"titre": s["titre"], "source": s["source"], "lien": s["lien"]} for s in m["sujets"]]
    if m.get("feuilleton"):
        sujets.append({"titre": "Le feuilleton : " + m["feuilleton"]["titre"], "source": "Flair", "lien": ""})
    infos = {"date": maintenant.isoformat(), "jour": m["date"], "titre": script.get("titre") or f"Flair FM du {m['date']}",
             "fichier": nom, "duree": duree, "octets": (SORTIE / nom).stat().st_size, "sujets": sujets,
             "script": [{"type": x["type"], "texte": x["texte"]} for x in seqs],
             "modeles": {"texte": script["modele"], "voix": modele_voix}}
    (SORTIE / "episode.json").write_text(json.dumps(infos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ {nom} : {duree // 60} min {duree % 60:02d} s, {infos['octets'] // 1024} Ko")


if __name__ == "__main__":
    main()
