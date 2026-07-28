"""exit_armscope_ab_2026_07_28.py -- EXIT-ARMSCOPE-TP1 pre-registered A/B scorecard, run
EXACTLY per analysis/recommendations/prereg-exit-armscope-tp1-2026-07-28.json (frozen before
any computation below ran).

THE INCIDENT (why this exists): 2026-07-28 Bold, 5x SPY260728C00741000, level_reclaim @741.0.
Entry 1.38, ran to HWM 2.16 (+56.5%) at 12:57 ET, closed ~0.79 (-42%) via structure_stop
because RIBBON_RIDE's profit-lock (trailing, trail_pct=0.15, arm_pct=0.05) only ARMS
post_tp1 -- and tp1_premium_pct=1.0 (+100%) was never reached even at HWM. The trail never
armed; the position round-tripped from +56% to a loss. exit_manager.py:73-81 names this
exact gap: ARM_SCOPE_FULL is expressible but never armed "until a live-machine scorecard +
STOP-B arms it." This IS that scorecard.

METHOD (non-negotiable, both are prior scars this file routes around):
  1. Exits are re-derived ONLY through backtest/lib/exit_manager_walk.walk_exit_manager,
     driving the REAL live exit core (automation/state/fleet/exit_manager.py#plan_exit_actions)
     -- NEVER simulator_real.simulate_trade_real. The 2026-07-09 SIM-EXIT-SHAPE-PARITY finding:
     the simulator arms profit-lock pre-TP1 by default while this live core arms post-TP1, so
     every simulate_trade_real-based scorecard crediting profit_lock overstated live
     protection. See engine_fullhist_replay.py's docstring for the two-layer pattern this file
     reuses verbatim (entries frozen, exits re-walked).
  2. ENTRIES ARE UNCHANGED ACROSS ALL 4 CELLS. This is an exit-only test on the SAME trade
     population engine_fullhist_replay.py / exit_leak_decompose.py already produced and
     verified: analysis/recommendations/engine-fullhist-replay-2026-07-23.json's `trades`
     (190, RIDE_THE_RIBBON family, real-OPRA-derived, entry+1 convention per
     markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md). Reused verbatim here --
     NEVER re-run at the entry layer (no run_backtest call in this file). Only the exit_shape
     dict fed into walk_exit_manager varies per cell; the registry (strategies.py) is never
     edited -- these shapes are constructed in-memory in build_cells() below.

4 CELLS (frozen, no sweep, no_other_knobs -- trail_pct/arm_pct/catastrophe_stop_pct/stop_mode
stay exactly as RIBBON_RIDE.exit ships):
  CONTROL : live config as-is (profit_lock_arm_scope="post_tp1", tp1_premium_pct=1.0)
  E1      : profit_lock_arm_scope="full" (arm the existing trail pre-TP1, at +5% favor). ONE key.
  E2      : tp1_premium_pct 1.0 -> 0.5 (a reachable TP1; arm_scope stays post_tp1). ONE key.
  E3      : E1 + E2 combined. TWO keys.

GATES (frozen, see prereg's `gates_frozen`):
  G1 positive aggregate delta vs CONTROL.
  G2 majority of CHANGED trades (cell_pnl != control_pnl) are positive.
  G3 survives dropping the single best (most positive) changed trade.
  G4 ANCHOR-NO-REGRESSION on the 35 RUNNER_TRAIL winners (+$15,774.05 total, identified from
     THIS file's own CONTROL walk, cross-checked against analysis/deep-research/
     EXIT-LEAK-2026-07-28.json's table1). A cell that degrades this cohort's aggregate FAILS
     regardless of G1 -- this is the book's entire profit engine (see CLAUDE.md C30/doctrine
     on why blanket-tighter exits were killed before).
  G5 no look-ahead: the pre-TP1 ARM_SCOPE_FULL ratchet cannot use a tick's OWN favorable
     extreme (point-sampled best_premium == worst_premium, exit_manager_walk.py's documented
     convention) to justify an exit trigger on that SAME tick. Structurally guaranteed by the
     arithmetic (floor = hwm*(1-trail_pct) < hwm whenever trail_pct>0) and pinned by a real
     synthetic-fixture test in backtest/tests/test_exit_armscope_ab.py -- not re-derived here,
     just referenced per-cell in the report (vacuous-pass for CONTROL/E2, which never touch
     the pre-TP1 arm_scope=full code path at all).
  G6 today's 2026-07-28 Bold trade must improve materially under E1 (and by extension E3,
     which contains E1's mechanism). SIGNAL-LEVEL, DISCLOSED: no OPRA cache exists for
     same-day 2026-07-28 (the backtest key has no same-day SIP entitlement), so this trade is
     NOT walked via walk_exit_manager/cached bars. Instead it is reconstructed from
     automation/state/core-decisions.jsonl's `exit_pass` field -- the LITERAL best_premium/
     worst_premium/last_closed_5m_close the LIVE engine observed and fed to plan_exit_actions
     every minute today (IEX-quote-derived; this is real recorded live data, not a synthetic
     bar series) -- and walked tick-by-tick through the SAME em.plan_exit_actions core, one
     run per cell. Disclosed as signal-level throughout; never presented as an OPRA replay.

OUTPUTS: analysis/recommendations/exit-armscope-tp1-ab-2026-07-28.{json,md}.

ANALYSIS ONLY: writes only to analysis/recommendations/. Never touches exit_manager.py,
strategies.py, params.json, or any trading-path file. No broker imports, no network calls.

Run: backtest/.venv/Scripts/python.exe backtest/tools/exit_armscope_ab_2026_07_28.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]          # repo root
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(FLEET_DIR), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import exit_manager as em  # noqa: E402  -- automation/state/fleet/exit_manager.py
import strategies as fleet_strategies  # noqa: E402  -- automation/state/fleet/strategies.py
from lib.exit_manager_walk import (  # noqa: E402
    DEFAULT_EXIT_SLIPPAGE, _fill_price, _stage_fill_level, walk_exit_manager,
)
from lib.option_pricing_real import load_contract_bars  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "prereg-exit-armscope-tp1-2026-07-28.json"
SOURCE_REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
ANCHOR_LEAK = REPO / "analysis" / "deep-research" / "EXIT-LEAK-2026-07-28.json"
SPY_FILE = BACKTEST / "data" / "spy_5m_2025-01-01_2026-07-22.csv"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"

OUT_JSON = REPO / "analysis" / "recommendations" / "exit-armscope-tp1-ab-2026-07-28.json"
OUT_MD = REPO / "analysis" / "recommendations" / "exit-armscope-tp1-ab-2026-07-28.md"

# Matches SAFE_BASE's time_stop_minutes_before_close=20, the SAME convention
# engine_fullhist_replay.py / exit_leak_decompose.py used to build SOURCE_REPLAY -- required
# for the CONTROL cell to byte-reconcile against the source population's dollar_pnl.
TIME_STOP_ET = dt.time(15, 40)

TODAY_SYMBOL = "SPY260728C00741000"
TODAY_ENTRY_PREMIUM = 1.38
TODAY_QTY = 5
TODAY_TRIGGER_LEVEL = 741.0
TODAY_SIDE = "C"
TODAY_TIME_STOP_ET = dt.time(15, 50)  # em.TIME_STOP_ET default (RIBBON_RIDE ships no override)

# RUNNER_TRAIL anchor cohort sanity: EXIT-LEAK-2026-07-28.json's table1 (independently derived
# from the SAME source population). Cross-checked, never assumed.
ANCHOR_RUNNER_N = 35
ANCHOR_RUNNER_PNL = 15774.05


def log(msg: str) -> None:
    print(f"[exit-armscope-ab] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# PURE HELPERS (unit-tested in backtest/tests/test_exit_armscope_ab.py)
# ---------------------------------------------------------------------------------------------
def build_cells(control_shape: dict) -> dict:
    """The 4 cells frozen in the prereg. Each is a FRESH dict copy of control_shape with
    EXACTLY the named key(s) changed -- no_other_knobs: trail_pct/arm_pct/catastrophe_stop_pct/
    stop_mode never move. Never aliases control_shape (coding-style: immutability)."""
    return {
        "CONTROL": dict(control_shape),
        "E1": dict(control_shape, profit_lock_arm_scope=em.ARM_SCOPE_FULL),
        "E2": dict(control_shape, tp1_premium_pct=0.5),
        "E3": dict(control_shape, profit_lock_arm_scope=em.ARM_SCOPE_FULL, tp1_premium_pct=0.5),
    }


CELL_N_KEYS_CHANGED = {"CONTROL": 0, "E1": 1, "E2": 1, "E3": 2}
# G5 (look-ahead) only ever exercises new code (the pre-TP1 ARM_SCOPE_FULL ratchet) on cells
# that actually set profit_lock_arm_scope="full" -- CONTROL/E2 never touch that branch.
CELLS_EXERCISING_ARM_SCOPE_FULL = ("E1", "E3")
# G6 formally gates only cells containing E1's mechanism (E1, E3); shown for E2/CONTROL as
# context/disclosure, never as a pass/fail bar (prereg names E1 explicitly as "the motivating
# case").
CELLS_GATED_ON_G6 = ("E1", "E3")


def exit_family(exit_reason: str, resolved_stop_mode: str) -> str:
    """Mechanical family a walk's terminal exit_reason belongs to. Extends
    exit_leak_decompose.py's exit_family with the ONE new stage E1/E3 can produce
    (profit_lock_floor firing pre-TP1, under arm_scope=full) that CONTROL/E2 never emit."""
    r = exit_reason or ""
    if r.startswith("profit_lock_floor"):
        return "PROFIT_LOCK_FLOOR_PRE_TP1"
    if r.startswith("premium_stop"):
        return "PREMIUM_STOP_20" if resolved_stop_mode == "premium" else "CATASTROPHE_50"
    if r.startswith("runner_stop"):
        return "RUNNER_TRAIL"
    if r.startswith("structure_stop"):
        return "STRUCTURE_STOP"
    if r.startswith("ribbon_flip"):
        return "RIBBON_FLIP"
    if r.startswith("time_stop"):
        return "TIME_STOP"
    if r.startswith("runner_target"):
        return "RUNNER_TARGET"
    if r.startswith("tp1"):
        return "TP1_FINAL"
    if r.startswith("data_exhausted"):
        return "DATA_EXHAUSTED"
    return "OTHER"


def build_ribbon_lookup(spy_df: pd.DataFrame) -> pd.DataFrame:
    """Continuous RTH-only ribbon (byte-identical construction to engine_fullhist_replay.py /
    exit_leak_decompose.py -- same warmup, same continuity across days)."""
    rth_mask = ((spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
                & (spy_df["timestamp_et"].dt.time < dt.time(16, 0)))
    spy_rth = spy_df.loc[rth_mask].reset_index(drop=True)
    ribbon = compute_ribbon(spy_rth["close"])
    out = spy_rth[["timestamp_et"]].copy()
    out["stack"] = ribbon["stack"].values
    return out.sort_values("timestamp_et").reset_index(drop=True)


def ribbon_tick_df_for(opt_df: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> pd.DataFrame:
    """Backward (no-lookahead) as-of join onto this trade's own option-bar timestamps."""
    left = opt_df[["timestamp_et"]].copy()
    if getattr(left["timestamp_et"].dt, "tz", None) is not None:
        left["timestamp_et"] = left["timestamp_et"].dt.tz_localize(None)
    right = ribbon_lookup.copy()
    if getattr(right["timestamp_et"].dt, "tz", None) is not None:
        right["timestamp_et"] = right["timestamp_et"].dt.tz_localize(None)
    left = left.sort_values("timestamp_et", kind="stable")
    right = right.sort_values("timestamp_et", kind="stable")
    merged = pd.merge_asof(left, right, on="timestamp_et", direction="backward")
    assert len(merged) == len(opt_df), "merge_asof row count drifted -- alignment broken"
    return merged.reset_index(drop=True)[["stack"]]


