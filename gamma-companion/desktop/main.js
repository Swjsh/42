"use strict";

// Gamma desktop app (Electron). Wraps the companion cockpit in a real desktop
// window -- no browser, no tabs, own taskbar entry. Crucially it AUTO-GRANTS the
// microphone so the OpenAI Realtime voice works with zero permission friction
// (the thing that snagged in Chrome). WebRTC + getUserMedia work natively here.

const { app, BrowserWindow, session } = require("electron");
const path = require("path");

// Cross-origin tailnet reach: the origin gate in server.js only trusts a host it
// reads from GAMMA_TAILNET_HOST -- and nobody set it, so every tailnet /api/chat
// 403'd. Seed it from the machine-specific .tailnet-host file (gitignored) BEFORE
// requiring server.js, so the phone/watch over Tailscale Serve can reach the PC.
// Absent file -> env stays unset -> localhost-only (the safe default), no throw.
if (!process.env.GAMMA_TAILNET_HOST) {
  try {
    const h = require("fs").readFileSync(path.join(__dirname, "..", "..", "automation", "state", ".tailnet-host"), "utf8").trim();
    if (h) process.env.GAMMA_TAILNET_HOST = h;
  } catch (e) { /* no tailnet host -> localhost only */ }
}

// Boot the embedded companion server in this process. Safe if one is already
// running on 4317 -- server.js has an EADDRINUSE handler that reuses it.
require(path.join(__dirname, "..", "server.js"));

const PORT = process.env.GAMMA_COMPANION_PORT || 4317;
let win = null;

function createWindow() {
  win = new BrowserWindow({
    width: 1180,
    height: 820,
    minWidth: 420,
    minHeight: 560,
    backgroundColor: "#0b0e1a",
    title: "Gamma",
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });

  // Auto-grant microphone + media so voice "just works" -- no permission dialog.
  const ses = win.webContents.session;
  ses.setPermissionRequestHandler((wc, permission, callback) => callback(true));
  ses.setPermissionCheckHandler(() => true);

  // The DESKTOP app is the pixel "office" — one animated worker per live Claude
  // session (the phone, m.html at "/", stays the controller). Load /desktop.html
  // explicitly. Always clear the HTTP cache first so a code update is never masked
  // by a stale cache. Use 127.0.0.1 (not localhost) to avoid Windows resolving to
  // ::1 before the IPv4-bound server.
  const load = () => { if (win && !win.isDestroyed()) ses.clearCache().finally(() => { if (win && !win.isDestroyed()) win.loadURL("http://127.0.0.1:" + PORT + "/desktop.html"); }); };
  win.webContents.on("did-fail-load", () => setTimeout(load, 700));
  setTimeout(load, 600);

  // RESILIENCE: the window must NOT die on a renderer crash. A JS error, a GPU
  // hiccup, or (most likely) the OpenAI voice WebRTC can take the renderer down --
  // without this, J is left staring at a dead window ("used it once then it
  // crashed"). Reload instead, with a small backoff cap so a hard crash-loop can't
  // spin. This is the window-side twin of server.js's crash guard.
  let renderRecoveries = 0;
  let lastCrashAt = 0;
  const tryRecover = () => {
    const now = Date.now();
    if (now - lastCrashAt > 60000) renderRecoveries = 0; // only cluster-within-60s counts as a loop
    lastCrashAt = now;
    if (renderRecoveries++ < 8) {
      setTimeout(load, Math.min(600 * Math.pow(2, renderRecoveries), 10000));
    } else if (win && !win.isDestroyed()) {
      win.loadURL("data:text/html,<body style='background:%230b0e1a;color:%23eee;font-family:sans-serif;padding:2rem'><h2>Gamma renderer crash-loop detected</h2><p>The window kept crashing on reload. Restart the app.</p></body>");
    }
  };
  win.webContents.on("render-process-gone", (_e, details) => { try { console.error("[gamma] renderer gone:", details && details.reason); } catch {} tryRecover(); });
  win.webContents.on("unresponsive", tryRecover);

  win.on("closed", () => { win = null; });
}

app.whenReady().then(createWindow);
app.on("activate", () => { if (win === null) createWindow(); });
app.on("window-all-closed", () => app.quit());
