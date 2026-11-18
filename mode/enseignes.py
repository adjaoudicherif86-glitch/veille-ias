"""
Grandes enseignes hors Shopify : Zara (API publique du site) et Uniqlo (API commerce du site).
Chaque fonction renvoie des articles au même format que collecte.analyser(), ou [] si l'enseigne ne répond pas.
Les « prix spéciaux » Zara sans ancien prix sont gardés avec remise = 0 et prix_special = True.
"""
import json
import re
import sys

import requests

NAV = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
       "Accept": "application/json", "Accept-Language": "fr-FR,fr;q=0.9"}


def _categorie(texte, categories):
    for nom, motif in categories:
        if re.search(motif, texte, re.I):
            return nom
    return None


# --- Zara -----------------------------------------------------------------

def zara(categories, debug=False):
    try:
        arbre = requests.get("https://www.zara.com/fr/fr/categories?ajax=true", headers=NAV, timeout=30).json()
    except Exception as e:
        print(f"  ✗ Zara : catégories illisibles ({e})", file=sys.stderr)
        return []
    cibles = []

    def parcours(noeuds, chemin=""):
        for n in noeuds or []:
            nom = n.get("name", "")
            if (chemin.startswith(" > HOMME") or chemin.startswith(" > FEMME")) and re.search(r"special prices|soldes|sale|prix", nom, re.I) and "CARTE" not in chemin:
                cibles.append((n.get("redirectCategoryId") or n.get("id"), f"{chemin} > {nom}"))
            parcours(n.get("subcategories"), f"{chemin} > {nom}")

    parcours(arbre.get("categories"))
    articles, vus = [], set()
    # 4 catégories homme et 3 femme au plus
    hommes = [c for c in cibles if c[1].startswith(" > HOMME")][:4]
    femmes = [c for c in cibles if c[1].startswith(" > FEMME")][:3]
    cibles = hommes + femmes
    for cid, chemin in cibles:
        g = "femme" if chemin.startswith(" > FEMME") else "homme"
        try:
            d = requests.get(f"https://www.zara.com/fr/fr/category/{cid}/products?ajax=true", headers=NAV, timeout=30).json()
        except Exception as e:
            print(f"  ✗ Zara {chemin} : {e}", file=sys.stderr)
            continue
        produits = [c for g in d.get("productGroups", []) for el in g.get("elements", []) for c in el.get("commercialComponents", [])
                    if c.get("type") == "Product"]
        if debug and produits:
            print("ZARA exemple :", json.dumps(produits[0], ensure_ascii=False)[:1500])
        for p in produits:
            if p.get("id") in vus or p.get("sectionName") not in (None, "MAN" if g == "homme" else "WOMAN"):
                continue
            vus.add(p.get("id"))
            prix = (p.get("price") or 0) / 100
            avant = (p.get("oldPrice") or 0) / 100
            couleurs = (p.get("detail") or {}).get("colors") or []
            c0 = couleurs[0] if couleurs else {}
            prix = (c0.get("price") or p.get("price") or 0) / 100 or prix
            avant = (c0.get("oldPrice") or p.get("oldPrice") or 0) / 100 or avant
            images = [m["url"].replace("{width}", "750") for m in (c0.get("xmedia") or p.get("xmedia") or []) if m.get("type") == "image" and m.get("url")][:3]
            cat = _categorie(f"{p.get('familyName', '')} {p.get('name', '')}", categories)
            if not images or not cat or not prix:
                continue
            seo = p.get("seo") or {}
            lien = (f"https://www.zara.com/fr/fr/{seo['keyword']}-p{seo['seoProductId']}.html"
                    + (f"?v1={seo['discernProductId']}" if seo.get("discernProductId") else "")) if seo.get("keyword") and seo.get("seoProductId") \
                else f"https://www.zara.com/fr/fr/search?searchTerm={requests.utils.quote(p.get('name', ''))}&section={'MAN' if g == 'homme' else 'WOMAN'}"
            remise = round((1 - prix / avant) * 100) if avant > prix else 0
            nom = p.get("name", "").capitalize()
            articles.append({
                "id": f"zara-{p['id']}", "genre": g, "boutique": "Zara", "domaine": "zara.com", "origine": "UE", "pays": "FR",
                "marque": "Zara", "nom": nom + (f" - {c0['name']}" if c0.get("name") else ""), "categorie": cat, "type": p.get("familyName", ""),
                "prix": prix, "avant": avant or prix, "devise": "EUR", "remise": remise, "prix_eur": round(prix, 2),
                "avant_eur": round(avant or prix, 2), "tailles": [], "images": images, "lien": lien, "styles_indice": ["minimal", "streetwear"],
                "description": "", "prix_special": remise == 0, "enseigne": True,
            })
    print(f"🛍️  Zara            {len(articles):3} articles ({', '.join(c for _, c in cibles) or 'aucune catégorie promo'})")
    return articles


