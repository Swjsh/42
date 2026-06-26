"use strict";

// Gamma companion server -- zero external npm dependencies (Node built-ins only).
// Serves the companion UI + a small JSON API over the REAL state files, plus the
// free-model FACE chat and the headless Claude escalation.
//
//   GET  /api/state        merged live state for the UI
//   POST /api/chat         { message, history } -> free-model face reply (may escalate)
//   GET  /api/ask-result   ?id=...  poll a Claude escalation result
//   POST /api/approve      { id, decision, note?, action? }
//
// Bound to 127.0.0.1 only. Port 4317 by default (never collides with the
// Next.js dashboard on 3000).

const http = require("http");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { buildState, summarize } = require("./lib/state");
const { resolveApproval, isCardSnoozed } = require("./lib/approvals");
const { runEscalation, getTasks, getTaskStatus, cancelTask, subscribeAskStream, unsubscribeAskStream, askFeedPath } = require("./lib/escalate");
const { loadOpenAIKey } = require("./lib/openai_key");
const { checkObligations } = require("./lib/obligations");
const { queueSummary, readQueue } = require("./lib/autobuild");
const push = require("./lib/push");
const crypto = require("crypto");

// ── CRASH GUARD (load-bearing) ──────────────────────────────────────────────
// The companion must SURVIVE any single bad escalation / face spawn / push / SSE
// error — never let one unhandled throw take down the whole server. This is the
// fix for "used it once, then it crashed": without these handlers a rejected
// fire-and-forget promise (e.g. runEscalation) exits the Node process. We log the
// stack to a crash file (so a real bug is still diagnosable) and KEEP RUNNING.
const CRASH_LOG = path.join(__dirname, "..", "automation", "state", "companion-crash.log");
function logCrash(kind, err) {
  try {
    const stack = err && err.stack ? err.stack : String(err);
    fs.appendFileSync(CRASH_LOG, new Date().toISOString() + " [" + kind + "] " + stack + "\n");
    process.stderr.write("[gamma-companion] survived " + kind + ": " + String((err && err.message) || err) + "\n");
  } catch {
    /* logging must NEVER itself crash the guard */
  }
}
process.on("uncaughtException", (err) => logCrash("uncaughtException", err));
process.on("unhandledRejection", (err) => logCrash("unhandledRejection", err));

