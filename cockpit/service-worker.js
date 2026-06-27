/*
 * Gamma face — service worker.
 *
 * STRATEGY (deliberate, to avoid serving stale app code — a known PWA foot-gun):
 *   - NETWORK-FIRST for navigations (the HTML shell), /api/* and /events.
 *     Always fetch fresh; fall back to cache ONLY when the network is unreachable.
 *   - CACHE-FIRST only for static assets (icons, the manifest) — they're versioned
 *     by the cache name and rarely change.
 *
 * The HTML shell is NEVER cache-first, so a deploy of new face.html / server.js
 * shows up immediately when online.
 */

const CACHE = 'gamma-face-v3';

// Static, rarely-changing assets safe to serve cache-first.
const STATIC_PRECACHE = [
  '/manifest.webmanifest',
  '/assets/icon-192.png',
  '/assets/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(STATIC_PRECACHE))
      .catch(() => { /* precache best-effort; never block install */ })
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// Is this a static asset we serve cache-first?
function isStaticAsset(url) {
  if (url.pathname === '/manifest.webmanifest') return true;
  if (url.pathname.startsWith('/assets/')) return true;
  return false;
}

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Only handle same-origin GETs; let everything else (POST /event, cross-origin
  // font CDN, etc.) pass straight through to the network untouched.
  if (req.method !== 'GET') return;

  let url;
  try { url = new URL(req.url); } catch (_) { return; }
  if (url.origin !== self.location.origin) return;

  // ── CACHE-FIRST: static assets only ──
  if (isStaticAsset(url)) {
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) return cached;
        return fetch(req).then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
          }
          return res;
        });
      })
    );
    return;
  }

  // ── NETWORK-FIRST: navigations, /api/*, /events, and everything else ──
  // Always try the network first; fall back to cache only when offline.
  event.respondWith(
    fetch(req)
      .then((res) => {
        // Cache successful navigation/document responses as an offline fallback,
        // but the live network response is always what's served when online.
        if (res && res.ok && (req.mode === 'navigate' || url.pathname === '/' || url.pathname === '/face')) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((cached) => {
        if (cached) return cached;
        // Last resort for a navigation with no cached page: try the cached shell.
        if (req.mode === 'navigate') {
          return caches.match('/').then((shell) => shell || Response.error());
        }
        return Response.error();
      }))
  );
});
