// Pièce Unique : reçoit les notifs (Web Push) et ouvre le site au bon endroit quand on touche la notif.
// Pas de cache hors ligne : le site reste toujours à jour.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || "Pièce Unique", {
    body: d.body || "De nouveaux bons plans t'attendent.",
    icon: "icone-192.png", badge: "icone-192.png", tag: d.tag || "pu", renotify: true,
    data: { url: d.url || "./" }
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || "./", self.registration.scope).href;
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(ws => {
    for (const w of ws) if (w.url.startsWith(self.registration.scope) && "focus" in w) { w.navigate(url); return w.focus(); }
    return clients.openWindow(url);
  }));
});