// Persist the page-auth token so a cached phone/watch PWA stays valid across
// server restarts (a per-process random token 403'd every authed POST after any
// restart until a hard reload). Read .companion-token if present + non-empty;
// else mint one and write it. Built from a direct __dirname/.. path (ROOT is
// declared LATER in this file, so we must NOT depend on it here). Never throws.
const GAMMA_TOKEN = (() => {
  const tokenPath = path.join(__dirname, "..", "automation", "state", ".companion-token");
  try {
    const existing = fs.readFileSync(tokenPath, "utf8").trim();
    if (existing) return existing;
  } catch {
    /* no token yet -> mint + persist below */
  }
  const fresh = crypto.randomBytes(24).toString("hex");
  try {
    fs.writeFileSync(tokenPath, fresh);
  } catch {
    /* couldn't persist (read-only fs?) -> still works this process, just not stable */
  }
  return fresh;
})();
// Seed the tailnet host from the machine-specific .tailnet-host file when the env
// isn't already set. Electron (desktop/main.js) seeds it; bare `node server.js`,
// LAUNCH-COMPANION.vbs, and the keepalive task do NOT -- so the phone 403'd over
// the tailnet. Doing it here covers EVERY launch path at one point; Electron still
// short-circuits (env already set). Absent file -> env stays unset -> localhost-only
// (the safe default), never throws.
if (!process.env.GAMMA_TAILNET_HOST) {
  try {
    const h = fs.readFileSync(path.join(__dirname, "..", "automation", "state", ".tailnet-host"), "utf8").trim();
    if (h) process.env.GAMMA_TAILNET_HOST = h;
  } catch {
    /* no tailnet host file -> localhost-only */
  }
}
// Origin allowlist: localhost/127.0.0.1 always, PLUS the exact Tailscale MagicDNS
// host from env (pinned host, NEVER a bare *.ts.net wildcard -- that would accept
// any tailnet's origin). Empty env -> localhost-only, the safe default.
const TAILNET_HOST = (process.env.GAMMA_TAILNET_HOST || "").trim().toLowerCase();
function originAllowed(origin) {
  if (!origin) return true; // same-origin / non-browser caller
  if (/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/i.test(origin)) return true;
  if (TAILNET_HOST) {
    try {
      const h = new URL(origin).host.toLowerCase();
      if (h === TAILNET_HOST) return true;
    } catch {
      /* malformed origin -> not allowed */
    }
  }
  return false;
}
function authed(req) {
  const origin = req.headers["origin"];
  if (!originAllowed(origin)) return false;
  // Constant-time compare (matches the timingSafeEqual used for approve/stream
  // tokens) — a plain === leaks length/prefix timing.
  const given = req.headers["x-gamma-token"];
  if (typeof given !== "string") return false;
  const a = Buffer.from(given);
  const b = Buffer.from(GAMMA_TOKEN);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

const ROOT = process.env.GAMMA_WORKSPACE || path.resolve(__dirname, "..");
const PORT = Number(process.env.GAMMA_COMPANION_PORT || 4317);
const PUBLIC = path.join(__dirname, "public");
function pickPython() {
  if (process.env.GAMMA_PYTHON) return process.env.GAMMA_PYTHON;
  const known =
    "C:\\Users\\jackw\\AppData\\Local\\Microsoft\\WindowsApps\\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\\python.exe";
  try {
    if (fs.existsSync(known)) return known;
  } catch {
    /* fall through to PATH lookup */
  }
  return "python";
}
const PY = pickPython();
const STATE = (...p) => path.join(ROOT, "automation", "state", ...p);

// Obligation rising-edge push. We persist the set of obligation ids that were
// red on the LAST poll (+ when we last pushed each), so we push ONLY on the
// rising edge (newly-red), never on every 5s poll, rate-limited per id. The diff
// lives here in server.js so state.js stays a pure read.
const PUSH_SEEN = STATE(".push-seen.json");
const OBLIG_PUSH_COOLDOWN_MS = 30 * 60 * 1000; // re-notify a still-red id at most every 30m
function readPushSeen() {
  try {
    const raw = JSON.parse(fs.readFileSync(PUSH_SEEN, "utf8"));
    return raw && typeof raw === "object" ? raw : { red: {} };
  } catch {
    return { red: {} };
  }
}
function writePushSeen(obj) {
  try {
    const tmp = PUSH_SEEN + ".tmp." + process.pid;
    fs.writeFileSync(tmp, JSON.stringify(obj));
    fs.renameSync(tmp, PUSH_SEEN);
  } catch {
    /* best effort -- a failed seen-write just means we may re-push once */
  }
}
// Given the current red obligation cards, push for any that are newly red (or
// red past the cooldown) and persist the new seen-set. Fire-and-forget.
function pushRisingObligations(obCards) {
  try {
    const now = Date.now();
    const seen = readPushSeen();
    const prevRed = seen.red || {};
    const nextRed = {};
    for (const c of obCards) {
      const wasSeenAt = Number(prevRed[c.id]);
      const isRising = !Number.isFinite(wasSeenAt);
      const isStale = Number.isFinite(wasSeenAt) && now - wasSeenAt > OBLIG_PUSH_COOLDOWN_MS;
      if (isRising || isStale) {
        nextRed[c.id] = now;
        push.sendPush(ROOT, {
          title: c.title || "Obligation unmet",
          body: c.detail || "An engine obligation is unmet.",
          tag: c.id,
          url: "/",
          actions: [],
        });
      } else {
        nextRed[c.id] = wasSeenAt; // carry forward the original first-seen time
      }
    }
    writePushSeen({ red: nextRed });
  } catch {
    /* never let a push-bookkeeping error break /api/state */
  }
}

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

function sendJSON(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

function serveStatic(req, res) {
  let rel = decodeURIComponent(req.url.split("?")[0]);
  // Phone-optimized UI is the default entry point. The PWA manifest start_url is
  // "/", and push notifications open "/m.html" -- route the root to m.html so the
  // installed phone app + a bare root load both get the current mobile build, not
  // the older desktop redesign (index.html, still reachable at /index.html).
  if (rel === "/") rel = "/m.html";
  const file = path.normalize(path.join(PUBLIC, rel));
  if (!file.startsWith(PUBLIC)) {
    res.writeHead(403);
    return res.end("forbidden");
  }
  fs.readFile(file, (err, buf) => {
    if (err) {
      res.writeHead(404, { "content-type": "text/plain" });
      return res.end("not found");
    }
    let out = buf;
    if (path.extname(file) === ".html") {
      out = Buffer.from(
        buf.toString("utf8").replace(
          "</head>",
          '<meta name="gamma-token" content="' + GAMMA_TOKEN + '" />\n' +
            '  <link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2040%2040%22%3E%3Crect%20x%3D%228%22%20y%3D%2212%22%20width%3D%2224%22%20height%3D%2220%22%20rx%3D%227%22%20fill%3D%22%2334e0a1%22%2F%3E%3C%2Fsvg%3E" />\n  </head>'
        )
      );
    }
    res.writeHead(200, {
      "content-type": MIME[path.extname(file)] || "application/octet-stream",
      "cache-control": "no-store",
    });
    res.end(out);
  });
}

function readBody(req, res, cb) {
  let body = "";
  let aborted = false;
  req.on("data", (c) => {
    if (aborted) return;
    body += c;
    if (body.length > 2e5) {
      // Oversized: a bare req.destroy() inside 'data' meant 'end' never fired and
      // cb() was never called -> the request hung forever. Send 413 ONCE, mark
      // aborted, then destroy. Both 'data' and 'end' bail on `aborted` so exactly
      // one response is ever sent.
      aborted = true;
      try { sendJSON(res, 413, { ok: false, error: "request too large" }); } catch { /* res may be gone */ }
      try { req.destroy(); } catch { /* noop */ }
    }
  });
  req.on("end", () => {
    if (aborted) return;
    try {
      cb(JSON.parse(body || "{}"));
    } catch {
      cb({});
    }
  });
  req.on("error", () => {
    // A socket error after we already 413'd is expected (we destroyed it); only
    // surface an unexpected pre-abort error, and never double-respond.
    if (aborted) return;
    aborted = true;
    try { sendJSON(res, 400, { ok: false, error: "request stream error" }); } catch { /* noop */ }
  });
}

// Spawn the Python face brain, pipe the request in, read its one-line JSON out.
function faceReply(payload) {
  return new Promise((resolve) => {
    const script = path.join(__dirname, "face", "face_brain.py");
    let out = "";
    let err = "";
    let child;
    try {
      child = spawn(PY, [script], { cwd: ROOT, windowsHide: true });
    } catch {
      return resolve({ ok: false, reply: "(face offline — python not found)", escalate: false });
    }
    const timer = setTimeout(() => {
      try {
        child.kill();
      } catch {
        /* noop */
      }
    }, payload && payload.voice ? 16000 : 35000);
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", () => {
      clearTimeout(timer);
      resolve({ ok: false, reply: "(face offline — python not found)", escalate: false });
    });
    child.on("close", () => {
      clearTimeout(timer);
      const line = out.trim().split(/\r?\n/).filter(Boolean).pop() || "";
      try {
        resolve(JSON.parse(line));
      } catch {
        resolve({
          ok: false,
          reply: "(face hiccup — try again in a sec)",
          escalate: false,
          _raw: out.slice(0, 900),
          _err: err.slice(0, 900),
        });
      }
    });
    try {
      child.stdin.write(JSON.stringify(payload));
      child.stdin.end();
    } catch {
      /* noop */
    }
  });
}

// Deterministic build-intent safety net. /api/chat trusts the FREE face model's
// exact ```escalate fence to decide whether to start a real Claude session — but
// that model may chat instead, drop the fence, truncate, or rate-limit, silently
// degrading a build/do request to a chat reply with NO session. So we ALSO regex
// the raw message for an imperative build/do verb at a clause start; if it matches
// AND the face did NOT escalate, we FORCE one. Anchored at a clause start (^ or
// after a separator) so "what did you build" / "how do I fix" don't misfire.
const BUILD_INTENT_RE =
  /(^|[.;!?,]\s+|\b(?:please|hey gamma|gamma|can you|could you|go|now|then)[,:]?\s+)(build|create|add|fix|make|write|implement|change|update|refactor|run|test|check|analy[sz]e|research|improve|set up|wire|remove|delete|investigate|patch|backtest|port|debug|optimi[sz]e|ship|generate)\b/i;

function isBuildIntent(message) {
  try {
    return BUILD_INTENT_RE.test(String(message || ""));
  } catch {
    return false;
  }
}

