"use strict";

// Unified activity ledger -- the companion's observability spine.
//
// Contract (gamma-activity.jsonl, append-only, one JSON object per line):
//   { ts, source, origin, tier, model, cost_usd, action, outcome }
//
//   ts        ISO-8601 timestamp, stamped here (caller never supplies it)
//   source    who produced the row, e.g. "escalate" | "approvals" | "kitchen"
//   origin    what triggered it, e.g. "card" | "text" | "discord" | "auto"
//   tier      coarse class, e.g. "agent" | "approval" | "engine" | "kitchen"
//   model     full model id if an LLM ran, else null (e.g. "claude-opus-4-8")
//   cost_usd  number; best-effort dollar cost of this row (0 when unknown)
//   action    short verb phrase of what happened (e.g. "ran escalation")
//   outcome   short result phrase ("success" | "error: ..." | "approved")
//
// Every function is defensive in the approvals.js house style: a missing or
// malformed file degrades to a safe empty value and NEVER throws. The ledger is
// telemetry -- it must not be able to crash the thing it is observing.

const fs = require("fs");
const path = require("path");

function activityPath(root) {
  return path.join(root, "automation", "state", "gamma-activity.jsonl");
}

// Append one activity row. Returns the written record (or null if the write
// could not happen). Never throws.
function logActivity(root, fields) {
  try {
    const f = fields || {};
    const cost = Number(f.cost_usd);
    const record = {
      ts: new Date().toISOString(),
      source: f.source != null ? String(f.source) : "unknown",
      origin: f.origin != null ? String(f.origin) : null,
      tier: f.tier != null ? String(f.tier) : null,
      model: f.model != null ? String(f.model) : null,
      cost_usd: Number.isFinite(cost) ? cost : 0,
      action: f.action != null ? String(f.action) : null,
      outcome: f.outcome != null ? String(f.outcome) : null,
    };
    fs.appendFileSync(activityPath(root), JSON.stringify(record) + "\n");
    return record;
  } catch {
    return null;
  }
}

// Parse the ledger into an array of records (oldest first). Bad lines are
// skipped, not fatal. Returns [] on any failure.
function loadActivity(root) {
  try {
    const raw = fs.readFileSync(activityPath(root), "utf8");
    const rows = [];
    for (const line of raw.split("\n")) {
      const s = line.trim();
      if (!s) continue;
      try {
        const rec = JSON.parse(s);
        if (rec && typeof rec === "object") rows.push(rec);
      } catch {
        /* skip malformed line */
      }
    }
    return rows;
  } catch {
    return [];
  }
}

// Tail the last n rows (newest last, chronological order preserved). Never throws.
function readActivity(root, n) {
  const rows = loadActivity(root);
  const count = Number.isFinite(Number(n)) && Number(n) > 0 ? Math.floor(Number(n)) : 20;
  return rows.slice(-count);
}

// Sum cost_usd across all rows whose ts falls on today's UTC calendar date.
// Returns a number (0 when nothing matches or the file is unreadable).
function todaySpend(root) {
  try {
    const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD (UTC)
    let sum = 0;
    for (const rec of loadActivity(root)) {
      const ts = rec && typeof rec.ts === "string" ? rec.ts : "";
      if (ts.slice(0, 10) !== today) continue;
      const c = Number(rec.cost_usd);
      if (Number.isFinite(c)) sum += c;
    }
    return sum;
  } catch {
    return 0;
  }
}

module.exports = { logActivity, readActivity, todaySpend, loadActivity, activityPath };