# --- Uniqlo ---------------------------------------------------------------

def uniqlo(categories, debug=False):
    base = "https://www.uniqlo.com/fr/api/commerce/v5/fr/products"
    h = NAV | {"x-fr-clientid": "uq.fr.web-spa"}
    articles = []
    for offset in range(0, 600, 100):
        try:
            r = requests.get(base, headers=h, timeout=30, params={"flagCodes": "discount", "limit": 100, "offset": offset, "httpFailure": "true"})
            d = r.json()
        except Exception as e:
            print(f"  ✗ Uniqlo : {e}", file=sys.stderr)
            break
        items = ((d.get("result") or {}).get("items")) or []
        if debug and offset == 0:
            print("UNIQLO réponse :", json.dumps(d, ensure_ascii=False)[:1500])
        for it in items:
            genre = json.dumps({k: it.get(k) for k in ("genderCategory", "genderName", "gender")}, ensure_ascii=False).upper()
            if "KIDS" in genre or "BABY" in genre or "ENFANT" in genre:
                continue
            if "WOMEN" in genre or "FEMME" in genre:
                g = "femme"
            elif "MEN" in genre or "HOMME" in genre:
                g = "homme"
            elif "UNISEX" in genre:
                g = "mixte"
            else:
                continue
            prix_d = it.get("prices") or {}
            avant = ((prix_d.get("base") or {}).get("value")) or 0
            prix = ((prix_d.get("promo") or {}).get("value")) or avant
            if not prix or not avant or prix >= avant:
                continue
            imgs = it.get("images") or {}
            images = [v.get("image") for v in (imgs.get("main") or {}).values() if isinstance(v, dict) and v.get("image")][:2]
            images += [v.get("image") for v in (imgs.get("sub") or []) if isinstance(v, dict) and v.get("image")][:1]
            cat = _categorie(it.get("name", ""), categories) or _categorie(json.dumps(it.get("categories", ""))[:300], categories)
            if not images or not cat:
                continue
            pid = it.get("productId", "")
            tailles = [s.get("name") for s in it.get("sizes") or [] if isinstance(s, dict) and s.get("name")]
            remise = round((1 - prix / avant) * 100)
            articles.append({
                "id": f"uniqlo-{pid}", "genre": g, "boutique": "Uniqlo", "domaine": "uniqlo.com", "origine": "UE", "pays": "FR",
                "marque": "Uniqlo", "nom": it.get("name", ""), "categorie": cat, "type": "", "prix": prix, "avant": avant, "devise": "EUR",
                "remise": remise, "prix_eur": round(prix, 2), "avant_eur": round(avant, 2), "tailles": tailles[:10], "images": images,
                "lien": f"https://www.uniqlo.com/fr/fr/products/{pid}", "styles_indice": ["minimal"], "description": "", "enseigne": True,
            })
        if len(items) < 100:
            break
    print(f"🛍️  Uniqlo          {len(articles):3} articles en promo")
    return articles