// Mint a collision-resistant ask id. Date.now() alone (ms) collided when two
// escalations fired in the same millisecond -> logAsk / runEscalation / the SSE
// feed file / findAskResult all shared one id and cross-attributed transcripts.
// 4 bytes of crypto entropy makes a same-ms collision effectively impossible.
function mintAskId(prefix) {
  return (prefix || "ask") + "-" + Date.now().toString(36) + "-" + crypto.randomBytes(4).toString("hex");
}

function logAsk(rec) {
  try {
    fs.appendFileSync(STATE("companion-asks.jsonl"), JSON.stringify(rec) + "\n");
  } catch {
    /* best effort */
  }
}

// ── ONE shared conversation log across BOTH clients (typed chat + realtime voice) ──
//
// /api/chat is stateless: neither the typed path (m.html) nor the voice path
// (realtime.js ask_gamma) passes prior turns, so the face brain forgot context and
// — worse — voice had no idea what was typed (and vice versa). They are the SAME
// interface (J's phone); he switches between typing and talking mid-thought. This
// server-side log is the shared memory, so NEITHER client needs to pass history.
//
// One JSON line per turn: { ts, channel:'voice'|'text', role:'user'|'gamma', text }.
// text is sliced (~600 chars) so a long Claude paragraph can't bloat the file. We
// log only the conversational message text — NEVER any key/secret/state path, so
// the log can't become a secrets sink. Retention cap (OP-22): when the file grows
// past ~200 lines we rewrite keeping the last ~150. Both helpers are best-effort
// and NEVER throw (a logging error must never break a chat/voice turn).
const CONVO_LOG = STATE("companion-conversation.jsonl");
// "No limit to Gamma's memory" (J): keep effectively the entire conversation durably
// (thousands of turns ~= a few MB) and feed a GENEROUS recent window to the brain each
// turn, so a long back-and-forth never loses the thread. The full log is always on disk.
const CONVO_MAX_LINES = 8000; // soft cap: trigger the rewrite above this (~a few MB)
const CONVO_KEEP_LINES = 6000; // retain this many on rewrite (effectively unbounded for a human session)
const CONVO_CONTEXT_TURNS = 40; // how many recent turns the brain sees as working memory each turn

function appendConvo(entry) {
  try {
    if (!entry || !entry.text) return;
    const channel = entry.channel === "voice" ? "voice" : "text";
    const role = entry.role === "gamma" ? "gamma" : "user";
    const text = String(entry.text).slice(0, 600);
    const rec = { ts: new Date().toISOString(), channel, role, text };
    fs.appendFileSync(CONVO_LOG, JSON.stringify(rec) + "\n");
    // Retention: rewrite keeping the last CONVO_KEEP_LINES once we exceed the cap.
    let lines;
    try {
      lines = fs.readFileSync(CONVO_LOG, "utf8").split(/\r?\n/).filter(Boolean);
    } catch {
      return; // can't read back -> skip the trim, the append already landed
    }
    if (lines.length > CONVO_MAX_LINES) {
      const kept = lines.slice(-CONVO_KEEP_LINES).join("\n") + "\n";
      const tmp = CONVO_LOG + ".tmp." + process.pid;
      try {
        fs.writeFileSync(tmp, kept);
        fs.renameSync(tmp, CONVO_LOG);
      } catch {
        /* best effort -- a failed trim just leaves a slightly-long file */
      }
    }
  } catch {
    /* a conversation-log error must NEVER break a chat/voice turn */
  }
}

// Compact recent history for the face brain: the last n turns as
// "You: …\nGamma: …\n…". Returns "" when there's nothing logged yet.
function recentConvo(n) {
  const count = Number.isFinite(n) && n > 0 ? Math.floor(n) : 8;
  try {
    const lines = fs.readFileSync(CONVO_LOG, "utf8").split(/\r?\n/).filter(Boolean);
    const tail = lines.slice(-count);
    const parts = [];
    for (const line of tail) {
      try {
        const r = JSON.parse(line);
        if (!r || !r.text) continue;
        parts.push((r.role === "gamma" ? "Gamma: " : "You: ") + String(r.text));
      } catch {
        /* skip a torn line */
      }
    }
    return parts.join("\n");
  } catch {
    return "";
  }
}

// Load the HEAD of the one Gamma soul (identity + voice + limits) for the realtime
// voice preamble, so the spoken Gamma and the typed Gamma are the same character.
function loadVoiceHead(root) {
  try {
    const md = fs.readFileSync(path.join(root, "automation", "presence", "GAMMA-VOICE.md"), "utf8");
    const cut = md.indexOf("\n## The identity of a thing that builds itself");
    return (cut > 0 ? md.slice(0, cut) : md).trim();
  } catch {
    return "";
  }
}

function findAskResult(id) {
  try {
    const lines = fs.readFileSync(STATE("companion-ask-results.jsonl"), "utf8").trim().split(/\r?\n/);
    for (let i = lines.length - 1; i >= 0; i--) {
      if (!lines[i]) continue;
      const r = JSON.parse(lines[i]);
      if (r.id === id) return r;
    }
  } catch {
    /* none yet */
  }
  return null;
}

// The last `n` FINISHED escalations from the DURABLE record (companion-ask-results.jsonl)
// — so the office can show "what ran while you were away" even after the server
// restarted (getTasks() is in-memory and resets). Slim + de-duped by id, newest last.
function recentResults(n) {
  try {
    const lines = fs.readFileSync(STATE("companion-ask-results.jsonl"), "utf8").trim().split(/\r?\n/);
    const byId = {};
    for (const ln of lines) {
      if (!ln) continue;
      try {
        const r = JSON.parse(ln);
        if (r && r.id) byId[r.id] = r; // last line per id wins
      } catch {
        /* skip a torn line */
      }
    }
    return Object.keys(byId)
      .map((k) => byId[k])
      .sort((a, b) => String(a.finished || "").localeCompare(String(b.finished || "")))
      .slice(-(n > 0 ? n : 6))
      .map((r) => ({ id: r.id, task: String(r.task || "").slice(0, 160), ok: r.ok, finished: r.finished, summary: String(r.summary || "").slice(0, 160) }));
  } catch {
    return [];
  }
}

