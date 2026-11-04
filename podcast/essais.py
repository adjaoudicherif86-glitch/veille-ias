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

ROCCO_PROFIL = """# AUDIO PROFILE: Rocco
Animateur de radio de nuit, la cinquantaine, voix grave et un peu éraillée. Vingt ans de micro : il ne joue pas
un rôle, il parle. Humour pince-sans-rire, jamais méchant. Français de France, accent standard.

## THE SCENE: Le studio de Flair FM, sept heures du matin
Une petite radio de nuit dans une grande ville futuriste. Il est seul au micro, un café froid à la main,
la ville se réveille derrière la vitre. Il s'adresse à un seul auditeur, comme à un ami accoudé au comptoir.

### DIRECTOR'S NOTES
Style : surtout PAS une lecture. Une vraie conversation, spontanée, comme s'il trouvait ses mots en parlant.
Rythme : irrégulier et humain. Il accélère sur les apartés, ralentit et appuie sur les chutes ironiques,
laisse de vraies petites respirations entre les idées. Aucun débit mécanique ni régulier.
Intonation : variée et naturelle, pas chantante. Les fins de phrases retombent simplement, sans emphase de présentateur.
Voix : posée, proche du micro, un léger sourire dans la voix sur les remarques ironiques.
Les éléments entre crochets sont des indications de jeu à interpréter, jamais à lire à voix haute."""

ROCCO_TEXTE = ("Flair FM, bonjour. C'est Rocco. Bon… il est sept heures, mon café est déjà froid, "
               "et les labos d'IA se tapent encore dessus pour la première place. [sighs] "
               "Cette semaine, c'est Google, avec Gemini 4 Carbon. La semaine prochaine ? Ce sera un autre. "
               "On a l'habitude. Non, le truc qui m'a fait lever un sourcil ce matin, c'est Anthropic. "
               "Ils disent qu'ils se rapprochent d'une IA capable de… s'améliorer toute seule. Voilà. [laughs] "
               "Ça, notez-le quelque part. Parce qu'on va en reparler, croyez-moi.")

INTRO = ("Rocco, version plus naturelle : texte réécrit en français parlé, nouvelles consignes de jeu, "
         "traitement radio allégé. Même texte, plusieurs timbres. Compare avec la version d'hier, tout en bas.")

ANIMATEURS = [
    {"id": "rocco-algenib", "nom": "Rocco · Algenib", "style": "Le même timbre qu'hier, rauque",
     "voix": "Algenib", "intensite": 0.45,
     "description": "La voix que tu as choisie, avec le nouveau texte et le nouveau jeu."},
    {"id": "rocco-umbriel", "nom": "Rocco · Umbriel", "style": "Plus décontracté",
     "voix": "Umbriel", "intensite": 0.45,
     "description": "Un timbre plus détendu, souvent plus naturel en conversation."},
    {"id": "rocco-zubenelgenubi", "nom": "Rocco · Zubenelgenubi", "style": "Plus familier",
     "voix": "Zubenelgenubi", "intensite": 0.45,
     "description": "Le timbre le plus « parlé » des voix Gemini, proche du ton d'un pote."},
    {"id": "rocco-gacrux", "nom": "Rocco · Gacrux", "style": "Plus mûr, plus grave",
     "voix": "Gacrux", "intensite": 0.45,
     "description": "Une voix plus âgée et posée, le vieux briscard de la radio."},
    {"id": "rocco-algenib-brut", "nom": "Rocco · Algenib sans filtre", "style": "Même voix, sans effet radio",
     "voix": "Algenib", "intensite": 0.0,
     "description": "Pour entendre si le filtre « radio » aide ou gêne. Seuls le jingle et la nappe restent."},
]
for a in ANIMATEURS:
    a["consignes"], a["texte"] = ROCCO_PROFIL, ROCCO_TEXTE


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    infos = {"genere": datetime.now(timezone.utc).isoformat(), "intro": INTRO, "animateurs": []}
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
    if (SORTIE / "rocco.mp3").exists():  # la version d'hier, pour comparer
        (SORTIE / "rocco.mp3").rename(SORTIE / "rocco-v1.mp3")
    if (SORTIE / "rocco-v1.mp3").exists():
        infos["animateurs"].append({"id": "rocco-v1", "nom": "Rocco · version d'hier", "style": "Pour comparer",
                                    "voix": "Algenib", "description": "Le premier essai, celui que tu trouvais trop « IA ».",
                                    "texte": "Ancien texte, plus écrit.", "fichier": "rocco-v1.mp3"})
    for vieux in ("vex.mp3", "nova.mp3"):
        (SORTIE / vieux).unlink(missing_ok=True)
    (SORTIE / "infos.json").write_text(json.dumps(infos, ensure_ascii=False, indent=1), encoding="utf-8")
    if not any("fichier" in x for x in infos["animateurs"]):
        sys.exit("Aucun extrait n'a pu être généré.")


if __name__ == "__main__":
    main()
