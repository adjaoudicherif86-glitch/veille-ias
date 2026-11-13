"""Sondage n°7 : flux RSS Dealabs (mode homme) lisibles ?"""
import re
import requests
H = {"User-Agent": "Mozilla/5.0 (compatible; PieceUnique/1.0; veille personnelle)"}
for u in ["https://www.dealabs.com/rss/groupe/mode-accessoires", "https://www.dealabs.com/rss/groupe/vetements-homme",
          "https://www.dealabs.com/rss/groupe/chaussures-homme", "https://www.dealabs.com/rss/groupe/sneakers",
          "https://www.dealabs.com/rss/hot", "https://www.dealabs.com/rss/nouveaux", "https://www.dealabs.com/rss/groupe/vetements"]:
    try:
        r = requests.get(u, headers=H, timeout=25)
        t = r.text
        items = re.findall(r"<item>(.*?)</item>", t, re.S)
        print("RSS", u, r.status_code, r.headers.get("content-type", "")[:30], len(t), len(items))
        for it in items[:3]:
            print("   ", re.sub(r"\s+", " ", it)[:700])
    except Exception as e:
        print("RSS", u, "ERREUR", e)
