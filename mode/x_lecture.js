// À exécuter (javascript_tool) sur une page de recherche X du type
// https://x.com/search?q=from%3ACaminoTV%20chck.me%20since%3A2026-11-10&f=live
// Fait défiler ~35 s et garde chaque post [compte, id, texte, ids images] dans localStorage « __pu_x ».
// Renvoie le nombre de posts gardés pour ce compte. Relancer une 2e fois si « encore » est true.
(async () => {
  const q = new URL(location).searchParams.get("q") || "";
  const compte = (q.match(/from:(\w+)/i) || [])[1];
  if (!compte) return "Ce n'est pas une recherche from:compte";
  const K = "__pu_x";
  let all = {};
  try { all = JSON.parse(localStorage.getItem(K) || "{}"); } catch (e) {}
  const t0 = Date.now(); let stable = 0, avant = -1;
  const lire = () => {
    for (const ar of document.querySelectorAll('article[data-testid="tweet"]')) {
      const h = [...ar.querySelectorAll('a[href*="/status/"]')].map(a => a.getAttribute("href")).find(h => /^\/[^/]+\/status\/\d+$/.test(h));
      if (!h || h.split("/")[1].toLowerCase() !== compte.toLowerCase()) continue;
      const id = h.split("/")[3];
      const el = ar.querySelector('[data-testid="tweetText"]');
      if (!el) continue;
      const c = el.cloneNode(true);
      c.querySelectorAll("a").forEach(a => a.replaceWith(document.createTextNode(" " + a.textContent.replace(/…$/, "") + " ")));
      c.querySelectorAll("img[alt]").forEach(i => i.replaceWith(document.createTextNode(i.alt)));
      const texte = c.textContent.replace(/\s+/g, " ").trim();
      // photos : id pbs.twimg.com/media ; vidéo : URL complète de l'aperçu. Les images chargent lentement :
      // on garde celles déjà vues si le post est relu sans elles.
      const imgs = [...new Set([...ar.querySelectorAll('img[src*="pbs.twimg.com/media/"]')].map(i => (i.src.match(/media\/([^?.]+)/) || [])[1]).filter(Boolean)
        .concat([...ar.querySelectorAll("video[poster]")].map(v => v.poster.split("?")[0])))];
      all[id] = [h.split("/")[1], id, texte, imgs.length ? imgs : ((all[id] || [])[3] || [])];
    }
  };
  while (Date.now() - t0 < 35000 && stable < 6) {
    lire();
    const n = Object.keys(all).length;
    stable = n === avant ? stable + 1 : 0; avant = n;
    scrollBy(0, 900);
    await new Promise(r => setTimeout(r, 2400));
  }
  lire();
  localStorage.setItem(K, JSON.stringify(all));
  return { compte, posts_compte: Object.values(all).filter(p => p[0].toLowerCase() === compte.toLowerCase()).length, total: Object.keys(all).length, encore: stable < 6 };
})();