def naive_dt(ts) -> dt.datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts


def load_today_bold_ticks() -> list:
    """Real recorded live ticks for TODAY_SYMBOL from automation/state/core-decisions.jsonl's
    `exit_pass` field -- the literal best_premium/worst_premium/last_closed_5m_close the LIVE
    engine observed each minute (account=='bold', date 2026-07-28). SIGNAL-LEVEL, DISCLOSED:
    this is real IEX-quote-derived data the live system itself consumed, not a synthetic bar
    series and not an OPRA replay (no same-day OPRA cache exists for today)."""
    rows = []
    if not CORE_DECISIONS.exists():
        return rows
    with CORE_DECISIONS.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if d.get("account") != "bold":
                continue
            ts = d.get("ts_et", "")
            if not ts.startswith("2026-07-28"):
                continue
            for ep in d.get("exit_pass", []) or []:
                if ep.get("symbol") == TODAY_SYMBOL:
                    rows.append((ts, ep))
    rows.sort(key=lambda r: r[0])
    return rows


def replay_today_trade(cell_shape: dict, ticks: list) -> dict:
    """Walk TODAY_SYMBOL's real recorded live ticks through the REAL em.plan_exit_actions
    decision core under `cell_shape`. Mirrors walk_exit_manager's own fill-price convention
    (_stage_fill_level / _fill_price) so limit-style stages fill at the triggered level and
    market-style stages fill at (this tick's worst_premium - slippage), the closest available
    analog to 'bar close' when driving real point-sample ticks instead of an OHLC frame.
    ribbon_flip_back is not present in this log (not recorded per-tick) so it is held False
    throughout -- disclosed; the actual live exit this trade took was structure_stop, not a
    ribbon flip, so this omission does not change the CONTROL reproduction."""
    state = em.ExitState.from_entry(
        symbol=TODAY_SYMBOL, side=TODAY_SIDE, entry_premium=TODAY_ENTRY_PREMIUM, qty=TODAY_QTY,
        exit_shape=cell_shape, strategy="ribbon_ride", trigger_level=TODAY_TRIGGER_LEVEL,
        structure_stop_enabled=True,
    )
    open_qty = TODAY_QTY
    realized = 0.0
    legs = []
    resolved = False
    exit_ts = None
    exit_reason = ""
    for ts_str, ep in ticks:
        if open_qty <= 0:
            break
        t = dt.datetime.fromisoformat(ts_str)
        best = float(ep["best_premium"])
        worst = float(ep["worst_premium"])
        closed5 = ep.get("last_closed_5m_close")
        closed5 = float(closed5) if closed5 is not None else None
        state_in = state
        dec = em.plan_exit_actions(
            state_in, best_premium=best, worst_premium=worst, open_qty=open_qty,
            now_et=t.time(), ribbon_flip_back=False, time_stop_et=TODAY_TIME_STOP_ET,
            last_closed_5m_close=closed5)
        state = dec.state
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            level = _stage_fill_level(a.stage, state_in, state)
            px = _fill_price(a.stage, level, worst)
            leg_pnl = (px - TODAY_ENTRY_PREMIUM) * a.qty * 100.0
            realized += leg_pnl
            open_qty -= a.qty
            legs.append({"ts_et": ts_str, "kind": a.kind, "qty": a.qty, "fill_price": round(px, 4),
                         "reason": a.reason, "stage": a.stage, "leg_pnl": round(leg_pnl, 2)})
        if dec.closes_position:
            resolved = True
            exit_ts = ts_str
            exit_reason = dec.actions[-1].reason
            break
    if not resolved and open_qty > 0 and ticks:
        last_ts, last_ep = ticks[-1]
        px = max(0.01, float(last_ep["worst_premium"]) - DEFAULT_EXIT_SLIPPAGE)
        leg_pnl = (px - TODAY_ENTRY_PREMIUM) * open_qty * 100.0
        realized += leg_pnl
        legs.append({"ts_et": last_ts, "kind": "SELL_ALL", "qty": open_qty, "fill_price": round(px, 4),
                     "reason": "data_exhausted_force_close", "stage": "force_close",
                     "leg_pnl": round(leg_pnl, 2)})
        exit_ts = last_ts
        exit_reason = "data_exhausted_force_close"
    hwm_observed = max((float(ep["best_premium"]) for _, ep in ticks), default=TODAY_ENTRY_PREMIUM)
    return {
        "dollar_pnl": round(realized, 2), "exit_reason": exit_reason, "exit_ts_et": exit_ts,
        "legs": legs, "hwm_observed": hwm_observed, "resolved_stop_mode": state.stop_mode,
        "family": exit_family(exit_reason, state.stop_mode),
    }


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:  # noqa: C901 -- single linear scorecard pipeline, deliberately unsplit
    t0 = time.time()
    assert PREREG.exists(), f"frozen pre-reg missing: {PREREG}"
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))

    src = json.loads(SOURCE_REPLAY.read_text(encoding="utf-8"))
    trades = src["trades"]
    log(f"loaded {len(trades)} frozen entries from {SOURCE_REPLAY.name} "
        f"(entries UNCHANGED -- exit-only test)")

    spy_df = pd.read_csv(SPY_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    ribbon_lookup = build_ribbon_lookup(spy_df)

    control_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    cells = build_cells(control_shape)
    log(f"cells: { {k: v for k, v in cells.items()} }")

    rows: list = []
    n_no_opra = 0
    n_no_spy_day = 0
    n_control_mismatch = 0

    for t in trades:
        symbol = t["symbol"]
        date = dt.date.fromisoformat(t["date"])
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            n_no_opra += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == date].reset_index(drop=True)
        if day_spy.empty:
            n_no_spy_day += 1
            continue

        entry_time_et = naive_dt(dt.datetime.fromisoformat(t["entry_time_et"]))
        entry_premium = float(t["entry_premium"])
        trigger_level = t["trigger_level"]
        trigger_level = float(trigger_level) if trigger_level is not None else None
        qty = int(t["qty"])
        rtd = ribbon_tick_df_for(opt_df, ribbon_lookup)
        common = dict(symbol=symbol, side=t["side"], entry_time_et=entry_time_et,
                      entry_premium=entry_premium, qty=qty, structure_stop_enabled=True,
                      trigger_level=trigger_level, strategy="ribbon_ride",
                      time_stop_et=TIME_STOP_ET, opt_df=opt_df, ribbon_tick_df=rtd,
                      five_min_spy_df=day_spy)

        row = {"date": t["date"], "entry_time_et": t["entry_time_et"], "symbol": symbol,
               "side": t["side"], "tier": t["tier"], "qty": qty,
               "entry_premium": round(entry_premium, 4), "trigger_level": trigger_level}
        for cell_name, shape in cells.items():
            res = walk_exit_manager(exit_shape=shape, **common)
            row[cell_name] = {
                "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
                "resolved_stop_mode": res.stop_mode, "hold_minutes": res.hold_minutes,
                "family": exit_family(res.exit_reason, res.stop_mode),
            }
        if abs(row["CONTROL"]["dollar_pnl"] - t["dollar_pnl"]) > 0.01:
            n_control_mismatch += 1
            row["control_mismatch_vs_source"] = True
        else:
            row["control_mismatch_vs_source"] = False
        rows.append(row)

    log(f"walked {len(rows)} trades x 4 cells -- n_no_opra={n_no_opra} "
        f"n_no_spy_day={n_no_spy_day} n_control_mismatch_vs_source={n_control_mismatch}")
    assert rows, "zero trades walked -- aborting"

    # --- runner-cohort identification (from THIS file's own CONTROL walk) --------------------
    runner_idx = [i for i, r in enumerate(rows) if r["CONTROL"]["family"] == "RUNNER_TRAIL"]
    runner_control_sum = round(sum(rows[i]["CONTROL"]["dollar_pnl"] for i in runner_idx), 2)
    log(f"runner cohort: n={len(runner_idx)} control_pnl_sum=${runner_control_sum} "
        f"(anchor: n={ANCHOR_RUNNER_N} pnl=${ANCHOR_RUNNER_PNL})")

    # --- today's trade (G6), 4 cells -----------------------------------------------------
    ticks = load_today_bold_ticks()
    log(f"today's trade: {len(ticks)} real recorded live ticks loaded for {TODAY_SYMBOL}")
    today_results = {cell_name: replay_today_trade(shape, ticks) for cell_name, shape in cells.items()}

    # --- per-cell gates ------------------------------------------------------------------
    cell_reports = {}
    for cell_name in ("E1", "E2", "E3"):
        cell_reports[cell_name] = compute_cell_gates(
            rows, cell_name, runner_idx, runner_control_sum, today_results, prereg)

    verdict = decide_arming(cell_reports)

    total_elapsed = time.time() - t0
    write_scorecard(prereg, rows, cells, control_shape, runner_idx, runner_control_sum,
                     today_results, cell_reports, verdict, n_no_opra, n_no_spy_day,
                     n_control_mismatch, ticks, total_elapsed)
    return 0


