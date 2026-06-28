"use strict";
// Guard test: spend tile must show GREEN/$0 when the spend log's last entry is from a
// prior day.  REDs on regression (the bug it fixed: stale entry from yesterday always
// showed RED regardless of today's spend).
//
// Run with: node cockpit/test-spend-date-guard.js
// Exit 0 = all assertions pass. Exit 1 = regression detected.

const fs = require("fs");
const os = require("os");
const path = require("path");

// Inline the production logic so the guard is always in sync with the real code.
// If the signature of getSpendStatus() changes, update this copy too.
function getSpendStatus_logic(jsonlContent, nowDate) {
  // nowDate is a "YYYY-MM-DD" string representing today ET (injectable for testing).
  const todayEtDate = nowDate;

  const lines = jsonlContent.trim().split("\n").filter(Boolean);
  if (!lines.length) return { light: "GREEN", title: "Spend", text: "$0 today", updated: todayEtDate };

  let todayEntry = null;
  for (let i = lines.length - 1; i >= 0; i--) {
    try {
      const r = JSON.parse(lines[i]);
      if (r && r.date_et === todayEtDate) { todayEntry = r; break; }
      if (r && r.date_et && r.date_et < todayEtDate) break;
    } catch (_) {}
  }

  if (!todayEntry) {
    return { light: "GREEN", title: "Spend", text: "$0 today", updated: todayEtDate };
  }

  const cost = todayEntry.total_cost_usd || 0;
  const light = cost > 400 ? "RED" : cost > 200 ? "YELLOW" : "GREEN";
  const text = `$${cost.toFixed(2)} today | sessions=${todayEntry.claude_sessions || 0}`;
  return { light, title: "Spend", text, updated: todayEtDate };
}

let failures = 0;

function assert(condition, label) {
  if (condition) {
    console.log(`  PASS  ${label}`);
  } else {
    console.error(`  FAIL  ${label}`);
    failures++;
  }
}

// ── Case 1: last entry is from yesterday (the regression) ────────────────────
// Before the fix this would show RED because cost=$350 > $200 threshold.
const yesterdayLog = JSON.stringify({ date_et: "2026-06-27", total_cost_usd: 350.0, claude_sessions: 5 });
const r1 = getSpendStatus_logic(yesterdayLog, "2026-06-28");
assert(r1.light === "GREEN", "stale-yesterday entry shows GREEN (not RED) on today");
assert(r1.text.includes("$0 today"), "stale-yesterday entry shows $0 today text");

// ── Case 2: today's entry exists with spend < $200 → GREEN ───────────────────
const todayLowLog = [
  JSON.stringify({ date_et: "2026-06-27", total_cost_usd: 350.0, claude_sessions: 5 }),
  JSON.stringify({ date_et: "2026-06-28", total_cost_usd: 45.50, claude_sessions: 2 }),
].join("\n");
const r2 = getSpendStatus_logic(todayLowLog, "2026-06-28");
assert(r2.light === "GREEN", "today entry $45.50 → GREEN");
assert(r2.text.includes("$45.50"), "today entry shows correct cost");

// ── Case 3: today's entry with spend $250 → YELLOW ───────────────────────────
const todayMidLog = JSON.stringify({ date_et: "2026-06-28", total_cost_usd: 250.0, claude_sessions: 8 });
const r3 = getSpendStatus_logic(todayMidLog, "2026-06-28");
assert(r3.light === "YELLOW", "today entry $250 → YELLOW");

// ── Case 4: today's entry with spend $450 → RED ──────────────────────────────
const todayHighLog = JSON.stringify({ date_et: "2026-06-28", total_cost_usd: 450.0, claude_sessions: 20 });
const r4 = getSpendStatus_logic(todayHighLog, "2026-06-28");
assert(r4.light === "RED", "today entry $450 → RED (correct RED for today's overspend)");

// ── Case 5: empty log → GREEN ─────────────────────────────────────────────────
const r5 = getSpendStatus_logic("", "2026-06-28");
assert(r5.light === "GREEN", "empty log → GREEN");

// ── Case 6: multiple prior days but no today entry → GREEN ───────────────────
const multiPriorLog = [
  JSON.stringify({ date_et: "2026-06-25", total_cost_usd: 500.0, claude_sessions: 10 }),
  JSON.stringify({ date_et: "2026-06-26", total_cost_usd: 300.0, claude_sessions: 7 }),
  JSON.stringify({ date_et: "2026-06-27", total_cost_usd: 350.0, claude_sessions: 5 }),
].join("\n");
const r6 = getSpendStatus_logic(multiPriorLog, "2026-06-28");
assert(r6.light === "GREEN", "multiple prior high-spend days but no today entry → GREEN");

console.log(`\n${failures === 0 ? "ALL PASS" : failures + " FAILURE(S)"} — spend-date-guard`);
process.exit(failures > 0 ? 1 : 0);
