# Gamma Companion — Mobile PWA + Voice Design

**Date:** 2026-06-21  
**Status:** Analysis & Design (no code changes)  
**Scope:** Android phone + Samsung Watch Wear OS, PWA installable, OpenAI Realtime voice over WebRTC  

---

## Executive Summary

The existing Gamma Companion (Node http server on 127.0.0.1:4317 + vanilla-JS UI + OpenAI Realtime WebRTC) can be converted into a mobile-installable PWA **without modifying server.js, app.js, or realtime.js**. The critical bottleneck is **secure context (HTTPS requirement for getUserMedia)**. The cleanest path:

1. **Bridge HTTPS via Tailscale Serve** (MagicDNS with auto-generated certs) → trusted by Android Chrome  
2. **Add manifest.webmanifest** to public/ → enables Add-to-Home-Screen on Android  
3. **Add service-worker.js** with offline fallback + cache-first for assets  
4. **Responsive CSS rewrite** from desktop-grid-optimized → mobile-first (phone/watch form factors)  

**No companion-code changes needed.** The token auth (x-gamma-token + Origin allowlist) already guards all /api/ calls. Realtime.js already uses ephemeral OpenAI tokens, so the browser never sees an API key.

---

## Core Problem: Secure Context for getUserMedia

### The Issue

[`realtime.js` calls `navigator.mediaDevices.getUserMedia({ audio: true })`](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia). This **requires a secure context**:

- **Secure contexts (allowed):** HTTPS, localhost (dev only), 127.0.0.1 (dev only)  
- **NOT secure:** http://192.168.x.x, http://192.168.1.50:4317, http://your-device-ip:4317  

**On Android Chrome:** HTTP is categorically rejected, even on local network. You MUST use HTTPS or localhost.

### Current Setup

- Companion runs on http://127.0.0.1:4317 (localhost, secure context ✓)  
- From desktop, everything works — getUserMedia succeeds  
- From **Android phone over same WiFi**: http://192.168.1.50:4317 is **NOT localhost**, so getUserMedia fails with `NotAllowedError`  
- From **Samsung Watch**: same problem  

### Solution: Tailscale Serve + HTTPS