def compute_cell_gates(rows: list, cell_name: str, runner_idx: list, runner_control_sum: float,
                       today_results: dict, prereg: dict) -> dict:
    control_pnls = [r["CONTROL"]["dollar_pnl"] for r in rows]
    cell_pnls = [r[cell_name]["dollar_pnl"] for r in rows]
    deltas = [round(c - ctl, 2) for c, ctl in zip(cell_pnls, control_pnls)]

    agg_delta = round(sum(deltas), 2)
    g1 = agg_delta > 0

    changed = [i for i, d in enumerate(deltas) if abs(d) > 0.005]
    n_pos = sum(1 for i in changed if deltas[i] > 0)
    n_neg = sum(1 for i in changed if deltas[i] < 0)
    g2 = n_pos > n_neg

    if changed:
        best1_i = max(changed, key=lambda i: deltas[i])
        best1_delta = deltas[best1_i]
        delta_ex_best1 = round(agg_delta - best1_delta, 2)
        best1_trade = {"date": rows[best1_i]["date"], "symbol": rows[best1_i]["symbol"],
                       "delta": best1_delta}
    else:
        best1_delta = 0.0
        delta_ex_best1 = agg_delta
        best1_trade = None
    g3 = delta_ex_best1 > 0

    runner_cell_sum = round(sum(rows[i][cell_name]["dollar_pnl"] for i in runner_idx), 2)
    runner_delta = round(runner_cell_sum - runner_control_sum, 2)
    n_runner_worse = sum(1 for i in runner_idx
                         if rows[i][cell_name]["dollar_pnl"] < rows[i]["CONTROL"]["dollar_pnl"] - 0.005)
    n_runner_better = sum(1 for i in runner_idx
                          if rows[i][cell_name]["dollar_pnl"] > rows[i]["CONTROL"]["dollar_pnl"] + 0.005)
    n_runner_unchanged = len(runner_idx) - n_runner_worse - n_runner_better
    g4 = runner_delta >= 0

    exercises_arm_scope_full = cell_name in CELLS_EXERCISING_ARM_SCOPE_FULL
    g5 = True  # structural invariant, guarded by backtest/tests/test_exit_armscope_ab.py;
               # vacuously true for cells that never touch the pre-TP1 arm_scope=full branch

    today_ctl = today_results["CONTROL"]["dollar_pnl"]
    today_cell = today_results[cell_name]["dollar_pnl"]
    today_delta = round(today_cell - today_ctl, 2)
    g6_gated = cell_name in CELLS_GATED_ON_G6
    g6 = (today_delta > 50.0) if g6_gated else None  # "materially" -- >$50 swing on a 5-lot

    required_gates = [g1, g2, g3, g4, g5] + ([g6] if g6_gated else [])
    clears_all = all(required_gates)

    return {
        "cell": cell_name, "n_keys_changed": CELL_N_KEYS_CHANGED[cell_name],
        "aggregate_control_pnl": round(sum(control_pnls), 2),
        "aggregate_cell_pnl": round(sum(cell_pnls), 2),
        "g1_positive_aggregate": {"delta": agg_delta, "pass": g1},
        "g2_majority_changed_positive": {"n_changed": len(changed), "n_positive": n_pos,
                                          "n_negative": n_neg, "pass": g2},
        "g3_survives_drop_best1": {"best1_trade": best1_trade, "best1_delta": best1_delta,
                                    "delta_ex_best1": delta_ex_best1, "pass": g3},
        "g4_runner_cohort_no_regression": {
            "n_cohort": len(runner_idx), "control_pnl_sum": runner_control_sum,
            "cell_pnl_sum": runner_cell_sum, "delta": runner_delta,
            "n_worse": n_runner_worse, "n_better": n_runner_better,
            "n_unchanged": n_runner_unchanged, "pass": g4},
        "g5_look_ahead_guard": {
            "exercises_arm_scope_full_pretp1": exercises_arm_scope_full,
            "note": ("guarded by backtest/tests/test_exit_armscope_ab.py -- structural "
                     "invariant (floor = hwm*(1-trail_pct) < hwm whenever trail_pct>0 means a "
                     "tick's own new HWM can never also breach the floor it just set)"
                     if exercises_arm_scope_full else
                     "vacuous pass -- this cell never touches the pre-TP1 arm_scope=full "
                     "ratchet branch at all"),
            "pass": g5},
        "g6_today_trade": {
            "gated": g6_gated, "control_pnl": today_ctl, "cell_pnl": today_cell,
            "delta": today_delta, "cell_exit_reason": today_results[cell_name]["exit_reason"],
            "pass": g6},
        "clears_all_required_gates": clears_all,
    }