// The FULL companion state: buildState() PLUS the enrichment (obligation cards,
// build queue, what-Claude-is-doing). This used to be bolted only onto the
// /api/state HTTP response, so summarize() -- what the FACE reads -- never saw
// `build`/`claude`/`obligations` and couldn't answer "what's cooking / up next".
// Factor it here so BOTH /api/state and /api/chat feed the SAME enriched object.
// `pushObligations` defaults true (the /api/state poll fires the rising-edge wrist
// push); /api/chat passes false so a typed question never triggers a push.
// Obligations whose remedy is RE-RUNNING A PRODUCER (premarket / EOD / gym /
// scheduled-task audit). Their evidence files are NOT in guard.js DENY_WRITE, so
// completing a "run the producer + verify evidence is fresh" task genuinely
// clears the card. Everything else (heartbeat_alive / watchers_fresh -- the
// engine-health / live-trading class) stays DIAGNOSIS-ONLY: those touch the
// guard-denied doctrine/heartbeat surface, so the build reports, it never edits.
const PRODUCER_RERUN = {
  premarket:
    "Daily obligation 'premarket' is UNMET ({DETAIL}). RUN the premarket producer to regenerate today's bias+levels: " +
    "execute setup/scripts/run-premarket.ps1 (PowerShell 5.1, windows). Then VERIFY automation/state/today-bias.json now " +
    "has today's ET date in its `date` field (fresh). Do NOT place trades, do NOT edit params/heartbeat/CLAUDE.md. " +
    "Report whether the evidence file is now fresh.",
  eod_pipeline:
    "Daily obligation 'eod_pipeline' is UNMET ({DETAIL}). RUN the EOD pipeline producer that writes today's daily brief " +
    "(analysis/daily-brief/{date}.md) -- find the producer (the gamma/analyst EOD skill or its run-*.ps1 wrapper) and run it. " +
    "Then VERIFY analysis/daily-brief/<today>.md now exists and is fresh. Do NOT place trades, do NOT edit params/heartbeat/CLAUDE.md. " +
    "Report whether the evidence file is now fresh.",
  gym_green:
    "Daily obligation 'gym_green' is UNMET ({DETAIL}). RUN the chart-reading gym producer (the gym-session skill / its runner) " +
    "to regenerate automation/state/gym-scorecard-<today>.json. Then VERIFY today's scorecard exists, is fresh, and its verdict " +
    "is not RED. Do NOT place trades, do NOT edit params/heartbeat/CLAUDE.md. Report whether the evidence file is now fresh.",
  scheduled_tasks:
    "Daily obligation 'scheduled_tasks' is UNMET ({DETAIL}). RUN the scheduled-tasks audit producer that writes " +
    "automation/state/scheduled-tasks-audit.json (find its run-*.ps1 / skill), then VERIFY the audit is fresh and health is not RED " +
    "with flags_count 0. Do NOT place trades, do NOT edit params/heartbeat/CLAUDE.md. Report whether the evidence file is now fresh.",
};

// Live evidence signature for an "oblig-<id>" card: the obligation's CURRENT
// detail string (what fullState uses as the card detail). Used as the snooze
// evidence_sig so the snooze auto-invalidates the moment the evidence changes.
// Returns null for non-obligation ids or on any error.
function obligationDetailFor(cardId) {
  try {
    if (!/^oblig-/.test(String(cardId || ""))) return null;
    const obId = String(cardId).replace(/^oblig-/, "");
    const all = checkObligations(ROOT);
    const hit = (all || []).find((o) => o && o.id === obId);
    return hit ? hit.detail || "" : null;
  } catch {
    return null;
  }
}

function buildObligationAction(o) {
  const tmpl = PRODUCER_RERUN[o.id];
  const task = tmpl
    ? tmpl.replace("{DETAIL}", String(o.detail || "").slice(0, 240))
    : // DIAGNOSIS-ONLY for engine-health / live-trading-class obligations (guard
      // forbids touching the heartbeat/params surface). Report, never auto-edit.
      "Daily obligation '" + o.id + "' (" + o.label + ") is UNMET: " + o.detail +
        ". Diagnose which scheduled task/producer stopped writing its evidence file " +
        "(see automation/state/obligations.json -> expect_evidence) and propose or apply " +
        "a SAFE fix. Do NOT place trades or edit live params/heartbeat. Report findings.";
  return { type: "escalate", model: "sonnet", task };
}

// Pending conductor proposals — the doctrine/strategy changes Gamma has DRAFTED
// autonomously and is waiting on J to ratify/revoke (the "your call" lane). The
// log is append-only, so de-dup by proposal_id (last line wins) before filtering to
// pending. Read-only surfacing in the queue fly-out. Best-effort; never throws.
function readPendingProposals(root) {
  try {
    const raw = fs.readFileSync(path.join(root, "automation", "state", "conductor-proposals.jsonl"), "utf8").trim();
    if (!raw) return [];
    const byId = {};
    for (const line of raw.split(/\r?\n/)) {
      if (!line.trim()) continue;
      try {
        const d = JSON.parse(line);
        const key = d && (d.proposal_id || d.title);
        if (key) byId[key] = d;
      } catch {
        /* skip a torn line */
      }
    }
    return Object.keys(byId)
      .map((k) => byId[k])
      .filter((d) => d && (d.status || "pending") === "pending" && d.title)
      .map((d) => ({ id: d.proposal_id || null, title: String(d.title).slice(0, 140), kind: d.kind || null }))
      .slice(0, 8);
  } catch {
    return [];
  }
}

