"""trade_autopsy.py -- the missing organ: Gamma forms its own hypotheses from its own losses.

WHY THIS EXISTS (J, 2026-07-08: "why doesn't Gamma think 'maybe we're stopping out too early'?
I need to stop having to prompt every single step"). Diagnosis: every autonomous loop was a
parameter-tuner (kitchen/chef/grinders) or a compliance-checker (analyst EOD) -- NO organ owned
"look at our own fills and ask why the money died." The 40/45-winners-stopped-first fact sat in
the fills-ledger for two weeks until J asked. This module is the standing fix: EVERY close it
autopsies EVERY real engine fill, replays counterfactuals through the LIVE exit_manager on real
1-min bars, tags the failure mechanism, and EMITS STRUCTURED HYPOTHESES into the queues the
kitchen/chef/conductor already consume. J reads one line in the firm-brief; the hypotheses flow
to the test machinery without anyone prompting.

The loop this closes (OP-33e -- the repeated question becomes an instrument):
    fills-ledger (broker truth, Gamma_BrokerFills)
      -> per-trade counterfactual replay (esp.replay_position = live exit_manager core)
      -> mechanism tags (stopped_then_paid / entry_spike / rode_winner_back / stop_cost $)
      -> rolling detectors -> hypothesis rows (automation/state/hypothesis-queue.jsonl)
      -> queue.md task blocks (conductor/chef intake) + Discord one-liner + firm-brief line.

Notify-only, $0 beyond the bar fetches, exits 0 always (a broken autopsy must never block
anything). Counterfactual shapes reference the STOP-A study; nothing here changes any live
shape (STOP-A/B governance untouched). Guard: backtest/tests/test_trade_autopsy.py.

FLEET-BLINDNESS FIX (2026-07-09 evening, HANDOFF-2026-07-09-TRUTH-AND-EXITS): the first live
fire (16:15 ET) wrote "No closed engine positions today" despite 10 real fleet round trips
sitting in the ledger. Root cause was NOT a core-only arm filter -- load_engine_positions()
already scoped to ANY arm (fleet_rest AND core, see its docstring), so `positions` was
non-empty at that fire. Every position was silently dropped one level down: autopsy_position()
called esp.fetch_option_bars() per symbol and got zero bars back for BOTH of today's 0DTE
contracts at T+15min from the 16:00 ET close (OPRA options-bar indexing lag for a
just-expired series) -- confirmed by re-running the identical pure logic against the
byte-unchanged ledger hours later and getting all 10 positions with 396 real bars each.
`if not bars: return None` collapsed that into the EXACT same "0 positions" render path as a
genuinely flat day (OP-33/C7 silent-success-is-failure). Fix, in order:
  (a) fetch_bars_cached() retries empty bars with backoff before giving up, and caches per
      symbol (several fleet arms routinely fill the SAME signal within the same second, so
      this also cuts redundant API calls, e.g. today's 10 positions -> 2 unique symbols).
  (b) main()/render_md()/queue_ping() now distinguish "0 positions in the ledger" (silent,
      still a real flat day -- unchanged message) from "N positions found but 0 replayable"
      (NEVER silent -- a distinct message + Discord ping; the autopsy is marked INCOMPLETE,
      not flat, so it can never again look like nothing happened).
  (c) every autopsied row is now tagged with `strategy` (joined from the arm's PERMANENT
      decision log -- decisions.jsonl / core-decisions.jsonl are never cleaned up -- by
      matching the entry order's broker-reported UTC created_at to the fill's entry_ts_utc)
      and `stop_mode` (best-effort from the arm's exit-state.json when the position is still
      resolvable there; exit_actuator clears a symbol's entry once flat, so this is usually
      None for a same-day-closed position by 16:15 ET -- expected, not a bug) so future
      autopsies can compare structure-stop (v15.3 chart-stop-primary, still flag-gated off
      per the STOP checkpoint) exits against premium-stop history once structure mode ships
      live. Read-only: no fleet_broker order-placement/cancel method is called anywhere in
      this module or its new helpers (guard: test_autopsy_never_calls_broker_mutators).
Guard: backtest/tests/test_trade_autopsy.py.

TWIN (mechanism) SECTION (B2c, 2026-07-11, markdown/planning/TWIN-PROGRAM.md): a
SEPARATE, clearly-labeled "## TWIN (mechanism)" section appended to the SAME daily
.md, sourcing the crypto twin's OWN journal.jsonl (automation/state/crypto-twin/) --
NEVER the SPY fills-ledger. Doctrine rail (non-negotiable, enforced by
test_trade_autopsy_twin_section.py's static + behavioral bite tests): the twin
validates MECHANISM, never edge -- no $ P&L counterfactual replay runs here, only
whether each close's `stage`/`reason` matches the coded exit_manager vocabulary.
Twin-derived hypotheses land in automation/state/crypto-twin/twin-hypotheses.jsonl
(a CODE-fix-only lane) and are NEVER written to hypothesis-queue.jsonl -- the main
SPY hypothesis queue chef/conductor treat as edge-adjacent intake. A twin failure
must never block the SPY autopsy above it, and vice versa (separate try/except in
main()). Guard: backtest/tests/test_trade_autopsy_twin_section.py.

Usage:
    backtest/.venv/Scripts/python.exe setup/scripts/trade_autopsy.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "trade-autopsy.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "trade-autopsy.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import json
import sys
import time as _time_mod
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet",
           REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402

STATE = REPO / "automation" / "state"
LEDGER = STATE / "fills-ledger.jsonl"
OUT_DIR = REPO / "analysis" / "autopsies"
LAST_JSON = STATE / "trade-autopsy-last.json"
HYP_QUEUE = STATE / "hypothesis-queue.jsonl"
QUEUE_MD = REPO / "automation" / "overnight" / "queue.md"
OUTBOX = STATE / "discord-outbox.jsonl"
LENS = "markdown/trading-knowledge/GENERATIVE-LENS.md"

# Arm/account taxonomy -- mirrors broker_fills.py's FLEET_REST_ARMS / CORE_ARMS EXACTLY (the
# ledger's own attribution rule already encodes this split; duplicated here only as small
# stable literals -- same pattern exit_shape_parity_study.py already uses -- so this module
# stays importable/testable without pulling broker_fills' heavier network-adjacent surface
# into scope at import time). Source of truth: setup/scripts/broker_fills.py.
# DELIBERATELY KEEPS "safe-1" even though broker_fills.py's OWN FLEET_REST_ARMS dropped it
# 2026-07-11 (safe-1 retired, account reassigned to core Safe/safe-2) -- the two constants
# serve DIFFERENT purposes and must NOT mirror on this one point. broker_fills.py's tuple
# decides attribution for a fill it just saw (must exclude safe-1 so a future core-Safe fill
# routes through CORE_ARM_ACCOUNT, not fleet_rest -- see that file's comment). THIS tuple only
# decides which FILE FORMAT to look up EXISTING ledger rows against (fleet/{arm}/decisions.jsonl
# vs core-decisions.jsonl-by-account) -- historical safe-1 fills are real and still need this
# path to resolve their setup_name/stop_mode. Dropping safe-1 here was tried and reverted after
# it broke test_lookup_strategy_fleet_arm_matches_by_broker_created_at +
# test_lookup_stop_mode_reads_exit_state_when_present (safe-1's real historical data went
# unreadable). Future safe-2-labeled fills are unaffected either way (arm=="safe-2" was never
# in this tuple, so its CORE_ARM_ACCOUNT routing is unchanged by safe-1's presence/absence here).
FLEET_REST_ARMS = ("safe-1", "safe-3", "risky-1", "risky-3")
CORE_ARM_ACCOUNT = {"safe-2": "safe", "bold-2": "bold"}  # arm -> core-decisions.jsonl `account`
CORE_DECISIONS = STATE / "core-decisions.jsonl"

# Bars-availability retry (the fix for the 2026-07-09 miss): bounded, only costs anything on
# the failure path (a normal day's first fetch succeeds and no retry ever sleeps).
BARS_RETRY_BACKOFF_SEC = (15.0, 30.0, 60.0)  # ~105s worst case per unique symbol

# Counterfactual menu -- the mechanism probes (NOT candidates; candidates live in the STOP-A
# pre-registration). Each answers ONE question about a dead trade.
COUNTERFACTUALS = {
    "wide_stop_-50": {   # "was the stop inside the noise floor?" (exit-A body)
        "premium_stop_pct": -0.50, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.667,
        "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9},
    "no_stop_ride": {    # "what was the thesis worth with no stop at all?"
        "premium_stop_pct": -0.95, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.667,
        "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9},
    "hold_to_time": {    # "does pure theta-ride beat what we did?"
        "premium_stop_pct": -0.95, "tp1_premium_pct": 999.0, "tp1_qty_fraction": 1.0,
        "profit_lock_mode": "fixed", "trail_pct": 0.0, "runner_target_pct": 999.0},
}

# Rolling-window hypothesis detectors: thresholds are the "is this a pattern yet" bar.
ROLL_N = 30                # positions in the rolling window
MIN_LOSERS = 6             # need at least this many losers before the stop-noise claim
STOP_NOISE_FRAC = 0.60     # >=60% of losers stopped-then-paid => hypothesis
ENTRY_SPIKE_MED = 0.08     # median paid-above-minute-low >= 8% => hypothesis
LEFT_TABLE_MIN = 300.0     # $ left on table (best-counterfactual delta) to matter
HYP_DEDUPE_DAYS = 7        # one emission per mechanism per week

# --- TWIN (mechanism) autopsy -- separate namespace, CODE-fix-only lane ------------------
# See module docstring's "TWIN (mechanism) SECTION". Doctrine: automation/state/crypto-twin/
# is B1's namespace (crypto_twin_core.py) -- this module only READS its journal.jsonl, never
# writes into it.
TWIN_STATE = STATE / "crypto-twin"
TWIN_JOURNAL = TWIN_STATE / "journal.jsonl"
TWIN_HYP_QUEUE = TWIN_STATE / "twin-hypotheses.jsonl"
# Deliberately a SUBDIRECTORY of OUT_DIR, not a `twin-` prefixed file directly inside it --
# load_recent_rows() globs OUT_DIR / "*.jsonl" for the SPY rolling window; a twin day-file
# living alongside the SPY ones would silently mix twin rows (no `actual_pnl` key, alien
# shape) into the SPY hypothesis detectors. A subdirectory is invisible to that non-recursive
# glob by construction, not by a "please remember" convention.
TWIN_OUT_DIR = OUT_DIR / "twin"

# exit_manager.ExitAction.stage literals (automation/state/fleet/exit_manager.py) + the two
# twin-native non-exit_manager close reasons (max-hold flatten guard, already-flat prune).
KNOWN_EXIT_STAGES = {"structure_stop", "premium_stop", "time_stop", "ribbon_flip",
                     "tp1", "trail", "runner_target", "be_stop", "arm"}
KNOWN_CLOSE_REASONS = {"max_hold_flatten", "broker shows flat"}

TWIN_ROLL_N = 20           # twin closes in the rolling window (twin ticks 24/7 -> denser than SPY)
TWIN_MIN_ANOMALIES = 3     # need at least this many same-tag anomalies before claiming a pattern
TWIN_HYP_DEDUPE_DAYS = 7   # one emission per mechanism per week (reuses dedupe_hypotheses)

# mechanism -> (claim prose, proposed CODE-only tests). CODE fixes only -- never a parameter
# or edge claim (TWIN-PROGRAM.md doctrine rail).
_TWIN_MECHANISM_COPY = {
    "broker_call_failed_on_close": (
        "the broker close call returned an error/refused/skipped marker on a CLOSED journal "
        "event -- the position may be marked closed locally while the broker never actually "
        "confirmed it (a CODE bug in the close-confirmation path, not a BTC market condition).",
        ["add a poll_fill-style confirmation after market_sell_crypto/close_all_crypto before "
         "writing a CLOSED journal row",
         "add a regression guard rejecting a CLOSED row whose broker dict carries _error/_refused"]),
    "external_flat_detected": (
        "the twin found itself flat on the broker without its own exit logic having closed the "
        "position (FLAT_PRUNED) -- something OTHER than exit_manager closed it (a missed tick, "
        "a manual intervention, or a race) -- a CODE gap worth tracing.",
        ["add a journal marker distinguishing 'we closed it' from 'we discovered it already "
         "closed' so this is visible without cross-referencing reason strings",
         "audit tick cadence around the affected timestamps for a gap"]),
    "unknown_exit_stage": (
        "a CLOSED/MANAGED row carries a `stage` string outside exit_manager's known vocabulary "
        "-- either a new/uncovered exit_manager branch or a typo'd stage literal (a CODE fix, "
        "not an edge finding).",
        ["diff the offending stage string against automation/state/fleet/exit_manager.py's "
         "ExitAction.stage literals",
         "add the new stage to trade_autopsy.py's KNOWN_EXIT_STAGES once confirmed intentional"]),
    "unlabeled_close": (
        "a CLOSED row carries neither a known exit_manager stage nor a known twin-native close "
        "reason -- an unlabeled/undocumented close path exists.",
        ["trace the offending journal row's code path and add an explicit stage/reason label"]),
}


# ---------- pure helpers (unit-tested; no I/O) ---------------------------------------------

def classify_position(actual_pnl: float, entry_price: float, entry_bar_low: float,
                      post_exit_high: float | None, cf_pnls: dict) -> dict:
    """Mechanism tags for ONE closed position. All inputs are plain numbers (testable).

    post_exit_high: highest premium AFTER the actual exit (None = no bars after / unknown).
    cf_pnls: {name: pnl} for the counterfactual replays (missing entries tolerated).
    """
    best_cf_name, best_cf = None, None
    for k, v in cf_pnls.items():
        if v is not None and (best_cf is None or v > best_cf):
            best_cf_name, best_cf = k, v
    stop_cost = round(best_cf - actual_pnl, 2) if best_cf is not None else None
    tags = []
    if actual_pnl < 0 and post_exit_high is not None and post_exit_high >= entry_price:
        tags.append("stopped_then_paid")           # the 741P class: loss, then thesis paid
    if stop_cost is not None and stop_cost > 25.0:
        tags.append("exit_shape_cost")             # a probe shape beat what we did
    entry_spike = None
    if entry_bar_low and entry_bar_low > 0:
        entry_spike = round(entry_price / entry_bar_low - 1.0, 4)
        if entry_spike >= 0.10:
            tags.append("paid_the_spike")          # defect #2: bought the signal-bar spike
    if (actual_pnl < 0 and cf_pnls.get("hold_to_time") is not None
            and cf_pnls["hold_to_time"] < actual_pnl):
        tags.append("exit_beat_theta")             # our exit was RIGHT vs riding (honesty tag)
    return {"tags": tags, "stop_cost_vs_best": stop_cost, "best_counterfactual": best_cf_name,
            "entry_spike_pct": entry_spike}


def detect_hypotheses(rows: list[dict], today: str) -> list[dict]:
    """Rolling-window detectors over autopsy rows (newest last). Pure. Each hypothesis is a
    STRUCTURED, testable claim with quoted evidence and concrete next tests."""
    window = rows[-ROLL_N:]
    losers = [r for r in window if r["actual_pnl"] < 0]
    hyps = []
    if len(losers) >= MIN_LOSERS:
        stp = [r for r in losers if "stopped_then_paid" in r.get("tags", [])]
        frac = len(stp) / len(losers)
        if frac >= STOP_NOISE_FRAC:
            hyps.append({
                "id": f"H-{today}-stop-noise", "mechanism": "stop_inside_noise_floor",
                "claim": "the live stop exits losers that then pay the thesis -- the stop is "
                         "harvesting winners, not cutting losers",
                "evidence": {"losers_in_window": len(losers), "stopped_then_paid": len(stp),
                             "fraction": round(frac, 3), "window_n": len(window)},
                "proposed_tests": [
                    "replay exit-A (-50/+150/sell66/trail15) on these exact fills via "
                    "exit_shape_parity_study (kill-check)",
                    "confirm on the fresh OPRA slice per the STOP-A pre-registration (T-W7)",
                ]})
    spikes = [r["entry_spike_pct"] for r in window if r.get("entry_spike_pct") is not None]
    if len(spikes) >= 8:
        med = sorted(spikes)[len(spikes) // 2]
        if med >= ENTRY_SPIKE_MED:
            hyps.append({
                "id": f"H-{today}-entry-spike", "mechanism": "paying_the_signal_spike",
                "claim": "entries fill materially above the signal-minute low -- the marketable "
                         "ask+buffer buys the local premium spike (defect #2)",
                "evidence": {"median_paid_above_min_low": round(med, 3), "n": len(spikes)},
                "proposed_tests": [
                    "entry_manager shadow (T-W5): log limit-below/patience counterfactual fills "
                    "next to real entries for 3+ sessions",
                ]})
    costs = [r["stop_cost_vs_best"] for r in window
             if r.get("stop_cost_vs_best") is not None and r["stop_cost_vs_best"] > 0]
    actual_sum = sum(r["actual_pnl"] for r in window)
    if costs and sum(costs) >= LEFT_TABLE_MIN and sum(costs) >= 2 * abs(actual_sum):
        hyps.append({
            "id": f"H-{today}-left-on-table", "mechanism": "exit_shape_dominated",
            "claim": "a fixed counterfactual shape beats the shipped exits by more than 2x the "
                     "window's net P&L -- the exit shape, not the signal, is the bottleneck",
            "evidence": {"sum_stop_cost": round(sum(costs), 2), "window_net_pnl": round(actual_sum, 2),
                         "n_dominated": len(costs), "window_n": len(window)},
            "proposed_tests": [
                "STOP-A sign-off -> T-W7 confirmatory on the frozen v2 candidates",
                f"enumerate levers beyond exit shape per {LENS} (DTE / spread / strike / sizing)",
            ]})
    return hyps


def dedupe_hypotheses(new: list[dict], existing_rows: list[dict], today: str) -> list[dict]:
    """One emission per mechanism per HYP_DEDUPE_DAYS. Pure. Generic over the
    `mechanism`/`date` keys only -- reused verbatim for TWIN hypotheses below
    (no SPY-specific coupling)."""
    cutoff = (datetime.fromisoformat(today) - timedelta(days=HYP_DEDUPE_DAYS)).date().isoformat()
    recent = {r.get("mechanism") for r in existing_rows
              if str(r.get("date", "")) >= cutoff}
    return [h for h in new if h["mechanism"] not in recent]


# ---------- TWIN (mechanism) pure helpers -- CODE-fix-only lane (B2c) ----------------------

def classify_twin_close(row: dict) -> dict:
    """PURE mechanism classifier for ONE twin CLOSED journal event
    (automation/state/crypto-twin/journal.jsonl). Doctrine rail
    (markdown/planning/TWIN-PROGRAM.md): twin findings are CODE-mechanism only --
    this NEVER touches $ P&L, only whether the close mechanism behaved as coded
    (its `stage`/`reason` is a member of the KNOWN vocabulary, and the broker
    call it carries didn't itself fail)."""
    tags: list[str] = []
    stage = row.get("stage")
    reason = str(row.get("reason") or "")
    broker = row.get("broker") if isinstance(row.get("broker"), dict) else None
    if broker and (broker.get("_error") or broker.get("_refused")):
        tags.append("broker_call_failed_on_close")
    if reason == "broker shows flat":
        tags.append("external_flat_detected")
    elif stage is not None and stage not in KNOWN_EXIT_STAGES:
        tags.append("unknown_exit_stage")
    elif stage is None and reason not in KNOWN_CLOSE_REASONS:
        tags.append("unlabeled_close")
    return {"tags": tags, "mechanism_ok": len(tags) == 0, "stage": stage, "reason": reason}


def detect_twin_hypotheses(rows: list[dict], today: str) -> list[dict]:
    """Rolling-window CODE-MECHANISM detectors over twin CLOSED events (each row
    must already carry a "tags" list from classify_twin_close -- newest last).
    Pure. Every hypothesis proposes a CODE fix only -- never a parameter/edge
    claim, never references $ P&L (doctrine rail, TWIN-PROGRAM.md)."""
    window = rows[-TWIN_ROLL_N:]
    if not window:
        return []
    tag_hits: dict[str, list[dict]] = {}
    for r in window:
        for t in r.get("tags", []):
            tag_hits.setdefault(t, []).append(r)
    hyps = []
    for tag, hits in tag_hits.items():
        if len(hits) < TWIN_MIN_ANOMALIES:
            continue
        claim, tests = _TWIN_MECHANISM_COPY.get(tag, (
            f"{len(hits)} twin closes tagged '{tag}' in the last {len(window)} -- an exit-"
            f"mechanism anomaly worth a CODE fix, not a parameter change.",
            [f"add a regression guard asserting no twin CLOSED row tags '{tag}'"]))
        hyps.append({
            "id": f"H-TWIN-{today}-{tag}", "mechanism": tag, "claim": claim,
            "evidence": {"n_hits": len(hits), "window_n": len(window),
                        "examples": [{"ts_utc": h.get("ts_utc"), "reason": h.get("reason"),
                                     "stage": h.get("stage")} for h in hits[:3]]},
            "proposed_tests": tests,
        })
    return hyps


def _closest_broker_created_row(rows: list[dict], symbol: str, entry_ts_utc: str,
                                block_key: str, max_delta_sec: float = 120.0) -> dict | None:
    """PURE: the decision row whose `<block_key>.broker.created_at` (Alpaca's own UTC order
    timestamp) is closest to `entry_ts_utc` (the fill's UTC timestamp), among rows whose
    `<block_key>.symbol == symbol`, within max_delta_sec. Both timestamps are broker-issued
    UTC ISO-8601 ("...Z"), so this needs no ET/offset reasoning at all -- deliberately
    avoids matching on the ET-naive `ts_et` fields, which differ in shape between fleet
    decisions.jsonl (offset-qualified) and core-decisions.jsonl (naive). `block_key` is
    "placement" for fleet rows, "exec" for core rows. None when no row's symbol matches, or
    none has a parseable created_at within the window (never raises)."""
    try:
        target = datetime.fromisoformat(str(entry_ts_utc).replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    best_row, best_delta = None, None
    for r in rows:
        blk = r.get(block_key)
        if not isinstance(blk, dict) or blk.get("symbol") != symbol:
            continue
        broker = blk.get("broker")
        created = broker.get("created_at") if isinstance(broker, dict) else None
        if not created:
            continue
        try:
            row_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        delta = abs((row_dt - target).total_seconds())
        if delta <= max_delta_sec and (best_delta is None or delta < best_delta):
            best_row, best_delta = r, delta
    return best_row


# ---------- I/O layer ----------------------------------------------------------------------

def load_engine_positions(date_et: str, ledger_path: Path = LEDGER) -> list[dict]:
    """Closed engine option positions for date_et from the broker-truth ledger -- ANY arm
    (fleet_rest AND core), attribution=='engine' (broker_fills' pre-decided rule).

    `ledger_path` is injectable for tests; production always uses the module-level LEDGER."""
    import exit_shape_parity_study as esp
    if not ledger_path.exists():
        return []
    fills = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if (r.get("attribution") == "engine" and r.get("is_option")
                and not r.get("is_crypto")):
            fills.append(r)
    positions = esp.reconstruct_positions(fills)
    return [p for p in positions if p["date_et"] == date_et and p["exit_fills"]]


def load_decision_rows(path: Path) -> list[dict]:
    """Generic jsonl loader for a decision ledger (fleet per-arm or core). [] on a missing
    file; malformed lines are skipped. This ledger is append-only and NEVER pruned (unlike
    exit-state.json), so it is the durable source for retrospective attribution."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def lookup_strategy(arm: str, symbol: str, entry_ts_utc: str) -> str | None:
    """Best-effort strategy/setup name for one closed position, joined from the arm's
    PERMANENT decision log (never cleaned up, unlike exit-state.json) by matching the entry
    order's broker-reported created_at (UTC) to the fill's entry_ts_utc. None on any miss --
    attribution is best-effort and must never distort or block an autopsy row."""
    try:
        if arm in FLEET_REST_ARMS:
            rows = load_decision_rows(STATE / "fleet" / arm / "decisions.jsonl")
            row = _closest_broker_created_row(rows, symbol, entry_ts_utc, "placement")
            return row.get("setup_name") if row else None
        account = CORE_ARM_ACCOUNT.get(arm)
        if account is None:
            return None
        rows = [r for r in load_decision_rows(CORE_DECISIONS) if r.get("account") == account]
        row = _closest_broker_created_row(rows, symbol, entry_ts_utc, "exec")
        return row.get("setup") if row else None
    except Exception:  # noqa: BLE001 -- attribution is best-effort, never fatal
        return None


def lookup_stop_mode(arm: str, symbol: str) -> str | None:
    """Best-effort stop_mode ('premium' | 'structure', see exit_manager.ExitState) for one
    position, read from the arm's LIVE exit-state.json IF the position is still tracked
    there. exit_actuator removes a symbol's entry once the position is fully flat, so this is
    routinely None for a same-day-closed position by the time the 16:15 ET autopsy runs --
    that is EXPECTED, not a bug (the task's own "if present" scoping). Fleet arms only:
    core arms (mcp_heartbeat execution) persist exit state via a different mechanism
    (current-position.json) that this module does not read -- returning None there is
    honest absence, not a guess. Never raises."""
    if arm not in FLEET_REST_ARMS:
        return None
    path = STATE / "fleet" / arm / "exit-state.json"
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        rec = data.get(symbol) if isinstance(data, dict) else None
        return rec.get("stop_mode") if isinstance(rec, dict) else None
    except (OSError, ValueError):
        return None


def fetch_bars_cached(esp, symbol: str, date_et: str, cache: dict,
                      sleep_fn=_time_mod.sleep) -> list[dict]:
    """Bars for (symbol, date_et), retried with backoff on empty before giving up (the
    2026-07-09 fix -- 0DTE OPRA options bars can still be indexing at T+15min from the 16:00
    ET close, which is exactly when Gamma_TradeAutopsy fires). Cached per (symbol, date_et)
    so multiple positions sharing a symbol -- the common case, several fleet arms routinely
    fill the SAME signal within the same second -- only fetch/retry once. A normal day (bars
    already available) never sleeps at all; the backoff only costs time on the failure path.
    `sleep_fn` is injectable for tests. Never raises -- worst case returns []."""
    key = (symbol, date_et)
    if key in cache:
        return cache[key]
    bars = esp.fetch_option_bars(symbol, date_et)
    for attempt, wait_s in enumerate(BARS_RETRY_BACKOFF_SEC, start=1):
        if bars:
            break
        print(f"[autopsy] {symbol} {date_et}: 0 bars (attempt {attempt}), "
              f"retrying in {wait_s:.0f}s", file=sys.stderr)
        sleep_fn(wait_s)
        bars = esp.fetch_option_bars(symbol, date_et)
    if not bars:
        print(f"[autopsy] {symbol} {date_et}: still 0 bars after "
              f"{len(BARS_RETRY_BACKOFF_SEC)} retries -- giving up for this run", file=sys.stderr)
    cache[key] = bars
    return bars


def autopsy_position(pos: dict, esp, bars: list[dict]) -> dict | None:
    """Replay one position's counterfactual menu on real 1-min bars. None if bars missing
    (the caller is responsible for fetching/retrying `bars` -- see fetch_bars_cached)."""
    if not bars:
        return None
    entry_ts = pos["entry_ts_utc"]
    entry_price = pos["entry_price"]
    path = [b for b in bars if b["t"] >= entry_ts]
    if not path:
        return None
    entry_bar_low = float(path[0]["l"])
    mfe = max(b["h"] for b in path) / entry_price - 1.0
    mae = min(b["l"] for b in path) / entry_price - 1.0
    exit_ts = max(ef["ts_utc"] for ef in pos["exit_fills"])
    post = [b for b in path if b["t"] > exit_ts]
    post_exit_high = max((b["h"] for b in post), default=None)
    cf_pnls = {}
    for name, shape in COUNTERFACTUALS.items():
        r = esp.replay_position(pos, bars, shape)
        cf_pnls[name] = r.get("pnl")
    cls = classify_position(pos["actual_exit_pnl"], entry_price, entry_bar_low,
                            post_exit_high, cf_pnls)
    return {
        "date": pos["date_et"], "arm": pos["arm"],
        "strategy": lookup_strategy(pos["arm"], pos["symbol"], entry_ts),
        "stop_mode": lookup_stop_mode(pos["arm"], pos["symbol"]),
        "symbol": pos["symbol"],
        "entry_ts_utc": entry_ts, "entry_price": entry_price, "qty": pos["entry_qty"],
        "actual_pnl": round(pos["actual_exit_pnl"], 2),
        "mfe_pct": round(mfe, 3), "mae_pct": round(mae, 3),
        "counterfactuals": cf_pnls, **cls,
    }


def load_recent_rows(days: int = 21) -> list[dict]:
    rows = []
    if OUT_DIR.exists():
        for f in sorted(OUT_DIR.glob("*.jsonl"))[-days:]:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
    return rows


def load_hypothesis_rows() -> list[dict]:
    if not HYP_QUEUE.exists():
        return []
    out = []
    for line in HYP_QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


# ---------- TWIN (mechanism) I/O -- reads B1's journal, writes ONLY the twin-only lane -----

def load_twin_closed_events(date_et: str, journal_path: Path = TWIN_JOURNAL) -> list[dict]:
    """CLOSED events from the twin's OWN journal.jsonl whose ts_utc calendar date
    matches `date_et`. Deliberately matched against the UTC calendar date portion
    of ts_utc, NOT an ET conversion -- the twin is UTC-day anchored (TWIN-PROGRAM.md:
    "session = UTC day" -- same anchor crypto_twin_core.py's breaker uses), unlike
    the SPY autopsy's date_et, which IS an ET trading day. [] on a missing/empty
    journal -- a quiet day (this module never writes to journal.jsonl -- read-only)."""
    if not journal_path.exists():
        return []
    out = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("event") != "CLOSED":
            continue
        if str(row.get("ts_utc", ""))[:10] == date_et:
            out.append(row)
    return out


def load_recent_twin_rows(days: int = 21) -> list[dict]:
    """Mirrors load_recent_rows() but reads TWIN_OUT_DIR (analysis/autopsies/twin/)
    -- a SEPARATE directory so this never mixes with load_recent_rows()'s SPY glob
    (see TWIN_OUT_DIR's module-level comment)."""
    rows = []
    if TWIN_OUT_DIR.exists():
        for f in sorted(TWIN_OUT_DIR.glob("*.jsonl"))[-days:]:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
    return rows


def load_twin_hypothesis_rows() -> list[dict]:
    if not TWIN_HYP_QUEUE.exists():
        return []
    out = []
    for line in TWIN_HYP_QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def append_twin_queue_md(hyps: list[dict], date_et: str, *, queue_md: Path = QUEUE_MD) -> None:
    """Distinctly-tagged queue.md entries (T-TWIN-AUTOPSY- prefix, [TWIN/CODE-ONLY]
    label) so a human/conductor scanning queue.md can never mistake these for SPY
    hypotheses -- queue.md is the general work-backlog file (not the doctrine-
    restricted hypothesis-queue.jsonl), so surfacing twin CODE-fix items here is
    fine; landing them in hypothesis-queue.jsonl itself is NOT (see
    write_twin_hypotheses)."""
    if not hyps:
        return
    try:
        with queue_md.open("a", encoding="utf-8") as fh:
            for h in hyps:
                fh.write(f"\n### T-TWIN-AUTOPSY-{h['id']} MED — [TWIN/CODE-ONLY] mechanism "
                         f"hypothesis: {h['mechanism']}\n\n"
                         f"**Claim:** {h['claim']} **Evidence:** `{json.dumps(h['evidence'])}` "
                         f"(analysis/autopsies/{date_et}.md).\n"
                         f"**Action:** {' · '.join(h['proposed_tests'])} "
                         f":: depends:none :: status:proposed\n")
    except OSError as e:
        print(f"[autopsy] WARN twin queue.md append failed: {e}", file=sys.stderr)


def write_twin_hypotheses(hyps: list[dict], date_et: str, *,
                          twin_hyp_queue: Path = TWIN_HYP_QUEUE, queue_md: Path = QUEUE_MD) -> None:
    """Writes NEW twin hypotheses to the TWIN-ONLY lane. DOCTRINE RAIL (non-
    negotiable, enforced by test_trade_autopsy_twin_section.py's static AST guard
    + a behavioral bite test): this function NEVER writes to HYP_QUEUE (the main
    hypothesis-queue.jsonl) -- twin-derived hypotheses may only propose CODE fixes
    and must stay structurally separate from SPY's hypothesis lane, which
    chef/conductor intake treats as edge-adjacent. `queue_md` is explicitly
    forwarded to append_twin_queue_md (not read off its own default) so an
    injected test path actually takes effect -- a bare default-parameter forward
    would silently keep pointing at the def-time-bound original (Python evaluates
    defaults once at def time, not per call)."""
    if not hyps:
        return
    with twin_hyp_queue.open("a", encoding="utf-8") as fh:
        for h in hyps:
            fh.write(json.dumps({**h, "date": date_et, "status": "proposed",
                                 "ts": et_now().isoformat(), "twin": True}) + "\n")
    append_twin_queue_md(hyps, date_et, queue_md=queue_md)


def render_twin_section_md(date_et: str, twin_rows: list[dict], twin_hyps: list[dict]) -> str:
    """Separate, clearly-labeled section for the twin's mechanism-only autopsy --
    NEVER mixed into the SPY engine table above it in the rendered .md. No $ P&L is
    computed or shown here (TWIN-PROGRAM.md kill criteria: twin P&L is a health
    gauge only, never an edge input) -- this section is exit-MECHANISM correctness
    only. `twin_rows` entries must each carry a "classification" key (see main()'s
    twin block, which attaches classify_twin_close's output before calling this)."""
    L = ["", "---", "", "## TWIN (mechanism) — BTC/USD crypto twin, CODE-fix-only lane", ""]
    L.append("_Mechanism-only per markdown/planning/TWIN-PROGRAM.md: never SPY P&L, never an "
             "edge claim, never a parameter proposal. Hypotheses here go to "
             "automation/state/crypto-twin/twin-hypotheses.jsonl, NEVER the main "
             "hypothesis-queue.jsonl._")
    L.append("")
    if not twin_rows:
        L.append(f"No twin CLOSED events on {date_et} (UTC-day). Nothing to autopsy.")
        return "\n".join(L) + "\n"
    n_ok = sum(1 for r in twin_rows if r["classification"]["mechanism_ok"])
    n_anom = len(twin_rows) - n_ok
    L.append(f"**{len(twin_rows)} twin close(s), {n_ok} clean / {n_anom} mechanism anomaly(ies).**")
    L.append("")
    L.append("| ts_utc | stage | reason | mechanism_ok | tags |")
    L.append("|---|---|---|---|---|")
    for r in twin_rows:
        c = r["classification"]
        L.append(f"| {r.get('ts_utc', '—')} | {c['stage'] or '—'} | {c['reason'] or '—'} "
                 f"| {'yes' if c['mechanism_ok'] else 'NO'} | {', '.join(c['tags']) or '—'} |")
    L.append("")
    if twin_hyps:
        L.append("### Twin hypotheses emitted (→ twin-hypotheses.jsonl, CODE-fix-only)")
        L.append("")
        for h in twin_hyps:
            L.append(f"- **{h['id']}** ({h['mechanism']}): {h['claim']} "
                     f"Evidence: `{json.dumps(h['evidence'])}`")
    else:
        L.append("_No new twin hypotheses this run._")
    return "\n".join(L) + "\n"


def render_md(date_et: str, rows: list[dict], hyps: list[dict], *,
             n_positions_found: int = 0, n_no_bars: int = 0) -> str:
    L = [f"# Trade autopsy — {date_et}", ""]
    if not rows:
        if n_positions_found > 0:
            # Positions existed in the broker-truth ledger but couldn't be replayed -- this
            # is NOT a flat day, and must never render/read like one (OP-33/C7).
            L.append(f"**INCOMPLETE — {n_positions_found} closed engine position(s) found in "
                     f"the broker-truth ledger, but bars data was unavailable for all "
                     f"{n_no_bars} of them after {len(BARS_RETRY_BACKOFF_SEC)} retries "
                     f"(likely OPRA options-bar indexing lag right after the 16:00 ET "
                     f"close). This is NOT a flat day. Re-run "
                     f"`backtest\\.venv\\Scripts\\python.exe setup\\scripts\\trade_autopsy.py "
                     f"--date {date_et}` once bars have landed.**")
            return "\n".join(L) + "\n"
        L.append("No closed engine positions today (broker-truth ledger). Nothing to autopsy.")
        return "\n".join(L) + "\n"
    total = sum(r["actual_pnl"] for r in rows)
    uniq = len(set((r["date"], r["symbol"]) for r in rows))
    L.append(f"**{len(rows)} closed engine positions ({uniq} unique signals) · net "
             f"{'+' if total >= 0 else ''}${total:.2f}.** Counterfactuals replayed through the "
             f"live exit_manager on real 1-min bars (frictionless fills at trigger levels).")
    L.append("")
    L.append("| symbol | arm | strategy | stop_mode | actual | MFE | MAE | best counterfactual | Δ vs best | tags |")
    L.append("|---|---|---|---|--:|--:|--:|---|--:|---|")
    for r in rows:
        bc = r.get("best_counterfactual") or "—"
        bc_pnl = r["counterfactuals"].get(bc) if bc != "—" else None
        L.append(f"| {r['symbol'][-9:]} | {r['arm']} | {r.get('strategy') or '—'} "
                 f"| {r.get('stop_mode') or '—'} "
                 f"| ${r['actual_pnl']} "
                 f"| {r['mfe_pct']*100:+.0f}% | {r['mae_pct']*100:+.0f}% "
                 f"| {bc} (${bc_pnl}) | ${r.get('stop_cost_vs_best', '—')} "
                 f"| {', '.join(r['tags']) or '—'} |")
    L.append("")
    if hyps:
        L.append("## Hypotheses emitted (→ hypothesis-queue.jsonl + queue.md)")
        L.append("")
        for h in hyps:
            L.append(f"- **{h['id']}** ({h['mechanism']}): {h['claim']}. "
                     f"Evidence: `{json.dumps(h['evidence'])}`")
    else:
        L.append("_No new hypotheses this run (below thresholds or deduped this week)._")
    L.append("")
    L.append(f"_Generated by trade_autopsy.py (Gamma_TradeAutopsy 16:15 ET). Lever menu: {LENS}._")
    return "\n".join(L) + "\n"


def append_queue_md(hyps: list[dict], date_et: str) -> None:
    if not hyps:
        return
    try:
        with QUEUE_MD.open("a", encoding="utf-8") as fh:
            for h in hyps:
                fh.write(f"\n### T-AUTOPSY-{h['id']} MED — autopsy hypothesis: {h['mechanism']}\n\n"
                         f"**Claim:** {h['claim']}. **Evidence:** `{json.dumps(h['evidence'])}` "
                         f"(analysis/autopsies/{date_et}.md).\n"
                         f"**Action:** {' · '.join(h['proposed_tests'])} "
                         f":: depends:none :: status:proposed\n")
    except OSError as e:
        print(f"[autopsy] WARN queue.md append failed: {e}", file=sys.stderr)


def queue_ping(date_et: str, rows: list[dict], hyps: list[dict], *,
              n_positions_found: int = 0, n_no_bars: int = 0,
              outbox_path: Path = OUTBOX) -> None:
    try:
        from trade_today_watcher import _load_user_mention
        mention = _load_user_mention()
    except Exception:  # noqa: BLE001
        mention = ""
    if not rows and n_positions_found == 0:
        return  # silent on genuinely no-trade days (don't spam)
    if not rows:
        # Positions existed but nothing could be replayed -- never silent (OP-33/C7): this
        # is a degraded/incomplete run, not a quiet flat day.
        msg = (f"{mention}[AUTOPSY] {date_et}: INCOMPLETE — {n_positions_found} closed engine "
               f"position(s) found but bars data was unavailable for all {n_no_bars} "
               f"(not a flat day). analysis/autopsies/{date_et}.md")
    else:
        total = sum(r["actual_pnl"] for r in rows)
        stp = sum(1 for r in rows if "stopped_then_paid" in r["tags"])
        hyp_s = (f" · {len(hyps)} new hypothesis(es): "
                 f"{', '.join(h['mechanism'] for h in hyps)}" if hyps else "")
        msg = (f"{mention}[AUTOPSY] {date_et}: {len(rows)} engine positions net ${total:.0f}; "
               f"{stp} stopped-then-paid{hyp_s}. analysis/autopsies/{date_et}.md")
    try:
        with outbox_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"content": msg, "source": "trade_autopsy",
                                 "queued_at": et_now().isoformat()}) + "\n")
    except OSError as e:
        print(f"[autopsy] WARN outbox append failed: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="ET date to autopsy (default: today ET)")
    args = ap.parse_args()
    date_et = args.date or et_now().date().isoformat()

    try:
        import exit_shape_parity_study as esp
        positions = load_engine_positions(date_et)
        bar_cache: dict = {}
        rows = []
        n_no_bars = 0
        for p in positions:
            bars = fetch_bars_cached(esp, p["symbol"], p["date_et"], bar_cache)
            if not bars:
                n_no_bars += 1
                _time_mod.sleep(0.1)
                continue
            r = autopsy_position(p, esp, bars)
            if r is not None:
                rows.append(r)
            _time_mod.sleep(0.1)

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        day_file = OUT_DIR / f"{date_et}.jsonl"
        day_file.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""),
                            encoding="utf-8")

        history = load_recent_rows()
        # today's rows are already in history via the file we just wrote? load_recent_rows
        # re-reads the dir, so yes -- no double-append.
        new_hyps = detect_hypotheses(history, date_et)
        new_hyps = dedupe_hypotheses(new_hyps, load_hypothesis_rows(), date_et)
        if new_hyps:
            with HYP_QUEUE.open("a", encoding="utf-8") as fh:
                for h in new_hyps:
                    fh.write(json.dumps({**h, "date": date_et, "status": "proposed",
                                         "ts": et_now().isoformat()}) + "\n")
            append_queue_md(new_hyps, date_et)

        md = render_md(date_et, rows, new_hyps,
                       n_positions_found=len(positions), n_no_bars=n_no_bars)
        (OUT_DIR / f"{date_et}.md").write_text(md, encoding="utf-8")
        LAST_JSON.write_text(json.dumps({
            "date": date_et, "n_positions": len(rows),
            "n_positions_found": len(positions), "n_no_bars": n_no_bars,
            "net_pnl": round(sum(r["actual_pnl"] for r in rows), 2) if rows else 0.0,
            "n_stopped_then_paid": sum(1 for r in rows if "stopped_then_paid" in r["tags"]),
            "new_hypotheses": [h["id"] for h in new_hyps],
            "md": f"analysis/autopsies/{date_et}.md",
            "generated_at": et_now().isoformat(),
        }, indent=2), encoding="utf-8")
        queue_ping(date_et, rows, new_hyps, n_positions_found=len(positions), n_no_bars=n_no_bars)
        print(f"[autopsy] {date_et}: {len(positions)} positions found, {len(rows)} autopsied, "
              f"{n_no_bars} skipped (no bars), {len(new_hyps)} new hypotheses -> {day_file.name}")
    except Exception as e:  # noqa: BLE001 -- notify-only: never propagate a failure
        print(f"[autopsy] ERROR (fail-open): {e}", file=sys.stderr)
        try:
            LAST_JSON.write_text(json.dumps({"date": date_et, "error": str(e)[:300],
                                             "generated_at": et_now().isoformat()}), encoding="utf-8")
        except OSError:
            pass

    # --- TWIN (mechanism) autopsy -- SEPARATE try/except: a twin failure must never
    # block the SPY autopsy above (already complete by this point either way), and a
    # SPY failure above must never skip the twin section. CODE-fix-only lane throughout
    # (see module docstring's "TWIN (mechanism) SECTION").
    twin_rows: list[dict] = []
    new_twin_hyps: list[dict] = []
    try:
        twin_closed = load_twin_closed_events(date_et)
        twin_rows = [{**r, "classification": classify_twin_close(r)} for r in twin_closed]

        TWIN_OUT_DIR.mkdir(parents=True, exist_ok=True)
        twin_day_file = TWIN_OUT_DIR / f"{date_et}.jsonl"
        twin_day_file.write_text(
            "\n".join(json.dumps(r) for r in twin_rows) + ("\n" if twin_rows else ""),
            encoding="utf-8")

        twin_history = load_recent_twin_rows()
        new_twin_hyps = detect_twin_hypotheses(twin_history, date_et)
        new_twin_hyps = dedupe_hypotheses(new_twin_hyps, load_twin_hypothesis_rows(), date_et)
        write_twin_hypotheses(new_twin_hyps, date_et)  # twin-only lane -- NEVER hypothesis-queue.jsonl

        n_anom = sum(1 for r in twin_rows if not r["classification"]["mechanism_ok"])
        print(f"[autopsy] TWIN {date_et}: {len(twin_rows)} closed events, {n_anom} mechanism "
             f"anomaly(ies), {len(new_twin_hyps)} new twin hypotheses -> {twin_day_file.name}")
    except Exception as e:  # noqa: BLE001 -- twin autopsy must never block the SPY autopsy
        print(f"[autopsy] TWIN ERROR (fail-open): {e}", file=sys.stderr)

    try:
        twin_md = render_twin_section_md(date_et, twin_rows, new_twin_hyps)
        main_md_path = OUT_DIR / f"{date_et}.md"
        if main_md_path.exists():
            with main_md_path.open("a", encoding="utf-8") as fh:
                fh.write(twin_md)
        else:
            # The SPY block above failed before writing its own .md -- still surface the
            # twin section rather than silently dropping it (OP-33/C7: never let one
            # lane's failure hide the other's data).
            main_md_path.write_text(f"# Trade autopsy — {date_et}\n\n"
                                    f"_(SPY section unavailable this run -- see stderr)_\n" + twin_md,
                                    encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[autopsy] TWIN section append ERROR (fail-open): {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
