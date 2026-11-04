"""
Habillage sonore original de Flair FM, entièrement synthétisé (aucun échantillon externe) :
jingle synthwave, transition, nappe de fond, et chaîne « voix radio ».
"""
import numpy as np
from scipy import signal

SR = 44100


def _t(duree):
    return np.arange(int(duree * SR)) / SR


def _note(n):
    """Numéro MIDI -> fréquence."""
    return 440.0 * 2 ** ((n - 69) / 12)


def _scie(f, t, desaccord=0.0):
    ph = (f * (1 + desaccord)) * t
    return 2 * (ph - np.floor(ph + 0.5))


def _enveloppe(n, attaque, relache):
    e = np.ones(n)
    a, r = min(n, max(1, int(attaque * SR))), min(n, max(1, int(relache * SR)))
    e[:a] = np.linspace(0, 1, a)
    e[-r:] *= np.linspace(1, 0, r)
    return e


def _passe_bas(x, fc, ordre=2):
    b, a = signal.butter(ordre, min(fc, SR / 2 - 100) / (SR / 2), "low")
    return signal.lfilter(b, a, x)


def _passe_haut(x, fc, ordre=2):
    b, a = signal.butter(ordre, fc / (SR / 2), "high")
    return signal.lfilter(b, a, x)


def _reverb(x, taille=0.35, melange=0.25):
    """Réverbération simple : quelques échos décroissants diffusés."""
    sortie = x.copy()
    for retard, gain in ((0.031, .5), (0.047, .42), (0.071, .35), (0.113, .27), (0.167, .2), (0.241, .14)):
        d = int(retard * SR * taille / 0.35)
        echo = np.zeros_like(x)
        echo[d:] = x[:-d] * gain
        sortie += _passe_bas(echo, 4500) * melange
    return sortie


def _pad(accord, duree, coupure=1800):
    t = _t(duree)
    x = sum(_scie(_note(n), t, d) for n in accord for d in (-0.004, 0.0, 0.005)) / (3 * len(accord))
    return _passe_bas(x, coupure, 2) * _enveloppe(len(t), 0.25, 0.6)


def _pluck(n, duree=0.18):
    t = _t(duree)
    x = np.sign(np.sin(2 * np.pi * _note(n) * t)) * 0.6 + _scie(_note(n), t) * 0.4
    return _passe_bas(x, 3200) * np.exp(-t * 18)


def _kick(duree=0.35):
    t = _t(duree)
    f = 45 + 110 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def _snare(duree=0.3):
    t = _t(duree)
    bruit = _passe_haut(np.random.default_rng(7).standard_normal(len(t)), 1200)
    return (bruit * 0.6 + np.sin(2 * np.pi * 190 * t) * 0.4) * np.exp(-t * 14)


def _placer(piste, son, debut):
    i = int(debut * SR)
    fin = min(len(piste), i + len(son))
    piste[i:fin] += son[:fin - i]


def jingle(duree=4.2, tempo=118):
    """Ouverture : progression La mineur → Fa, arpège en doubles croches, batterie à réverbération « années 80 »."""
    piste = np.zeros(int(duree * SR))
    noire = 60 / tempo
    _placer(piste, _pad([57, 60, 64], noire * 4, 1500) * 0.75, 0)            # La mineur
    _placer(piste, _pad([53, 57, 60, 64], duree - noire * 4, 2200) * 0.75, noire * 4)  # Fa maj7
    arpege = [69, 72, 76, 81, 76, 72] * 3 + [65, 69, 72, 77, 72, 69, 76, 81]
    for k, n in enumerate(arpege):
        if k * noire / 4 < duree - 0.3:
            _placer(piste, _pluck(n) * 0.38, k * noire / 4)
    for k in range(int(duree / noire)):
        _placer(piste, _kick() * 0.38, k * noire)
        if k % 2 == 1:
            _placer(piste, _passe_bas(_reverb(np.pad(_snare(), (0, int(0.3 * SR))), 0.5, 0.6), 7000) * 0.2, k * noire)
    t = _t(duree)
    basse = _passe_bas(_scie(_note(33), t), 400) * (t < noire * 4) + _passe_bas(_scie(_note(29), t), 400) * (t >= noire * 4)
    piste += basse * 0.16 * _enveloppe(len(t), 0.02, 0.8)
    return _normaliser(_reverb(piste, 0.4, 0.2) * _enveloppe(len(piste), 0.01, 0.9), -3)


