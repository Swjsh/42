"use strict";

// Reads the REAL Project Gamma state files and merges them into one object the
// companion UI can render. Every read is defensive -- a missing or malformed
// file degrades to null, never throws. Paths mirror dashboard/lib/workspace.ts
// so the companion and the existing dashboard share one contract.

const fs = require("fs");
const path = require("path");
const { readApprovals } = require("./approvals");
const { loadActivity } = require("./activity");

function readJSON(p) {
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return null;
  }
}

function pickEquity(o) {
  if (!o || typeof o !== "object") return null;
  const keys = [
    "equity",
    "account_equity",
    "current_equity",
    "sod_equity",
    "start_equity",
    "start_of_day_equity",
  ];
  for (const k of keys) {
    if (typeof o[k] === "number") return o[k];
  }
  return null;
}

// Read live equity from a circuit-breaker file.
// Safe schema: .current_equity; Aggressive schema: .equity_current
// (divergent field names -- see _schema_note in each breaker file; C9 symmetry trap).
function breakerEquity(breakerObj, safeSchema) {
  if (!breakerObj || typeof breakerObj !== "object") return null;
  const key = safeSchema ? "current_equity" : "equity_current";
  const v = breakerObj[key];
  return typeof v === "number" && isFinite(v) && v > 0 ? v : null;
}

function accountView(label, pos, loop, breakerObj, safeSchema) {
  const inPos = !!(pos && pos.status);
  // Prefer circuit-breaker live equity (updated every heartbeat tick) over
  // loop-state (which rarely carries an equity field).
  const equity = breakerEquity(breakerObj, safeSchema) ?? pickEquity(loop);
  return {
    label,
    status: inPos ? "in position" : "flat",
    in_position: inPos,
    equity,
    position: inPos ? pos.status : null,
  };
}

function timeOf(x) {
  const t = Date.parse(x || "");
  return Number.isFinite(t) ? t : 0;
}

// Collapse whitespace and clip to a clean word boundary so feed rows stay tidy.
function tidy(text, max) {
  const limit = max || 56;
  const s = String(text || "").replace(/\s+/g, " ").trim();
  if (s.length <= limit) return s;
  const cut = s.slice(0, limit);
  const sp = cut.lastIndexOf(" ");
  return (sp > 28 ? cut.slice(0, sp) : cut).trim() + "…";
}

// Real, actionable cards derived from live state -- not demos. Each carries an
// `action` the companion runs on Approve (today: escalate to Claude).
function derivedCards(health, kitchen) {
  const cards = [];

  // Only flag a GENUINELY large failure pile — the kitchen normally carries ~10
  // failed and a >=20 trigger nagged J on noise. >=60 means something actually
  // needs a cleanup pass, not routine R&D attrition.
  if (kitchen && typeof kitchen.failed === "number" && kitchen.failed >= 60) {
    cards.push({
      id: "act-kitchen-failed",
      severity: "info",
      title: `Kitchen has ${kitchen.failed} permanently-failed tasks`,
      detail: "Worth a triage pass — cluster the failure reasons, prune junk, flag any worth retrying.",
      source: "kitchen-status",
      action: {
        type: "escalate",
        model: "sonnet",
        task:
          "Review the failed_permanent tasks in automation/state/cook-queue.jsonl (kitchen reports " +
          kitchen.failed +
          " of them). Cluster the failure reasons, report which are junk to prune vs worth retrying, and propose a cleanup. Read-only analysis + proposal only — do NOT place trades or edit live params/heartbeat.",
      },
    });
  }

  if (health && Array.isArray(health.checks)) {
    for (const c of health.checks) {
      if (!c || typeof c !== "object") continue;
      if (c.status === "RED" && c.critical) {
        cards.push({
          id: "act-" + c.name,
          severity: "warn",
          title: "Engine check RED: " + c.name,
          detail: c.detail,
          source: "engine-health",
          action: {
            type: "escalate",
            model: "sonnet",
            task:
              "Engine health check '" +
              c.name +
              "' is RED: '" +
              c.detail +
              "'. Diagnose the root cause from automation/state and logs, then propose or apply a safe fix. Do NOT place trades or edit params/heartbeat. Report what you found.",
          },
        });
      }
    }
  }

  return cards.slice(0, 3);
}

