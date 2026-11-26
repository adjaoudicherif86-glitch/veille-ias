"""Pièce Unique : notifications sur le téléphone de Chérif (Web Push, site installé sur l'écran d'accueil).

Lancé après chaque collecte (mode.yml) et chaque lecture X (comptes.yml).
Au plus une notif par créneau (matin, après-midi, soir, heure de Paris), donc 3 par jour au maximum,
et seulement s'il y a du neuf : pépites notées 9 et plus, nouveaux relais X, lancement Black Friday.
Rien la nuit (23 h - 8 h) : ce qui arrive la nuit part dans la notif du matin.

Secrets GitHub :
  VAPID_PRIVE      clé privée VAPID (base64url, 32 octets) ; la clé publique est dans docs/mode/index.html
  PU_ABONNEMENT    le code copié depuis le site (un ou plusieurs abonnements, JSON, un par ligne accepté)
Sans ces secrets, le script ne fait que tenir à jour la liste de ce qui a déjà été vu.
"""
import json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

RACINE = Path(__file__).resolve().parent.parent
ETAT = RACINE / "etat" / "notifs.json"
SITE = "https://adjaoudicherif86-glitch.github.io/veille-ias/mode/"
PARIS = ZoneInfo("Europe/Paris")
CRENEAUX = [("matin", 8, 12), ("aprem", 12, 18), ("soir", 18, 23)]
CONTACT = "mailto:noreply@users.noreply.github.com"


def lire(p, defaut):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return defaut


def eur(x):
    if x is None:
        return ""
    return (f"{x:.0f}" if abs(x - round(x)) < 0.01 else f"{x:.2f}".replace(".", ",")) + " €"


def creneau(maintenant):
    h = maintenant.astimezone(PARIS).hour
    for nom, debut, fin in CRENEAUX:
        if debut <= h < fin:
            return nom
    return None


def candidats(maintenant):
    """Tout ce qui pourrait mériter une notif, avec une clé unique par élément."""
    d = lire(RACINE / "docs/mode/data.json", {})
    c = lire(RACINE / "docs/mode/camino.json", {})
    bf = lire(RACINE / "docs/mode/blackfriday.json", {})
    out = []
    # pépites : remises bien réelles, notées 9+ par l'IA, côté homme, zone principale, boutique pas « prudence »
    for a in d.get("articles", []):
        if (a.get("note") or 0) >= 9 and a.get("remise", 0) > 0 and a.get("genre", "homme") == "homme" \
                and a.get("zone") == "principal" and a.get("fiab") != "prudence":
            out.append({"cle": "p:" + a["id"], "type": "pepite", "id": a["id"], "note": a.get("note", 0),
                        "texte": f"{a.get('marque') or a.get('boutique')} · {a.get('nom', '')} à {eur(a.get('prix_eur'))} (−{a.get('remise')} %)"})
    # relais X : posts gardés par l'IA (les baskets sont déjà écartées), homme ou mixte, moins de 2 jours
    for p in c.get("posts", []):
        try:
            dt = datetime.fromisoformat(p["date"].replace("Z", "+00:00"))
        except Exception:
            continue
        pcs = [x for x in p.get("pieces") or [] if x.get("nom")]
        if not pcs or p.get("genre", "homme") == "femme" or maintenant - dt > timedelta(days=2):
            continue
        x = sorted(pcs, key=lambda x: (x.get("prix") is None, x.get("prix") or 0))[0]
        prix = f" à {eur(x['prix'])}" if x.get("prix") is not None else ""
        rem = ""
        if x.get("prix") and x.get("prix_avant") and x["prix_avant"] > x["prix"]:
            rem = f" (−{round((1 - x['prix'] / x['prix_avant']) * 100)} %)"
        out.append({"cle": "x:" + str(p.get("tweet_id")), "type": "relai", "id": "x-" + str(p.get("tweet_id")),
                    "src": p.get("compte_nom") or p.get("compte"),
                    "texte": f"{x.get('marque') or ''} {x['nom']}{prix}{rem}".strip()})
    # Black Friday : une marque suivie qui démarre aujourd'hui (ou hier soir)
    auj = maintenant.astimezone(PARIS).date()
    for o in bf.get("offres", []) if isinstance(bf, dict) else []:
        try:
            debut = datetime.fromisoformat(o["debut"]).date()
        except Exception:
            continue
        fin = o.get("fin")
        if debut <= auj <= (datetime.fromisoformat(fin).date() if fin else auj) and (auj - debut).days <= 1:
            out.append({"cle": f"bf:{o.get('marque')}:{o.get('debut')}", "type": "bf",
                        "texte": f"{o.get('marque')} : {o.get('offre')}"})
    return out


