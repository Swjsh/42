"use strict";

// Overnight self-build runner -- the queue reader for Gamma's bounded,
// one-step-per-fire self-improvement loop.
//
// Contract: automation/state/companion-build-order.jsonl is an append-only
// JSONL queue of SAFE build tasks. Each line is one task:
//   { id, title, task, tier, status, created_at, updated_at?, outcome? }
//     id      -- stable unique slug (e.g. "wire-activity-ledger")
//     title   -- short human label
//     task    -- the full prompt handed to runEscalation() (Claude does the work)
//     tier    -- "authoring" | "doctrine" | "readonly"  (informs gating, NOT a
//                permission -- guard.js#canUseTool is the real wall)
//     status  -- "pending" | "in_progress" | "done" | "failed" | "blocked"
//
// This module ONLY reads the queue and flips one task's status. It NEVER spawns
// Claude itself (that's runEscalation in escalate.js, behind guard.js) and NEVER
// touches doctrine/params/orders. Pure, defensive, fail-loud-but-never-throw on
// a malformed line (skip + keep going, OP-25: surface the bad line, don't crash).

const fs = require("fs");
const path = require("path");

const VALID_STATUS = new Set(["pending", "in_progress", "done", "failed", "blocked"]);

function orderPath(root) {
  return path.join(root, "automation", "state", "companion-build-order.jsonl");
}

// Parse the JSONL queue into an array of task objects. A malformed line is
// skipped (logged to stderr) rather than throwing -- one bad row must never
// stall the whole overnight loop.
function readQueue(root) {
  let raw;
  try {
    raw = fs.readFileSync(orderPath(root), "utf8");
  } catch {
    return []; // no queue yet == nothing to build
  }
  const tasks = [];
  const lines = raw.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    let rec;
    try {
      rec = JSON.parse(line);
    } catch {
      process.stderr.write("[autobuild] skipping malformed queue line " + (i + 1) + "\n");
      continue;
    }
    if (rec && typeof rec === "object" && rec.id && rec.task) {
      tasks.push(rec);
    } else {
      process.stderr.write("[autobuild] skipping incomplete queue line " + (i + 1) + " (needs id+task)\n");
    }
  }
  return tasks;
}

// Return the next task to run: the first 'pending' item in queue order, or null
// if the queue is empty / fully drained. BOUNDED: the caller runs exactly this
// one and stops. We deliberately do NOT pick up 'failed'/'blocked' items -- those
// need a human (an Approve card / a fix) before they re-enter the queue.
function nextBuildStep(root) {
  const tasks = readQueue(root);
  for (const t of tasks) {
    const status = t.status || "pending";
    if (status === "pending") return t;
  }
  return null;
}

// Flip one task's status by id. Rewrites the JSONL atomically (read-all,
// mutate-one, write-tmp, rename) so a crash mid-write can't corrupt the queue.
// Returns the updated task, or null if the id wasn't found / status invalid.
function markStep(root, id, status, extra) {
  if (!VALID_STATUS.has(status)) {
    process.stderr.write("[autobuild] refusing invalid status '" + status + "' for " + id + "\n");
    return null;
  }
  const tasks = readQueue(root);
  let updated = null;
  const next = tasks.map((t) => {
    if (t.id !== id) return t;
    updated = Object.assign({}, t, {
      status,
      updated_at: new Date().toISOString(),
    });
    if (extra && typeof extra === "object") {
      if (extra.outcome != null) updated.outcome = String(extra.outcome).slice(0, 2000);
      if (extra.ask_id != null) updated.ask_id = String(extra.ask_id);
    }
    return updated;
  });

  if (!updated) {
    process.stderr.write("[autobuild] markStep: no task with id '" + id + "'\n");
    return null;
  }

  const body = next.map((t) => JSON.stringify(t)).join("\n") + "\n";
  const tmp = orderPath(root) + ".tmp";
  try {
    fs.writeFileSync(tmp, body);
    fs.renameSync(tmp, orderPath(root));
  } catch (e) {
    process.stderr.write("[autobuild] markStep write failed: " + String((e && e.message) || e) + "\n");
    return null;
  }
  return updated;
}

// Small helper for the scheduled fire / conductor: a one-line snapshot of the
// queue so STATUS / activity logs can show "3 pending, 1 in_progress, 9 done".
function queueSummary(root) {
  const tasks = readQueue(root);
  const counts = { pending: 0, in_progress: 0, done: 0, failed: 0, blocked: 0, total: tasks.length };
  for (const t of tasks) {
    const s = t.status || "pending";
    if (counts[s] != null) counts[s]++;
  }
  return counts;
}

module.exports = { nextBuildStep, markStep, readQueue, queueSummary, orderPath };