def fin(duree=3.2, tempo=118):
    """Fermeture : arpège descendant sur Fa maj7 puis La mineur, dernier coup de batterie qui résonne."""
    piste = np.zeros(int(duree * SR))
    noire = 60 / tempo
    _placer(piste, _pad([53, 57, 60, 64], duree, 1600) * 0.5, 0)
    for k, n in enumerate([81, 77, 76, 72, 69, 65, 64, 60]):
        _placer(piste, _pluck(n, 0.25) * 0.22, k * noire / 4)
    _placer(piste, _kick() * 0.8, 0)
    _placer(piste, _kick() * 0.8, noire * 2)
    _placer(piste, _reverb(np.pad(_snare(), (0, int(1.0 * SR))), 0.9, 0.9) * 0.4, noire * 2)
    t = _t(duree)
    piste += _passe_bas(_scie(_note(29), t), 300) * 0.22 * np.exp(-t * 1.2)
    return _normaliser(_reverb(piste, 0.5, 0.25) * _enveloppe(len(piste), 0.005, 1.6), -3)


def transition(duree=0.8):
    """Balayage montant filtré + petit « bip » numérique."""
    t = _t(duree)
    bruit = np.random.default_rng(3).standard_normal(len(t))
    balayage = np.zeros_like(bruit)
    for k in range(0, len(t), 512):  # filtre qui s'ouvre progressivement
        fc = 300 + 6000 * (k / len(t)) ** 2
        bloc = bruit[k:k + 1024]
        balayage[k:k + 512] = _passe_bas(bloc, fc)[:512][:len(balayage[k:k + 512])]
    balayage *= np.linspace(0, 1, len(t)) ** 2 * _enveloppe(len(t), 0.01, 0.15)
    bip = np.zeros_like(t)
    tb = _t(0.12)
    _placer(bip, np.sign(np.sin(2 * np.pi * 1760 * tb)) * np.exp(-tb * 30) * 0.3, duree - 0.16)
    return _normaliser(balayage * 0.5 + bip, -8)


def nappe(duree):
    """Fond d'ambiance discret : accord tenu très filtré + rumeur de ville."""
    t = _t(duree)
    accords = [[45, 52, 57, 60], [41, 48, 53, 57]]
    x = np.zeros(len(t))
    bloc = 8.0
    for k in range(int(np.ceil(duree / bloc))):
        p = _pad(accords[k % 2], bloc + 1.0, 700)
        _placer(x, p, k * bloc)
    rumeur = _passe_bas(np.random.default_rng(11).standard_normal(len(t)), 250, 2) * 0.15
    lfo = 0.85 + 0.15 * np.sin(2 * np.pi * 0.07 * t)
    return _normaliser((x + rumeur) * lfo * _enveloppe(len(t), 1.5, 2.0), -12)


def voix_radio(x_24k, intensite=1.0):
    """Chaîne « voix radio » : rééchantillonnage, coupe-bas, coupe-haut, présence, saturation douce, compression."""
    x = signal.resample_poly(x_24k.astype(np.float64), 147, 80)  # 24 kHz -> 44,1 kHz
    x = x / (np.max(np.abs(x)) or 1)
    x = _passe_haut(x, 90 + 60 * intensite, 2)
    x = _passe_bas(x, 11000 - 3800 * intensite, 4)
    b, a = _pic(2600, 1.2, 4.5 * intensite)        # présence
    x = signal.lfilter(b, a, x)
    if intensite > 0.6:                             # saturation douce, seulement pour un son « radio » marqué
        sature = np.tanh(x * (1.6 + 0.8 * intensite)) / np.tanh(1.6 + 0.8 * intensite)
        x = 0.7 * x + 0.3 * sature
    if intensite <= 0:                              # voix brute : juste la normalisation
        return _normaliser(x, -1)
    return _normaliser(_compresser(x, seuil_db=-20, ratio=1.5 + 2 * intensite), -1)


def _pic(f0, q, gain_db):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / SR
    alpha = np.sin(w) / (2 * q)
    b = np.array([1 + alpha * A, -2 * np.cos(w), 1 - alpha * A])
    a = np.array([1 + alpha / A, -2 * np.cos(w), 1 - alpha / A])
    return b / a[0], a / a[0]