def message(neufs):
    pep = sorted([x for x in neufs if x["type"] == "pepite"], key=lambda x: -x["note"])
    rel = [x for x in neufs if x["type"] == "relai"]
    bfs = [x for x in neufs if x["type"] == "bf"]
    lignes, url = [], SITE
    if bfs:
        lignes.append("Black Friday lancé : " + ", ".join(x["texte"] for x in bfs[:2]) + (f" (+{len(bfs) - 2})" if len(bfs) > 2 else ""))
        url = SITE + "#vue=bf"
    if pep:
        lignes.append("Pépite : " + pep[0]["texte"] + (f" (+{len(pep) - 1} autre{'s' if len(pep) > 2 else ''})" if len(pep) > 1 else ""))
        if not bfs:
            url = SITE + "#id=" + pep[0]["id"]
    if rel:
        lignes.append(f"Relais {rel[0]['src']} : {rel[0]['texte']}" + (f" (+{len(rel) - 1})" if len(rel) > 1 else ""))
        if not bfs and not pep:
            url = SITE + ("#id=" + rel[0]["id"] if len(rel) == 1 else "#vue=camino")
    n = len(neufs)
    titre = "Pièce Unique · " + (f"{n} nouveau{'x' if n > 1 else ''} bon{'s' if n > 1 else ''} plan{'s' if n > 1 else ''}")
    return {"title": titre, "body": "\n".join(lignes)[:300], "url": url, "tag": "pu"}


def abonnements():
    # 1) etat/abonnements.json (codes envoyés à Claude), 2) secret PU_ABONNEMENT (facultatif)
    subs = [a.get("sub") for a in lire(RACINE / "etat" / "abonnements.json", {}).get("abonnements", [])]
    brut = (os.environ.get("PU_ABONNEMENT") or "").strip()
    if not brut:
        return dedoublonner(subs)
    try:
        v = json.loads(brut)
        subs = v if isinstance(v, list) else [v]
    except Exception:
        for ligne in brut.splitlines():
            ligne = ligne.strip()
            if ligne:
                try:
                    subs.append(json.loads(ligne))
                except Exception:
                    print("Abonnement illisible, ignoré")
    return dedoublonner(subs)


def dedoublonner(subs):
    vus, out = set(), []
    for s in subs:
        if isinstance(s, dict) and s.get("endpoint") and s["endpoint"] not in vus:
            vus.add(s["endpoint"]); out.append(s)
    return out


def envoyer(msg, subs, cle_privee):
    from pywebpush import webpush, WebPushException
    ok = 0
    for s in subs:
        try:
            webpush(subscription_info=s, data=json.dumps(msg, ensure_ascii=False), vapid_private_key=cle_privee,
                    vapid_claims={"sub": CONTACT}, ttl=6 * 3600, headers={"Urgency": "normal"})
            ok += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            print(f"Envoi refusé ({code}) : {'abonnement expiré, réactive les notifs sur le site' if code in (404, 410) else e}")
        except Exception as e:
            print("Envoi impossible :", e)
    return ok


def main():
    maintenant = datetime.now(timezone.utc)
    etat = lire(ETAT, {"vus": {}, "envois": []})
    vus = etat.setdefault("vus", {})
    premier = not vus and not etat.get("envois")
    cands = candidats(maintenant)
    neufs = [x for x in cands if x["cle"] not in vus]
    subs, cle = abonnements(), (os.environ.get("VAPID_PRIVE") or "").strip()
    jour, cr = maintenant.astimezone(PARIS).date().isoformat(), creneau(maintenant)
    deja = any(e.get("jour") == jour and e.get("creneau") == cr for e in etat.get("envois", []))
    print(f"{len(cands)} candidats, {len(neufs)} nouveaux ; créneau {cr or 'nuit'}{' (déjà servi)' if deja else ''} ; {len(subs)} abonnement(s)")

    if "--test" in sys.argv:
        if not (subs and cle):
            print("Test impossible : il manque", "le secret VAPID_PRIVE" if not cle else "un abonnement"); sys.exit(1)
        n = envoyer({"title": "Pièce Unique · test", "body": "Ça marche ! Tes vraies notifs arriveront ici, 3 par jour au plus, rien la nuit.",
                     "url": SITE, "tag": "pu-test"}, subs, cle)
        print(f"Notif de test envoyée à {n} appareil(s) sur {len(subs)}"); sys.exit(0 if n else 1)
    envoye = False
    if premier:
        print("Premier passage : tout ce qui existe déjà est marqué comme vu, pas de notif.")
    elif neufs and cr and not deja and subs and cle:
        msg = message(neufs)
        print("Notif :", msg["title"], "|", msg["body"].replace("\n", " | "))
        if "--essai" in sys.argv:
            envoye = True
        else:
            envoye = envoyer(msg, subs, cle) > 0
        if envoye:
            etat.setdefault("envois", []).append({"le": maintenant.isoformat(timespec="seconds"), "jour": jour, "creneau": cr,
                                                   "titre": msg["title"], "texte": msg["body"]})
    # on ne marque comme vu que ce qui a été notifié (ou au premier passage, ou sans abonnement) :
    # ce qui arrive la nuit ou dans un créneau déjà servi part au créneau suivant
    if premier or envoye or not (subs and cle):
        for x in cands:
            vus.setdefault(x["cle"], maintenant.isoformat(timespec="seconds"))
    # ménage : on oublie les clés de plus de 30 jours, on garde les 60 derniers envois
    limite = (maintenant - timedelta(days=30)).isoformat()
    etat["vus"] = {k: v for k, v in vus.items() if v >= limite}
    etat["envois"] = etat.get("envois", [])[-60:]
    if "--essai" not in sys.argv:
        ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=0), encoding="utf-8")


if __name__ == "__main__":
    main()
