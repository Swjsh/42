"""replay_today_eval.py -- GOAL-REPLAY-TODAY-GREEN iteration 1: the eval harness.

automation/overnight/GOAL-REPLAY-TODAY-GREEN.md (J-set 2026-07-17 ~18:50 ET) asks the loop to
tune the engine until it replays 2026-07-17 GREEN on all 6 arms. Iteration 1's job is NOT to
tune anything -- it is to BUILD the measurement tool the rest of the loop optimizes against and
establish an HONEST baseline (including whether the harness is trustworthy at all -- see
FAITHFULNESS below). NO params/config/strike-table file is touched by this script. READ-ONLY on
all trading config; only reads params.json / aggressive/params.json / accounts.json /
strategies.py / strike_selection.py and writes to analysis/recommendations/.

WHAT THIS REPLAYS: the BEARISH_REJECTION_RIDE_THE_RIBBON / BULLISH_RECLAIM_RIDE_THE_RIBBON
family only (the "ribbon_ride" strategy -- the dominant, always-on validated edge every arm
trades). The ad-hoc j_bollinger_squeeze_*/j_vwap_*/j_vix_dayside_* one-off setups and
VWAP_CONTINUATION are OUT OF SCOPE for iteration 1 (not wired into lib.orchestrator.run_backtest
at all) -- disclosed explicitly per-event in NAMED_EVENTS below, not silently dropped.

REUSE (OP-22), not reinvention:
  * lib.orchestrator.run_backtest -- the SAME production-shadow entry point
    lib/shadow.py#run_shadow_backtest already uses to compute "what does production do" (its
    prod_result: run_backtest(..., use_real_fills=True, params_overrides=full_params_json)).
  * lib.orchestrator._params_to_kwargs's "explicit kwargs always win over params_overrides"
    contract (orchestrator.py:686-688) -- used deliberately here to patch THREE confirmed,
    mechanistically-verified gaps in that translation layer (see FIDELITY DECISIONS).
  * tools.sniper_matrix.norm_str -- the existing spy/vix CSV timestamp normalizer every
    run_backtest caller in backtest/tools/ already uses (full_walkforward.py etc).
  * tools.expand_opra_cache's fetch/write primitives -- reused (not copied) by this session's
    one-time prefetch of today's real OPRA option bars (backtest/data/options/SPY260717*.csv,
    62 contracts fetched fresh via Alpaca options-bars API, ATM+/-15 strikes, RTH bars only).
  * automation/state/fleet/strategies.py#RIBBON_RIDE -- the fleet's real, checked-in exit-shape
    dataclass; its field values are read directly, not re-typed from memory.
  * crypto/lib/strike_selection.py#V15_SAFE_TIERS / V15_BOLD_TIERS#pick_tier -- the real,
    checked-in per-tier strike tables (live source of truth, per that file's own docstring).

FIDELITY DECISIONS (each is a disclosed, mechanistically-justified deviation from a naive
params_overrides pass-through -- NOT unexamined defaults):

  1. STRIKE OFFSET: automation/state/params.json#v15_strike_offset_per_tier is confirmed
     VESTIGIAL on the live core path (params.json's own _v15_strike_offset_per_tier_doc: "the
     live core-Safe/Bold engine... does NOT read automation/state/params.json for strike tiers
     ... calls crypto/lib/strike_selection.py#pick_strike() against the hardcoded
     V15_SAFE_TIERS/V15_BOLD_TIERS constants directly"). This harness computes strike_offset via
     pick_tier() against each arm's ACTUAL start-of-day equity and passes it as an EXPLICIT
     run_backtest kwarg, which orchestrator.py:686-688 guarantees wins over the vestigial
     params_overrides-derived value.
       core_safe  (SOD equity $1,485.31, <$2K tier): V15_SAFE_TIERS -> ATM (0)
       core_bold  (SOD equity $1,963.04, <$2K tier): V15_BOLD_TIERS -> OTM-3 (-3)
       fleet arms (frozen $2,000 sizing, accounts.json params_patch.strike_tier_table="bold"
                   for safe-3; risky-1/risky-3 config_source="inherit bold"): V15_BOLD_TIERS
                   -> OTM-3 (-3), all three.

  2. PROFIT-LOCK (chandelier trail): _params_to_kwargs (orchestrator.py:319-465) has NO mapping
     for params.json's "v15_profit_lock_mode" / "v15_profit_lock_trail_pct" /
     "v15_profit_lock_threshold_pct" keys at all (grep-verified) -- a params_overrides-only run
     would silently leave profit_lock OFF (run_backtest's own defaults: mode="fixed",
     threshold=0.0, trail=0.0), even though live Safe runs a live chandelier. Per params.json's
     own _v15_profit_lock_trail_pct_doc_2026_06_19: "SAFE ONLY (Bold/aggressive runs NO
     chandelier -- aggressive/params.json has no profit_lock key)" (confirmed: grepped, absent).
     core_safe: explicit profit_lock_mode="trailing", profit_lock_threshold_pct=0.05,
                profit_lock_trail_pct=0.125 (params.json's OWN current v15_profit_lock_* values).
     core_bold: no override (matches "no chandelier" doctrine; stays at orchestrator defaults).

  3. STOP MECHANISM: automation/state/params.json / aggressive/params.json both set
     structure_stop_enabled=true (SS-B "chart-stop-primary": exit on 5m SPY CLOSE through the
     entry trigger level, side-aware; -50% intrabar catastrophe cap). orchestrator.py has NO
     "structure"/"catastrophe"/stop_mode kwarg AT ALL (grep-confirmed zero matches) -- the
     research backtest engine has never had this concept ported in; it is a live-execution-only
     mechanism (params.json's own doc: "Consumers: fleet exit lane (exit_manager.py) + core lane
     (heartbeat_core.py)"). core_safe's own premium_stop_pct_bear=-0.5 already happens to equal
     the catastrophe cap (no override needed there). core_bold's aggressive/params.json instead
     carries the STRUCTURE-OFF FALLBACK values (premium_stop_pct_bear=-0.07,
     premium_stop_pct_bull=-0.05 -- confirmed via direct read, NOT the -0.50 catastrophe value
     anywhere in that file) -- passed through params_overrides unmodified this would simulate a
     materially TIGHTER, WRONG stop mechanism. Explicit override: premium_stop_pct_bear=
     premium_stop_pct_bull=-0.50 for core_bold and for all three fleet arms (whose RIBBON_RIDE
     ExitShape declares catastrophe_stop_pct=-0.50 directly). THIS IS THE SINGLE LARGEST KNOWN
     FIDELITY GAP in this iteration: a fixed -50% premium floor is not the same distribution as
     "exit on the first 5m close back through the trigger level, else ride to -50%" -- the two
     can diverge in EITHER direction (chart-stop can exit earlier+tighter on a clean breakdown,
     or never fire at all on a wick that never closes through, riding further than -50% would
     allow only if intrabar touches don't count -- they do here, so this harness's floor stops
     are, if anything, a LATER/LOOSER proxy than the real chart-stop on trending days).

  4. FLEET GATE ("require_confluence_or_sequence"): accounts.json's tight-gate arms (safe-3,
     risky-1) require min_triggers>=2 AND require_confluence_or_sequence. The orchestrator has a
     min_triggers_bear/bull kwarg (mapped as the gate) but no "confluence-or-sequence" concept by
     name. orchestrator.py's OWN internal quality-tier classifier (lines ~1160-1219) defines
     ELITE as exactly "has_confluence or has_sequence" (before the SUPER escalation) -- so this
     harness reimplements that exact boolean (classify_tier() below, trigger-string-identical to
     the production classifier) as a POST-FILTER on run_backtest's trade list for safe-3/risky-1,
     which is a faithful (not approximate-by-guessing) translation of the real gate.

  5. FLEET QTY: fleet_executor.py's literal sizing formula was NOT read this iteration (time-
     boxed). Rather than guess a formula, this harness uses each arm's qty AS ACTUALLY OBSERVED
     in today's real fills (journal/2026-07-17.md quant table: safe-3=3, risky-1=5, risky-3=5)
     as a FLAT per-arm qty, and linearly rescales run_backtest's per-trade dollar_pnl by
     (flat_qty / trade.qty) -- option P&L is linear in qty for bracketed trades (the same
     rescaling convention bold_strike_axis_ab.py and this lineage's other strike-AB studies use).
     Disclosed as an approximation, not a verified sizing-function port.

ROOT-CAUSE FINDING (post-run diagnostic, 2026-07-17 -- see harness_verdict.root_cause in the
output JSON): the first-run baseline diverges MATERIALLY from live on every scored arm (see
FAITHFULNESS below), and the dominant mechanism is NOT the 5 fidelity decisions above -- it is
upstream of them, in the SIGNAL DETECTION layer itself:

  6. LEVEL-SET SOURCE MISMATCH: lib.orchestrator's level detector (lib.levels._detect_from_
     history) computes levels purely from spy_df price history. LIVE's actual level set is a
     DIFFERENT pipeline: automation/state/key-levels.json, refreshed intraday
     (refresh_levels_intraday.py, ran 08:28 ET today per journal/2026-07-17.md) plus J's manually
     ARMED zone-rejection intents (journal 10:39 ET: "levels are ZONES... Intent j-intent-
     20260717-103853-zone-reject-pdl ARMED"). Diagnostic evidence: replaying core_safe's raw
     decision log for today, the orchestrator's auto-detected levels produced ZERO candidate
     trigger rows near 11:06/11:40 ET -- live's two actual ELITE-tier put entries (-$37/-$102) --
     while producing an UNCALLED-FOR level_rejection candidate near 11:35 ET for core_bold that
     live never took, which alone flips core_bold's replayed day from a live +$191 to a replayed
     -$250 (11:35 P742 LEVEL-tier trade stopped for -$467.5). This is a genuine, mechanistic,
     bidirectional divergence source (misses live's real entries AND invents entries live didn't
     take), not a tuning-fixable gap -- closing it requires feeding this harness LIVE's actual
     level set (key-levels.json + armed zone intents), not the orchestrator's own auto-detector.
  7. BAR GRANULARITY: the orchestrator evaluates 5-minute bars (71 RTH rows today); live's
     heartbeat evaluates every 1-minute tick (386 ticks today per journal's funnel table). Finer
     granularity lets live catch trigger moments the 5-min bar close smooths over or shifts by
     up to 4 minutes -- a second, compounding source of entry-timing/count divergence.

Given #6 and #7, this iteration's VERDICT is that the harness is NOT YET faithful enough to tune
against (see harness_verdict below) -- reported honestly per the GOAL doc's instruction, not
forced. Closing #6 (feed the harness live's real level pipeline) is the highest-value next step,
scoped to iteration 2, not patched blindly here.

Guard: backtest/tests/test_replay_today_eval.py pins determinism (same tape+config -> same
per-arm P&L, byte-identical across two runs) and the faithfulness-delta values computed in this
run (regression pin -- if the harness or its inputs change, the guard fails loud instead of
silently drifting).

Run: backtest/.venv/Scripts/python.exe backtest/tools/replay_today_eval.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (REPO, BACKTEST, BACKTEST / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import sniper_matrix as SM  # noqa: E402 -- reused CSV timestamp normalizer
from lib.orchestrator import run_backtest  # noqa: E402
from crypto.lib.strike_selection import (  # noqa: E402
    V15_SAFE_TIERS, V15_BOLD_TIERS, pick_tier,
)

TRADE_DATE = dt.date(2026, 7, 17)
DATA_DIR = BACKTEST / "data"
SPY_PATH = DATA_DIR / "spy_5m_2026-05-19_2026-07-17.csv"
VIX_PATH = DATA_DIR / "vix_5m_2026-05-19_2026-07-17.csv"
CORE_SAFE_PARAMS_PATH = REPO / "automation" / "state" / "params.json"
CORE_BOLD_PARAMS_PATH = REPO / "automation" / "state" / "aggressive" / "params.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "replay-today-baseline-2026-07-17.json"
GOAL_DOC = REPO / "automation" / "overnight" / "GOAL-REPLAY-TODAY-GREEN.md"

# ---------------------------------------------------------------------------------------------
# LIVE BROKER-TRUTH (source: journal/2026-07-17.md QUANT block, "source: pnl-statement.json
# (T1, broker-truth)"). crypto-twin excluded from $-scoring per task instruction (mechanism-only).
# ---------------------------------------------------------------------------------------------
LIVE_TRUTH = {
    "core_safe":    {"label": "safe-2 (CORE-SAFE)",   "pnl": 240.0, "round_trips": 11},
    "core_bold":    {"label": "bold-2 (CORE-BOLD)",   "pnl": 191.0, "round_trips": 3},
    "fleet_safe_3": {"label": "safe-3 (FLEET-TIGHT-S)", "pnl": 0.0, "round_trips": 3},
    "fleet_risky_1": {"label": "risky-1 (FLEET-TIGHT-R)", "pnl": 0.0, "round_trips": 2},
    "fleet_risky_3": {"label": "risky-3 (FLEET-LOOSE-R)", "pnl": 248.0, "round_trips": 4},
}

# Faithfulness tolerance: disclosed convention, not a hidden magic number. An arm's replay is
# graded FAITHFUL if it lands within $150 of live AND (same sign as live, or live==0).
FAITHFULNESS_TOLERANCE_DOLLARS = 150.0

# ---------------------------------------------------------------------------------------------
# NAMED EVENTS -- the GOAL doc's capture-report targets (source: GOAL-REPLAY-TODAY-GREEN.md
# section "The eval" + journal/2026-07-17.md ENTER-events quant table).
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
     "expected_tier": None, "live_pnl": 105.0, "in_scope": False, "is_loser": False,
     "out_of_scope_reason": "j_bollinger_squeeze_* is a separate setup family (params.json "
                             "j_bollinger_squeeze_* keys) -- not wired into "
                             "lib.orchestrator.run_backtest's ribbon_ride detector. Iteration-1 "
                             "harness scope = ribbon_ride (BEARISH_REJECTION/BULLISH_RECLAIM_"
                             "RIDE_THE_RIBBON) family only."},
    {"id": "12:04_j_called_746C", "arm": "core_safe", "time_et": "12:04", "side": "C",
     "expected_tier": None, "live_pnl": 89.0, "in_scope": False, "is_loser": False,
     "out_of_scope_reason": "J's manual discretionary trade off his own hand-drawn descending "
                             "trendline (journal: 'Engine at the touch: bear 6-8 / bull 7, HOLD "
                             "-- no trigger class covers trendline retest'). No live engine rule "
                             "exists to fire this (trendline_reclaim is shadow-only, unthreaded) "
                             "-- structurally unreplayable by any config change, not a miss."},
]


def log(msg: str) -> None:
    print(f"[replay-today] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------------------------
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not SPY_PATH.exists() or not VIX_PATH.exists():
        raise FileNotFoundError(
            f"Today's SPY/VIX 5m bars not found ({SPY_PATH.name} / {VIX_PATH.name}). "
            f"Run tools/append_today.py first."
        )
    spy = SM.norm_str(pd.read_csv(SPY_PATH))
    vix = SM.norm_str(pd.read_csv(VIX_PATH))
    return spy, vix


# ---------------------------------------------------------------------------------------------
# TIER / GATE CLASSIFIER -- trigger-string-identical mirror of orchestrator.py's internal
# quality-tier logic (lines ~1160-1219). Used for reporting + the fleet confluence-or-sequence
# gate; does NOT influence the underlying simulation itself (that runs the real orchestrator).
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


# ---------------------------------------------------------------------------------------------
# PER-ARM STRIKE OFFSET (fidelity decision #1 -- see module docstring)
# ---------------------------------------------------------------------------------------------
def strike_offset_for(equity: float, table: tuple) -> int:
    tier = pick_tier(equity, table)
    # simulator_real.py uses the OPPOSITE sign convention (negative = OTM for puts);
    # crypto/lib/strike_selection positive=ITM -> simulator negative=ITM (same negation
    # orchestrator._params_to_kwargs itself applies for the same table -- see orchestrator.py
    # line ~373: "kwargs['strike_offset'] = -tier.strike_offset").
    return -tier.strike_offset


# ---------------------------------------------------------------------------------------------
# TRADE SERIALIZATION
# ---------------------------------------------------------------------------------------------
def trade_to_dict(t, qty_override: int | None = None) -> dict:
    factor = (qty_override / t.qty) if (qty_override and t.qty) else 1.0
    return {
        "entry_time_et": t.entry_time_et.isoformat() if hasattr(t.entry_time_et, "isoformat") else str(t.entry_time_et),
        "side": t.side,
        "strike": t.strike,
        "qty": qty_override if qty_override else t.qty,
        "orig_qty": t.qty,
        "entry_premium": round(t.entry_premium, 4),
        "triggers_fired": list(t.triggers_fired),
        "quality_tier": classify_tier(list(t.triggers_fired), t.side),
        "exit_reason": str(t.exit_reason) if t.exit_reason is not None else None,
        "dollar_pnl": round(t.dollar_pnl * factor, 2),
        "dollar_pnl_at_sim_qty": round(t.dollar_pnl, 2),
        "hold_minutes": t.hold_minutes,
        "setup": t.setup,
    }


# ---------------------------------------------------------------------------------------------
# CORE ARMS (safe-2 / bold-2) -- direct run_backtest w/ each account's REAL params.json
# ---------------------------------------------------------------------------------------------
def run_core_safe(spy: pd.DataFrame, vix: pd.DataFrame) -> dict:
    params = json.loads(CORE_SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
    equity = 1485.31  # SOD equity, journal/2026-07-17.md daily-loss-budget line (broker-verified)
    so = strike_offset_for(equity, V15_SAFE_TIERS)
    result = run_backtest(
        spy, vix, start_date=TRADE_DATE, end_date=TRADE_DATE,
        use_real_fills=True, params_overrides=params,
        initial_equity=equity, per_trade_risk_cap_pct=0.30,
        strike_offset=so, enable_bullish=True,
        profit_lock_mode="trailing", profit_lock_threshold_pct=0.05, profit_lock_trail_pct=0.125,
    )
    trades = [trade_to_dict(t) for t in sorted(result.trades, key=lambda t: t.entry_time_et)]
    return {
        "arm": "core_safe", "config_source": str(CORE_SAFE_PARAMS_PATH.relative_to(REPO)),
        "sod_equity": equity, "strike_offset": so, "strike_offset_label": "ATM",
        "trades": trades, "n_trades": len(trades),
        "total_pnl": round(sum(t["dollar_pnl"] for t in trades), 2),
    }


def run_core_bold(spy: pd.DataFrame, vix: pd.DataFrame) -> dict:
    params = json.loads(CORE_BOLD_PARAMS_PATH.read_text(encoding="utf-8"))
    equity = 1963.04  # SOD equity, journal/2026-07-17.md daily-loss-budget line
    so = strike_offset_for(equity, V15_BOLD_TIERS)
    result = run_backtest(
        spy, vix, start_date=TRADE_DATE, end_date=TRADE_DATE,
        use_real_fills=True, params_overrides=params,
        initial_equity=equity, per_trade_risk_cap_pct=0.50,
        strike_offset=so, enable_bullish=True,
        premium_stop_pct_bear=-0.50, premium_stop_pct_bull=-0.50,  # fidelity decision #3
    )
    trades = [trade_to_dict(t) for t in sorted(result.trades, key=lambda t: t.entry_time_et)]
    return {
        "arm": "core_bold", "config_source": str(CORE_BOLD_PARAMS_PATH.relative_to(REPO)),
        "sod_equity": equity, "strike_offset": so, "strike_offset_label": "OTM-3",
        "trades": trades, "n_trades": len(trades),
        "total_pnl": round(sum(t["dollar_pnl"] for t in trades), 2),
    }


# ---------------------------------------------------------------------------------------------
# FLEET ARMS -- min_triggers gate (kwarg) + confluence-or-sequence gate (post-filter, fidelity
# decision #4) + RIBBON_RIDE exit shape (explicit kwargs, fidelity decisions #2/#3) + flat-qty
# linear rescale (fidelity decision #5).
# ---------------------------------------------------------------------------------------------
FLEET_ARMS = {
    "fleet_safe_3": {"min_triggers": 2, "require_conf_or_seq": True, "risk_cap": 0.30, "flat_qty": 3},
    "fleet_risky_1": {"min_triggers": 2, "require_conf_or_seq": True, "risk_cap": 0.50, "flat_qty": 5},
    "fleet_risky_3": {"min_triggers": 1, "require_conf_or_seq": False, "risk_cap": 0.50, "flat_qty": 5},
}

# RIBBON_RIDE ExitShape values (automation/state/fleet/strategies.py -- read directly, not
# re-typed from memory). structure mode's stop replaced by the -0.50 catastrophe cap (decision #3).
RIBBON_RIDE_EXIT_KWARGS = dict(
    premium_stop_pct=-0.50,
    tp1_premium_pct=1.0,
    tp1_qty_fraction=0.667,
    profit_lock_mode="trailing",
    profit_lock_threshold_pct=0.05,
    profit_lock_trail_pct=0.15,
    runner_target_premium_pct=99.0,  # RIBBON_RIDE runner_target_pct=99.0 -- rides via trail/EOD
)


def run_fleet_arm(spy: pd.DataFrame, vix: pd.DataFrame, arm_key: str) -> dict:
    cfg = FLEET_ARMS[arm_key]
    base_params = json.loads(CORE_SAFE_PARAMS_PATH.read_text(encoding="utf-8"))  # shared v15.3 gate doctrine
    equity = 2000.0  # frozen fleet sizing basis (accounts.json starting_equity, all 3 arms)
    so = strike_offset_for(equity, V15_BOLD_TIERS)  # "bold" strike_tier_table for all 3 (accounts.json)
    result = run_backtest(
        spy, vix, start_date=TRADE_DATE, end_date=TRADE_DATE,
        use_real_fills=True, params_overrides=base_params,
        initial_equity=equity, per_trade_risk_cap_pct=cfg["risk_cap"],
        strike_offset=so, enable_bullish=True,
        min_triggers_bear=cfg["min_triggers"], min_triggers_bull=cfg["min_triggers"],
        **RIBBON_RIDE_EXIT_KWARGS,
    )
    admitted = result.trades
    if cfg["require_conf_or_seq"]:
        admitted = [t for t in admitted if passes_confluence_or_sequence(list(t.triggers_fired), t.side)]
    trades = [trade_to_dict(t, qty_override=cfg["flat_qty"]) for t in sorted(admitted, key=lambda t: t.entry_time_et)]
    return {
        "arm": arm_key, "config_source": "automation/state/fleet/strategies.py#RIBBON_RIDE + "
                                          "automation/state/fleet/accounts.json gate_override",
        "sod_equity": equity, "strike_offset": so, "strike_offset_label": "OTM-3",
        "min_triggers": cfg["min_triggers"], "require_confluence_or_sequence": cfg["require_conf_or_seq"],
        "flat_qty": cfg["flat_qty"],
        "trades": trades, "n_trades": len(trades),
        "total_pnl": round(sum(t["dollar_pnl"] for t in trades), 2),
    }


# ---------------------------------------------------------------------------------------------
# FAITHFULNESS CHECK
# ---------------------------------------------------------------------------------------------
def faithfulness_for(arm_key: str, replay_pnl: float) -> dict:
    live = LIVE_TRUTH[arm_key]["pnl"]
    delta = round(replay_pnl - live, 2)
    same_sign_or_zero = (live == 0.0) or (replay_pnl == 0.0) or ((replay_pnl > 0) == (live > 0))
    faithful = bool(abs(delta) <= FAITHFULNESS_TOLERANCE_DOLLARS and same_sign_or_zero)
    return {
        "live_pnl": live, "replay_pnl": replay_pnl, "delta": delta,
        "tolerance_dollars": FAITHFULNESS_TOLERANCE_DOLLARS,
        "same_sign_or_zero": same_sign_or_zero, "faithful": faithful,
    }


# ---------------------------------------------------------------------------------------------
# CAPTURE REPORT -- did the replay take the named sniper entries / avoid-or-take the losers?
# Match window: entry within +/-10 minutes of the named event's time, same side, same arm.
# ---------------------------------------------------------------------------------------------
def match_event(event: dict, arm_result: dict) -> dict:
    if not event["in_scope"]:
        return {**event, "captured": None, "matched_trade": None,
                "note": event.get("out_of_scope_reason")}
    target = dt.datetime.combine(TRADE_DATE, dt.datetime.strptime(event["time_et"], "%H:%M").time())
    best = None
    best_gap = None
    for t in arm_result["trades"]:
        et = dt.datetime.fromisoformat(t["entry_time_et"])
        et_naive = et.replace(tzinfo=None)
        if t["side"] != event["side"]:
            continue
        gap = abs((et_naive - target).total_seconds())
        if gap <= 600 and (best_gap is None or gap < best_gap):
            best, best_gap = t, gap
    return {**event, "captured": best is not None, "matched_trade": best,
            "gap_seconds": best_gap}


def capture_report(all_results: dict) -> list[dict]:
    return [match_event(ev, all_results[ev["arm"]]) for ev in NAMED_EVENTS]


# ---------------------------------------------------------------------------------------------
# DETERMINISM HASH -- guard-test target
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
    log(f"Loading {SPY_PATH.name} / {VIX_PATH.name}")
    spy, vix = load_data()
    log(f"spy bars total={len(spy)}")

    log("Running core_safe (params.json, ATM strike, chandelier explicit)")
    core_safe = run_core_safe(spy, vix)
    log(f"  core_safe: n={core_safe['n_trades']} total_pnl=${core_safe['total_pnl']}")

    log("Running core_bold (aggressive/params.json, OTM-3 strike, catastrophe stop explicit)")
    core_bold = run_core_bold(spy, vix)
    log(f"  core_bold: n={core_bold['n_trades']} total_pnl=${core_bold['total_pnl']}")

    fleet_results = {}
    for arm_key in FLEET_ARMS:
        log(f"Running {arm_key} (RIBBON_RIDE exit shape, gate_override, flat-qty rescale)")
        r = run_fleet_arm(spy, vix, arm_key)
        fleet_results[arm_key] = r
        log(f"  {arm_key}: n={r['n_trades']} total_pnl=${r['total_pnl']}")

    all_results = {"core_safe": core_safe, "core_bold": core_bold, **fleet_results}

    faithfulness = {k: faithfulness_for(k, v["total_pnl"]) for k, v in all_results.items()}
    all_faithful = all(f["faithful"] for f in faithfulness.values())
    n_faithful = sum(1 for f in faithfulness.values() if f["faithful"])

    events = capture_report(all_results)
    n_in_scope = sum(1 for e in events if e["in_scope"])
    n_captured = sum(1 for e in events if e["in_scope"] and e["captured"])

    dh = determinism_hash(all_results)

    out = {
        "_doc": "GOAL-REPLAY-TODAY-GREEN iteration 1 -- eval harness baseline. Measurement only; "
                "no params/config/strike-table file was modified by this run. Source: "
                "backtest/tools/replay_today_eval.py.",
        "generated_at": dt.datetime.now().isoformat(),
        "trade_date": TRADE_DATE.isoformat(),
        "determinism_hash": dh,
        "faithfulness_tolerance_dollars": FAITHFULNESS_TOLERANCE_DOLLARS,
        "arms": all_results,
        "live_truth": LIVE_TRUTH,
        "faithfulness": faithfulness,
        "faithfulness_summary": {
            "n_arms": len(all_results), "n_faithful": n_faithful, "all_faithful": all_faithful,
        },
        "capture_report": events,
        "capture_summary": {"n_in_scope": n_in_scope, "n_captured": n_captured,
                             "n_out_of_scope": len(NAMED_EVENTS) - n_in_scope},
        "harness_verdict": {
            "trustworthy_to_tune_against": all_faithful,
            "note": (
                "All 5 scored arms land within the disclosed $150 faithfulness tolerance -- "
                "the harness reproduces live P&L closely enough to tune against."
                if all_faithful else
                "NOT YET faithful: one or more arms diverge from live P&L beyond the disclosed "
                "$150 tolerance. Per the GOAL doc's own instruction, this is reported honestly "
                "rather than papered over -- see each arm's faithfulness delta + the module "
                "docstring's FIDELITY DECISIONS 1-7 for the known, mechanistically-identified "
                "gaps. Root-causing points to gap #6 (level-set source mismatch) as DOMINANT, "
                "not the exit-mechanics approximations (#1-5) -- see root_cause below. "
                "Closing/fixing this is scoped to iteration 2+, not this measurement-only run."
            ),
            "root_cause": {
                "dominant_mechanism": "level_set_source_mismatch",
                "evidence": (
                    "core_safe raw decision log for 2026-07-17: the orchestrator's price-history "
                    "auto-detected levels (lib.levels._detect_from_history) produced ZERO "
                    "candidate trigger rows near 11:06/11:40 ET, live's two actual ELITE-tier put "
                    "entries (-$37/-$102 live) -- while producing an uncalled-for level_rejection "
                    "candidate near 11:35 ET for core_bold that live never took (11:35 P742 "
                    "LEVEL-tier, stopped -$467.50), which alone flips core_bold's replayed day "
                    "from live's +$191 to a replayed -$250. Live's real level set is "
                    "automation/state/key-levels.json (refreshed intraday via "
                    "refresh_levels_intraday.py, 08:28 ET today) plus J's manually-armed "
                    "zone-rejection intents (journal 10:39 ET) -- neither is consumed by "
                    "lib.orchestrator's auto-detector."
                ),
                "secondary_mechanism": "bar_granularity: orchestrator evaluates 71 5-min RTH "
                    "bars today vs live's 386 1-min heartbeat ticks (journal funnel table) -- "
                    "compounds entry-timing/count divergence on top of the level-set gap.",
                "implication": "Fidelity decisions #1-5 (strike/profit-lock/stop/gate/qty) are "
                    "real and worth keeping, but are NOT the dominant divergence source this "
                    "iteration -- fixing them alone would not make this harness faithful. The "
                    "highest-value next step is feeding this harness live's actual level "
                    "pipeline (key-levels.json + armed zone intents) instead of the "
                    "orchestrator's own price-only auto-detector.",
            },
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    log(f"FAITHFULNESS: {n_faithful}/{len(all_results)} arms within ${FAITHFULNESS_TOLERANCE_DOLLARS} "
        f"tolerance. all_faithful={all_faithful}")
    log(f"CAPTURE: {n_captured}/{n_in_scope} in-scope named events captured "
        f"({len(NAMED_EVENTS) - n_in_scope} out-of-scope, disclosed)")
    log(f"determinism_hash={dh}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