function buildState(root) {
  const S = (...p) => path.join(root, "automation", "state", ...p);

  const health = readJSON(S("engine-health.json"));
  const kitchenRaw = readJSON(S("kitchen-status.json"));
  const dialogue = readJSON(S("dashboard-dialogue.json"));
  const posSafe = readJSON(S("current-position-safe.json"));
  const posBold = readJSON(S("current-position-bold.json"));
  const loopSafe = readJSON(S("loop-state.json"));
  const loopBold = readJSON(S("aggressive", "loop-state.json"));
  // Circuit-breaker files carry the most up-to-date equity per heartbeat tick.
  // Schemas diverge: safe uses .current_equity; aggressive uses .equity_current.
  const cbSafe = readJSON(S("circuit-breaker.json"));
  const cbBold = readJSON(S("aggressive", "circuit-breaker.json"));

  const kitchen = kitchenRaw
    ? {
        daemon_alive: !!kitchenRaw.daemon_alive,
        idle: !!kitchenRaw.idle,
        pending: kitchenRaw.queue_summary?.by_status?.pending ?? null,
        completed: kitchenRaw.queue_summary?.by_status?.completed ?? null,
        failed: kitchenRaw.queue_summary?.by_status?.failed_permanent ?? null,
        cost_today: kitchenRaw.today_cost_usd_paid_tier ?? null,
        cost_cap: kitchenRaw.today_cost_cap_usd ?? null,
        recent: Array.isArray(kitchenRaw.recent_completed_top_10)
          ? kitchenRaw.recent_completed_top_10
              .slice(0, 3)
              .map((r) => ({ task: r.task, at: r.completed_at, model: r.model }))
          : [],
      }
    : null;

  const accounts = {
    safe: accountView("Gamma-Safe", posSafe, loopSafe, cbSafe, true),
    bold: accountView("Gamma-Bold", posBold, loopBold, cbBold, false),
  };

  // Read the two card sources independently so a derivedCards throw can NEVER
  // drop real queued approvals (the whole try used to blank both).
  const queued = readApprovals(root);
  let derived = [];
  try { derived = derivedCards(health, kitchen); } catch { /* derived cards are best-effort */ }
  const approvals = [...queued, ...derived];

  // Read the append-only activity ledger ONCE per poll (OP-22), then derive BOTH
  // the recent-activity feed (last 10) and today's spend from the same rows —
  // buildState used to read the whole file twice (readActivity + todaySpend).
  const activityRows = loadActivity(root);
  const recentActivity = activityRows.slice(-10);
  // TZ-SYSTEMIC FIX (2026-06-26): machine is Mountain time; using UTC date for "today"
  // bucketing means activity after midnight ET but before midnight UTC gets credited to
  // the wrong day.  Use Intl API to get the ET date, consistent with obligations.etToday.
  const todayET = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date()); // YYYY-MM-DD
  let spendToday = 0;
  for (const rec of activityRows) {
    const ts = rec && typeof rec.ts === "string" ? rec.ts : "";
    if (ts.slice(0, 10) !== todayET) continue;
    const c = Number(rec && rec.cost_usd);
    if (Number.isFinite(c)) spendToday += c;
  }

  // Feed = what Gamma has been DOING (agents + kitchen R&D). Engine-health
  // lives in the status strip, not here, so the feed stays uncluttered.
  const feed = [];
  if (dialogue && dialogue.agents) {
    for (const [name, a] of Object.entries(dialogue.agents)) {
      if (a && a.speech) {
        feed.push({ ts: a.last_active_at, kind: "agent", name, text: tidy(a.speech) });
      }
    }
  }
  if (kitchen && kitchen.recent) {
    for (const r of kitchen.recent) {
      feed.push({ ts: r.at, kind: "kitchen", name: "kitchen", text: tidy(r.task) });
    }
  }
  for (const a of recentActivity) {
    feed.push({
      ts: a.ts,
      kind: "activity",
      name: a.source || "gamma",
      text: tidy((a.action || "did something") + " — " + (a.outcome || "")),
    });
  }
  feed.sort((a, b) => timeOf(b.ts) - timeOf(a.ts));

  let speech;
  if (approvals.length) {
    speech =
      approvals.length === 1
        ? "1 thing needs your OK — tap me."
        : `${approvals.length} things need your OK — tap me.`;
  } else if (dialogue && (dialogue.ticker_speech || dialogue.claude_reasoning)) {
    speech = dialogue.ticker_speech || dialogue.claude_reasoning;
  } else {
    speech = "All quiet. Standing watch.";
  }

  return {
    updated_at: new Date().toISOString(),
    spend_today_usd: spendToday,
    market_open: !!(health && health.market_open),
    verdict: health ? health.verdict : "UNKNOWN",
    health: health
      ? { verdict: health.verdict, checks: health.checks, reds: health.reds || [] }
      : null,
    kitchen,
    accounts,
    dialogue: dialogue
      ? {
          ticker_speech: dialogue.ticker_speech,
          claude_status: dialogue.claude_status,
          claude_reasoning: dialogue.claude_reasoning,
        }
      : null,
    approvals,
    speech,
    feed: feed.slice(0, 4),
  };
}

