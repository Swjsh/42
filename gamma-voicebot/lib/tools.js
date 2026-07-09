"use strict";

// The THREE read-only rig-state tools the Realtime model must use for any state
// question (facts are TOOLS, never model memory -- OP-33). Every reader is
// fail-open: on any error it returns an honest error string for the model to
// SAY, never a throw that kills the session. Nothing here writes anything.

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

// Schemas in the exact shape the companion's /api/realtime-token uses.
const toolSchemas = [
  {
    type: "function",
    name: "engine_state",
    description:
      "Current engine state: the last decision row per account (safe + bold) from the " +
      "core decision ledger -- SPY price, VIX, ribbon, verdict/action, reason, armed flag -- " +
      "plus each account's open-position state. Use for: what's the engine doing, are we in " +
      "a trade, why did it hold/enter, is it armed.",
    parameters: { type: "object", properties: {}, required: [] },
  },
  {
    type: "function",
    name: "funnel_today",
    description:
      "Today's fill funnel per account (ticks -> signals -> ENTER -> rule-blocked -> " +
      "attempted -> accepted -> filled -> exited) with a GREEN/DEGRADED/RED/IDLE verdict and " +
      "flags. THE authority on 'did we actually trade today and where did entries die'.",
    parameters: { type: "object", properties: {}, required: [] },
  },
  {
    type: "function",
    name: "evening_debrief",
    description:
      "Gamma's own evening narrative of the trading day (what I saw / did / learned / am " +
      "changing), plus tonight's question for J. Use when J asks how the day went or what " +
      "the debrief said.",
    parameters: { type: "object", properties: {}, required: [] },
  },
  {
    type: "function",
    name: "kitchen_status",
    description:
      "The Kitchen: the 24/7 free-tier R&D loop that COOKS strategy candidates and analysis " +
      "(it does NOT place trades -- the engine/fleet do that). Returns whether the daemon is " +
      "alive/working, the queue counts (pending/completed/failed), today's spend, and the last " +
      "few things it cooked. Use for: what's the kitchen doing, what are we cooking, what's the " +
      "swarm/R&D loop up to.",
    parameters: { type: "object", properties: {}, required: [] },
  },
];

// ---------------------------------------------------------------------------
// engine_state
// ---------------------------------------------------------------------------

// Read the tail of a possibly-large JSONL without loading the whole file.
function readTail(file, bytes) {
  const fd = fs.openSync(file, "r");
  try {
    const size = fs.fstatSync(fd).size;
    const want = Math.min(size, bytes);
    const buf = Buffer.allocUnsafe(want);
    fs.readSync(fd, buf, 0, want, size - want);
    return buf.toString("utf8");
  } finally {
    fs.closeSync(fd);
  }
}

function lastRowPerAccount(root) {
  const file = path.join(root, "automation", "state", "core-decisions.jsonl");
  const lines = readTail(file, 512 * 1024).split(/\r?\n/).filter(Boolean);
  const out = {};
  for (let i = lines.length - 1; i >= 0 && Object.keys(out).length < 2; i--) {
    let row;
    try {
      row = JSON.parse(lines[i]);
    } catch {
      continue; // first line of a tail read is usually torn -- expected
    }
    const acct = String(row.account || "core");
    if (out[acct]) continue;
    out[acct] = {
      ts_et: row.ts_et,
      armed: row.armed,
      spy: row.spy,
      vix: row.vix,
      ribbon: row.ribbon,
      htf_15m: row.htf_15m,
      verdict: row.verdict,
      action: row.action,
      setup: row.setup,
      reason: row.reason,
      bear_score: row.bear_score,
      bull_score: row.bull_score,
    };
  }
  return out;
}

function positionFor(root, name) {
  try {
    const raw = JSON.parse(
      fs.readFileSync(path.join(root, "automation", "state", `current-position-${name}.json`), "utf8")
    );
    if (!raw || raw.status === null || raw.status === undefined) return "FLAT";
    // Pass the live position through minus bookkeeping keys.
    const pos = {};
    for (const k of Object.keys(raw)) if (!k.startsWith("_")) pos[k] = raw[k];
    return pos;
  } catch (e) {
    return "unreadable (" + e.message + ")";
  }
}

function engineState(root) {
  const accounts = lastRowPerAccount(root);
  if (!Object.keys(accounts).length) {
    return Promise.resolve("engine_state ERROR: no rows readable from core-decisions.jsonl");
  }
  // Staleness disclosure: outside market hours the last tick is naturally old --
  // say so instead of letting the model imply the engine is live right now.
  let newest = "";
  for (const a of Object.values(accounts)) if ((a.ts_et || "") > newest) newest = a.ts_et || "";
  // ts_et carries no UTC offset and the rig must never guess one blindly (TZ scar,
  // CLAUDE.md). Try both EDT/EST readings and keep the smaller sane age.
  let ageMin = null;
  if (newest) {
    const ages = ["-04:00", "-05:00"]
      .map((off) => Math.round((Date.now() - new Date(newest + off).getTime()) / 60000))
      .filter((m) => Number.isFinite(m) && m >= -5);
    if (ages.length) ageMin = Math.min(...ages);
  }
  return Promise.resolve(
    JSON.stringify({
      note:
        ageMin !== null && ageMin > 10
          ? `last engine tick was ${newest} ET (~${ageMin} min ago) -- engine is not ticking right now (market likely closed)`
          : "engine ticked within the last few minutes",
      last_decision_per_account: accounts,
      open_positions: { safe: positionFor(root, "safe"), bold: positionFor(root, "bold") },
    })
  );
}

