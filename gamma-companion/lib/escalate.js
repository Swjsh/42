"use strict";

// Escalation runner -- the ONE chokepoint where Gamma drives Claude.
// Every escalation runs through guard.js#canUseTool: full power EXCEPT the hard
// denylist (doctrine/params/keys writes + live order tools) and the halt flag.
// We do NOT use bypassPermissions -- canUseTool is the permission handler, so the
// denylist holds. cwd = repo root, so Claude can edit the companion app, use the
// project's MCP servers (TradingView, etc.), run backtests, and build features.
//
// VISIBILITY + CONTROL: every escalation is tracked in a live registry (`tasks`)
// so Gamma + J can SEE what Claude is doing right now (getTasks) and CANCEL a
// running one (cancelTask, via the per-task AbortController). The durable result
// still lands in companion-ask-results.jsonl + the activity spine.

const fs = require("fs");
const path = require("path");
const { makeCanUseTool, isHalted } = require("./guard");
const { logActivity } = require("./activity");
const push = require("./push");

// ── Live transcript registry ────────────────────────────────────────────────
// Per-ask step stream so J can WATCH Claude work in real time. Each step is
// (a) appended durably to companion-ask-feed/<id>.jsonl (replayable for a
// late-joining / reconnecting SSE client) AND (b) pushed to every SSE response
// currently subscribed to <id>. The feed is the source of truth; the in-memory
// registry is a best-effort live fan-out. NEVER throws -- a telemetry write must
// never break the escalation itself.
const subscribers = new Map(); // id -> Set<res>

function askFeedDir(root) {
  return path.join(root, "automation", "state", "companion-ask-feed");
}
function askFeedPath(root, id) {
  return path.join(askFeedDir(root), String(id).replace(/[^a-zA-Z0-9._-]/g, "_") + ".jsonl");
}

// OP-22 hygiene: the per-ask feed files (companion-ask-feed/<id>.jsonl) are
// appended once per build and NOTHING ever deleted them, so the dir leaked disk
// forever. Best-effort prune: keep the ~50 most-recently-modified files, drop the
// rest. Called after each escalation finishes. Never throws (telemetry hygiene
// must never break the result write).
function pruneFeedDir(root, keep) {
  try {
    const dir = askFeedDir(root);
    const names = fs.readdirSync(dir).filter((n) => n.endsWith(".jsonl"));
    if (names.length <= keep) return;
    const stamped = names
      .map((n) => {
        const fp = path.join(dir, n);
        try { return { fp, mtime: fs.statSync(fp).mtimeMs }; } catch { return { fp, mtime: 0 }; }
      })
      .sort((a, b) => b.mtime - a.mtime);
    for (const f of stamped.slice(keep)) {
      try { fs.unlinkSync(f.fp); } catch { /* best-effort */ }
    }
  } catch {
    /* prune is best-effort */
  }
}

// Subscribe an SSE response to live steps for <id>. server.js calls this AFTER
// it has replayed the durable feed, so no live step is lost in the gap.
function subscribeAskStream(id, res) {
  if (!id || !res) return;
  let set = subscribers.get(id);
  if (!set) { set = new Set(); subscribers.set(id, set); }
  set.add(res);
}
function unsubscribeAskStream(id, res) {
  const set = subscribers.get(id);
  if (!set) return;
  set.delete(res);
  if (!set.size) subscribers.delete(id);
}

// Append one step to the durable feed AND push it to live subscribers. The `rec`
// is a plain step object ({ step, ... }); we stamp an ISO `t` on it. Best-effort
// on every path -- a broken pipe to one SSE client must not abort the loop.
function emit(root, id, rec) {
  try {
    const line = JSON.stringify(Object.assign({ t: new Date().toISOString() }, rec));
    try {
      fs.mkdirSync(askFeedDir(root), { recursive: true });
      fs.appendFileSync(askFeedPath(root, id), line + "\n");
    } catch {
      /* durable write best-effort */
    }
    // Stamp the CURRENT activity on the task so the desktop "office" (one pixel
    // character per session) can animate it from a single authed /api/claude poll.
    // Only the animation-relevant steps, not every text delta.
    if (rec && /^(queued|session|thinking|tool_start|tool|tool_result|result)$/.test(rec.step)) {
      try {
        const t = tasks.get(id);
        if (t) { t.lastStep = rec.step; t.lastTool = rec.name || rec.label || null; }
      } catch { /* noop */ }
    }
    const set = subscribers.get(id);
    if (set && set.size) {
      const frame = "data: " + line + "\n\n";
      for (const res of [...set]) {
        try {
          res.write(frame);
        } catch {
          // dead socket -> drop it so we don't leak the res object
          try { set.delete(res); } catch { /* noop */ }
        }
      }
    }
  } catch {
    /* emit can never throw */
  }
}