def decide_arming(cell_reports: dict) -> dict:
    """arming_rule: arm ONLY the single best-performing cell that clears all required gates;
    if the top performers are within a small practical tie, prefer the SIMPLER (fewer keys
    changed). If none clear, arm nothing."""
    candidates = [c for c in ("E1", "E2", "E3") if cell_reports[c]["clears_all_required_gates"]]
    if not candidates:
        return {"decision": "ARM_NOTHING", "cell": None, "reason": "no cell cleared all required gates"}
    candidates.sort(key=lambda c: cell_reports[c]["g1_positive_aggregate"]["delta"], reverse=True)
    top = candidates[0]
    top_delta = cell_reports[top]["g1_positive_aggregate"]["delta"]
    tied = [c for c in candidates
           if abs(cell_reports[c]["g1_positive_aggregate"]["delta"] - top_delta) <= 25.0]
    if len(tied) > 1:
        tied.sort(key=lambda c: cell_reports[c]["n_keys_changed"])
        chosen = tied[0]
        reason = (f"practical tie among {tied} (within $25 aggregate) -- chose simpler "
                  f"({cell_reports[chosen]['n_keys_changed']} key(s) changed)")
    else:
        chosen = top
        reason = f"best aggregate delta among cells clearing all gates: {candidates}"
    return {"decision": "ARM", "cell": chosen, "reason": reason, "candidates_cleared": candidates}