// Compact one-screen text the FACE model reads as context each turn.
function summarize(state) {
  const a = state.accounts || {};
  const k = state.kitchen || {};
  const lines = [];
  lines.push(`Engine: ${state.verdict} | market ${state.market_open ? "OPEN" : "closed"}`);
  if (a.safe) lines.push(`Gamma-Safe: ${a.safe.status}${a.safe.equity != null ? " $" + a.safe.equity : ""}`);
  if (a.bold) lines.push(`Gamma-Bold: ${a.bold.status}${a.bold.equity != null ? " $" + a.bold.equity : ""}`);
  if (k && k.daemon_alive != null) {
    lines.push(
      `Kitchen: ${k.daemon_alive ? "alive" : "down"} | ${k.completed ?? "?"} done, ${k.pending ?? "?"} pending, ${k.failed ?? "?"} failed | $${k.cost_today ?? 0}/${k.cost_cap ?? "?"} today`
    );
  }
  // "What's cooking" -- the kitchen counts, phrased so the FACE can answer it directly.
  if (k && (k.completed != null || k.pending != null)) {
    lines.push(`Cooking: ${k.completed ?? "?"} done, ${k.pending ?? "?"} pending`);
  }
  // "Up next" -- the next pending build-queue task the FACE can name.
  if (state.build && state.build.next && state.build.next.title) {
    lines.push("Up next: " + state.build.next.title);
  }
  // What Claude is building right now, so "is Claude working" has a real answer.
  if (state.claude && Array.isArray(state.claude.running) && state.claude.running.length) {
    lines.push(
      "Claude working on: " +
        state.claude.running.map((t) => tidy(t.task, 70)).filter(Boolean).join(" | ")
    );
  }
  if (typeof state.spend_today_usd === "number") {
    lines.push("Spend today: $" + state.spend_today_usd.toFixed(2));
  }
  if (Array.isArray(state.approvals) && state.approvals.length) {
    lines.push("Needs OK: " + state.approvals.map((x) => x.title).join(" | "));
  }
  if (Array.isArray(state.feed) && state.feed.length) {
    lines.push("Recent activity:");
    for (const f of state.feed) lines.push(`  - [${f.kind}] ${f.text}`);
  }
  if (state.dialogue && state.dialogue.ticker_speech) lines.push("Latest note: " + state.dialogue.ticker_speech);
  // Keep the FACE context compact (~1.5KB cap) so the free model isn't drowned.
  const out = lines.join("\n");
  return out.length > 1500 ? out.slice(0, 1499) + "…" : out;
}

module.exports = { buildState, summarize, readJSON };