// Map a tool call into J's language: "Reading X" / "Editing Y" / "Ran: cmd" /
// "Searching: pat" / "Using <tool>". mcp__* collapses to the bare tool name.
function basename(p) {
  const s = String(p || "");
  const parts = s.split(/[\\/]/);
  return parts[parts.length - 1] || s;
}
function humanize(name, input) {
  try {
    const n = String(name || "tool");
    const inp = input && typeof input === "object" ? input : {};
    if (n === "Read") return "Reading " + basename(inp.file_path || inp.path || inp.notebook_path);
    if (n === "Edit" || n === "Write" || n === "MultiEdit" || n === "NotebookEdit")
      return "Editing " + basename(inp.file_path || inp.path || inp.notebook_path);
    if (n === "Bash" || n === "bash") return "Ran: " + String(inp.command || "").replace(/\s+/g, " ").trim().slice(0, 80);
    if (n === "Grep") return "Searching: " + String(inp.pattern || "").slice(0, 60);
    if (n === "Glob") return "Finding " + String(inp.pattern || "").slice(0, 60);
    if (/^mcp__/.test(n)) return "Using " + n.replace(/^mcp__/, "").replace(/__/g, " ");
    return "Using " + n;
  } catch {
    return "Using " + String(name || "tool");
  }
}

const MODEL_MAP = {
  opus: "claude-opus-4-8",
  sonnet: "claude-sonnet-4-6",
  haiku: "claude-haiku-4-5",
};

// ── The Gamma soul, injected as the SYSTEM prompt (not incidental context) ──
// Appended to the claude_code preset so the escalation IS the Claude Code agent
// AND knows it is Gamma, bound by the 10 rules + the hard guard (lib/guard.js).
// Paired with settingSources:['user','project'] below so CLAUDE.md (the full
// soul) loads deterministically from cwd=repo root regardless of SDK defaults.
const SOUL =
  "You are Gamma, J's autonomous 0DTE SPY research+build agent. CLAUDE.md in the repo root is your soul — obey it, especially the 10 rules and the Operating Principles. Repo note: human docs live under markdown/ (per CLAUDE.md's filing rule) and markdown/specs/ARCHITECTURE.md is the current cold-start 'how it's wired today' snapshot (it states its own last-refreshed date) — and you ALWAYS read LIVE files via your tools, so you are on the CURRENT repo tree; never assume a stale layout, and if a doc's currency matters, open it and check its stated date. " +
  "WHERE TO WRITE (one cohesive Gamma — every face/worker uses the SAME places): human docs → under markdown/ in the matching subfolder (never the repo root, never a code dir); runtime state + logs → automation/state/ and automation/state/logs/; the shared activity ledger → automation/state/gamma-activity.jsonl; the shared voice/chat conversation log → automation/state/companion-conversation.jsonl. " +
  "You run inside a hard guard (lib/guard.js): you may build/edit code, run backtests, and use the project MCP servers, but you must NEVER write CLAUDE.md / params*.json / heartbeat*.md / filters.py / *.key and NEVER place, cancel, or close live orders — propose those as TEXT instead. Act autonomously within that boundary, verify your own work, and never claim unverified work is done. " +
  "When you REPORT BACK, keep it in Gamma's voice — warm, sharp, brief — and terse + scannable on J's phone: LEAD WITH THE RESULT (no preamble, no filler), then markdown the phone renders — **bold** a short mini-header, '- ' bullets for what changed, and `inline code` (backticks) for paths / values / commands. Default to a few tight bullets, not a wall of text. You can drop ONE fitting emoji where it lands (✅ shipped, 🔧 built/fixed, 📈 a market read, ⚡ fast) — but keep the work itself precise, never let flavor blur a fact, and stay clean (no emoji) on anything about a loss, a risk, or a refusal.";