// ---------------------------------------------------------------------------
// funnel_today -- run the canonical producer, never re-derive funnel math here
// ---------------------------------------------------------------------------

function pickPython(root) {
  const venv = path.join(root, "backtest", ".venv", "Scripts", "python.exe");
  try {
    if (fs.existsSync(venv)) return venv;
  } catch {
    /* fall through */
  }
  return "python";
}

function funnelToday(root) {
  return new Promise((resolve) => {
    const script = path.join(root, "setup", "scripts", "fill_funnel.py");
    let out = "";
    let err = "";
    let child;
    try {
      child = spawn(pickPython(root), [script], { cwd: root, windowsHide: true });
    } catch (e) {
      return resolve("funnel_today ERROR: could not spawn python: " + e.message);
    }
    const timer = setTimeout(() => {
      try {
        child.kill();
      } catch {
        /* noop */
      }
      resolve("funnel_today ERROR: fill_funnel.py timed out after 25s");
    }, 25000);
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", (e) => {
      clearTimeout(timer);
      resolve("funnel_today ERROR: " + e.message);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (out.trim()) return resolve(out.trim().slice(0, 4000));
      resolve(`funnel_today ERROR: exit ${code}, no output. stderr: ` + err.slice(0, 500));
    });
  });
}

// ---------------------------------------------------------------------------
// evening_debrief
// ---------------------------------------------------------------------------

function eveningDebrief(root) {
  try {
    const n = JSON.parse(
      fs.readFileSync(path.join(root, "automation", "state", "gamma-narrative.json"), "utf8")
    );
    const spoken = (n.spoken || n.text || "").trim();
    if (!spoken) return Promise.resolve("evening_debrief: no narrative text available yet for " + (n.date || "today"));
    return Promise.resolve(
      JSON.stringify({ date: n.date, debrief: spoken, question_for_j: n.question || null })
    );
  } catch (e) {
    return Promise.resolve("evening_debrief ERROR: " + e.message);
  }
}

// ---------------------------------------------------------------------------
// kitchen_status -- the R&D loop (NOT the trader). Reads kitchen-status.json.
// ---------------------------------------------------------------------------

// Signal-0 existence probe -- authoritative liveness, timezone-proof.
// true = running, false = gone, null = unknown pid. EPERM means it exists but
// we can't signal it (still alive).
function pidAlive(pid) {
  if (!pid || !Number.isFinite(pid)) return null;
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return e.code === "EPERM";
  }
}

function kitchenStatus(root) {
  try {
    const file = path.join(root, "automation", "state", "kitchen-status.json");
    const k = JSON.parse(fs.readFileSync(file, "utf8"));
    const q = k.queue_summary || {};
    const by = q.by_status || {};
    // Liveness the RELIABLE way (a false "kitchen is down" burned J once): the
    // daemon's own updated_at_et string LAGS real ET -- it tracks the last
    // COMPLETED task, so a long grinder job makes it look hours stale while the
    // daemon is fine. Trust instead (a) is the pid actually running, and (b) the
    // file's own mtime (rewritten every loop). Both are timezone-proof.
    const running = pidAlive(Number(k.daemon_pid));
    let fileAgeMin = null;
    try {
      fileAgeMin = Math.round((Date.now() - fs.statSync(file).mtimeMs) / 60000);
    } catch {
      /* ignore */
    }
    const fresh = fileAgeMin !== null && fileAgeMin <= 15;
    const alive = running === true || (k.daemon_alive === true && fresh);
    const cooked = (k.recent_completed_top_10 || [])
      .slice(0, 3)
      .map((t) => String(t.task || "").split(/[:.]/)[0].slice(0, 90))
      .filter(Boolean);
    let note;
    if (!alive) {
      note =
        "kitchen daemon looks DOWN (pid not running" +
        (fileAgeMin !== null ? ", status file " + fileAgeMin + " min stale" : "") + ")";
    } else if (k.idle) {
      note = "kitchen daemon alive, idle right now";
    } else {
      note = "kitchen daemon alive and working a task (a grinder backtest can run a while)";
    }
    return Promise.resolve(
      JSON.stringify({
        note,
        it_does_not_trade: "the kitchen is R&D -- it cooks strategy candidates; the engine/fleet place trades",
        queue: { pending: by.pending || 0, completed: by.completed || 0, failed: by.failed_permanent || 0 },
        today_cost_usd: k.today_cost_usd_paid_tier != null ? k.today_cost_usd_paid_tier : null,
        recently_cooked: cooked,
      })
    );
  } catch (e) {
    return Promise.resolve("kitchen_status ERROR: " + e.message);
  }
}

// ---------------------------------------------------------------------------

const handlers = {
  engine_state: engineState,
  funnel_today: funnelToday,
  evening_debrief: eveningDebrief,
  kitchen_status: kitchenStatus,
};

// Dispatch by name; ALWAYS resolves to a string the model can speak.
function runTool(root, name) {
  const h = handlers[name];
  if (!h) return Promise.resolve("unknown tool: " + name);
  return h(root).catch((e) => name + " ERROR: " + ((e && e.message) || e));
}

module.exports = { toolSchemas, runTool };