def write_scorecard(prereg, rows, cells, control_shape, runner_idx, runner_control_sum,
                    today_results, cell_reports, verdict, n_no_opra, n_no_spy_day,
                    n_control_mismatch, ticks, total_elapsed) -> None:
    out = {
        "_doc": __doc__,
        "prereg_id": prereg["prereg_id"],
        "prereg_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "generated_at": dt.datetime.now().isoformat(),
        "runtime_seconds": round(total_elapsed, 1),
        "population": {
            "source": str(SOURCE_REPLAY.relative_to(REPO)).replace("\\", "/"),
            "n_trades_source": len(rows), "n_excluded_no_opra_cache": n_no_opra,
            "n_excluded_no_spy_day": n_no_spy_day,
            "n_control_mismatch_vs_source": n_control_mismatch,
            "note": "entries UNCHANGED from CONTROL (exit-only A/B); real-OPRA-only P&L.",
        },
        "cells": cells,
        "runner_cohort": {
            "n": len(runner_idx), "control_pnl_sum": runner_control_sum,
            "anchor_check": {"expected_n": ANCHOR_RUNNER_N, "expected_pnl": ANCHOR_RUNNER_PNL,
                             "n_matches": len(runner_idx) == ANCHOR_RUNNER_N,
                             "pnl_matches": abs(runner_control_sum - ANCHOR_RUNNER_PNL) < 1.0},
            "trades": [{"date": rows[i]["date"], "symbol": rows[i]["symbol"],
                       "control_pnl": rows[i]["CONTROL"]["dollar_pnl"]} for i in runner_idx],
        },
        "today_trade": {
            "symbol": TODAY_SYMBOL, "entry_premium": TODAY_ENTRY_PREMIUM, "qty": TODAY_QTY,
            "trigger_level": TODAY_TRIGGER_LEVEL,
            "n_real_ticks_used": len(ticks),
            "disclosure": ("signal-level reconstruction from automation/state/core-decisions.jsonl "
                           "exit_pass ticks (real live IEX-derived best/worst premium the engine "
                           "observed each minute) -- no same-day OPRA cache exists; NOT a "
                           "walk_exit_manager bar replay, disclosed as such"),
            "per_cell": today_results,
        },
        "gates": cell_reports,
        "arming_recommendation": verdict,
        "trades": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"VERDICT: {verdict}")