if __name__ == "__main__":
    sys.path.insert(0, "mode")
    from collecte import CATEGORIES
    for f in (zara, uniqlo):
        a = f(CATEGORIES, debug=True)
        for x in a[:4]:
            print(" ", x["nom"], x["categorie"], x["prix_eur"], x["avant_eur"], x["remise"], x["lien"], x["images"][:1])


# --- Carhartt WIP ------------------------------------------------------------
# Leur site (Next.js) s'appuie sur Constructor.io, le moteur de recherche public que le navigateur de chaque visiteur
# interroge. On lit les mêmes groupes que la page (Black Friday, promos), avec les prix France.

CARHARTT_CLE = "key_QG9KK8DOmSUeFblV"


def _carhartt_lien(slug):
    """Le format d'URL produit n'est pas documenté : on teste les formats plausibles une fois par passage."""
    for f in ("https://www.carhartt-wip.com/fr-fr/p/{}", "https://www.carhartt-wip.com/fr-fr/{}", "https://www.carhartt-wip.com/fr-fr/product/{}"):
        try:
            r = requests.get(f.format(slug), headers=NAV, timeout=20)
            if r.status_code == 200:
                return f
        except requests.RequestException:
            pass
    return None


def carhartt(categories, debug=False):
    base = "https://ac.cnstrc.com/browse/group_id/{}"
    vus, articles, fmt = set(), [], None
    for groupe in ("black-friday", "homme-promos-hiver", "homme-promos-ete", "femme-promos-hiver", "femme-promos-ete"):
        for page in range(1, 6):
            try:
                r = requests.get(base.format(groupe), headers=NAV, timeout=25, params={
                    "key": CARHARTT_CLE, "section": "Products", "num_results_per_page": 100, "page": page,
                    "fmt_options[show_hidden_fields]": "true"})
                res = r.json()["response"]["results"]
            except (requests.RequestException, ValueError, KeyError):
                break
            for x in res:
                d = x.get("data", {})
                prix, avant = d.get("price_FR_EUR"), d.get("list_price_FR_EUR")
                if not prix or not avant or d.get("hide_from_webshop") or not d.get("main_visible_flag_b2c", True):
                    continue
                prix, avant = prix / 100, avant / 100
                if prix >= avant or d.get("url") in vus or (d.get("stock_quantity") is not None and d["stock_quantity"] <= 0):
                    continue
                vus.add(d["url"])
                gids = " ".join(d.get("group_ids", []) + d.get("attr_main_category_url", []))
                g = "femme" if ("femme" in gids and "homme" not in gids) or d.get("product_title", "").lower().startswith("women") else "homme"
                titre = f"{d.get('product_title', '')} {d.get('color_description', '')}".strip()
                cat = _categorie(f"{titre} {' '.join(d.get('type', []))}", categories) or "accessoire"
                if fmt is None:
                    fmt = _carhartt_lien(d["url"]) or ""
                lien = fmt.format(d["url"]) if fmt else f"https://www.carhartt-wip.com/fr-fr/search?q={requests.utils.quote(d.get('product_title', ''))}"
                images = [i + "?w=900&fmt=auto" for i in (d.get("images") or [d.get("image_url")])[:3] if i]
                remise = round((1 - prix / avant) * 100)
                articles.append({
                    "id": f"carhartt-{d.get('id') or d['url']}", "genre": g, "boutique": "Carhartt WIP", "domaine": "carhartt-wip.com",
                    "origine": "UE", "pays": "DE", "marque": "Carhartt WIP", "nom": titre, "categorie": cat, "type": " ".join(d.get("type", [])),
                    "prix": prix, "avant": avant, "devise": "EUR", "remise": remise, "prix_eur": round(prix, 2), "avant_eur": round(avant, 2),
                    "tailles": [], "images": images, "lien": lien, "styles_indice": ["workwear", "streetwear"],
                    "description": re.sub(r"<[^>]+>", " ", d.get("description", ""))[:300], "prix_special": False, "enseigne": True,
                })
            if len(res) < 100:
                break
    print(f"🛍️  Carhartt WIP    {len(articles):3} articles en promo (lien produit : {'ok' if fmt else 'recherche'})")
    return articles