// Hard wall-clock cap for one escalation. A query() that hangs without throwing
// or yielding a `result` (e.g. a network stall to Anthropic) would otherwise pin
// the inflight slot forever; this fires ac.abort() so it always lands on the
// catch/abort path -> result record + terminal frame + freed slot.
const ESCALATION_TIMEOUT_MS = 15 * 60 * 1000;

// Concurrent companion escalations. Raised 2->4 so J can watch several workers in
// the office at once. These are J-initiated builds on the Max subscription; market-
// hours discipline still applies (heavy interactive work can starve the heartbeat).
const MAX_INFLIGHT = 4;
let inflight = 0;

// Live registry: id -> { id, task, model, origin, started, status, finished, ok }.
// status: running | done | failed | cancelled | busy | blocked. Kept to ~30 most
// recent. `controllers` holds the AbortController for each RUNNING task.
const tasks = new Map();
const controllers = new Map();
const MAX_TASKS = 30;

function setTask(id, patch) {
  const cur = tasks.get(id) || { id };
  tasks.set(id, Object.assign(cur, patch));
  if (tasks.size > MAX_TASKS) {
    const keys = [...tasks.keys()];
    for (let i = 0; i < keys.length - MAX_TASKS; i++) tasks.delete(keys[i]);
  }
}

function slim(t) {
  return { id: t.id, task: t.task, model: t.model, origin: t.origin, started: t.started, finished: t.finished, status: t.status, ok: t.ok, sessionId: t.sessionId, card_id: t.card_id, cleared: t.cleared, summary: t.summary, lastStep: t.lastStep, lastTool: t.lastTool };
}

// What Claude is doing right now + recently. Exposed on /api/state.
function getTasks() {
  const all = [...tasks.values()];
  return {
    inflight,
    max: MAX_INFLIGHT,
    running: all.filter((t) => t.status === "running").map(slim),
    recent: all.slice(-12).reverse().map(slim),
  };
}

// Per-id status snapshot for the SSE route's subscribe-gap fix. Returns a slim
// { status, ok, summary? } or null if the id is unknown. A "terminal" status
// (done|failed|cancelled|busy|blocked) means the build already finished, so a
// late SSE connect must synthesize a final frame rather than wait forever.
const TERMINAL_STATUS = new Set(["done", "failed", "cancelled", "busy", "blocked"]);
function getTaskStatus(id) {
  const t = tasks.get(id);
  if (!t) return null;
  return { status: t.status, ok: t.ok, terminal: TERMINAL_STATUS.has(t.status) };
}

// Cancel a running escalation by id (aborts the underlying Claude query).
function cancelTask(id) {
  const ac = controllers.get(id);
  if (!ac) return { ok: false, error: "no running task with that id" };
  try { ac.abort(); } catch { /* already gone */ }
  return { ok: true, cancelled: id };
}

function resultsPath(root) {
  return path.join(root, "automation", "state", "companion-ask-results.jsonl");
}

// Card↔ask linkage helper: for an "oblig-<id>" card, re-run the obligation check
// and return whether THAT obligation is now ok (true), still unmet (false), or
// indeterminate (null on any error). Lazy-require to avoid a load-order cycle.
function recheckObligationCleared(root, cardId) {
  try {
    const obId = String(cardId).replace(/^oblig-/, "");
    const { checkObligations } = require("./obligations");
    const all = checkObligations(root);
    const hit = (all || []).find((o) => o && o.id === obId);
    return hit ? !!hit.ok : null;
  } catch {
    return null;
  }
}

// The obligation's CURRENT detail string for an "oblig-<id>" card — used as the
// snooze evidence_sig (matches server.js#obligationDetailFor) so a long snooze
// written on clear auto-invalidates the moment the evidence changes. Best-effort.
function recheckObligationDetail(root, cardId) {
  try {
    const obId = String(cardId).replace(/^oblig-/, "");
    const { checkObligations } = require("./obligations");
    const all = checkObligations(root);
    const hit = (all || []).find((o) => o && o.id === obId);
    return hit ? hit.detail || "" : null;
  } catch {
    return null;
  }
}