[Tailscale Serve auto-generates HTTPS certificates](https://tailscale.com/docs/features/tailscale-serve) within your tailnet. Configure Serve to forward `https://gamma.tailnet:443` → localhost:4317. Android Chrome trusts Tailscale's certificates automatically (issued by Let's Encrypt for your MagicDNS domain).

**Result:** Phone accesses `https://gamma.tailnet/` → secure context ✓ → getUserMedia works.

---

## Design: 4 Layers

### Layer 1: HTTPS Termination (Tailscale Serve)

**What:** One-line Tailscale config to proxy HTTPS → localhost:4317.

**How:**

```bash
# On the desktop machine running Gamma companion:
tailscale serve https://gamma.tailnet:443 http://localhost:4317
```

**Verification:**  
```bash
# From phone on same tailnet:
curl -I https://gamma.tailnet/
# → 200 OK (TLS cert valid, issued by Tailscale MagicDNS)
```

**Why this works:**
- Tailscale auto-issues certs for your MagicDNS domain (gamma.tailnet)  
- Android Chrome trusts them (via system CA)  
- No self-signed cert warnings  
- No manual cert management  

---

### Layer 2: PWA Manifest

**File:** `gamma-companion/public/manifest.webmanifest`

```json
{
  "name": "Gamma Trading Assistant",
  "short_name": "Gamma",
  "description": "Real-time trading AI with voice interface",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "theme_color": "#08231c",
  "background_color": "#08231c",
  "orientation": "portrait-primary",
  "icons": [
    {
      "src": "/gamma-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/gamma-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/gamma-maskable-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "maskable"
    },
    {
      "src": "/gamma-maskable-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "maskable"
    }
  ],
  "categories": ["finance", "productivity"],
  "screenshots": [
    {
      "src": "/screenshot-mobile.png",
      "sizes": "540x720",
      "type": "image/png",
      "form_factor": "narrow"
    },
    {
      "src": "/screenshot-tablet.png",
      "sizes": "1280x800",
      "type": "image/png",
      "form_factor": "wide"
    }
  ],
  "shortcuts": [
    {
      "name": "Ask Gamma",
      "short_name": "Ask",
      "description": "Quick question to Gamma",
      "url": "/?shortcut=ask",
      "icons": [
        {
          "src": "/gamma-ask-96.png",
          "sizes": "96x96"
        }
      ]
    }
  ]
}
```

**Update in index.html** (head):
```html
<link rel="manifest" href="/manifest.webmanifest" />
<meta name="theme-color" content="#08231c" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
```

**Icons needed** (place in public/):
- `gamma-192.png` (192×192, square, solid background)
- `gamma-512.png` (512×512, square)
- `gamma-maskable-192.png` & `gamma-maskable-512.png` (adaptive icons, safe-zone center)
- `screenshot-mobile.png` (540×720)
- `screenshot-tablet.png` (1280×800)

**Gotcha:** Manifest path must be from the root of your origin. If companion serves from `https://gamma.tailnet/`, manifest must be at `/manifest.webmanifest`.

---

### Layer 3: Service Worker

**File:** `gamma-companion/public/service-worker.js`

```javascript
const CACHE_NAME = "gamma-v1";
const ASSETS = [
  "/",
  "/index.html",
  "/styles.css",
  "/app.js",
  "/realtime.js",
  "/vendor/gridstack-all.js",
  "/vendor/gridstack.min.css",
  "/manifest.webmanifest",
  "/gamma-192.png",
];

// Install: pre-cache static assets
self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      cache.addAll(ASSETS).catch(() => {
        // Some assets may 404 during install (e.g., icons if not yet added).
        // Don't block install — just cache what's available.
      });
      self.skipWaiting();
    })
  );
});

// Activate: clean old caches
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch: cache-first for assets, network-first for API
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // For /api/* → always network-first (real-time data)
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(e.request)
        .catch(() => new Response("offline", { status: 503 }))
    );
    return;
  }

  // For assets → cache-first, fallback to network
  if (e.request.method === "GET") {
    e.respondWith(
      caches
        .match(e.request)
        .then((cached) => cached || fetch(e.request))
        .catch(() => new Response("offline", { status: 503 }))
    );
    return;
  }

  // For other methods (POST, etc.) → network-only
  e.respondWith(fetch(e.request));
});
```

**Register in index.html** (before closing </body>):
```html
<script>
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/service-worker.js").catch((err) => {
      console.warn("ServiceWorker registration failed:", err);
    });
  }
</script>
```

**Why this design:**
- **Cache-first for assets** → works offline, instant load  
- **Network-first for /api/** → always get fresh state, approvals, feed  
- **Graceful fallback** → on network error, 503 response instead of broken UI  

---

### Layer 4: Responsive CSS Rewrite

**Current state:** index.html uses Gridstack (12-column desktop grid). On a 5-inch phone, a 12-column grid becomes unreadably thin.

**Needed:** Mobile-first breakpoints + stacked single-column on small screens.

#### Mobile-First Architecture

```css
/* Base: mobile (< 600px) — single column, stacked */
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.topbar {
  flex-shrink: 0;
  padding: 12px;
  background: #08231c;
}

.scroll {
  flex: 1;
  overflow-y: auto;
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  padding: 12px;
}

.grid-stack-item {
  /* Override gridstack's grid positioning on mobile */
  grid-column: 1 !important;
  grid-row: auto !important;
  min-height: 200px;
}

/* Tablet: 768px and up — 2 column */
@media (min-width: 768px) {
  .scroll {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Desktop: 1200px and up — keep original gridstack layout */
@media (min-width: 1200px) {
  .scroll {
    display: block; /* Let gridstack manage layout */
  }
  .grid-stack-item {
    grid-column: auto !important;
    grid-row: auto !important;
  }
}

/* Watch-specific: <280px */
@media (max-width: 280px) {
  .topbar {
    padding: 6px;
    font-size: 12px;
  }
  .hero {
    display: none; /* Robot SVG too big for watch */
  }
  .robot-status {
    font-size: 10px;
    line-height: 1.2;
  }
}
```

#### Responsive Typography & Touch Targets

```css
/* Touch targets: min 44px for buttons on phone */
button {
  min-height: 44px;
  min-width: 44px;
  padding: max(8px, 2vw);
  font-size: clamp(12px, 4vw, 16px);
}

/* Heading scale */
h1 {
  font-size: clamp(18px, 8vw, 32px);
}
h2 {
  font-size: clamp(14px, 6vw, 20px);
}

/* Input field on mobile */
#chat-input {
  font-size: 16px; /* Prevents zoom-on-focus on iOS */
  padding: 12px;
}

/* Micro-layout for watch */
@media (max-height: 280px) {
  .askbar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    max-height: 50%;
  }
}
```

#### Feed & Approvals on Mobile

```css
/* Timeline feed: cards instead of list on mobile */
.timeline {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.timeline li {
  background: rgba(255, 255, 255, 0.05);
  padding: 8px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.4;
  white-space: normal; /* Wrap on mobile */
}

/* Approvals queue: stack vertically */
.approvals-item {
  margin-bottom: 12px;
  border: 1px solid rgba(52, 224, 161, 0.3);
  padding: 12px;
  border-radius: 8px;
}

.approval-buttons {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.approval-buttons button {
  flex: 1;
  font-size: 12px;
  padding: 8px;
}
```

---

## Watch-Specific Considerations

### Wear OS Constraints

- **Screen:** ~1.4 inches (280px width), round or square  
- **Interaction:** Rotating crown + touch, no keyboard  
- **Connectivity:** via phone (BLE tether) or direct WiFi  
- **Battery:** hours, not days  

### UX Adaptation

1. **Hide heavy visualizations** (robot SVG, large grids) on watch  
2. **Approval buttons** → touchable cards with large hit zones  
3. **Text** → condensed, single-column  
4. **Voice priority** → mic button always visible (bottom-floating)  
5. **No full chat log** → show last 3 messages only  

### Watch HTML Variant (optional)

Create a lightweight watch route:

```html
<!-- In index.html, detect User-Agent or add ?watch=1 -->
<body data-device="phone">
  <!-- Current app layout -->
</body>

<script>
  if (/Wear OS|Android.*Watch/.test(navigator.userAgent)) {
    document.body.dataset.device = "watch";
  }
</script>
```

```css
body[data-device="watch"] .hero { display: none; }
body[data-device="watch"] .timeline { max-height: 100px; font-size: 11px; }
body[data-device="watch"] #chat-log { display: none; }
body[data-device="watch"] .mic { position: fixed; bottom: 12px; right: 12px; width: 60px; height: 60px; }
```

---

## Security: No Changes Required

**Existing safeguards remain:**

1. **x-gamma-token** header (random 48-byte hex, per-session) → all /api/ calls checked in `authed(req)`  
2. **Origin allowlist** in `authed(req)` → only localhost/127.0.0.1 origins allowed (can extend to Tailscale MagicDNS domain)  
3. **lib/guard.js** → companion Claude escalations still blocked from editing CLAUDE.md, params.json, placing orders  
4. **Ephemeral tokens for OpenAI** → realtime.js requests token from /api/realtime-token, uses it once, token expires  

**To allow Tailscale origin:**

In `server.js` line 27, update the Origin regex:
```javascript
if (origin && !/^https?:\/\/(localhost|127\.0\.0\.1|.*\.tailnet)(:|\/|$)/i.test(origin)) return false;
```

---

## Implementation Roadmap

### Phase 1: HTTPS Bridging (1h, no code changes)

1. Install Tailscale on desktop if not already (J has it)  
2. Enable Serve:  
   ```bash
   tailscale serve https://gamma.tailnet:443 http://localhost:4317
   ```
3. Test from phone:  
   ```
   https://gamma.tailnet/
   ```

### Phase 2: Manifest + Service Worker (30m)

1. Create `/public/manifest.webmanifest` (copy JSON above)  
2. Create `/public/service-worker.js` (copy code above)  
3. Update `/public/index.html` to link manifest + register SW  
4. Generate PNG icons (or use J's existing Gamma SVG + convert)  

### Phase 3: Responsive CSS (2–3h, medium effort)

1. Create `/public/styles-mobile.css` or refactor `styles.css` with breakpoints  
2. Test on Chrome DevTools (device emulation: iPhone 12, Pixel 5, Wear OS)  
3. Refinements: button hit zones, text sizing, watch layout  

### Phase 4: Real Device Testing (1h)

1. J's Android phone: visit https://gamma.tailnet/ → "Add to Home Screen" via Chrome menu  
2. Samsung Watch: same, adjust watch CSS if needed  
3. Voice test: tap mic, speak "what's the plan" → should capture + reach /api/chat  

---

## Known Gotchas

### 1. **Tailscale Domain ≠ Localhost**

The origin changes from `http://127.0.0.1:4317` to `https://gamma.tailnet`. Update `authed(req)` in `server.js` to accept the new origin.

### 2. **Service Worker Scope Mismatch**

If manifest `start_url` is `/` but server redirects to `/index.html`, SW scope may not match. Ensure:
```javascript
// server.js, serveStatic():
if (rel === "/") rel = "/index.html";  // ✓ already does this
```

### 3. **Cache Invalidation**

Service Worker caches assets by filename. On new companion release:
- Rename JS files (e.g., `app-v2.js`) OR  
- Change `CACHE_NAME` in SW to bust old caches  

### 4. **Offline APIs**

/api/ calls fail on no network. app.js should handle offline gracefully (already does per line 44: `catch (err)`).

### 5. **Watch Battery & Connectivity**

Wear OS apps over BLE have aggressive timeouts. Test with screen on, then dark. If watch goes dark, connection may drop — OK, user just taps to wake.

---

## Testing Checklist

- [ ] Desktop: https://gamma.tailnet/ loads, chat + voice work  
- [ ] Desktop: F12 → Application → Service Workers → registered & active  
- [ ] Desktop: offline (DevTools throttle), chat input shows graceful error  
- [ ] Phone: "Add to Home Screen" works, app icon on home  
- [ ] Phone: app launched from home screen runs standalone (no Chrome UI)  
- [ ] Phone: mic works, voice captures audio, sends to /api/chat  
- [ ] Phone: approvals queue renders, buttons tappable (44px+)  
- [ ] Watch: app launches (may be stripped-down view)  
- [ ] Watch: mic button visible, voice works  
- [ ] All: approvals UI readable (font size, color contrast)  

---

## Cost Impact (OP-3 Lean)

- **Tailscale Serve:** Already included in free tier or Pro ($4/mo if needed; Gamma likely on free)  
- **PWA assets:** Zero — manifest + SW are HTML/JS, hosted from existing 4317 server  
- **Icons:** Zero if using existing SVG → PNG conversion script  
- **Testing:** Zero, uses Chrome DevTools emulation  

**Total:** $0/month (Tailscale Serve is free for single user)

---

## Next Steps

1. **Create MEMORY.md entry** for this design (mobile_pwa_design.md)  
2. **Phase 1** (Tailscale): J runs one command, tests from phone  
3. **Phase 2–3** (manifest + CSS): Can be done autonomously or by J depending on priority  
4. **Phase 4** (real device): J tests on phone/watch, reports gotchas  

If J wants voice on watch, Watch OS has a "dictation" input (system-level) as fallback — no code needed.

---

## Sources

- [MDN: getUserMedia() — Secure Context Requirements](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
- [Tailscale: Serve & HTTPS Certificates](https://tailscale.com/docs/features/tailscale-serve)
- [OpenAI: Realtime API with WebRTC](https://developers.openai.com/api/docs/guides/realtime-webrtc)
- [web.dev: Add a web app manifest](https://web.dev/articles/add-manifest)
- [Gomage: PWA Add to Home Screen 2025](https://www.gomage.com/blog/pwa-add-to-home-screen/)