function fullState(opts) {
  const pushObligations = !opts || opts.pushObligations !== false;
  const state = buildState(ROOT);
  const allObligations = checkObligations(ROOT);
  // Suppress the synthetic "registry" card ONLY on a fresh install (obligations.json
  // truly absent) — there it was a scary, unactionable, escalate-on-Approve card. A
  // present-but-MALFORMED registry must STILL surface (info-severity, non-escalating)
  // so a torn registry is never silently hidden (the fail-green trap to avoid).
  const registryFileExists = fs.existsSync(path.join(ROOT, "automation", "state", "obligations.json"));
  const obCardsAll = allObligations
    .filter((o) => !o.ok && (o.id !== "registry" || registryFileExists))
    .map((o) => ({
      id: "oblig-" + o.id,
      severity: o.id === "registry" ? "info" : o.severity === "critical" || o.severity === "high" ? "warn" : "info",
      title: "Obligation unmet: " + o.label,
      detail: o.detail,
      source: "obligations",
      action: o.id === "registry" ? null : buildObligationAction(o),
    }));
  // Suppress cards the user already tapped (snoozed) WHILE the snooze is unexpired
  // AND the evidence signature (the card detail) is unchanged. A snooze that has
  // lapsed, or a card whose evidence genuinely changed, re-surfaces -- we NEVER
  // permanently hide a real red. The evidence_sig is the card's detail.
  const obCards = obCardsAll.filter((c) => !isCardSnoozed(ROOT, c.id, c.detail));
  // The act-* derived cards (engine-RED / kitchen-failed) live INSIDE state.approvals
  // and are ALSO synthetic + regenerated every poll — so they need the SAME snooze
  // filter, or a tapped act-* card re-surfaces on the next poll and a re-tap fires a
  // duplicate escalation. Real queued cards (no synthetic id) are never snoozed here.
  const surfacedApprovals = state.approvals.filter(
    (c) => !(c && /^(oblig|act)-/.test(String(c.id || "")) && isCardSnoozed(ROOT, c.id, c.detail))
  );
  state.approvals = [...obCards, ...surfacedApprovals];
  state.obligations = allObligations;
  // Rising-edge wrist push for newly-red obligations (rate-limited per id). Only
  // for the cards we're actually surfacing -- a snoozed card must not re-ping.
  if (pushObligations) pushRisingObligations(obCards);
  const queue = readQueue(ROOT);
  state.build = {
    summary: queueSummary(ROOT),
    next: queue.find((t) => (t.status || "pending") === "pending") || null,
    queue: queue.map((t) => ({ id: t.id, title: t.title, tier: t.tier, status: t.status || "pending" })),
  };
  // Live view of what Claude is doing right now (+ recent) so Gamma + J can
  // SEE and CONTROL the escalations.
  state.claude = getTasks();
  // The decisions Gamma has teed up and is WAITING ON J for (conductor proposals).
  state.proposals = readPendingProposals(ROOT);
  return state;
}

