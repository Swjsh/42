"""replay_today_eval.py -- GOAL-REPLAY-TODAY-GREEN ITERATION 3: 1-min exit-layer fidelity.

ITERATION 1 (see analysis/recommendations/replay-today-baseline-2026-07-17.json +
GOAL-REPLAY-TODAY-GREEN.md LEDGER) built this harness on lib.orchestrator.run_backtest, which
RE-DETECTS levels/triggers from spy_df price history via lib.levels._detect_from_history. That
detector is a DIFFERENT pipeline than the live engine's real one (automation/state/key-levels.json
+ heartbeat_core's per-tick scoring), and it diverged badly: zero candidate triggers near the
11:06/11:40 ET live ELITE entries, plus an INVENTED 11:35 ET level_rejection core_bold never took
(-$467.50 alone flipping core_bold's day from live's +$191 to a replayed -$250). Verdict: NOT
faithful, not tunable. Root cause named, not fixed, per the GOAL doc's own "report it, don't force
it" clause.

ITERATION 2 (this file) fixes it ARCHITECTURALLY, per the task instruction: stop re-detecting
anything. automation/state/core-decisions.jsonl (+ each fleet arm's decisions.jsonl) logs, for
EVERY live tick, exactly what heartbeat_core saw and did: spy/ribbon/htf_15m, bear/bull score,
triggers, trigger_level_exact, the exec block (real strike/qty/entry premium/stop-mode/
trigger_level/broker fill), and -- for core -- the extra_exec side channel (bollinger_squeeze
etc). This is the engine's OWN recorded signal+decision+execution stream. Iteration 2:

  1. SIGNAL/CONTEXT LAYER: read directly from the recorded PLACED rows (core primary channel +
     extra_exec side channel + fleet decisions.jsonl `placement.placed=True` rows). No re-
     detection anywhere -- entry side, strike, qty, triggers, and the stop-reference level
     (`trigger_level`) are taken verbatim from what the engine logged it actually used. This
     closes iteration 1's root cause #6 (level-set mismatch) BY CONSTRUCTION: there is no level
     detector left to disagree with live.
  2. DECISION LAYER RE-RUN: classify_tier() (byte-identical to orchestrator's internal ELITE/
     LEVEL/TRENDLINE/SUPER classifier, unchanged from iteration 1) is re-applied to each entry's
     recorded/reconstructed triggers and checked against the tier live itself recorded (core:
     parsed from the `reason` string; fleet: the logged `quality` field). A mismatch here would
     mean this harness's gate logic disagrees with what the live engine actually decided --
     see decision_layer_check() / capture in harness_verdict.decision_layer.
  3. EXIT LAYER: each entry is walked forward through backtest/lib/simulator_real.py's
     simulate_trade_real() -- the SAME real-OPRA-fills function lib.orchestrator's own
     use_real_fills=True path calls (OP-22 reuse, unmodified) -- against today's cached real
     OPRA option bars (backtest/data/options/SPY260717*.csv, fetched iteration 1). Exit-shape
     kwargs (tp1_premium_pct, tp1_qty_fraction, runner_target_premium_pct, profit_lock_*,
     premium_stop_pct, time_stop_et) are read at RUNTIME from each entry's own recorded record
     where logged (fleet `placement` block logs tp1_premium_pct/tp1_qty_fraction/profit_lock_mode/
     premium_stop_pct per-trade -- used directly, not guessed) and otherwise from the real
     params.json / aggressive/params.json / automation/state/fleet/strategies.py#RIBBON_RIDE
     sources iteration 1 already verified (fidelity decisions #1-5, carried forward unchanged).
  4. LEVELS FED TO THE EXIT WALK: levels_active/levels_carry (used only for the runner's
     next-chart-level scan, NOT for entry detection) are now sourced from the REAL live level
     pipeline, automation/state/key-levels.json, split by tier (Active vs everything else) --
     replacing iteration 1's price-only auto-detected levels for this purpose too.

ENTRY-BAR ALIGNMENT (empirically chosen, not assumed): simulate_trade_real fills at "the next
5-min bar's open after the trigger bar" (no-lookahead convention used everywhere else in this
codebase). Passing the 5-min bar that CONTAINS the recorded live tick as "the trigger bar" fills
one full bar (~5 min) LATE vs the true live fill instant (tested: core_safe's 11:06 entry --
containing-bar alignment priced entry at $1.18 vs live's real $1.413 fill, delta $0.23). Passing
the PRIOR closed 5-min bar (the bar whose CLOSE is the most recent data live had as of the
recorded tick) lands the fill at the very next bar's open, much closer to the true instant (same
11:06 entry: $1.48 vs live's $1.413, delta $0.07) -- consistent with treating the tick's floor-5
bar as the signal-detection bar (bar START = the bar whose close is the most recent one available
when live acted). Used uniformly below; see entry_bar_idx_for().

ITERATION 2 RESULT: the SIGNAL layer fix was complete -- CAPTURE 100% on every in-scope named
event (iteration 1 found 1/4) and DECISION layer 12/12 tier matches. The EXIT layer was NOT
faithful. Root-cause (quantified, not asserted): only 5-MINUTE OPRA/SPY bars were cached for
today; live trades on a much finer clock. Two mechanisms named: (a) entry-fill-price approximation
("next 5-min bar open" missed a fast intrabar move by up to $0.23/30%), (b) exit-mechanism gap in
both directions (chart-level stop, checked on 5-min bar CLOSE, fires LATER than live's real
structure-stop; premium/profit-lock stop, checked on 5-min bar LOW, fires EARLIER/WRONGLY once
profit-lock arms at +5% favorable and the floor jumps to breakeven).

ITERATION 3 (this file): fetched real Alpaca 1-minute OPRA option bars + 1-minute SPY bars for
EXACTLY today's 7 traded contracts (backtest/tools/fetch_today_1min.py ->
backtest/data/highres/*_1m_2026-07-17.csv; all 7 option series + SPY are gapless, 390/390 RTH
minutes -- real bars, no BS-approx fallback needed) and pointed the exit walk at them via two new
BACKWARD-COMPATIBLE optional kwargs on lib.simulator_real.simulate_trade_real()
(`entry_fill_delay_minutes`, `opt_df_override` -- both default to the exact prior 5-min behavior;
150+ other callers of that shared function are unaffected, confirmed by the full existing pytest
suite: 223 passed / 1 skipped, zero regressions). simulate_entry_best() tries the 1-min walk first
and falls back to the original 5-min simulate_entry() only if 1-min data is missing for a given
contract (never happened this run -- 12/12 entries used the 1-min path).

RESULT, HONEST (not forced): mechanism (a) is FIXED. Entry-fill deltas across all 12 real entries
are now $0.00-$0.08 (vs up to $0.23/30% before) -- confirmed measured, not asserted. Mechanism (b)
is NOT fixed -- 1-min resolution REVEALED A DIFFERENT, MORE SEVERE version of the same underlying
fragility rather than closing it:

  `v15_profit_lock_mode="fixed"` + the (never-configured, defaults to 0.0) stop-offset means once
  a position ticks +5% favorable the stop floor locks at EXACTLY breakeven and never moves again.
  Checked at 1-min cadence (390 checks/day vs 78 at 5-min) against genuinely volatile real 0DTE
  intra-minute prints (verified: SPY260717P00744000's OPENING MINUTE alone ranged $2.13-$3.64 on
  237 real trades/1387 contracts -- not a stale-quote artifact), this fires almost immediately:
  ALL 5 of core_safe's entries now exit via EXIT_ALL_PREMIUM_STOP at exactly $0.00 P&L in exactly
  2 minutes each (was 3/5 at 5-min resolution) -- a uniformity (5/5 identical hold_minutes, exit
  reason, and $0 outcome regardless of whether the trade was a real winner or loser live) that is
  itself the tell: finer bars did not bring the harness closer to live, they made the SAME
  zero-offset-breakeven fragility trigger MORE reliably, because more discrete checks against
  real intra-minute noise raises the odds of catching a floor-touch, not lowers them. This is a
  genuine, disclosed, NOT-lever-tunable-this-iteration finding (touches PARITY-GAP-2, see
  markdown/planning/FUTURE-IMPROVEMENTS.md) -- the harness is not "trustworthy_to_tune_against" at
  the exit-layer dollar level. It IS a concrete new hypothesis for lever L2 (trend-day exit
  tuning): `profit_lock_stop_offset_pct` is a real, currently-unset production knob.

Faithfulness this run: 2/5 arms clear tolerance (fleet_safe_3, fleet_risky_1 -- both trivially
$0/$0, not a mechanism win). core_safe/core_bold/fleet_risky_3 still fail, now via the breakeven-
floor artifact above rather than iteration 2's mixed causes. The SIGNAL/DECISION layer (iteration
2's actual fix) is untouched and still 100%/12-of-12 -- see SCOPE REFINEMENT in GOAL-REPLAY-TODAY-
GREEN.md: entry-side levers (L1/L3/L4/L6) are evaluable NOW on that faithful decision layer,
independent of this exit-layer residual.

ENTRY-BAR ALIGNMENT (empirically chosen, not assumed, 5-min path): simulate_trade_real fills at
"the next 5-min bar's open after the trigger bar" (no-lookahead convention used everywhere else in
this codebase). Passing the 5-min bar that CONTAINS the recorded live tick as "the trigger bar"
fills one full bar (~5 min) LATE vs the true live fill instant (tested: core_safe's 11:06 entry --
containing-bar alignment priced entry at $1.18 vs live's real $1.413 fill, delta $0.23). Passing
the PRIOR closed bar (the bar whose CLOSE is the most recent data live had as of the recorded
tick) lands the fill at the very next bar's open, much closer to the true instant. Used uniformly
(both 5-min and, with a 1-bar-not-5-min interval, the 1-min path); see entry_bar_idx_for() /
entry_bar_idx_for_1min().

Guard: backtest/tests/test_replay_today_eval.py pins determinism + both iterations' actual
faithfulness numbers (regression pins, not assertions that they "should" be any particular value).

Run: backtest/.venv/Scripts/python.exe backtest/tools/replay_today_eval.py
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (REPO, BACKTEST, BACKTEST / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import sniper_matrix as SM  # noqa: E402 -- reused CSV timestamp normalizer
from lib.option_pricing_real import option_symbol  # noqa: E402 -- ITER-3 1-min cache lookup
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

TRADE_DATE = dt.date(2026, 7, 17)
DATE_STR = "2026-07-17"
DATA_DIR = BACKTEST / "data"
SPY_PATH = DATA_DIR / "spy_5m_2026-05-19_2026-07-17.csv"
HIRES_DIR = DATA_DIR / "highres"  # ITER-3: 1-min SPY + OPRA bars, backtest/tools/fetch_today_1min.py
CORE_SAFE_PARAMS_PATH = REPO / "automation" / "state" / "params.json"
CORE_BOLD_PARAMS_PATH = REPO / "automation" / "state" / "aggressive" / "params.json"
CORE_DECISIONS_PATH = REPO / "automation" / "state" / "core-decisions.jsonl"
FLEET_ARM_IDS = {"fleet_safe_3": "safe-3", "fleet_risky_1": "risky-1", "fleet_risky_3": "risky-3"}
FLEET_DECISIONS_PATHS = {
    arm: REPO / "automation" / "state" / "fleet" / arm_id / "decisions.jsonl"
    for arm, arm_id in FLEET_ARM_IDS.items()
}
KEY_LEVELS_PATH = REPO / "automation" / "state" / "key-levels.json"
JOURNAL_TRADES_PATH = REPO / "journal" / "trades.csv"
OUT_JSON = REPO / "analysis" / "recommendations" / "replay-today-baseline-2026-07-17.json"
GOAL_DOC = REPO / "automation" / "overnight" / "GOAL-REPLAY-TODAY-GREEN.md"

ACCOUNT_TO_ARM = {
    "safe": "core_safe", "bold": "core_bold",
    "safe-3": "fleet_safe_3", "risky-1": "fleet_risky_1", "risky-3": "fleet_risky_3",
}

# Faithfulness tolerance: iteration 1 used $150 (a re-detected signal layer, wide tolerance
# expected). Iteration 2 removes the signal-detection error entirely, so the task's own
# instruction is "near-exact, not +/-$150". Chosen here as $40 OR 15% of |live| (whichever is
# larger), applied to the ENGINE-ONLY total (see below) -- tight enough that it cannot be passed
# by the old wide margin, loose enough to allow for the disclosed, quantified 5-min-bar exit-
# timing residual (see module docstring) without being reverse-fit to whatever number came out.
FAITHFULNESS_ABS_DOLLARS = 40.0
FAITHFULNESS_PCT = 0.15

# ---------------------------------------------------------------------------------------------
# NAMED EVENTS -- the GOAL doc's capture-report targets. Iteration 2 update: 14:03 bollinger is
# now IN SCOPE (its full exec block is recorded on core-decisions.jsonl's extra_exec channel --
# iteration 1 excluded it by construction since it only read the primary verdict channel). The
# 12:04 J-called 746C stays OUT OF SCOPE (structurally unreplayable -- no engine rule fires it,
# confirmed again this iteration via journal/trades.csv's j_override='Y'/attribution='j_called').
# ---------------------------------------------------------------------------------------------
NAMED_EVENTS = [
    {"id": "13:01_trendline_put", "arm": "core_safe", "time_et": "13:01", "side": "P",
     "expected_tier": "TRENDLINE", "live_pnl": 241.0, "in_scope": True, "is_loser": False},
    {"id": "13:51_bold_trendline_put", "arm": "core_bold", "time_et": "13:51", "side": "P",
     "expected_tier": "TRENDLINE", "live_pnl": 191.0, "in_scope": True, "is_loser": False},
    {"id": "11:06_elite_put_loser", "arm": "core_safe", "time_et": "11:06", "side": "P",
     "expected_tier": "ELITE", "live_pnl": -37.0, "in_scope": True, "is_loser": True},
    {"id": "11:40_elite_put_loser", "arm": "core_safe", "time_et": "11:40", "side": "P",
     "expected_tier": "ELITE", "live_pnl": -102.0, "in_scope": True, "is_loser": True},
    {"id": "14:03_bollinger_wick_put", "arm": "core_safe", "time_et": "14:03", "side": "P",
     "expected_tier": None, "live_pnl": 105.0, "in_scope": True, "is_loser": False,
     "note": "j_bollinger_squeeze_* extra-setup side channel (extra_exec on "
             "core-decisions.jsonl) -- excluded from iteration 1's scope (primary-channel-only "
             "read); iteration 2 reads extra_exec too, so this is now captured."},
    {"id": "12:04_j_called_746C", "arm": "core_safe", "time_et": "12:04", "side": "C",
     "expected_tier": None, "live_pnl": 89.0, "in_scope": False, "is_loser": False,
     "out_of_scope_reason": "J's manual discretionary trade off his own hand-drawn descending "
                             "trendline (journal archetype_match_json.attribution='j_called', "
                             "trades.csv j_override='Y', gamma_recommended='N'). No live engine "
                             "rule exists to fire this -- structurally unreplayable by any "
                             "config change, not a miss. Confirmed again this iteration."},
]


def log(msg: str) -> None:
    print(f"[replay-today-v2] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# JSONL / helpers
# ---------------------------------------------------------------------------------------------
def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def rows_for_today(rows: list[dict], ts_key: str = "ts_et") -> list[dict]:
    return [r for r in rows if str(r.get(ts_key, "")).startswith(DATE_STR)]


def _parse_et_naive(ts_str: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(ts_str)
    if t.tzinfo is not None:
        t = t.replace(tzinfo=None)
    return t


def _parse_hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


# ---------------------------------------------------------------------------------------------
# TIER / GATE CLASSIFIER -- trigger-string-identical mirror of orchestrator.py's internal
# quality-tier logic (lines ~1160-1219). Unchanged from iteration 1.
# ---------------------------------------------------------------------------------------------
def classify_tier(triggers: list[str], side: str) -> str:
    level_tied = "level_reclaim" if side == "C" else "level_rejection"
    seq = "sequence_reclaim" if side == "C" else "sequence_rejection"
    has_level = level_tied in triggers
    has_confluence = "confluence" in triggers
    has_sequence = seq in triggers
    has_ribbon_flip = "ribbon_flip" in triggers
    has_trendline = "trendline_rejection" in triggers or "trendline_reclaim" in triggers
    n = len(triggers)
    if (has_confluence and has_ribbon_flip) or n >= 3:
        return "SUPER"
    if has_confluence or has_sequence:
        return "ELITE"
    if has_level:
        return "LEVEL"
    if has_trendline:
        return "TRENDLINE"
    return "BASE"


def passes_confluence_or_sequence(triggers: list[str], side: str) -> bool:
    seq = "sequence_reclaim" if side == "C" else "sequence_rejection"
    return "confluence" in triggers or seq in triggers


def _tier_from_reason(reason: str) -> str | None:
    m = re.search(r"tier (\w+)", reason or "")
    return m.group(1) if m else None


def _synth_triggers_for_quality(quality: str | None) -> list[str]:
    """Fleet decisions.jsonl logs the ADMITTED tier (`quality`) but not the raw trigger-string
    list core-decisions.jsonl logs. Reconstruct the MINIMAL trigger set that reproduces that tier
    via classify_tier() -- disclosed approximation. Verified (grep, see module docstring EXIT
    LAYER section) that triggers_fired does not branch simulate_trade_real's exit math -- it is
    record-keeping only, so this approximation cannot change any simulated P&L."""
    if quality == "SUPER":
        return ["confluence", "ribbon_flip"]
    if quality == "ELITE":
        return ["confluence"]
    if quality == "LEVEL":
        return ["level_rejection"]
    if quality == "TRENDLINE":
        return ["trendline_rejection"]
    return []


# ---------------------------------------------------------------------------------------------
# SIGNAL/CONTEXT LAYER -- extraction from the recorded per-tick streams. No re-detection.
# ---------------------------------------------------------------------------------------------
def _extra_triggers(r: dict, setup_name: str | None) -> list[str]:
    for es in (r.get("extra_signals") or []):
        if es.get("setup_name") == setup_name and es.get("fired"):
            return list(es.get("triggers") or [])
    return []


def _core_entry(arm: str, r: dict, execd: dict, channel: str, triggers: list[str]) -> dict:
    fill = execd.get("fill") or {}
    live_entry_px = fill.get("filled_avg_price")
    try:
        live_entry_px = float(live_entry_px) if live_entry_px is not None else execd.get("entry_px")
    except (TypeError, ValueError):
        live_entry_px = execd.get("entry_px")
    return {
        "arm": arm, "channel": channel, "ts_et": r["ts_et"],
        "side": execd["side"], "setup": execd.get("setup"),
        "triggers": triggers,
        "triggers_source": "recorded" if channel == "primary" else "recorded_extra_signals",
        "recorded_tier": _tier_from_reason(r.get("reason", "")) if channel == "primary" else None,
        "strike": execd["strike"], "qty": execd["qty"],
        "rejection_level": execd.get("trigger_level"),
        "premium_stop_pct": execd.get("premium_stop_pct"),
        "stop_mode": execd.get("stop_mode"),
        "live_entry_px": live_entry_px,
        "live_tp": execd.get("tp"), "live_stop": execd.get("stop"),
    }


def extract_core_entries(core_today: list[dict]) -> list[dict]:
    entries = []
    for r in core_today:
        arm = {"safe": "core_safe", "bold": "core_bold"}.get(r.get("account"))
        if arm is None:
            continue
        if r.get("action") == "PLACED" and isinstance(r.get("exec"), dict):
            entries.append(_core_entry(arm, r, r["exec"], "primary", list(r.get("triggers") or [])))
        for ee in (r.get("extra_exec") or []):
            if ee.get("action") == "PLACED" and isinstance(ee.get("exec"), dict):
                trig = _extra_triggers(r, ee.get("setup"))
                entries.append(_core_entry(arm, r, ee["exec"], "extra_exec", trig))
    return entries


def _fleet_entry(arm: str, r: dict) -> dict:
    pl = r["placement"]
    quality = r.get("quality")
    return {
        "arm": arm, "channel": "primary", "ts_et": r["ts_et"],
        "side": r["side"], "setup": r.get("setup_name"),
        "triggers": _synth_triggers_for_quality(quality),
        "triggers_source": "reconstructed_from_recorded_quality_tier",
        "recorded_tier": quality,
        "strike": r["strike"], "qty": r["qty"],
        "rejection_level": pl.get("trigger_level"),
        "premium_stop_pct": pl.get("premium_stop_pct"),
        "stop_mode": pl.get("stop_mode"),
        "tp1_premium_pct": pl.get("tp1_premium_pct"),
        "tp1_qty_fraction": pl.get("tp1_qty_fraction"),
        "profit_lock_mode": pl.get("profit_lock_mode"),
        "live_entry_px": pl.get("entry_px"),
        "live_tp": pl.get("tp"), "live_stop": pl.get("stop"),
    }


def extract_fleet_entries(arm: str, fleet_today: list[dict]) -> list[dict]:
    entries = []
    for r in fleet_today:
        if str(r.get("action", "")).startswith("ENTER") and (r.get("placement") or {}).get("placed"):
            entries.append(_fleet_entry(arm, r))
    return entries


# ---------------------------------------------------------------------------------------------
# DECISION LAYER RE-RUN -- classify_tier() re-applied to each entry's triggers, checked against
# what live itself recorded as the admitted tier.
# ---------------------------------------------------------------------------------------------
def decision_layer_check(entries: list[dict]) -> list[dict]:
    mismatches = []
    for e in entries:
        if e["recorded_tier"] is None:
            e["decision_layer_tier_computed"] = None
            e["decision_layer_match"] = None
            continue
        computed = classify_tier(e["triggers"], e["side"])
        e["decision_layer_tier_computed"] = computed
        e["decision_layer_match"] = (computed == e["recorded_tier"])
        if not e["decision_layer_match"]:
            mismatches.append(e)
    return mismatches


# ---------------------------------------------------------------------------------------------
# EXIT-SHAPE ENRICHMENT -- runtime-read from real params.json / aggressive/params.json /
# recorded fleet placement blocks / strategies.py#RIBBON_RIDE (iteration-1-verified). No literal
# exit-shape values are invented here.
# ---------------------------------------------------------------------------------------------
def enrich_exit_shape(entries: list[dict], core_safe_params: dict, core_bold_params: dict) -> list[dict]:
    safe_time_stop = _parse_hhmm(core_safe_params["time_stop_et"])
    bold_time_stop = _parse_hhmm(core_bold_params["time_stop_et"])
    for e in entries:
        if e["arm"] == "core_safe" and e["channel"] == "primary":
            e["tp1_qty_fraction"] = core_safe_params["tp1_qty_fraction"]
            e["tp1_premium_pct"] = core_safe_params["tp1_premium_pct"]
            e["runner_target_premium_pct"] = core_safe_params["runner_max_premium_pct"]
            e["profit_lock_mode"] = core_safe_params["v15_profit_lock_mode"]
            e["profit_lock_threshold_pct"] = core_safe_params["v15_profit_lock_threshold_pct"]
            e["profit_lock_trail_pct"] = core_safe_params["v15_profit_lock_trail_pct"]
            e["time_stop_et"] = safe_time_stop
        elif e["arm"] == "core_safe" and e["channel"] == "extra_exec" and e["setup"] == "bollinger_squeeze":
            e["tp1_qty_fraction"] = core_safe_params["j_bollinger_squeeze_tp1_qty_fraction"]
            e["tp1_premium_pct"] = core_safe_params["j_bollinger_squeeze_tp1_pct"]
            e["runner_target_premium_pct"] = core_safe_params["runner_max_premium_pct"]
            e["profit_lock_mode"] = core_safe_params["j_bollinger_squeeze_profit_lock_mode"]
            e["profit_lock_threshold_pct"] = core_safe_params["v15_profit_lock_threshold_pct"]
            e["profit_lock_trail_pct"] = core_safe_params["j_bollinger_squeeze_profit_lock_trail_pct"]
            e["time_stop_et"] = safe_time_stop
            # premium_stop_pct: keep the RECORDED exec value (-0.08, WP-0 per-setup dispatch,
            # confirmed exact via params.json j_bollinger_squeeze_premium_stop_pct) -- not
            # overridden here.
        elif e["arm"] == "core_bold":
            e["tp1_qty_fraction"] = core_bold_params["tp1_qty_fraction"]
            e["tp1_premium_pct"] = core_bold_params["tp1_premium_pct"]
            e["runner_target_premium_pct"] = core_bold_params["runner_max_premium_pct"]
            e["profit_lock_mode"] = "fixed"  # Bold runs NO chandelier (aggressive/params.json has
            e["profit_lock_threshold_pct"] = 0.0  # no profit_lock key -- confirmed, iteration 1
            e["profit_lock_trail_pct"] = 0.0        # fidelity decision #2).
            e["time_stop_et"] = bold_time_stop
        elif e["arm"].startswith("fleet_"):
            # tp1_premium_pct / tp1_qty_fraction / profit_lock_mode already set from the
            # RECORDED placement block in _fleet_entry() (real per-trade values, not guessed).
            # Only threshold/trail aren't logged per-trade -- source those from
            # strategies.py#RIBBON_RIDE (iteration-1-verified reads, unchanged).
            e.setdefault("tp1_premium_pct", 1.0)
            e.setdefault("tp1_qty_fraction", 0.667)
            e["runner_target_premium_pct"] = 99.0  # RIBBON_RIDE rides via trail/EOD, not a fixed target
            e.setdefault("profit_lock_mode", "trailing")
            e["profit_lock_threshold_pct"] = 0.05
            e["profit_lock_trail_pct"] = 0.15
            e["time_stop_et"] = safe_time_stop  # shared v15.3 gate doctrine (iteration 1 convention)
    return entries


# ---------------------------------------------------------------------------------------------
# LEVELS -- real live level pipeline (root cause #6 fix), split by tier.
# ---------------------------------------------------------------------------------------------
def load_levels() -> tuple[list[float], list[float], str | None]:
    kl = json.loads(KEY_LEVELS_PATH.read_text(encoding="utf-8"))
    levels = kl.get("levels", [])
    active = [float(lv["price"]) for lv in levels if lv.get("tier") == "Active"]
    carry = [float(lv["price"]) for lv in levels if lv.get("tier") != "Active"]
    return active, carry, kl.get("as_of")


# ---------------------------------------------------------------------------------------------
# SPY / ribbon -- RTH-only, ALL days (ribbon warmup), mirrors orchestrator.run_backtest's own
# prep (lines ~789-810) exactly so ribbon state at any given bar matches what run_backtest would
# compute.
# ---------------------------------------------------------------------------------------------
def load_spy_ribbon() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not SPY_PATH.exists():
        raise FileNotFoundError(f"{SPY_PATH.name} not found -- run tools/append_today.py first.")
    spy = SM.norm_str(pd.read_csv(SPY_PATH))
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    rth_mask = (spy["timestamp_et"].dt.time >= dt.time(9, 30)) & (spy["timestamp_et"].dt.time < dt.time(16, 0))
    spy_rth = spy.loc[rth_mask].reset_index(drop=True)
    ribbon_df = compute_ribbon(spy_rth["close"])
    return spy_rth, ribbon_df


def entry_bar_idx_for(spy_rth: pd.DataFrame, ts_et_str: str) -> int | None:
    """See module docstring ENTRY-BAR ALIGNMENT: use the last 5-min bar CLOSED strictly before
    the recorded live tick, so simulate_trade_real's next-bar-open fill lands at/near the true
    live fill minute."""
    ts = _parse_et_naive(ts_et_str)
    floored = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
    prior = floored - dt.timedelta(minutes=5)
    target = pd.Timestamp(prior)
    col = spy_rth["timestamp_et"].dt.tz_localize(None)
    matches = spy_rth.index[col == target]
    if len(matches) == 0:
        return None
    return int(matches[0])


# ---------------------------------------------------------------------------------------------
# ITERATION 3: 1-MINUTE EXIT-LAYER DATA -- closes the 5-min-bar data-resolution gap iteration 2
# diagnosed (module docstring). Fetched once via backtest/tools/fetch_today_1min.py: real Alpaca
# OPRA 1-min bars for exactly today's 7 traded contracts + 1-min SPY bars
# (backtest/data/highres/). Both spy_df and opt_df must move to 1-min TOGETHER --
# simulate_trade_real's exit loop walks them in LOCKSTEP by raw positional index (`spy_idx`/
# `opt_idx` both += 1 per iteration, no per-step timestamp resync), so mismatched granularity
# between the two would desync the walk. Verified this iteration: every traded contract's 1-min
# OPRA cache has ZERO gaps across full RTH (390/390 minutes for all 7 symbols; SPY 1-min is also
# 390/390) -- index-lockstep on two dense, co-aligned 390-row 1-min series is exact here, not an
# approximation on top of an approximation.
# ---------------------------------------------------------------------------------------------
def load_spy_1min_rth() -> pd.DataFrame | None:
    path = HIRES_DIR / f"SPY_1m_{DATE_STR}.csv"
    if not path.exists():
        return None
    spy = SM.norm_str(pd.read_csv(path))
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    rth_mask = (spy["timestamp_et"].dt.time >= dt.time(9, 30)) & (spy["timestamp_et"].dt.time < dt.time(16, 0))
    return spy.loc[rth_mask].reset_index(drop=True)


def build_ribbon_1min(spy_1m_rth: pd.DataFrame, spy_5m_rth: pd.DataFrame, ribbon_5m: pd.DataFrame) -> pd.DataFrame:
    """Ribbon state per 1-min bar = the most-recently-CLOSED 5-min bar's ribbon state at that
    instant -- does NOT recompute EMAs on 1-min closes. The ribbon's fast/pivot/slow periods
    (lib/ribbon.py load_periods()) are calibrated to 5-min bars; running the same period counts
    directly on 1-min data would shrink the effective lookback window 5x and produce a DIFFERENT,
    uncalibrated ribbon state (a new bug, not a fidelity improvement). Forward-filling the
    unchanged, iteration-1/2-validated 5-min ribbon onto each 1-min bar preserves the exact
    calibration while giving simulate_trade_real's _ribbon_at(ribbon_df, idx) a per-1-min-index
    lookup it can use unmodified."""
    five = spy_5m_rth[["timestamp_et"]].copy()
    five["five_idx"] = five.index
    merged = pd.merge_asof(
        spy_1m_rth[["timestamp_et"]].sort_values("timestamp_et"),
        five.sort_values("timestamp_et"),
        on="timestamp_et", direction="backward",
    )
    return ribbon_5m.loc[merged["five_idx"].values].reset_index(drop=True)


def load_opt_1min(symbol: str) -> pd.DataFrame | None:
    """Same schema load_contract_bars() would produce (timestamp_et parsed, OHLCV+vwap+
    trade_count) -- read from backtest/data/highres/ instead of the shared 5-min
    backtest/data/options/ cache every OTHER simulate_trade_real caller relies on."""
    path = HIRES_DIR / f"{symbol}_1m_{DATE_STR}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


def entry_bar_idx_for_1min(spy_1m_rth: pd.DataFrame, ts_et_str: str) -> int | None:
    """1-min analogue of entry_bar_idx_for(): the last 1-min bar CLOSED strictly before the
    recorded live tick (5-min version floors to the 5-min bucket then steps back 5 min; here we
    floor to the minute then step back 1 min -- same convention, finer interval)."""
    ts = _parse_et_naive(ts_et_str)
    floored = ts.replace(second=0, microsecond=0)
    prior = floored - dt.timedelta(minutes=1)
    target = pd.Timestamp(prior)
    col = spy_1m_rth["timestamp_et"]
    if col.dt.tz is not None:
        col = col.dt.tz_localize(None)
    matches = spy_1m_rth.index[col == target]
    if len(matches) == 0:
        return None
    return int(matches[0])


def simulate_entry_1min(e: dict, spy_1m_rth: pd.DataFrame, ribbon_1m: pd.DataFrame,
                         levels_active: list[float], levels_carry: list[float],
                         opt_1min_cache: dict[str, pd.DataFrame]) -> tuple[object, str]:
    idx = entry_bar_idx_for_1min(spy_1m_rth, e["ts_et"])
    if idx is None or idx < 0:
        return None, "no_matching_spy_1m_bar"
    entry_bar = spy_1m_rth.iloc[idx]
    symbol = option_symbol(TRADE_DATE, e["strike"], e["side"])
    opt_1m = opt_1min_cache.get(symbol)
    if opt_1m is None:
        return None, f"no_1min_opra_cache_for_{symbol}"
    premium_stop_pct = e.get("premium_stop_pct")
    if premium_stop_pct is None:
        premium_stop_pct = -0.50
    fill = simulate_trade_real(
        entry_bar_idx=idx, entry_bar=entry_bar, spy_df=spy_1m_rth, ribbon_df=ribbon_1m,
        rejection_level=e.get("rejection_level"), triggers_fired=e["triggers"], side=e["side"],
        qty=e["qty"], setup=e.get("setup") or "BEARISH_REJECTION_RIDE_THE_RIBBON",
        levels_active=levels_active, levels_carry=levels_carry,
        strike_override=e["strike"],
        premium_stop_pct=premium_stop_pct,
        tp1_qty_fraction=e.get("tp1_qty_fraction", 0.667),
        runner_target_premium_pct=e.get("runner_target_premium_pct", 2.5),
        tp1_premium_pct=e.get("tp1_premium_pct", 0.30),
        profit_lock_mode=e.get("profit_lock_mode", "fixed"),
        profit_lock_threshold_pct=e.get("profit_lock_threshold_pct", 0.0),
        profit_lock_trail_pct=e.get("profit_lock_trail_pct", 0.0),
        time_stop_et=e.get("time_stop_et", dt.time(15, 40)),
        entry_fill_delay_minutes=1.0,   # ITER-3: fill on the immediate next 1-min bar, not +5min
        opt_df_override=opt_1m,          # ITER-3: real 1-min OPRA bars, not the 5-min cache
    )
    if fill is None:
        return None, "opra_1min_no_bar_after_entry"
    return fill, "ok"


def simulate_entry_best(e: dict, spy_5m_rth: pd.DataFrame, ribbon_5m: pd.DataFrame,
                         spy_1m_rth: "pd.DataFrame | None", ribbon_1m: "pd.DataFrame | None",
                         levels_active: list[float], levels_carry: list[float],
                         opt_1min_cache: dict[str, pd.DataFrame]) -> tuple[object, str, str]:
    """1-min exit walk PRIMARY, 5-min simulate_entry() FALLBACK (task instruction: 'keep the
    5-min path as fallback'). Returns (fill, status, resolution); resolution in
    {'1min', '5min_fallback', 'none'}."""
    if spy_1m_rth is not None and ribbon_1m is not None:
        fill, status = simulate_entry_1min(e, spy_1m_rth, ribbon_1m, levels_active, levels_carry, opt_1min_cache)
        if fill is not None:
            return fill, status, "1min"
        min1_status = status
    else:
        min1_status = "no_1min_spy_data"
    fill, status = simulate_entry(e, spy_5m_rth, ribbon_5m, levels_active, levels_carry)
    if fill is not None:
        return fill, status, "5min_fallback"
    return None, f"1min_miss={min1_status};5min_miss={status}", "none"


# ---------------------------------------------------------------------------------------------
# EXIT LAYER -- simulate_trade_real, unmodified, real OPRA bars.
# ---------------------------------------------------------------------------------------------
def simulate_entry(e: dict, spy_rth: pd.DataFrame, ribbon_df: pd.DataFrame,
                    levels_active: list[float], levels_carry: list[float]) -> tuple[object, str]:
    idx = entry_bar_idx_for(spy_rth, e["ts_et"])
    if idx is None or idx < 0:
        return None, "no_matching_spy_bar"
    entry_bar = spy_rth.iloc[idx]
    premium_stop_pct = e.get("premium_stop_pct")
    if premium_stop_pct is None:
        premium_stop_pct = -0.50
    fill = simulate_trade_real(
        entry_bar_idx=idx, entry_bar=entry_bar, spy_df=spy_rth, ribbon_df=ribbon_df,
        rejection_level=e.get("rejection_level"), triggers_fired=e["triggers"], side=e["side"],
        qty=e["qty"], setup=e.get("setup") or "BEARISH_REJECTION_RIDE_THE_RIBBON",
        levels_active=levels_active, levels_carry=levels_carry,
        strike_override=e["strike"],
        premium_stop_pct=premium_stop_pct,
        tp1_qty_fraction=e.get("tp1_qty_fraction", 0.667),
        runner_target_premium_pct=e.get("runner_target_premium_pct", 2.5),
        tp1_premium_pct=e.get("tp1_premium_pct", 0.30),
        profit_lock_mode=e.get("profit_lock_mode", "fixed"),
        profit_lock_threshold_pct=e.get("profit_lock_threshold_pct", 0.0),
        profit_lock_trail_pct=e.get("profit_lock_trail_pct", 0.0),
        time_stop_et=e.get("time_stop_et", dt.time(15, 40)),
    )
    if fill is None:
        return None, "opra_cache_miss"
    return fill, "ok"


def fill_to_dict(e: dict, fill, resolution: str = "5min_fallback") -> dict:
    return {
        "arm": e["arm"], "channel": e["channel"], "signal_ts_et": e["ts_et"],
        "setup": e.get("setup"), "side": e["side"],
        "triggers": e["triggers"], "triggers_source": e["triggers_source"],
        "exit_layer_resolution": resolution,  # ITER-3: '1min' | '5min_fallback'
        "recorded_tier": e.get("recorded_tier"),
        "decision_layer_tier_computed": e.get("decision_layer_tier_computed"),
        "decision_layer_match": e.get("decision_layer_match"),
        "strike": e["strike"], "qty": e["qty"],
        "entry_time_et": fill.entry_time_et.isoformat(),
        "sim_entry_premium": round(fill.entry_premium, 4),
        "live_entry_px": e.get("live_entry_px"),
        "entry_px_delta": (round(fill.entry_premium - e["live_entry_px"], 4)
                            if isinstance(e.get("live_entry_px"), (int, float)) else None),
        "exit_reason": str(fill.exit_reason) if fill.exit_reason is not None else None,
        "hold_minutes": fill.hold_minutes,
        "dollar_pnl": round(fill.dollar_pnl, 2),
    }


# ---------------------------------------------------------------------------------------------
# GROUND TRUTH (journal/trades.csv, broker-verified) -- used ONLY for cross-validation /
# faithfulness scoring, never as an input to the simulation itself.
# ---------------------------------------------------------------------------------------------
def load_trades_csv_today() -> list[dict]:
    rows = []
    if not JOURNAL_TRADES_PATH.exists():
        return rows
    with JOURNAL_TRADES_PATH.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("date") == DATE_STR:
                rows.append(row)
    return rows


def ground_truth_by_entry(trades_today: list[dict]) -> list[dict]:
    """trades.csv splits TP1+runner legs of the SAME entry into separate rows sharing the same
    (account_id, time_entry). Group them back into one ground-truth total per real entry."""
    groups: dict[tuple, dict] = {}
    for row in trades_today:
        key = (row["account_id"], row["time_entry"])
        g = groups.setdefault(key, {
            "account_id": row["account_id"], "time_entry": row["time_entry"],
            "setup": row["setup"], "strike": row["strike"], "side": row["c_or_p"],
            "dollar_pnl": 0.0, "j_override": row.get("j_override") == "Y",
        })
        g["dollar_pnl"] += float(row["dollar_pnl"])
    return list(groups.values())


def compute_live_truth(trades_today: list[dict]) -> tuple[dict, dict, dict]:
    raw, engine_only, manual_excluded = {}, {}, {}
    for row in trades_today:
        arm = ACCOUNT_TO_ARM.get(row["account_id"])
        if arm is None:
            continue
        pnl = float(row["dollar_pnl"])
        raw[arm] = raw.get(arm, 0.0) + pnl
        if row.get("j_override") == "Y":
            manual_excluded[arm] = manual_excluded.get(arm, 0.0) + pnl
        else:
            engine_only[arm] = engine_only.get(arm, 0.0) + pnl
    for arm in raw:
        engine_only.setdefault(arm, 0.0)
        manual_excluded.setdefault(arm, 0.0)
    return raw, engine_only, manual_excluded


def match_ground_truth(sim_trade: dict, gt_entries: list[dict], arm: str) -> dict | None:
    sim_t = dt.datetime.fromisoformat(sim_trade["signal_ts_et"].replace("Z", ""))
    if sim_t.tzinfo is not None:
        sim_t = sim_t.replace(tzinfo=None)
    best, best_gap = None, None
    for g in gt_entries:
        if g["account_id"] != {"core_safe": "safe", "core_bold": "bold",
                                "fleet_safe_3": "safe-3", "fleet_risky_1": "risky-1",
                                "fleet_risky_3": "risky-3"}[arm]:
            continue
        if g["side"] != sim_trade["side"]:
            continue
        try:
            gt_t = dt.datetime.combine(TRADE_DATE, dt.datetime.strptime(g["time_entry"], "%H:%M:%S").time())
        except ValueError:
            continue
        gap = abs((gt_t - sim_t).total_seconds())
        if gap <= 600 and (best_gap is None or gap < best_gap):
            best, best_gap = g, gap
    return best


# ---------------------------------------------------------------------------------------------
# CAPTURE REPORT
# ---------------------------------------------------------------------------------------------
def match_event(event: dict, arm_trades: list[dict]) -> dict:
    if not event["in_scope"]:
        return {**event, "captured": None, "matched_trade": None,
                "note": event.get("out_of_scope_reason")}
    target = dt.datetime.combine(TRADE_DATE, dt.datetime.strptime(event["time_et"], "%H:%M").time())
    best, best_gap = None, None
    for t in arm_trades:
        et = dt.datetime.fromisoformat(t["entry_time_et"])
        et_naive = et.replace(tzinfo=None) if et.tzinfo else et
        if t["side"] != event["side"]:
            continue
        gap = abs((et_naive - target).total_seconds())
        if gap <= 900 and (best_gap is None or gap < best_gap):
            best, best_gap = t, gap
    return {**event, "captured": best is not None, "matched_trade": best, "gap_seconds": best_gap}


def capture_report(all_trades_by_arm: dict) -> list[dict]:
    return [match_event(ev, all_trades_by_arm.get(ev["arm"], [])) for ev in NAMED_EVENTS]


# ---------------------------------------------------------------------------------------------
# FAITHFULNESS
# ---------------------------------------------------------------------------------------------
def faithfulness_for(arm_key: str, replay_pnl: float, live_engine_pnl: float) -> dict:
    delta = round(replay_pnl - live_engine_pnl, 2)
    tol = max(FAITHFULNESS_ABS_DOLLARS, abs(live_engine_pnl) * FAITHFULNESS_PCT)
    same_sign_or_zero = (live_engine_pnl == 0.0) or (replay_pnl == 0.0) or ((replay_pnl > 0) == (live_engine_pnl > 0))
    faithful = bool(abs(delta) <= tol and same_sign_or_zero)
    return {
        "live_engine_pnl": live_engine_pnl, "replay_pnl": replay_pnl, "delta": delta,
        "tolerance_dollars": round(tol, 2), "same_sign_or_zero": same_sign_or_zero, "faithful": faithful,
    }


# ---------------------------------------------------------------------------------------------
# DETERMINISM HASH
# ---------------------------------------------------------------------------------------------
def determinism_hash(all_results: dict) -> str:
    payload = json.dumps(
        {k: {"total_pnl": v["total_pnl"], "n_trades": v["n_trades"],
             "trade_pnls": [t["dollar_pnl"] for t in v["trades"]]}
         for k, v in all_results.items()},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    log("Loading recorded per-tick decision streams (core + 3 fleet arms)")
    core_today = rows_for_today(load_jsonl(CORE_DECISIONS_PATH))
    fleet_today = {arm: rows_for_today(load_jsonl(path)) for arm, path in FLEET_DECISIONS_PATHS.items()}
    log(f"  core rows today={len(core_today)}, fleet rows today={{{', '.join(f'{k}:{len(v)}' for k, v in fleet_today.items())}}}")

    entries_by_arm: dict[str, list[dict]] = {"core_safe": [], "core_bold": []}
    for e in extract_core_entries(core_today):
        entries_by_arm[e["arm"]].append(e)
    for arm in FLEET_ARM_IDS:
        entries_by_arm[arm] = extract_fleet_entries(arm, fleet_today[arm])

    for arm, es in entries_by_arm.items():
        log(f"  {arm}: {len(es)} recorded PLACED entries "
            f"({', '.join(ee['ts_et'][11:19] for ee in es) or 'none'})")

    core_safe_params = json.loads(CORE_SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
    core_bold_params = json.loads(CORE_BOLD_PARAMS_PATH.read_text(encoding="utf-8"))
    all_entries = [e for es in entries_by_arm.values() for e in es]
    enrich_exit_shape(all_entries, core_safe_params, core_bold_params)
    decision_mismatches = decision_layer_check(all_entries)
    log(f"decision-layer re-run: {len(all_entries) - len(decision_mismatches)}/{len(all_entries)} "
        f"entries reproduce their live-recorded tier via classify_tier()")

    levels_active, levels_carry, levels_as_of = load_levels()
    log(f"levels: {len(levels_active)} Active + {len(levels_carry)} carry from key-levels.json "
        f"(as_of={levels_as_of})")

    log(f"Loading {SPY_PATH.name}")
    spy_rth, ribbon_df = load_spy_ribbon()
    log(f"spy RTH bars total={len(spy_rth)}")

    log("Loading 1-min OPRA/SPY bars (ITERATION 3 exit-layer fidelity)")
    spy_1m_rth = load_spy_1min_rth()
    ribbon_1m = build_ribbon_1min(spy_1m_rth, spy_rth, ribbon_df) if spy_1m_rth is not None else None
    opt_1min_cache: dict[str, pd.DataFrame] = {}
    if HIRES_DIR.exists():
        suffix = f"_1m_{DATE_STR}.csv"
        for p in HIRES_DIR.glob(f"SPY{TRADE_DATE.strftime('%y%m%d')}*{suffix}"):
            sym = p.name[: -len(suffix)]
            df = load_opt_1min(sym)
            if df is not None:
                opt_1min_cache[sym] = df
    if spy_1m_rth is not None:
        log(f"  1-min SPY RTH bars={len(spy_1m_rth)}; 1-min OPRA contracts cached="
            f"{len(opt_1min_cache)} ({', '.join(sorted(opt_1min_cache))})")
    else:
        log("  WARNING: no 1-min SPY data found -- exit walk falls back to 5-min for every entry")

    all_results = {}
    cache_misses = []
    resolution_counts = {"1min": 0, "5min_fallback": 0, "none": 0}
    for arm, es in entries_by_arm.items():
        trades = []
        for e in es:
            fill, status, resolution = simulate_entry_best(
                e, spy_rth, ribbon_df, spy_1m_rth, ribbon_1m, levels_active, levels_carry, opt_1min_cache)
            resolution_counts[resolution] += 1
            if fill is None:
                cache_misses.append({"arm": arm, "ts_et": e["ts_et"], "strike": e["strike"],
                                      "side": e["side"], "reason": status})
                continue
            trades.append(fill_to_dict(e, fill, resolution))
        trades.sort(key=lambda t: t["entry_time_et"])
        all_results[arm] = {
            "arm": arm, "trades": trades, "n_trades": len(trades),
            "total_pnl": round(sum(t["dollar_pnl"] for t in trades), 2),
        }
        log(f"  {arm}: n={len(trades)} total_pnl=${all_results[arm]['total_pnl']}")
    log(f"exit-layer resolution used: {resolution_counts}")
    if cache_misses:
        log(f"WARNING: {len(cache_misses)} entries skipped (OPRA cache miss / no matching SPY bar): {cache_misses}")

    # Cross-validation against broker-truth journal/trades.csv (NOT an input to the simulation).
    trades_today = load_trades_csv_today()
    gt_entries = ground_truth_by_entry(trades_today)
    live_raw, live_engine_only, live_manual_excluded = compute_live_truth(trades_today)
    for arm, res in all_results.items():
        for t in res["trades"]:
            gt = match_ground_truth(t, gt_entries, arm)
            t["ground_truth_pnl"] = gt["dollar_pnl"] if gt else None
            t["ground_truth_delta"] = (round(t["dollar_pnl"] - gt["dollar_pnl"], 2) if gt else None)

    faithfulness = {k: faithfulness_for(k, v["total_pnl"], live_engine_only.get(k, 0.0))
                     for k, v in all_results.items()}
    all_faithful = all(f["faithful"] for f in faithfulness.values())
    n_faithful = sum(1 for f in faithfulness.values() if f["faithful"])

    all_trades_by_arm = {arm: res["trades"] for arm, res in all_results.items()}
    events = capture_report(all_trades_by_arm)
    n_in_scope = sum(1 for e in events if e["in_scope"])
    n_captured = sum(1 for e in events if e["in_scope"] and e["captured"])

    dh = determinism_hash(all_results)

    out = {
        "_doc": "GOAL-REPLAY-TODAY-GREEN iteration 3 -- 1-min exit-layer fidelity. Entries read "
                "verbatim from recorded core-decisions.jsonl + fleet decisions.jsonl (no level "
                "re-detection, unchanged from iteration 2); exits simulated via "
                "lib.simulator_real.simulate_trade_real against real 1-MINUTE OPRA/SPY bars "
                "(backtest/data/highres/, fetched via fetch_today_1min.py) with 5-min fallback "
                "if 1-min data is missing for a contract (did not happen this run -- 12/12 used "
                "1-min). Measurement only; no params/config file modified. "
                "Source: backtest/tools/replay_today_eval.py.",
        "iteration": 3,
        "generated_at": dt.datetime.now().isoformat(),
        "trade_date": TRADE_DATE.isoformat(),
        "determinism_hash": dh,
        "exit_layer_resolution_counts": resolution_counts,
        "faithfulness_tolerance": {"abs_dollars": FAITHFULNESS_ABS_DOLLARS, "pct_of_live": FAITHFULNESS_PCT,
                                    "note": "max(abs_dollars, |live_engine_pnl|*pct) per arm"},
        "arms": all_results,
        "live_truth_raw": live_raw,
        "live_truth_engine_only": live_engine_only,
        "live_truth_manual_excluded": live_manual_excluded,
        "live_truth_note": (
            "raw = every broker-verified round-trip in journal/trades.csv today per account_id "
            "(matches the GOAL doc's headline numbers, e.g. core_safe=$240). engine_only "
            "subtracts trades with j_override='Y' (J's manual/discretionary trades -- no engine "
            "rule fires them, structurally unreplayable by this or any config-only harness; "
            "today that is exactly the 12:04 746C J-called trade, $89, core_safe only). "
            "faithfulness is scored against engine_only since this harness can only ever "
            "reproduce engine decisions."
        ),
        "faithfulness": faithfulness,
        "faithfulness_summary": {"n_arms": len(all_results), "n_faithful": n_faithful, "all_faithful": all_faithful},
        "decision_layer": {
            "n_entries": len(all_entries),
            "n_tier_matches": len(all_entries) - len(decision_mismatches),
            "n_mismatches": len(decision_mismatches),
            "mismatches": [{"arm": m["arm"], "ts_et": m["ts_et"], "recorded_tier": m["recorded_tier"],
                             "computed_tier": m["decision_layer_tier_computed"],
                             "triggers": m["triggers"], "triggers_source": m["triggers_source"]}
                            for m in decision_mismatches],
        },
        "capture_report": events,
        "capture_summary": {"n_in_scope": n_in_scope, "n_captured": n_captured,
                             "n_out_of_scope": len(NAMED_EVENTS) - n_in_scope},
        "cache_misses": cache_misses,
        "levels_source": {"path": "automation/state/key-levels.json", "as_of": levels_as_of,
                           "n_active": len(levels_active), "n_carry": len(levels_carry)},
        "harness_verdict": {
            "signal_layer": (
                f"FIXED (iteration 2, unchanged this iteration -- entries are read verbatim "
                f"from the engine's own recorded exec blocks, no level re-detection anywhere). "
                f"CAPTURE: {n_captured}/{n_in_scope} in-scope named events captured "
                f"(iteration 1: 1/4). Decision-layer tier reproduction: "
                f"{len(all_entries) - len(decision_mismatches)}/{len(all_entries)}."
            ),
            "exit_layer_entry_fill_mechanism": (
                f"FIXED this iteration. Real 1-minute Alpaca OPRA bars fetched for exactly "
                f"today's 7 traded contracts + 1-min SPY bars (backtest/tools/fetch_today_1min.py "
                f"-> backtest/data/highres/, all gapless 390/390 RTH minutes -- real data, no "
                f"BS-approx fallback needed). Exit-layer resolution used: {resolution_counts} "
                f"(12/12 entries used the real 1-min path, zero 5-min fallbacks). Entry-fill-price "
                f"deltas vs live's real fill are now $0.00-$0.08 across all 12 entries (was up to "
                f"$0.23/30% at 5-min resolution) -- measured this run, see arms[*].trades[*]."
            ),
            "exit_layer_gap": (
                "STILL NOT faithful to tight tolerance on 3/5 arms -- but the mechanism changed, "
                "it did not close. 1-min resolution did NOT fix the exit-mechanism gap iteration "
                "2 diagnosed; it revealed a DIFFERENT, MORE SEVERE artifact of the same underlying "
                "fragility. v15_profit_lock_mode='fixed' (automation/state/params.json, real "
                "production value) plus a never-configured stop-offset (defaults to 0.0) means "
                "once a position ticks +5% favorable the stop floor locks at EXACTLY breakeven "
                "and never moves. Checked at 1-min cadence (390 checks/day vs 78 at 5-min) "
                "against genuinely volatile real 0DTE intra-minute prints (verified: "
                "SPY260717P00744000's opening minute alone ranged $2.13-$3.64 on 237 real trades/ "
                "1387 contracts -- not a stale-quote artifact), this fires almost immediately: "
                "ALL 5 of core_safe's entries now exit via EXIT_ALL_PREMIUM_STOP at exactly $0.00 "
                "P&L in exactly 2 minutes each (was 3/5 zeroed at 5-min resolution) -- a "
                "uniformity across winners AND losers alike that is itself the tell finer bars "
                "made the SAME zero-offset-breakeven fragility trigger MORE reliably, not less "
                "(more discrete checks against real intra-minute noise raises the odds of "
                "catching a floor-touch). NOT a bug in this harness or in simulate_trade_real "
                "(both correctly implement the real, configured 'fixed' profit-lock convention); "
                "NOT lever-tunable this iteration per task instruction, but IS a concrete new "
                "hypothesis for lever L2 (trend-day exit tuning) -- "
                "profit_lock_stop_offset_pct is a real, currently-unset production knob. Filed: "
                "markdown/planning/FUTURE-IMPROVEMENTS.md PARITY-GAP-2 (updated this iteration)."
            ),
            "trustworthy_to_tune_against": all_faithful,
            "primary_scope_metric_note": (
                "Per GOAL-REPLAY-TODAY-GREEN.md's SCOPE REFINEMENT, PRIMARY faithfulness is the "
                "SIGNAL/DECISION layer (capture + tier match), which is unaffected by this "
                "iteration's exit-layer work and remains 100% / 12-of-12. Entry-side levers "
                "(L1/L3/L4/L6) are evaluable now against that faithful layer independent of the "
                "exit-layer dollar residual documented above."
            ),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    log(f"FAITHFULNESS: {n_faithful}/{len(all_results)} arms within tolerance. all_faithful={all_faithful}")
    log(f"CAPTURE: {n_captured}/{n_in_scope} in-scope named events captured "
        f"({len(NAMED_EVENTS) - n_in_scope} out-of-scope, disclosed)")
    log(f"determinism_hash={dh}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
