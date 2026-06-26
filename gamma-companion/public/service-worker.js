"use strict";

// Gamma companion service worker.
//   * Cache-first for static assets (shell loads instantly + offline-ish).
//   * Network-first for /api/* (live state is never stale-served).
//   * push        -> showNotification with Approve/Reject actions from payload.
//   * notificationclick -> fetch the tapped action's signed /api/approve-signed
//                          URL (the ONE unauthenticated, single-use route), then
//                          focus/close. This is how a wrist tap resolves an
//                          approval without the page token.

const CACHE = "gamma-shell-v7";
const SHELL = [
  "/",
  "/m.html",
  "/realtime.js",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((c) => c.addAll(SHELL).catch(() => undefined))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return; // never cache POSTs (chat/approve)
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // let cross-origin pass through

  // Never intercept the signed-approve route or realtime token -- always live.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(req).catch(() =>
        caches.match(req).then((hit) => hit || new Response('{"ok":false,"error":"offline"}', { headers: { "content-type": "application/json" } }))
      )
    );
    return;
  }

  // App shell + static: NETWORK-FIRST so code is never stale (cache-first served a
  // stale app.js after an update); fall back to cache only when actually offline.
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok && res.type === "basic") {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => undefined);
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match("/m.html") || caches.match("/")))
  );
});

// ── push -> notification with Approve/Reject action buttons ─────────────────
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    try {
      data = { title: "Gamma", body: event.data ? event.data.text() : "" };
    } catch {
      data = {};
    }
  }
  const title = data.title || "Gamma";
  const actions = Array.isArray(data.actions)
    ? data.actions.map((a) => ({ action: a.action, title: a.title })).slice(0, 2)
    : [];
  const options = {
    body: data.body || "",
    tag: data.tag || undefined, // same tag => OS replaces/clears the pinned card
    renotify: !!data.tag,
    requireInteraction: !!data.requireInteraction,
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    data: {
      url: data.url || "/",
      // map action name -> its signed URL so notificationclick can fetch it
      actionUrls: Array.isArray(data.actions)
        ? data.actions.reduce((m, a) => {
            if (a && a.action && a.url) m[a.action] = a.url;
            return m;
          }, {})
        : {},
    },
    actions,
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// ── notificationclick -> resolve via the tapped action's signed URL ─────────
self.addEventListener("notificationclick", (event) => {
  const notif = event.notification;
  notif.close();
  const d = (notif && notif.data) || {};
  const actionUrls = d.actionUrls || {};
  const tappedUrl = event.action && actionUrls[event.action];

  event.waitUntil(
    (async () => {
      if (tappedUrl) {
        // Resolve the approval server-side. Best-effort; the in-app queue stays
        // authoritative if this fails (poor connectivity on the watch, etc.).
        try {
          await fetch(tappedUrl, { method: "GET", cache: "no-store" });
        } catch {
          /* swallow -- user can still resolve in the app */
        }
        return;
      }
      // Body tap (no action): focus an existing window or open the app.
      const target = d.url || "/";
      const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const c of all) {
        if ("focus" in c) {
          try {
            await c.focus();
            return;
          } catch {
            /* try next */
          }
        }
      }
      if (self.clients.openWindow) await self.clients.openWindow(target);
    })()
  );
});