def _compresser(x, seuil_db=-18, ratio=3.0, attaque=0.005, relache=0.12):
    env = np.abs(x)
    a_att, a_rel = np.exp(-1 / (attaque * SR)), np.exp(-1 / (relache * SR))
    suivi = signal.lfilter([1 - a_rel], [1, -a_rel], env)          # suiveur d'enveloppe (approché)
    suivi = np.maximum(suivi, signal.lfilter([1 - a_att], [1, -a_att], env) * 0.7)
    niveau = 20 * np.log10(np.maximum(suivi, 1e-6))
    reduction = np.minimum(0, (seuil_db - niveau) * (1 - 1 / ratio))
    return x * 10 ** (reduction / 20)


def _normaliser(x, crete_db=-1.0):
    m = np.max(np.abs(x)) or 1.0
    return x / m * 10 ** (crete_db / 20)


def monter(voix_24k, intensite=1.0, avec_nappe=True):
    """Assemble jingle -> voix (sur nappe) -> fin de jingle. Renvoie un signal mono 44,1 kHz."""
    j = jingle()
    v = voix_radio(voix_24k, intensite)
    entree_voix = len(j) - int(1.1 * SR)          # la voix entre pendant la fin du jingle
    fermeture = fin()
    total = entree_voix + len(v) + int(0.4 * SR) + len(fermeture)
    piste = np.zeros(total)
    piste[:len(j)] += j * 0.8
    piste[entree_voix:entree_voix + len(v)] += v
    if avec_nappe:
        n = nappe(len(v) / SR + 1.5)
        piste[entree_voix:entree_voix + len(n)] += n * 10 ** (-24 / 20)
    _placer(piste, fermeture * 0.8, (entree_voix + len(v)) / SR + 0.4)
    return _normaliser(piste, -1.0)


def monter_episode(sequences, intensite=1.0):
    """sequences : liste de (type, pcm 24 kHz). Jingle, puis chaque séquence séparée par une vraie respiration
    (et un son de transition avant chaque nouveau sujet), nappe sous toute la voix, fermeture musicale."""
    rng = np.random.default_rng(5)
    j = jingle()
    morceaux, pos = [], len(j) - int(1.1 * SR)
    debuts = []                                     # début de chaque séquence dans l'épisode (en secondes)
    for k, (genre, pcm) in enumerate(sequences):
        if k == 0:
            debuts.append(0.0)
        if k > 0:
            if genre in ("sujet", "histoire"):
                pos += int(0.35 * SR)
                debuts.append(round(pos / SR, 1))
                morceaux.append((pos, transition() * 0.55))
                pos += int(0.95 * SR)
            else:
                pos += int(rng.uniform(0.55, 0.8) * SR)
                debuts.append(round(pos / SR, 1))
        v = voix_radio(pcm, intensite)
        morceaux.append((pos, v))
        pos += len(v)
    debut_voix, fin_voix = len(j) - int(1.1 * SR), pos
    fermeture = fin()
    piste = np.zeros(fin_voix + int(0.5 * SR) + len(fermeture))
    piste[:len(j)] += j * 0.8
    n = nappe((fin_voix - debut_voix) / SR + 1.5)
    piste[debut_voix:debut_voix + len(n)] += n[:len(piste) - debut_voix] * 10 ** (-26 / 20)
    for p0, son in morceaux:
        piste[p0:p0 + len(son)] += son[:len(piste) - p0]
    _placer(piste, fermeture * 0.8, fin_voix / SR + 0.5)
    return _normaliser(piste, -1.0), debuts


def forme_d_onde(x, barres=240):
    """Niveau sonore de l'épisode en `barres` valeurs entre 0 et 1, pour dessiner la forme d'onde."""
    n = len(x) // barres
    rms = np.sqrt(np.mean(x[:n * barres].reshape(barres, n) ** 2, axis=1))
    rms = rms / (np.max(rms) or 1)
    return [round(float(v), 2) for v in np.sqrt(rms)]


def en_mp3(x, chemin, debit=96):
    import lameenc
    enc = lameenc.Encoder()
    enc.set_bit_rate(debit)
    enc.set_in_sample_rate(SR)
    enc.set_channels(1)
    enc.set_quality(2)
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()
    with open(chemin, "wb") as f:
        f.write(enc.encode(pcm) + enc.flush())
