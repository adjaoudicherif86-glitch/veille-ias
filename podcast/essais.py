"""
Extraits d'essai de Flair FM : trois animateurs originaux, même habillage sonore.
Lancé à la main par le workflow « Podcast : extraits d'essai ». Résultat dans docs/podcast/essais/.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sons  # noqa: E402
import voix  # noqa: E402

SORTIE = Path(__file__).resolve().parent.parent / "docs" / "podcast" / "essais"

DECOR = ("# DÉCOR\nUne radio de nuit dans une mégalopole futuriste, néons et pluie fine. L'émission s'appelle Flair FM : "
         "le flash d'actualité de l'intelligence artificielle. Studio intime, micro proche.\n")

ANIMATEURS = [
    {
        "id": "vex", "nom": "Vex", "style": "Le survolté",
        "voix": "Fenrir", "intensite": 1.2,
        "description": "Énergie à fond, débit rapide, il vit chaque annonce comme un match.",
        "consignes": DECOR + ("# PERSONNAGE\nVex, animateur de radio survolté et charismatique, un brin frimeur.\n"
                              "# JEU\nDébit rapide, énergie très haute, sourire dans la voix, emphase sur les chiffres, "
                              "petites pauses dramatiques avant chaque numéro. Diction parfaitement claire en français."),
        "texte": ("Flair FM, il est sept heures, et l'IA, elle, n'a pas dormi ! Vex au micro, accrochez-vous. "
                  "Numéro un : Google sort Gemini 4 Carbon et reprend la tête des classements. Accès encore limité, "
                  "mais le message est clair : la course est relancée ! Numéro deux : Mistral libère les poids de Large 4. "
                  "Mille milliards de paramètres, en accès libre. La France tape du poing sur la table ! "
                  "Restez branchés, la suite arrive."),
    },
    {
        "id": "rocco", "nom": "Rocco", "style": "Le blasé pince-sans-rire",
        "voix": "Algenib", "intensite": 0.9,
        "description": "Voix rocailleuse, ironie sèche, il en a vu d'autres. Rien ne l'impressionne… presque.",
        "consignes": DECOR + ("# PERSONNAGE\nRocco, vieux briscard de la radio de nuit, désabusé et drôle malgré lui.\n"
                              "# JEU\nDébit posé, voix grave et un peu rauque, humour pince-sans-rire, soupirs légers, "
                              "ironie dans les fins de phrase. Diction claire en français."),
        "texte": ("Flair FM. Ici Rocco. Il est sept heures, le café est froid, et les labos d'IA se battent encore "
                  "pour la première place. Cette semaine, c'est Google, avec Gemini 4 Carbon. La semaine prochaine, "
                  "ce sera quelqu'un d'autre. Bref. Plus intéressant : Anthropic prévient qu'elle approche d'une IA "
                  "capable de s'améliorer toute seule. Rassurant. Notez-le quelque part… on en reparlera."),
    },
    {
        "id": "nova", "nom": "Nova", "style": "La voix de fin de nuit",
        "voix": "Sulafat", "intensite": 0.8,
        "description": "Chaude, posée, presque confidentielle. L'ambiance des émissions de 4 heures du matin.",
        "consignes": DECOR + ("# PERSONNAGE\nNova, animatrice de la dernière tranche de nuit, calme, mystérieuse, chaleureuse.\n"
                              "# JEU\nVoix douce et proche du micro, débit lent mais fluide, pauses qui installent "
                              "l'ambiance, légère complicité avec l'auditeur. Diction claire en français."),
        "texte": ("Ici Nova, sur Flair FM. La ville dort encore… mais les serveurs, eux, tournent à plein régime. "
                  "Cette nuit, OpenAI a dévoilé GPT-6 Rosalind, un modèle taillé pour la biologie et les laboratoires. "
                  "Et dans l'ombre, des chercheurs ont réparé les boucles de raisonnement d'un petit modèle Qwen, "
                  "en modifiant à peine un poids sur six mille. Gardez l'oreille ouverte. La journée ne fait que commencer."),
    },
]


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    infos = {"genere": datetime.now(timezone.utc).isoformat(), "animateurs": []}
    for a in ANIMATEURS:
        print(f"🎙️  {a['nom']} ({a['voix']})…")
        try:
            pcm, nom_modele = voix.parler(a["texte"], a["voix"], a["consignes"])
        except Exception as e:
            print(f"  ✗ {e}", file=sys.stderr)
            infos["animateurs"].append({**{k: a[k] for k in ("id", "nom", "style", "voix", "description", "texte")}, "erreur": str(e)[:300]})
            continue
        mix = sons.monter(pcm, a["intensite"])
        sons.en_mp3(mix, SORTIE / f"{a['id']}.mp3")
        duree = round(len(mix) / sons.SR, 1)
        print(f"  ✓ {a['id']}.mp3 : {duree} s, modèle {nom_modele}")
        infos["animateurs"].append({**{k: a[k] for k in ("id", "nom", "style", "voix", "description", "texte")},
                                    "fichier": f"{a['id']}.mp3", "duree": duree, "modele": nom_modele})
    (SORTIE / "infos.json").write_text(json.dumps(infos, ensure_ascii=False, indent=1), encoding="utf-8")
    if not any("fichier" in x for x in infos["animateurs"]):
        sys.exit("Aucun extrait n'a pu être généré.")


if __name__ == "__main__":
    main()