const server = http.createServer((req, res) => {
  const u = req.url.split("?")[0];

  if (req.method === "GET" && u === "/api/state") {
    if (!authed(req)) return sendJSON(res, 403, { ok: false, error: "unauthorized" });
    try {
      const state = fullState();
      return sendJSON(res, 200, { ok: true, voice: !!loadOpenAIKey(ROOT), ...state });
    } catch (e) {
      return sendJSON(res, 500, { ok: false, error: String((e && e.message) || e) });
    }
  }

  if (req.method === "GET" && u === "/api/ask-result") {
    if (!authed(req)) return sendJSON(res, 403, { ok: false, error: "unauthorized" });
    const m = /[?&]id=([^&]+)/.exec(req.url);
    const id = m ? decodeURIComponent(m[1]) : "";
    const r = id && findAskResult(id);
    return sendJSON(res, 200, r ? { ok: true, done: true, result: r } : { ok: true, done: false });
  }

  // Lightweight roster of Claude sessions (running + recent) for the desktop "office"
  // pixel view — just getTasks(), NOT the heavy fullState(), so the office can poll
  // it ~1s for smooth per-session activity. Authed by the page token (a normal fetch).
  if (req.method === "GET" && u === "/api/claude") {
    if (!authed(req)) return sendJSON(res, 403, { ok: false, error: "unauthorized" });
    return sendJSON(res, 200, { ok: true, claude: getTasks(), done: recentResults(6) });
  }

  // ── Live transcript stream (Server-Sent Events) ──
  //
  // GET /api/ask-stream?id=<askId>&tok=<streamToken>
  //   text/event-stream of the build's humanized steps so J can WATCH Claude work.
  //
  // AUTH: EventSource cannot send the x-gamma-token header, so this route is
  // gated by a short-lived HMAC stream token (push.mintStreamToken, minted per
  // ask when /api/chat /api/approve /api/diagram create it). Domain-separated
  // from the approve tokens (a "stream|" payload prefix) so it can NEVER be
  // replayed as an approve/reject. The stream is READ-ONLY telemetry -- it
  // replays a build's step feed and grants no write/approve/escalate power.
  // 403 on a bad/expired/missing token. We still enforce the origin allowlist.
  if (req.method === "GET" && u === "/api/ask-stream") {
    if (!originAllowed(req.headers["origin"])) {
      res.writeHead(403, { "content-type": "text/plain" });
      return res.end("forbidden");
    }
    const mi = /[?&]id=([^&]+)/.exec(req.url);
    const mt = /[?&]tok=([^&]+)/.exec(req.url);
    const id = mi ? decodeURIComponent(mi[1]) : "";
    const tok = mt ? decodeURIComponent(mt[1]) : "";
    const v = push.verifyStreamToken(ROOT, tok);
    if (!id || !v.ok || v.id !== id) {
      res.writeHead(403, { "content-type": "text/plain", "cache-control": "no-store" });
      return res.end("forbidden");
    }
    res.writeHead(200, {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-store",
      connection: "keep-alive",
      "x-accel-buffering": "no",
    });
    // SUBSCRIBE-GAP RACE FIX: subscribe to live frames FIRST, then read+replay the
    // durable feed. The old order (read THEN subscribe) lost any emit() — including
    // the terminal `result` of a fast build — that fired in the gap, stranding the
    // phone on "On it…" forever (no EventSource error -> no poll fallback). With
    // subscribe-first, no live step is lost; we de-dup the replay so a frame that
    // arrives both live and in the feed is written only once.
    const seen = new Set();
    let hbTimer = null;
    const done = () => {
      try { unsubscribeAskStream(id, res); } catch { /* noop */ }
      if (hbTimer) { try { clearInterval(hbTimer); } catch { /* noop */ } hbTimer = null; }
    };
    // 1) Subscribe BEFORE replay so nothing emitted in the gap is lost.
    subscribeAskStream(id, res);
    // 2) Replay the durable feed for catch-up (reconnect / late join), de-duped.
    try {
      const raw = fs.readFileSync(askFeedPath(ROOT, id), "utf8").trim();
      if (raw) {
        for (const line of raw.split(/\r?\n/)) {
          if (line && !seen.has(line)) {
            seen.add(line);
            try { res.write("data: " + line + "\n\n"); } catch { /* dead socket */ }
          }
        }
      }
    } catch {
      /* no feed yet -> live frames will arrive once the build starts */
    }
    // 3) If the build is ALREADY terminal at connect time (post-completion connect),
    // the feed already holds its result frame OR the in-memory task is terminal but
    // the feed is gone/pruned. Either way, synthesize a final `result` frame so the
    // client always settles instead of hanging. Cheap + idempotent (client de-dups
    // on the durable record anyway).
    try {
      const st = getTaskStatus(id);
      if (st && st.terminal) {
        const fin = JSON.stringify({
          step: "result",
          ok: !!st.ok,
          subtype: st.ok ? "success" : (st.status || "ended"),
          summary: st.ok ? "Done" : "(" + (st.status || "ended") + ")",
          synthetic: true,
        });
        try { res.write("data: " + fin + "\n\n"); } catch { /* dead socket */ }
      }
    } catch {
      /* status lookup is best-effort */
    }
    // 4) SSE heartbeat: a comment frame every ~15s keeps idle Tailscale/proxy hops
    // from dropping a long build. A cleanly-dropped socket fires req "close" -> done().
    // A throwing write reaps a hard-destroyed socket. But a HALF-OPEN stalled client
    // (backgrounded PWA that never FIN'd) does NOT throw — res.write() just returns
    // false and buffers forever. So we ALSO watch backpressure: if the send buffer
    // never drains across ~4 consecutive beats (~60s), the peer is gone -> destroy +
    // reap, which prevents a leaked subscriber + a forever-firing timer.
    let stalledBeats = 0;
    hbTimer = setInterval(() => {
      let wrote;
      try {
        wrote = res.write(": ping\n\n");
      } catch {
        return done(); // hard-destroyed socket
      }
      if (wrote) {
        stalledBeats = 0;
      } else if (++stalledBeats >= 4) {
        try { res.destroy(); } catch { /* noop */ }
        return done(); // half-open: buffer never drained for ~60s
      }
    }, 15000);
    req.on("close", done);
    req.on("end", done);
    res.on("error", done);
    return;
  }

  if (req.method === "POST" && u === "/api/chat") {
    if (!authed(req)) return sendJSON(res, 403, { ok: false, error: "unauthorized" });
    return readBody(req, res, (b) => {
      const message = String(b.message || "").slice(0, 4000);
      const history = String(b.history || "").slice(0, 4000);
      if (!message.trim()) return sendJSON(res, 400, { ok: false, error: "empty message" });

      // FAST PATH: a clear imperative build/do request escalates IMMEDIATELY, skipping
      // the ~7s free-face round-trip — so the worker walks into the office in ~1s, not
      // 7s ("I sent a task and no agent appeared"). The face would only escalate this
      // anyway (via the safety net), so we go straight to Claude.
      if (isBuildIntent(message)) {
        const askId = mintAskId("ask");
        const task = "J asked via the Gamma companion: " + message;
        logAsk({ id: askId, model: "sonnet", task, ts: new Date().toISOString(), forced: true, fast: true });
        runEscalation(ROOT, { id: askId, model: "sonnet", task, origin: "chat" }).catch((e) => logCrash("runEscalation", e));
        // Shared conversation log: record the user turn + the short ack so the OTHER
        // client (voice<->text) sees this exchange on its next recentConvo() read.
        const fastReply = "On it 🧠 — starting that now.";
        appendConvo({ channel: b.voice ? "voice" : "text", role: "user", text: message });
        appendConvo({ channel: b.voice ? "voice" : "text", role: "gamma", text: fastReply });
        return sendJSON(res, 200, {
          ok: true, reply: fastReply, escalate: true,
          model: "sonnet", ask_id: askId, stream_token: push.mintStreamToken(ROOT, askId), source_model: null,
        });
      }

      let summary = "(state unavailable)";
      try {
        // fullState() (not bare buildState) so the FACE sees build/claude/obligations
        // and can answer "what's cooking / up next". pushObligations:false -- a typed
        // question must never trigger a wrist push.
        summary = summarize(fullState({ pushObligations: false }));
      } catch {
        /* keep fallback */
      }
      // Use the SHARED server-side conversation log as history (the last 8 turns),
      // NOT the client-supplied `history` -- so the face brain sees what the OTHER
      // client (voice<->text) just said, and neither client has to pass it.
      faceReply({ message, history: recentConvo(CONVO_CONTEXT_TURNS), state: summary, voice: !!b.voice }).then((face) => {
        let askId = null;
        let streamToken = null;
        let reply = (face && face.reply) || "(no reply)";
        const faceEscalated = !!(face && face.escalate && String(face.task || "").trim().length > 3);
        if (faceEscalated) {
          askId = mintAskId("ask");
          logAsk({ id: askId, model: face.model, task: face.task, ts: new Date().toISOString() });
          runEscalation(ROOT, { id: askId, model: face.model, task: face.task, origin: "chat" }).catch((e) => logCrash("runEscalation", e));
          streamToken = push.mintStreamToken(ROOT, askId);
        } else if (isBuildIntent(message)) {
          // Safety net: the message is an imperative build/do request but the face
          // didn't escalate (chatted / dropped the fence / truncated / rate-limited).
          // FORCE one real session so a do-request never silently degrades to chat.
          // Never double-fires — this branch only runs when the face did NOT escalate.
          askId = mintAskId("ask");
          const forcedTask = "J asked via the Gamma companion: " + message;
          logAsk({ id: askId, model: "sonnet", task: forcedTask, ts: new Date().toISOString(), forced: true });
          runEscalation(ROOT, { id: askId, model: "sonnet", task: forcedTask, origin: "chat" }).catch((e) => logCrash("runEscalation", e));
          streamToken = push.mintStreamToken(ROOT, askId);
        } else if (!face || face.ok === false || /^\s*\(\s*(face|all free|no reply)/i.test(reply)) {
          // HICCUP FALLBACK: the free face CHOKED (rate-limited / offline / all 3
          // models down) on a plain question. Never dead-end J with "(face hiccup —
          // try again)" — escalate to Claude so the question ALWAYS gets a real
          // answer. It lands in the feed via the stream; J sees a clean "On it" first.
          askId = mintAskId("ask");
          const fbTask =
            "J asked this via the Gamma companion: " + message +
            "\n\nAnswer it directly and concisely as Gamma (warm, sharp, a fitting emoji). This is a conversational question, NOT a build task — just answer it from what you know about this repo/system; do not edit files unless explicitly asked.";
          logAsk({ id: askId, model: "sonnet", task: fbTask, ts: new Date().toISOString(), fallback: true });
          runEscalation(ROOT, { id: askId, model: "sonnet", task: fbTask, origin: "chat" }).catch((e) => logCrash("runEscalation", e));
          streamToken = push.mintStreamToken(ROOT, askId);
        }
        // When we ESCALATE (either the face emitted a fence OR the safety net forced
        // it), the spoken/returned reply must be a CLEAN acknowledgement. Small fast/
        // voice models sometimes leak their reasoning ("We need to respond as Gamma…")
        // or a "(face hiccup…)" fallback as the pre-fence text — which the VOICE would
        // read aloud. Keep a face preamble only if it's short + clean; else use a
        // deterministic on-brand line. (Non-escalating Tier-1 replies pass through.)
        if (askId) {
          const leaky = /\b(we need to|the user (asks|wants|said|is)|i should|let me (think|see)|as gamma,|i'?ll respond|here'?s (what|my)|the request|reasoning)\b/i;
          const clean = !!reply && reply.length <= 140 && !leaky.test(reply) && !/[`{}]|\(\s*(face|no reply)/i.test(reply);
          if (!clean) reply = "On it 🧠 — handing this to Claude now. The result lands in the feed.";
        }
        // Shared conversation log: record this user turn + Gamma's (final) reply so
        // the OTHER client sees the exchange on its next recentConvo() read. Logged
        // AFTER the clean-ack rewrite so we store exactly what J was shown/told.
        appendConvo({ channel: b.voice ? "voice" : "text", role: "user", text: message });
        appendConvo({ channel: b.voice ? "voice" : "text", role: "gamma", text: reply });
        sendJSON(res, 200, {
          // A forced session IS a success even if the free face model hiccuped —
          // the request did start a real Claude session, so don't report ok:false.
          ok: !!askId || !!(face && face.ok !== false),
          reply,
          escalate: !!askId,
          model: (face && face.model) || (askId ? "sonnet" : null),
          ask_id: askId,
          stream_token: streamToken,
          source_model: (face && face.source_model) || null,
        });
      });
    });
  }

  if (req.method === "POST" && u === "/api/approve") {
    if (!authed(req)) return sendJSON(res, 403, { ok: false, error: "unauthorized" });
    return readBody(req, res, (b) => {
      const { id, decision, note, action } = b;
      if (!id || (decision !== "approve" && decision !== "reject")) {
        return sendJSON(res, 400, { ok: false, error: "need id and decision approve|reject" });
      }
      // Validate + clamp the action shape before it can reach the escalation
      // (rank 20): a non-string / empty task is dropped; model is clamped to the
      // known set; the task is length-capped. An invalid action just means "no
      // escalate", the decision still logs.
      let act = null;
      if (decision === "approve" && action && action.type === "escalate") {
        const t = typeof action.task === "string" ? action.task.trim() : "";
        if (t.length > 3) {
          const m = ["opus", "sonnet", "haiku"].indexOf(String(action.model || "")) >= 0 ? action.model : "sonnet";
          act = { type: "escalate", model: m, task: t.slice(0, 8000) };
        }
      }
      const willEscalate = !!act;

      // Evidence signature for the snooze: prefer the LIVE obligation detail
      // (authoritative, never a stale client value); fall back to the detail the
      // client posted. resolveApproval snoozes synthetic cards by this sig so the
      // tapped card stays cleared until the snooze lapses OR the evidence changes.
      const evidenceSig = obligationDetailFor(id) || (b && b.detail) || null;
      // Resolve FIRST so the idempotency guard (already:true) tells us whether
      // THIS request actually won the decision. skipLongSnooze: when this approve
      // launches an escalation, only a SHORT grace snooze is written here — the
      // escalation completion then snoozes long ONLY if the obligation cleared
      // (fail-green: a failed rerun re-surfaces the card instead of hiding it).
      const r = resolveApproval(ROOT, id, decision, note, evidenceSig, { skipLongSnooze: willEscalate });

      let escalated = null;
      let streamToken = null;
      // Only fire the escalation if THIS request actually resolved the card
      // (not a duplicate double-tap) — prevents two concurrent sessions for one tap.
      if (act && !r.already) {
        escalated = mintAskId("ask");
        logAsk({
          id: escalated,
          model: act.model,
          task: act.task,
          ts: new Date().toISOString(),
          from_card: id,
        });
        // Pass the originating card id through so escalate.js can record whether
        // the build actually cleared the obligation (card↔ask↔resolution linkage).
        runEscalation(ROOT, { id: escalated, model: act.model, task: act.task, origin: "card", card_id: id }).catch((e) => logCrash("runEscalation", e));
        streamToken = push.mintStreamToken(ROOT, escalated);
      }
      return sendJSON(res, 200, { ok: true, ...r, escalated, stream_token: streamToken });
    });
  }

  // Cancel a running Claude escalation by id (Gamma's control over Claude).
  if (req.method === "POST" && u === "/api/cancel-task") {
    if (!authed(req)) return sendJSON(res, 403, { ok: false, error: "unauthorized" });
    return readBody(req, res, (b) => {
      if (!b || !b.id) return sendJSON(res, 400, { ok: false, error: "need a task id" });
      return sendJSON(res, 200, cancelTask(String(b.id)));
    });
  }

  if (req.method === "POST" && u === "/api/diagram") {
    if (!authed(req)) return sendJSON(res, 403, { ok: false, error: "unauthorized" });
    return readBody(req, res, (b) => {
      const topic = String(b.topic || "how the whole Gamma system works").slice(0, 600);
      const id = mintAskId("dgm");
      const task =
        "Produce ONE technical diagram as a single self-contained SVG that clearly explains: " +
        topic +
        ". Read whatever project files you need to be accurate. Output ONLY a fenced ```svg ... ``` block and NOTHING else. " +
        'Requirements: <svg viewBox="0 0 900 560">; dark-friendly colors (accent #34e0a1, node fills #16223a with #2b3b5c strokes, text #e7eefc at 13-16px, arrows #5b6b8c); clear labeled boxes and arrows; on each major node element add a data-q attribute whose value is a short natural follow-up question about that node; NO <script>, NO <foreignObject>, NO external href/url() references; keep it under ~40 nodes.';
      logAsk({ id, model: "sonnet", task, ts: new Date().toISOString(), kind: "diagram" });
      runEscalation(ROOT, { id, model: "sonnet", task, origin: "diagram" }).catch((e) => logCrash("runEscalation", e));
      return sendJSON(res, 200, { ok: true, ask_id: id, stream_token: push.mintStreamToken(ROOT, id) });
    });
  }

  if (req.method === "GET" && u === "/api/realtime-token") {
    if (!authed(req)) return sendJSON(res, 403, { ok: false, error: "unauthorized" });
    const key = loadOpenAIKey(ROOT);
    if (!key) {
      return sendJSON(res, 400, {
        ok: false,
        error: "No OpenAI key yet. Paste your key (starts with sk-) into automation/state/.openai.key, then tap the mic again.",
      });
    }
    const sessionConfig = {
      session: {
        type: "realtime",
        model: "gpt-realtime-2",
        instructions:
          (loadVoiceHead(ROOT) ? loadVoiceHead(ROOT) + "\n\n---\n\n" : "") +
          "You are SPEAKING OUT LOUD. For ANY request about the system, live data, status, analysis, coding, or real work, call the ask_gamma tool and speak its answer concisely and naturally in your own warm voice. Never invent trading numbers. If a tool call takes a moment, say a short 'one sec' ONCE then wait silently -- NEVER repeat phrases like 'that request is still running'. If the answer says Claude is working on something, say it once and offer to tell J when it's done. After answering, offer one useful next step. The typed chat and this voice share ONE memory and brain -- when J references something he 'just asked' or 'typed', call ask_gamma (it sees the shared conversation history) instead of assuming you didn't catch it.",
        audio: { input: { turn_detection: { type: "semantic_vad" } }, output: { voice: "marin" } },
        tools: [
          {
            type: "function",
            name: "ask_gamma",
            description:
              "Ask Gamma's brain anything about the trading system, or give it a task. Returns Gamma's answer. Use for status, live data, analysis, coding, or any real work.",
            parameters: {
              type: "object",
              properties: {
                request: { type: "string", description: "J's question or task, in plain language." },
              },
              required: ["request"],
            },
          },
        ],
      },
    };
    (async () => {
      try {
        const r = await fetch("https://api.openai.com/v1/realtime/client_secrets", {
          method: "POST",
          headers: { Authorization: "Bearer " + key, "Content-Type": "application/json" },
          body: JSON.stringify(sessionConfig),
        });
        const data = await r.json();
        if (!r.ok) {
          return sendJSON(res, 502, {
            ok: false,
            error: (data && data.error && data.error.message) || "OpenAI token request failed",
          });
        }
        return sendJSON(res, 200, data);
      } catch (e) {
        return sendJSON(res, 502, { ok: false, error: String((e && e.message) || e) });
      }
    })();
    return;
  }

  // ── Web Push: subscribe (authed -- the page carries the token) ──
  if (req.method === "POST" && u === "/api/push/subscribe") {
    if (!authed(req)) return sendJSON(res, 403, { ok: false, error: "unauthorized" });
    return readBody(req, res, (b) => {
      const sub = b && b.subscription ? b.subscription : b;
      const saved = push.saveSub(ROOT, sub);
      if (!saved) return sendJSON(res, 400, { ok: false, error: "need { endpoint, keys:{p256dh,auth} }" });
      return sendJSON(res, 200, { ok: true, subscribed: true });
    });
  }

  // ── Web Push: VAPID public key for pushManager.subscribe (authed) ──
  if (req.method === "GET" && u === "/api/push/vapid-public") {
    if (!authed(req)) return sendJSON(res, 403, { ok: false, error: "unauthorized" });
    const vapid = push.loadVapid(ROOT);
    if (!vapid || !vapid.publicKey) {
      return sendJSON(res, 200, { ok: true, enabled: false, publicKey: null });
    }
    return sendJSON(res, 200, { ok: true, enabled: true, publicKey: vapid.publicKey });
  }

  // ── Wrist-tap approve (the ONE deliberately-unauthenticated route) ──
  //
  // A service-worker notificationclick fetch runs in SW global scope and CANNOT
  // carry the page's x-gamma-token, so this route does NOT call authed(). It is
  // safe ONLY because the token is HMAC-signed (unforgeable), single-use, and
  // ~15-min expiring -- a captured URL can at worst approve/reject ONE existing
  // queue id ONCE. It calls resolveApproval (plain fs, NOT an SDK tool, so the
  // guard is irrelevant to it) and NOTHING ELSE.
  //
  // SECURITY INVARIANT (smoke-guard-style assertion): this route MUST NEVER
  // import or call runEscalation, and MUST refuse any action/escalate payload.
  // Reaching the guard's escalate path from here would reopen the exact hole
  // guard.js exists to close. It takes NO body and ignores all query params but
  // `tok`. Do not add escalate handling here. Ever.
  if (req.method === "GET" && u === "/api/approve-signed") {
    const m = /[?&]tok=([^&]+)/.exec(req.url);
    const tok = m ? decodeURIComponent(m[1]) : "";
    const v = push.verifyApproveToken(ROOT, tok);
    if (!v.ok) {
      res.writeHead(403, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
      return res.end("<!doctype html><meta name=viewport content='width=device-width'><body style='font-family:system-ui;background:#0b1120;color:#e7eefc;display:grid;place-items:center;height:90vh;margin:0'><p>Link expired or already used. Open the app to decide.</p></body>");
    }
    // resolveApproval ONLY. No runEscalation, no action payload, no escalate path.
    // Pass the live obligation detail (if this is a synthetic card) so the snooze
    // is keyed to current evidence -- a captured link still only snoozes ONE card.
    const r = resolveApproval(ROOT, v.id, v.decision, null, obligationDetailFor(v.id));
    res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
    return res.end(
      "<!doctype html><meta name=viewport content='width=device-width'><body style='font-family:system-ui;background:#0b1120;color:#34e0a1;display:grid;place-items:center;height:90vh;margin:0;text-align:center'><div><h2 style='margin:0 0 6px'>" +
        (v.decision === "approve" ? "Approved" : "Rejected") +
        "</h2><p style='color:#9aa6bd'>Logged — you can close this.</p></div></body>"
    );
  }

  if (req.method === "GET") return serveStatic(req, res);
  res.writeHead(405);
  res.end("method not allowed");
});

server.on("error", (err) => {
  if (err && err.code === "EADDRINUSE") {
    process.stdout.write(`[gamma-companion] port ${PORT} already in use — reusing the running server\n`);
  } else {
    process.stdout.write(`[gamma-companion] server error: ${(err && err.message) || err}\n`);
  }
});

server.listen(PORT, "127.0.0.1", () => {
  process.stdout.write(`[gamma-companion] reading state from ${ROOT}\n`);
  process.stdout.write(`[gamma-companion] open http://localhost:${PORT}\n`);
  // Pre-warm the Python face so the first real chat answers instantly.
  try { faceReply({ message: "ping", history: "", state: "warmup", voice: true }); } catch {}
});
