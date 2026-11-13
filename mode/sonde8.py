"""Sondage n°8 : structure des fiches du site LinkDeal."""
import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "fr-FR"}
x = requests.get("https://lnkd-linkdeal.fr", headers=H, timeout=30).text
i = x.find("Veste doublée polaire")
print("CARTE", x[max(0, i - 2500):i + 1200].replace("\n", " "))
print("LIENS", re.findall(r'href="([^"]+)"', x)[:80])
j = x.find("self.__next_f")
print("RSC", len(x), x.count("self.__next_f"), x[j:j + 1500].replace("\n", " ") if j > 0 else "aucun")
k = x.find('\\"price')
print("PRIX_JSON", x[max(0, k - 600):k + 600] if k > 0 else "aucun")