function appendResult(root, rec) {
  try {
    fs.appendFileSync(resultsPath(root), JSON.stringify(rec) + "\n");
  } catch {
    /* best effort */
  }
  logActivity(root, {
    source: "escalate",
    origin: rec.origin || "text",
    tier: "agent",
    model: rec.model || null,
    cost_usd: 0,
    action: rec.task ? "ran escalation" : "escalation skipped",
    outcome: rec.ok
      ? "success"
      : "error: " + String(rec.summary || rec.error || "failed").slice(0, 120),
  });
}

async function runEscalation(root, { id, model, task, origin, card_id }) {
  const fullModel = MODEL_MAP[model] || MODEL_MAP.sonnet;
  const started = new Date().toISOString();
  const shortTask = String(task || "").replace(/\s+/g, " ").trim().slice(0, 160);
  const org = origin || "text";
  const cardId = card_id || null;

  if (isHalted(root)) {
    setTask(id, { task: shortTask, model: fullModel, origin: org, card_id: cardId, started, status: "blocked", finished: new Date().toISOString(), ok: false });
    emit(root, id, { step: "result", ok: false, subtype: "halted", summary: "(halted)" });
    appendResult(root, { id, model: fullModel, ok: false, started, finished: new Date().toISOString(), card_id: cardId, summary: "(halted: companion-halt.flag present)" });
    return;
  }
  // Card de-dup: never run two concurrent builds for the SAME card. A re-tap of a
  // card whose build is still running (e.g. a snooze lapsed mid-build) must NOT
  // spawn a duplicate — no-op with an "already working" terminal so the slot and
  // the Max-pool aren't double-spent.
  if (cardId) {
    for (const t of tasks.values()) {
      if (t && t.card_id === cardId && t.status === "running" && t.id !== id) {
        setTask(id, { task: shortTask, model: fullModel, origin: org, card_id: cardId, started, status: "busy", finished: new Date().toISOString(), ok: false });
        emit(root, id, { step: "result", ok: false, subtype: "duplicate", summary: "(already working on that)" });
        appendResult(root, { id, model: fullModel, ok: false, started, finished: new Date().toISOString(), card_id: cardId, summary: "(already working on that card — no duplicate build started)" });
        return;
      }
    }
  }
  if (inflight >= MAX_INFLIGHT) {
    setTask(id, { task: shortTask, model: fullModel, origin: org, card_id: cardId, started, status: "busy", finished: new Date().toISOString(), ok: false });
    emit(root, id, { step: "result", ok: false, subtype: "busy", summary: "(busy)" });
    appendResult(root, { id, model: fullModel, ok: false, started, finished: new Date().toISOString(), card_id: cardId, summary: "(busy: too many tasks running — try again in a moment)" });
    return;
  }

  inflight++;
  const ac = new AbortController();
  controllers.set(id, ac);
  setTask(id, { task: shortTask, model: fullModel, origin: org, card_id: cardId, started, status: "running", ok: null, finished: null });
  emit(root, id, { step: "queued", task: shortTask, model: fullModel });

  let resultText = "";
  let subtype = "";
  let ok = false;

  // Wall-clock killer: a stalled query() always lands on the catch/abort path.
  // Cleared on every exit (catch + normal completion) so a fast build doesn't
  // leave a dangling timer. `timedOut` lets the catch tell a TIMEOUT (report it +
  // push the wrist) apart from a real user cancel (silent) — both call ac.abort().
  let timedOut = false;
  const killer = setTimeout(() => {
    timedOut = true;
    try { ac.abort(); } catch { /* already gone */ }
  }, ESCALATION_TIMEOUT_MS);

  try {
    const { query } = await import("@anthropic-ai/claude-agent-sdk");
    for await (const m of query({
      prompt: task,
      options: {
        model: fullModel,
        cwd: root,
        // SOUL: the claude_code preset makes this the real Claude Code agent;
        // `append: SOUL` makes it Gamma + the guard boundary part of the SYSTEM
        // prompt (not incidental context). settingSources pins CLAUDE.md loading
        // from cwk=repo root so a future SDK default flip can't silently drop the
        // soul ('project' is required to load CLAUDE.md per the SDK type defs).
        // SUBSCRIPTION AUTH: no apiKey is set anywhere — the SDK uses J's Claude
        // Code Max login. maxTurns bounds a runaway loop on the shared Max pool.
        systemPrompt: { type: "preset", preset: "claude_code", append: SOUL },
        settingSources: ["user", "project"],
        maxTurns: 60,
        canUseTool: makeCanUseTool(root, org),
        abortController: ac,
        includePartialMessages: true,
      },
    })) {
      // Message dispatcher: humanize every step into the live transcript. The
      // guard (canUseTool) is UNTOUCHED -- a denied tool still streams a
      // "Using X" then surfaces denied in the result. This is read-only telemetry.
      try {
        if (m.type === "system" && m.subtype === "init") {
          setTask(id, { sessionId: m.session_id });
          emit(root, id, { step: "session", sessionId: m.session_id, model: m.model, tools: (m.tools || []).length });
        } else if (m.type === "assistant") {
          for (const b of (m.message && m.message.content) || []) {
            if (b.type === "text" && String(b.text || "").trim())
              emit(root, id, { step: "text", text: String(b.text).slice(0, 2000) });
            else if (b.type === "thinking" && String(b.thinking || "").trim())
              emit(root, id, { step: "thinking", text: "(thinking) " + String(b.thinking).slice(0, 400) });
            else if (b.type === "tool_use")
              emit(root, id, { step: "tool", name: b.name, label: humanize(b.name, b.input) });
          }
        } else if (m.type === "user") {
          for (const b of (m.message && m.message.content) || []) {
            if (b.type === "tool_result") {
              const raw = Array.isArray(b.content)
                ? b.content.map((x) => (x && x.type === "text" ? x.text : "")).join(" ")
                : b.content;
              emit(root, id, { step: "tool_result", ok: !b.is_error, preview: String(raw || "").replace(/\s+/g, " ").trim().slice(0, 200) });
            }
          }
        } else if (m.type === "stream_event") {
          const e = m.event || {};
          if (e.type === "content_block_start" && e.content_block && e.content_block.type === "tool_use")
            emit(root, id, { step: "tool_start", name: e.content_block.name, label: "Using " + String(e.content_block.name || "tool").replace(/^mcp__/, "").replace(/__/g, " ") });
          else if (e.type === "content_block_delta" && e.delta && e.delta.type === "text_delta" && e.delta.text)
            emit(root, id, { step: "delta", text: String(e.delta.text).slice(0, 400) });
        } else if (m.type === "result") {
          resultText = m.result || resultText;
          subtype = m.subtype || "";
          ok = m.subtype === "success" && !m.is_error;
          const secs = m.duration_ms != null ? (m.duration_ms / 1000).toFixed(1) : null;
          emit(root, id, {
            step: "result",
            ok,
            subtype,
            cost: m.total_cost_usd, // kept in the durable log for subscription-usage tracking
            ms: m.duration_ms,
            // No "$" in the user-facing status: escalations run on J's Max SUBSCRIPTION
            // (no per-query charge), so a dollar sign reads like a bill it isn't.
            // HONEST failure: error_max_turns / error_during_execution often yield an
            // EMPTY result text, so a "Done in Ns" would be a cheery lie. Say it stopped.
            summary: ok
              ? "Done" + (secs != null ? " in " + secs + "s" : "")
              : "Stopped: " + (subtype || "error"),
          });
        }
      } catch {
        /* one bad message must not abort the loop */
      }
    }
  } catch (e) {
    clearTimeout(killer);
    inflight--;
    controllers.delete(id);
    const aborted = ac.signal.aborted;
    // A user cancel and the 15-min wall-clock kill BOTH abort the same controller.
    // Separate them: a real cancel (aborted && !timedOut) is silent + "by you"; a
    // timeout is a FAILURE we must surface (honest label + a wrist push).
    const userCancel = aborted && !timedOut;
    const failSummary = timedOut
      ? "(timed out after 15m — no response from Claude)"
      : userCancel
      ? "(cancelled by you)"
      : "(escalation error -- " + String((e && e.message) || e).slice(0, 200) + ")";
    setTask(id, { status: userCancel ? "cancelled" : "failed", finished: new Date().toISOString(), ok: false, summary: String(failSummary).replace(/\s+/g, " ").trim().slice(0, 200) });
    // Terminal frame so a watching SSE client closes cleanly (the SDK `result`
    // message never arrived on the throw/abort path).
    emit(root, id, {
      step: "result",
      ok: false,
      subtype: timedOut ? "timeout" : userCancel ? "cancelled" : "error",
      summary: timedOut ? "Stopped: timed out after 15m" : userCancel ? "(cancelled by you)" : "(error)",
    });
    appendResult(root, {
      id,
      model: fullModel,
      ok: false,
      started,
      finished: new Date().toISOString(),
      origin: org,
      card_id: cardId,
      task,
      summary: failSummary,
      error: String((e && e.message) || e),
    });
    // Ping the wrist that the build finished (error path). Fire-and-forget;
    // push is a never-throws no-op when there's no .vapid.json. Skip the noise
    // ONLY for a real user-initiated cancel -- a timeout still pings (it failed
    // on its own, J needs to know).
    if (!userCancel) {
      try {
        push.sendPush(root, {
          title: timedOut ? "Gamma build timed out" : "Gamma build hit an error",
          body: shortTask + (timedOut ? " — timed out (15m)" : " — failed"),
          tag: "ask-" + id,
          url: "/m.html",
          actions: [],
        });
      } catch { /* push can never break the result write */ }
    }
    pruneFeedDir(root, 50);
    return;
  }

  clearTimeout(killer);
  inflight--;
  controllers.delete(id);
  // Card↔ask linkage: when this build was launched from an obligation card,
  // re-check whether the underlying obligation actually CLEARED now (evidence
  // fresh again), so the result honestly records cleared:true|false. Best-effort
  // -- a re-check failure never blocks the result write.
  let cleared = null;
  if (cardId && /^(oblig|act)-/.test(cardId)) {
    // FAIL-GREEN completion: the approve wrote a grace snooze covering the whole
    // build. Now that it's done, resolve the card deterministically — snooze LONG
    // (45m) if it succeeded, or UNSNOOZE (re-surface now) if it failed — so a still-
    // unmet card always comes back and a satisfied one stays hidden. Best-effort;
    // a snooze write can never break the result.
    try {
      const { snoozeCard, unsnoozeCard } = require("./approvals");
      let resolved;
      let sig = null;
      if (/^oblig-/.test(cardId)) {
        // Obligation: resolved only if the underlying evidence is fresh again now.
        cleared = recheckObligationCleared(root, cardId);
        resolved = cleared === true;
        sig = recheckObligationDetail(root, cardId);
      } else {
        // act-* advisory card (engine-RED / kitchen-failed): a SUCCESSFUL analysis
        // satisfies the tap (J got the answer); a failed build should re-surface.
        resolved = ok === true;
      }
      if (resolved) snoozeCard(root, cardId, sig, 45);
      else unsnoozeCard(root, cardId);
    } catch { /* snooze is best-effort */ }
  }
  setTask(id, { status: ok ? "done" : "failed", finished: new Date().toISOString(), ok, cleared, summary: String(resultText || (ok ? "" : "Stopped: " + (subtype || "error"))).replace(/\s+/g, " ").trim().slice(0, 200) });
  appendResult(root, {
    id,
    model: fullModel,
    ok,
    subtype,
    origin: org,
    card_id: cardId,
    cleared,
    started,
    finished: new Date().toISOString(),
    task,
    // HONEST summary: a non-success subtype (error_max_turns / error_during_execution)
    // usually has empty result text — record "Stopped: <subtype>" rather than a bare
    // "(no output)" that reads like a clean finish.
    summary: ok
      ? String(resultText || "(no output)").trim().slice(0, 20000)
      : String(resultText || ("Stopped: " + (subtype || "error"))).trim().slice(0, 20000),
  });
  // Ping the wrist that the build finished (success/normal-completion path).
  // Fire-and-forget; push is a never-throws no-op when there's no .vapid.json.
  try {
    push.sendPush(root, {
      title: ok ? "Gamma finished a build" : "Gamma build hit an error",
      body: shortTask + (ok ? "" : " — failed"),
      tag: "ask-" + id,
      url: "/m.html",
      actions: [],
    });
  } catch { /* push can never break the result write */ }
  pruneFeedDir(root, 50);
}

module.exports = { runEscalation, getTasks, getTaskStatus, cancelTask, MODEL_MAP, subscribeAskStream, unsubscribeAskStream, askFeedPath };
