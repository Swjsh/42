"use strict";

// The read-only tools the Realtime model uses for any state question (facts are
// TOOLS, never model memory -- OP-33). Every STATE reader is fail-open: on any
// error it returns an honest error string for the model to SAY, never a throw
// that kills the session. The one exception in spirit is ask_gamma_brain, the
// deep catch-all -- it spawns a read-only Claude over the whole repo (lib/brain.js).
// Nothing here writes anything.

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { askGammaBrain } = require("./brain");

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
  {
    type: "function",
    name: "account_pnl",
    description:
      "Per-account money: current equity, today's P&L (dollars and %), day-trades used in the " +
      "rolling 5, and kill-switch status -- for both accounts (Safe + Bold). Paper accounts. " +
      "Use for: how are my accounts, am I up or down today, what's my equity/balance, how much " +
      "have I made/lost, did we trip the kill switch.",
    parameters: { type: "object", properties: {}, required: [] },
  },
  {
    type: "function",
    name: "market_now",
    description:
      "Current market context: latest SPY price (WITH freshness -- the price feed only updates " +
      "during market hours, so after the close it's the last print), VIX, the EMA-ribbon trend, " +
      "today's session bias, and the nearest support/resistance levels. Use for: where's SPY, " +
      "what's the price, what are the levels, what's the bias, what's the market/tape doing.",
    parameters: { type: "object", properties: {}, required: [] },
  },
  {
    type: "function",
    name: "recent_trades",
    description:
      "The last few journaled option fills: date, setup, strike, side, quantity, dollar P&L, and " +
      "which account. Use for: what were my recent trades, how did my last trades go, what did I " +
      "trade this week, show me the last fills. NOTE these are the last RECORDED fills, not " +
      "necessarily today.",
    parameters: { type: "object", properties: {}, required: [] },
  },
  {
    type: "function",
    name: "ask_gamma_brain",
    description:
      "Your DEEP brain -- a full Claude that can read the ENTIRE repo (all of Chief). Use this " +
      "ONLY when NO other tool fits: questions about repo internals, code, doctrine, params values, " +
      "strategy or lesson details, 'why/how does X work', or history/frequency the state tools " +
      "don't carry (e.g. what the kitchen has done over several days). It takes ~30-40 seconds, so " +
      "FIRST say out loud a short 'let me dig into that, give me a moment' BEFORE relying on it, " +
      "then speak its answer. It is READ-ONLY -- it cannot change anything.",
    parameters: {
      type: "object",
      properties: {
        question: {
          type: "string",
          description: "The full, self-contained question to research, in plain words.",
        },
      },
      required: ["question"],
    },
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
// account_pnl  (per-account equity + day P&L from the circuit-breaker files)
// ---------------------------------------------------------------------------

function readJson(root, ...seg) {
  return JSON.parse(fs.readFileSync(path.join(root, ...seg), "utf8"));
}

// Safe and Bold circuit-breaker files use DIFFERENT key names -- branch on it.
function acctFromBreaker(cb, isBold) {
  const start = isBold ? cb.equity_start_of_day : cb.starting_equity_today;
  const cur = isBold ? cb.equity_current : cb.current_equity;
  const killPct = isBold ? cb.daily_loss_kill_switch_pct : cb.daily_loss_limit_pct;
  const reason = isBold ? cb.trip_reason : cb.tripped_reason;
  const pnl = cur != null && start != null ? Math.round((cur - start) * 100) / 100 : null;
  const pnlPct = pnl != null && start ? Math.round((pnl / start) * 1000) / 10 : null;
  return {
    equity: cur != null ? Math.round(cur) : null,
    day_pnl_usd: pnl,
    day_pnl_pct: pnlPct,
    day_trades_used_5d: cb.day_trades_used_5d != null ? cb.day_trades_used_5d : null,
    kill_switch_limit_pct: killPct != null ? killPct : null,
    kill_switch_tripped: cb.tripped === true,
    kill_switch_reason: reason || null,
  };
}

function accountPnl(root) {
  try {
    const out = {};
    let any = false;
    try {
      out.safe = acctFromBreaker(readJson(root, "automation", "state", "circuit-breaker.json"), false);
      any = true;
    } catch (e) {
      out.safe = "read failed: " + e.message;
    }
    try {
      out.bold = acctFromBreaker(readJson(root, "automation", "state", "aggressive", "circuit-breaker.json"), true);
      any = true;
    } catch (e) {
      out.bold = "read failed: " + e.message;
    }
    if (!any) return Promise.resolve("account_pnl ERROR: neither circuit-breaker file is readable");
    out.note = "paper accounts; day P&L = current equity minus start-of-day equity";
    return Promise.resolve(JSON.stringify(out));
  } catch (e) {
    return Promise.resolve("account_pnl ERROR: " + e.message);
  }
}

// ---------------------------------------------------------------------------
// market_now  (SPY from the sight beacon + VIX + bias + nearest levels)
// ---------------------------------------------------------------------------

function marketNow(root) {
  try {
    const out = {};
    let spot = null;
    // SPY: the beacon's age_s is ALWAYS 0 at write time -- compute real age from
    // ts_utc. The beacon only runs during RTH, so after the close it's the last
    // print, and we say so rather than implying it's live.
    try {
      const b = readJson(root, "automation", "state", "sight-beacon.json");
      spot = typeof b.spy === "number" ? b.spy : null;
      out.spy = spot;
      out.ribbon = b.ribbon_stack || null;
      let ageMin = null;
      if (b.ts_utc) ageMin = Math.round((Date.now() - new Date(b.ts_utc).getTime()) / 60000);
      out.spy_freshness =
        ageMin === null
          ? "unknown age"
          : ageMin <= 3
          ? "live (" + ageMin + " min ago)"
          : "last print " + ageMin + " min ago (feed only runs during market hours)";
    } catch (e) {
      out.spy = "beacon read failed: " + e.message;
    }
    // VIX from the loop-state cache (not in the beacon).
    try {
      const ls = readJson(root, "automation", "state", "loop-state.json");
      if (ls.vix_cache && ls.vix_cache.value != null) {
        out.vix = ls.vix_cache.value;
        out.vix_dir = ls.vix_cache.dir || null;
      }
    } catch {
      /* optional */
    }
    // Bias + nearest levels from key-levels.json (tier is the importance proxy).
    try {
      const kl = readJson(root, "automation", "state", "key-levels.json");
      if (kl.session_bias) {
        out.bias = kl.session_bias.direction + (kl.session_bias.confidence ? " (" + kl.session_bias.confidence + ")" : "");
      }
      if (spot == null && typeof kl.spot_at_compute === "number") { spot = kl.spot_at_compute; out.spy = out.spy || spot; }
      const lv = (kl.levels || []).filter((l) => l && typeof l.price === "number");
      const isRes = (l) => /resist/i.test(String(l.role || l.type || ""));
      const isSup = (l) => /support/i.test(String(l.role || l.type || ""));
      out.nearest_resistance = lv
        .filter((l) => isRes(l) && (spot == null || l.price >= spot))
        .map((l) => l.price).sort((a, b) => a - b).slice(0, 2);
      out.nearest_support = lv
        .filter((l) => isSup(l) && (spot == null || l.price <= spot))
        .map((l) => l.price).sort((a, b) => b - a).slice(0, 2);
    } catch (e) {
      out.levels = "key-levels read failed: " + e.message;
    }
    return Promise.resolve(JSON.stringify(out));
  } catch (e) {
    return Promise.resolve("market_now ERROR: " + e.message);
  }
}

// ---------------------------------------------------------------------------
// recent_trades  (last N journaled fills from trades.csv)
// ---------------------------------------------------------------------------

function recentTrades(root) {
  try {
    const raw = fs
      .readFileSync(path.join(root, "journal", "trades.csv"), "utf8")
      .replace(/^﻿/, ""); // strip the BOM on the header
    const lines = raw.split(/\r?\n/).filter((l) => l.trim().length);
    if (lines.length < 2) return Promise.resolve(JSON.stringify({ note: "no trades journaled yet" }));
    const header = lines[0].split(",");
    const at = (name) => header.indexOf(name);
    // Only columns BEFORE the free-text notes col are comma-safe; account_id is
    // the LAST field, so read it positionally to survive commas in notes.
    const iDate = at("date"), iSetup = at("setup"), iStrike = at("strike"),
      iCP = at("c_or_p"), iQty = at("qty"), iPnl = at("dollar_pnl");
    const rows = lines.slice(1).slice(-5).map((ln) => {
      const c = ln.split(",");
      const pnl = iPnl >= 0 && c[iPnl] !== undefined && c[iPnl] !== "" ? Number(c[iPnl]) : null;
      return {
        date: c[iDate],
        setup: c[iSetup] || null,
        strike: c[iStrike] || null,
        side: c[iCP] || null,
        qty: c[iQty] || null,
        pnl_usd: Number.isFinite(pnl) ? pnl : null,
        account: c[c.length - 1] || null,
      };
    });
    const sum = rows.reduce((s, r) => s + (Number.isFinite(r.pnl_usd) ? r.pnl_usd : 0), 0);
    return Promise.resolve(
      JSON.stringify({
        note: "last " + rows.length + " journaled fills, oldest first; these are the last RECORDED fills, not necessarily today",
        trades: rows,
        sum_pnl_usd: Math.round(sum * 100) / 100,
      })
    );
  } catch (e) {
    return Promise.resolve("recent_trades ERROR: " + e.message);
  }
}

// ---------------------------------------------------------------------------

// State handlers take (root); the brain takes (root, args, opts) for its question.
const handlers = {
  engine_state: engineState,
  funnel_today: funnelToday,
  evening_debrief: eveningDebrief,
  kitchen_status: kitchenStatus,
  account_pnl: accountPnl,
  market_now: marketNow,
  recent_trades: recentTrades,
  ask_gamma_brain: (root, args, opts) => askGammaBrain(root, args && args.question, opts),
};

// Dispatch by name; ALWAYS resolves to a string the model can speak. args carries
// tool arguments (only ask_gamma_brain uses them); opts carries a { log } passthrough.
function runTool(root, name, args, opts) {
  const h = handlers[name];
  if (!h) return Promise.resolve("unknown tool: " + name);
  return Promise.resolve(h(root, args || {}, opts || {})).catch(
    (e) => name + " ERROR: " + ((e && e.message) || e)
  );
}

module.exports = { toolSchemas, runTool };