def _fmt_money(v) -> str:
    return f"${v:+,.2f}"


def write_markdown(out: dict) -> None:
    v = out["arming_recommendation"]
    gates = out["gates"]
    rc = out["runner_cohort"]
    tt = out["today_trade"]

    if v["decision"] == "ARM":
        g = gates[v["cell"]]
        verdict_line = (
            f"**VERDICT: ARM {v['cell']}** ({out['cells'][v['cell']]}) -- clears all "
            f"required gates: aggregate {_fmt_money(g['g1_positive_aggregate']['delta'])}, "
            f"runner cohort {_fmt_money(g['g4_runner_cohort_no_regression']['delta'])}, "
            f"today's trade {_fmt_money(g['g6_today_trade']['delta'])} swing "
            f"({_fmt_money(g['g6_today_trade']['control_pnl'])} -> "
            f"{_fmt_money(g['g6_today_trade']['cell_pnl'])})."
        )
    else:
        verdict_line = f"**VERDICT: ARM NOTHING** -- {v['reason']}."

    L = [
        "# EXIT-ARMSCOPE-TP1 A/B scorecard -- 2026-07-28",
        "",
        verdict_line,
        "",
        f"Pre-reg: `{out['prereg_file']}`. Generated {out['generated_at']}. "
        f"Runtime {out['runtime_seconds']}s.",
        "",
        "## Population",
        "",
        f"- Source (entries UNCHANGED, exit-only test): `{out['population']['source']}`",
        f"- N trades: {out['population']['n_trades_source']} "
        f"(excluded no-OPRA={out['population']['n_excluded_no_opra_cache']}, "
        f"no-SPY-day={out['population']['n_excluded_no_spy_day']})",
        f"- CONTROL reconciliation vs source replay: "
        f"{out['population']['n_control_mismatch_vs_source']} mismatches "
        f"(must be 0 for this scorecard to be trusted)",
        "",
        "## Per-cell G1-G6 verdict table",
        "",
        "| Gate | E1 (arm_scope=full) | E2 (tp1=0.5) | E3 (both) |",
        "|---|---|---|---|",
    ]
    rows_spec = [
        ("G1 positive aggregate", lambda g: f"{_fmt_money(g['g1_positive_aggregate']['delta'])} "
                                              f"{'PASS' if g['g1_positive_aggregate']['pass'] else 'FAIL'}"),
        ("G2 majority changed +", lambda g: f"{g['g2_majority_changed_positive']['n_positive']}/"
                                              f"{g['g2_majority_changed_positive']['n_negative']} "
                                              f"{'PASS' if g['g2_majority_changed_positive']['pass'] else 'FAIL'}"),
        ("G3 survives drop-best1", lambda g: f"{_fmt_money(g['g3_survives_drop_best1']['delta_ex_best1'])} "
                                               f"{'PASS' if g['g3_survives_drop_best1']['pass'] else 'FAIL'}"),
        ("G4 runner cohort (n=35)", lambda g: f"{_fmt_money(g['g4_runner_cohort_no_regression']['delta'])} "
                                                f"{'PASS' if g['g4_runner_cohort_no_regression']['pass'] else 'FAIL'}"),
        ("G5 look-ahead guard", lambda g: f"{'PASS (real)' if g['g5_look_ahead_guard']['exercises_arm_scope_full_pretp1'] else 'PASS (vacuous)'}"),
        ("G6 today's trade", lambda g: (f"{_fmt_money(g['g6_today_trade']['delta'])} "
                                          f"{'PASS' if g['g6_today_trade']['pass'] else 'FAIL'}")
                                          if g['g6_today_trade']['gated']
                                          else f"{_fmt_money(g['g6_today_trade']['delta'])} (not gated)"),
        ("CLEARS ALL REQUIRED", lambda g: "YES" if g["clears_all_required_gates"] else "no"),
    ]
    for label, fn in rows_spec:
        L.append(f"| {label} | {fn(gates['E1'])} | {fn(gates['E2'])} | {fn(gates['E3'])} |")

    L += [
        "",
        "## Runner-cohort effect (G4 detail, the book's profit engine)",
        "",
        f"Anchor check: n={rc['n']} (expected {rc['anchor_check']['expected_n']}, "
        f"match={rc['anchor_check']['n_matches']}); control_pnl_sum={_fmt_money(rc['control_pnl_sum'])} "
        f"(expected {_fmt_money(15774.05)}, match={rc['anchor_check']['pnl_matches']})",
        "",
        "| Cell | Cohort P&L | Delta vs CONTROL | N worse | N better | N unchanged | G4 |",
        "|---|---|---|---|---|---|---|",
    ]
    for cell in ("E1", "E2", "E3"):
        g4 = gates[cell]["g4_runner_cohort_no_regression"]
        L.append(f"| {cell} | {_fmt_money(g4['cell_pnl_sum'])} | {_fmt_money(g4['delta'])} | "
                 f"{g4['n_worse']} | {g4['n_better']} | {g4['n_unchanged']} | "
                 f"{'PASS' if g4['pass'] else 'FAIL'} |")

    L += [
        "",
        "## Today's 2026-07-28 Bold trade under each cell (G6, signal-level)",
        "",
        f"Entry {TODAY_ENTRY_PREMIUM} x{TODAY_QTY} {TODAY_SYMBOL}, level_reclaim @{TODAY_TRIGGER_LEVEL}. "
        f"{tt['disclosure']}. N real ticks used: {tt['n_real_ticks_used']}.",
        "",
        "| Cell | Exit P&L | Exit reason | vs CONTROL |",
        "|---|---|---|---|",
    ]
    for cell in ("CONTROL", "E1", "E2", "E3"):
        r = tt["per_cell"][cell]
        delta = round(r["dollar_pnl"] - tt["per_cell"]["CONTROL"]["dollar_pnl"], 2)
        L.append(f"| {cell} | {_fmt_money(r['dollar_pnl'])} | {r['exit_reason']} | "
                 f"{_fmt_money(delta) if cell != 'CONTROL' else '--'} |")

    L += [
        "",
        "## Changed-trade tables (top 15 by |delta| per cell)",
        "",
    ]
    for cell in ("E1", "E2", "E3"):
        trades = out["trades"]
        deltas = [(i, round(trades[i][cell]["dollar_pnl"] - trades[i]["CONTROL"]["dollar_pnl"], 2))
                 for i in range(len(trades))]
        deltas = [(i, d) for i, d in deltas if abs(d) > 0.005]
        deltas.sort(key=lambda x: abs(x[1]), reverse=True)
        L += [f"### {cell} -- top {min(15, len(deltas))} of {len(deltas)} changed trades", "",
              "| Date | Symbol | Tier | CONTROL | " + cell + " | Delta | Control exit | " + cell + " exit |",
              "|---|---|---|---|---|---|---|---|"]
        for i, d in deltas[:15]:
            t = trades[i]
            L.append(f"| {t['date']} | {t['symbol']} | {t['tier']} | "
                     f"{_fmt_money(t['CONTROL']['dollar_pnl'])} | {_fmt_money(t[cell]['dollar_pnl'])} | "
                     f"{_fmt_money(d)} | {t['CONTROL']['exit_reason']} | {t[cell]['exit_reason']} |")
        L.append("")

    L += [
        "## Arming recommendation",
        "",
        f"- Decision: **{v['decision']}**" + (f" ({v['cell']})" if v.get("cell") else ""),
        f"- Reason: {v['reason']}",
        "",
        "## Honest caveats",
        "",
        "- G6 (today's trade) is reconstructed from real live tick data (core-decisions.jsonl), "
        "NOT an OPRA bar replay -- no same-day cache exists for 2026-07-28. This is disclosed, "
        "signal-level, and uses the exact same em.plan_exit_actions decision core as every "
        "other cell, but ribbon_flip_back is held False throughout (not logged per-tick in the "
        "source) -- immaterial here since the real exit was structure_stop, not a ribbon flip.",
        "- The 190-trade population is Safe-account (core_safe) entries only, per "
        "engine-fullhist-replay-2026-07-23.json's documented scope (RIDE_THE_RIBBON family "
        "only; Bold/aggressive and the extra setups are not in this population). Today's "
        "motivating trade was Bold -- the exit SHAPE (RIBBON_RIDE) is shared across both "
        "accounts, so the mechanism finding transfers, but the 190-trade aggregate numbers "
        "are a Safe-account-only estimate of the effect size.",
        "- G4's 'no regression' bar is cohort-AGGREGATE, not per-trade -- see the N worse/N "
        "better/N unchanged columns above for the per-trade distribution within a passing or "
        "failing cell.",
        "- kill_criteria_post_arm (per the frozen pre-reg): forward 10 sessions or n>=8 fills; "
        "if realized expectancy is worse than the counterfactual control behavior, revert.",
        "",
        "---",
        f"_Source: `backtest/tools/exit_armscope_ab_2026_07_28.py`. Full trade-level JSON: "
        f"`analysis/recommendations/exit-armscope-tp1-ab-2026-07-28.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
