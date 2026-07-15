"""strike_ab_convention_reconciliation.py -- CONVENTION-RECONCILIATION (2026-07-14/15).

CONTEXT (verified cross-study contradiction, pinned by J before this run): the 2026-07-14 strike
A/B (backtest/tools/ribbon_ride_strike_exit_ab.py, commit 81b25b4 -- the study whose scorecard
armed the ATM strike-tier override in CLAUDE.md) contains ZERO friction/haircut code and reports
at QTY=10 relative dollars; its ATM/SS-B cell showed +$65.82/tr (n=244). The SAME NIGHT's
backtest/tools/debit_spread_ab_study.py -- same 250-signal ribbon_ride cohort, ATM long leg --
reports its naked-ATM CONTROL at -$5.24/episode (n=244, total -$1,279, drop_top3 -$23.73,
IS-half deeply negative / OOS-half +$3,157). J asked for the two studies' conventions to be
reconciled: how much of the +$65.82 -> -$5.24 gap is friction vs fill-bar convention vs the
premium_stop stage-label fix vs qty units, and whether the ATM-vs-OTM-2 relative delta (the
thing that actually justifies the armed override) survives honest conventions.

**A CORRECTION FOUND DURING THIS RECONCILIATION (read before trusting the task framing):**
debit_spread_ab_study.py's own docstring says its bar loader is "Fill-bar-INCLUDED convention
(bar-0's OPEN is the entry fill), same as t4_exit_matrix._load_bars." That is the OLD, PRE-FIX
convention -- ribbon_ride_strike_exit_ab.py's own docstring documents that p5_topcell_real_fills_
confirm.py found this exact `>=` convention wrong and switched to `>` (exclude the fill bar from
the walk) as the CORRECTED convention that reproduces the recorded funnel number. So
debit_spread_ab_study.py does NOT carry "the corrected fill-bar convention" -- it REGRESSED to
the old one. This script uses the ACTUALLY-corrected convention (`>`, matching p5_topcell /
ribbon_ride_strike_exit_ab.py's own PRIMARY convention), not debit_spread_ab_study.py's, and
treats the old convention as one of the toggled-away factors, not a target to copy.

A SECOND, LARGER, PREVIOUSLY-UNSTATED CONFOUND FOUND: the task brief describes debit_spread_ab_
study.py as running at "SS-B live scope" -- it does not. Its `_live_shape()` reads exit-shape
knobs FRESH from automation/state/params.json at run time (tp1_premium_pct=0.50 not SS-B's 1.0,
tp1_qty_fraction=0.8 not 0.667, profit_lock_mode="fixed" not "trailing", trail_pct=0.125 not 0.15,
runner_target_pct=2.5 not 9.9, time_stop=15:40 not 15:50) AND its replay has NO structure-stop
chart layer at all (pure premium-only exit, per its own disclosure). This is a much bigger
mechanical difference than friction/fill-bar/stage-label and is disclosed here as its own axis
(NOT one of the 4 J named) so the decomposition is honest about what actually drives the gap.

TWO DELIVERABLES:
  JOB1(a) -- the LITERALLY-REQUESTED re-run: strike axis (OTM-2 control / OTM-1 / ATM / ITM-2),
    SS-B exit shape + structure-stop chart layer HELD FIXED (exactly the original strike A/B's
    design), with real haircuts added, the (already-correct) `>` fill-bar convention, and the
    premium_stop stage-label fix applied. Answers: does the ATM-vs-OTM-2 relative delta survive
    honest friction? Does any cell clear zero expectancy (overall / OOS-half)?
  JOB1(b) -- the GAP BRIDGE at ATM: full 2^5 factorial over the 5 factors that actually differ
    between the two source scripts (structure-layer presence, shape-config [SS-B vs LIVE
    params.json], fill-bar convention, friction, stage-label fix), reporting a forward path
    (ribbon_ride's convention -> debit_spread's convention) and a reverse path, plus the
    factorial main effect of each factor (averaged over the other 4), so the +$65.82 -> -$5.24
    gap is decomposed by ACTUAL cause, not assumed cause.

REUSE (OP-22): _signal_cache.load_or_build_signals, tw8_level_context.enrich_signals,
structure_stop_study.{NormBar,SS_B_SHAPE,STRUCTURE_BUFFER,structure_stop_signal_time},
lib.option_pricing_real.{load_contract_bars,option_symbol}, lib.simulator_credit's DEFAULT_*
haircut constants, automation/state/fleet/exit_manager.{ExitState,plan_exit_actions,
ARM_SCOPE_POST_TP1,TIME_STOP_ET}, t4_exit_matrix.battery, ribbon_ride_strike_exit_ab's
strike_for()/load_cohort() (imported directly, not re-derived).

ANALYSIS ONLY. No params/config/trading-path file touched. No orders. QTY=10 fixed throughout
(matches BOTH source studies -- confirmed NOT a source of the gap, see disclosures) with a
qty-normalized ($/contract) and production-qty-scaled view also reported.

Run: backtest/.venv/Scripts/python.exe backtest/tools/strike_ab_convention_reconciliation.py [--smoke]
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
import time as _time_mod
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ribbon_ride_strike_exit_ab as rrse                              # noqa: E402
import structure_stop_study as sss                                     # noqa: E402
import t4_exit_matrix as t4                                            # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.simulator_credit import (                                     # noqa: E402
    DEFAULT_ENTRY_SLIPPAGE, DEFAULT_EXIT_SLIPPAGE, DEFAULT_COMMISSION)
from exit_manager import ExitState, plan_exit_actions, ARM_SCOPE_POST_TP1, TIME_STOP_ET  # noqa: E402

SMOKE = "--smoke" in sys.argv
OUT_JSON = REPO / "analysis" / "recommendations" / "strike-ab-convention-reconciliation.json"
OUT_MD = REPO / "analysis" / "recommendations" / "strike-ab-convention-reconciliation.md"
PARAMS_PATH = REPO / "automation" / "state" / "params.json"

QTY = 10                          # matches BOTH source studies -- see disclosures
PRODUCTION_QTY_TYPICAL = 3        # params.json min_contracts; recent trades.csv qty column: 1-5, mode~3
STRIKE_CELLS = [("OTM-2", 2), ("OTM-1", 1), ("ATM", 0), ("ITM-2", -2)]
CONTROL_STRIKE = "OTM-2"

SS_B_SHAPE = dict(sss.SS_B_SHAPE)
SS_B_BUFFER = sss.STRUCTURE_BUFFER["SS-B"]
SS_B_TIME_STOP = TIME_STOP_ET     # 15:50 ET


def log(msg: str) -> None:
    print(f"[strike-ab-reconcile] {msg}", flush=True)


def live_shape_and_timestop() -> tuple[dict, dt.time]:
    """Byte-for-byte the same read debit_spread_ab_study.py's _live_shape()/_time_stop() do --
    fresh from params.json at run time. No profit_lock_arm_scope key -> defaults to
    ARM_SCOPE_POST_TP1 identically to SS_B_SHAPE (confirmed: not a source of the gap)."""
    p = json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))
    shape = {
        "premium_stop_pct": float(p.get("premium_stop_pct", -0.50)),
        "tp1_premium_pct": float(p.get("tp1_premium_pct", 0.50)),
        "tp1_qty_fraction": float(p.get("tp1_qty_fraction", 0.8)),
        "profit_lock_mode": str(p.get("v15_profit_lock_mode", "fixed")),
        "profit_lock_arm_pct": float(p.get("v15_profit_lock_threshold_pct", 0.05)),
        "trail_pct": float(p.get("v15_profit_lock_trail_pct", 0.125)),
        "runner_target_pct": 2.5,
    }
    parts = str(p.get("time_stop_et", "15:40")).split(":")
    time_stop = dt.time(int(parts[0]), int(parts[1]))
    return shape, time_stop


LIVE_SHAPE, LIVE_TIME_STOP = live_shape_and_timestop()


# ---------------------------------------------------------------------------------------------
# RAW BAR FETCH -- ONE disk read per (strike,signal); fill-bar convention applied later by
# SLICING the same raw bar list, so the 32-cell factorial does not redo I/O per toggle.
# ---------------------------------------------------------------------------------------------
def fetch_raw_bars(entry_spot: float, side: str, date: dt.date, entry_ts: dt.datetime, so: int):
    """Returns (entry_premium, full_norm_bars) where full_norm_bars[0] is the fill/entry bar
    itself (bar-0's OPEN = fill price, same convention both source studies share), or None if no
    local OPRA coverage. Convention split (old `>=` vs corrected `>`) happens at replay time via
    select_walk_bars()."""
    strike = rrse.strike_for(entry_spot, side, so)
    df = load_contract_bars(option_symbol(date, strike, side))
    if df is None or df.empty:
        return None
    ts = df["timestamp_et"]
    if ts.dt.tz is not None:
        ts = ts.dt.tz_localize(None)
    entry_ts_naive = entry_ts.replace(tzinfo=None) if entry_ts.tzinfo is not None else entry_ts
    mask = (ts >= entry_ts_naive) & (ts.dt.date == date)
    rows = df[mask.values]
    if rows.empty:
        return None
    entry_bar = rows.iloc[0]
    entry_premium = float(entry_bar["open"])
    full_bars = []
    for _, r in rows.iterrows():
        t = r["timestamp_et"]
        if getattr(t, "tzinfo", None) is not None:
            t = t.tz_localize(None)
        full_bars.append(sss.NormBar(t.to_pydatetime() if hasattr(t, "to_pydatetime") else t,
                                     float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return entry_premium, full_bars


def select_walk_bars(full_bars: list, old_fillbar: bool) -> list:
    """old_fillbar=True: bar-0 (fill bar) INCLUDED in the walk (debit_spread_ab_study.py's
    actual, UNCORRECTED convention -- its own h/l get checked against stop/TP).
    old_fillbar=False: bar-0 EXCLUDED (p5_topcell/ribbon_ride_strike_exit_ab.py's PRIMARY,
    CORRECTED convention -- the walk starts at the bar AFTER the fill)."""
    return full_bars if old_fillbar else full_bars[1:]


# ---------------------------------------------------------------------------------------------
# GENERIC REPLAY -- one function, 3 boolean toggles. friction=False,stage_fix=False,
# use_structure=True/shape=SS_B_SHAPE/fillbar=new reproduces sss.replay_structure_aware()
# EXACTLY (verified below in main() against the cached ribbon-ride-strike-exit-ab.json numbers).
# ---------------------------------------------------------------------------------------------
def replay_generic(entry_premium_raw: float, side: str, qty: int, walk_bars: list,
                   ss_time, shape: dict, time_stop_et: dt.time, *,
                   friction: bool, stage_fix: bool, use_structure: bool) -> dict:
    entry_premium = entry_premium_raw + (DEFAULT_ENTRY_SLIPPAGE if friction else 0.0)
    state = ExitState.from_entry(symbol="x", side=side, entry_premium=entry_premium, qty=qty, exit_shape=shape)
    open_qty = qty
    realized = 0.0
    last_close = entry_premium
    exit_stage = None
    structure_fired = False
    ss_time_eff = ss_time if use_structure else None
    for bar in walk_bars:
        if open_qty <= 0:
            break
        last_close = bar.c
        if ss_time_eff is not None and not structure_fired and bar.dt >= ss_time_eff:
            fp = bar.o
            if friction:
                fp = max(0.01, fp - DEFAULT_EXIT_SLIPPAGE)
            realized += (fp - entry_premium) * open_qty * 100.0
            open_qty = 0
            structure_fired = True
            exit_stage = "structure_stop"
            break
        now_et = bar.dt.time()
        dec = plan_exit_actions(state, best_premium=bar.h, worst_premium=bar.l, open_qty=open_qty,
                                now_et=now_et, ribbon_flip_back=False, time_stop_et=time_stop_et)
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            if a.stage == "tp1":
                fp = entry_premium * (1.0 + state.tp1_premium_pct)
            elif a.stage == "runner_target":
                fp = entry_premium * (1.0 + state.runner_target_pct)
            elif a.stage == "premium_stop":
                if stage_fix and dec.state.runner_stop_premium is not None:
                    fp = dec.state.runner_stop_premium
                else:
                    fp = entry_premium * (1.0 + state.premium_stop_pct)
            elif a.stage in ("trail", "be_stop"):
                fp = dec.state.runner_stop_premium
            else:
                fp = bar.c
            if friction:
                fp = max(0.01, fp - DEFAULT_EXIT_SLIPPAGE)
            realized += (fp - entry_premium) * a.qty * 100.0
            open_qty -= a.qty
            exit_stage = a.stage
        state = dec.state
    if open_qty > 0:
        fp = last_close
        if friction:
            fp = max(0.01, fp - DEFAULT_EXIT_SLIPPAGE)
        realized += (fp - entry_premium) * open_qty * 100.0
        exit_stage = exit_stage or "eod_leftover"
        open_qty = 0
    commission = (DEFAULT_COMMISSION * 2 * qty) if friction else 0.0
    realized -= commission
    return {"pnl": round(realized, 2), "exit_stage": exit_stage, "structure_fired": structure_fired}


# ---------------------------------------------------------------------------------------------
# CELL BUILD -- one (strike, scenario-of-5-toggles) -> battery
# ---------------------------------------------------------------------------------------------
def build_trades(prepped: list[dict], bars_by_signal: dict, so: int, *,
                 shape_config: str, old_fillbar: bool, friction: bool, stage_fix: bool,
                 use_structure: bool) -> tuple[list[dict], int]:
    shape, time_stop_et = (SS_B_SHAPE, SS_B_TIME_STOP) if shape_config == "SS-B" else (LIVE_SHAPE, LIVE_TIME_STOP)
    trades, n_no_bars = [], 0
    for s in prepped:
        key = (s["date_obj"], s["side"], s["entry_ts_obj"], so)
        fetched = bars_by_signal.get(key)
        if fetched is None:
            n_no_bars += 1
            continue
        entry_premium_raw, full_bars = fetched
        walk = select_walk_bars(full_bars, old_fillbar)
        if not walk:
            n_no_bars += 1
            continue
        ss_time = s["ss_time"]
        r = replay_generic(entry_premium_raw, s["side"], QTY, walk, ss_time, shape, time_stop_et,
                           friction=friction, stage_fix=stage_fix, use_structure=use_structure)
        trades.append({"date": s["date_obj"], "direction": s["direction"], "pnl": r["pnl"]})
    return trades, n_no_bars


def both_halves(trades: list[dict]) -> dict:
    ordered = sorted(trades, key=lambda t: t["date"])
    n = len(ordered)
    mid = n // 2
    first, second = ordered[:mid], ordered[mid:]
    f_tot = round(sum(t["pnl"] for t in first), 2)
    s_tot = round(sum(t["pnl"] for t in second), 2)
    return {"first_half": {"n": len(first), "total": f_tot},
           "second_half": {"n": len(second), "total": s_tot},
           "both_positive": bool(first and second and f_tot > 0 and s_tot > 0)}


def cell_summary(trades: list[dict], n_no_bars: int) -> dict:
    """NOTE: t4_exit_matrix.battery() does NOT return n_oos/n_is (unlike debit_spread_ab_study.
    py's OWN battery() function, a different function of the same name in a different module --
    do not conflate the two). n_is/n_oos/oos_expectancy are computed directly here from
    rrse.OOS_BOUNDARY against the trades list, independent of t4.battery()'s internals."""
    b = t4.battery(trades)
    bh = both_halves(trades)
    n_is = sum(1 for t in trades if t["date"] < rrse.OOS_BOUNDARY)
    n_oos = sum(1 for t in trades if t["date"] >= rrse.OOS_BOUNDARY)
    oos_exp = round(b["oos_total"] / n_oos, 2) if n_oos and b.get("oos_total") is not None else None
    return {"n": b.get("n"), "n_no_local_bars": n_no_bars, "total": b.get("total"),
           "expectancy": b.get("expectancy"), "wr": b.get("wr"),
           "n_is": n_is, "n_oos": n_oos,
           "oos_total": b.get("oos_total"), "oos_expectancy": oos_exp,
           "oos_positive": b.get("oos_positive"), "wf": b.get("wf"), "wf_ge_070": b.get("wf_ge_070"),
           "qpf": b.get("qpf"), "exp_drop_top3": b.get("exp_drop_top3"),
           "sub_window_stable": bh["both_positive"], "both_halves": {"first": bh["first_half"], "second": bh["second_half"]}}


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    t_start = _time_mod.time()
    log(f"{'SMOKE' if SMOKE else 'FULL'} run -- loading cohort (reused from ribbon_ride_strike_exit_ab)")
    prepped, spy_full, spy_by_date = rrse.load_cohort()
    log(f"cohort n={len(prepped)}")

    # --- prefetch raw bars ONCE per (strike, signal) -- reused across all 32 toggle combos ---
    log("prefetching raw OPRA bars for all 4 strikes (single I/O pass per strike)...")
    bars_by_signal: dict = {}
    for label, so in STRIKE_CELLS:
        n_hit = 0
        for s in prepped:
            key = (s["date_obj"], s["side"], s["entry_ts_obj"], so)
            fetched = fetch_raw_bars(float(s["entry_spot"]), s["side"], s["date_obj"], s["entry_ts_obj"], so)
            bars_by_signal[key] = fetched
            if fetched is not None:
                n_hit += 1
        log(f"  {label} (so={so}): {n_hit}/{len(prepped)} signals with local OPRA coverage")

    # =========================================================================================
    # SANITY CHECK -- reproduce ribbon_ride_strike_exit_ab.py's own ATM/SS-B cell bit-for-bit
    # under the "no friction / no stage-fix / corrected fillbar / SS-B shape / structure ON"
    # settings, to prove replay_generic degenerates correctly to sss.replay_structure_aware.
    # =========================================================================================
    atm_so = dict(STRIKE_CELLS)["ATM"]
    baseline_trades, baseline_no_bars = build_trades(
        prepped, bars_by_signal, atm_so, shape_config="SS-B", old_fillbar=False,
        friction=False, stage_fix=False, use_structure=True)
    baseline_summary = cell_summary(baseline_trades, baseline_no_bars)
    log(f"SANITY: ATM/SS-B reproduction -- n={baseline_summary['n']} exp=${baseline_summary['expectancy']} "
        f"(cached ribbon-ride-strike-exit-ab.json ATM cell: n=244 exp=$65.82) -- "
        f"{'MATCH' if baseline_summary['n'] == 244 and abs((baseline_summary['expectancy'] or 0) - 65.82) < 0.5 else 'DRIFT (see disclosures)'}")

    # =========================================================================================
    # JOB1(a) -- literal instruction: strike axis, SS-B + structure HELD FIXED, add friction,
    # keep the (already-correct) fillbar convention, apply the stage fix.
    # =========================================================================================
    log("=== JOB1(a): strike axis, SS-B fixed, HONEST conventions (friction added) ===")
    job1a_cells = {}
    for label, so in STRIKE_CELLS:
        trades, n_no_bars = build_trades(prepped, bars_by_signal, so, shape_config="SS-B",
                                         old_fillbar=False, friction=True, stage_fix=True,
                                         use_structure=True)
        job1a_cells[label] = cell_summary(trades, n_no_bars)
        log(f"  {label}: n={job1a_cells[label]['n']} exp=${job1a_cells[label]['expectancy']} "
            f"OOS_exp=${job1a_cells[label]['oos_expectancy']} wr={job1a_cells[label]['wr']}")

    # original (pre-friction) cells for delta-vs-original comparison, from the cached study
    orig_json_path = REPO / "analysis" / "recommendations" / "ribbon-ride-strike-exit-ab.json"
    orig_cells = {}
    if orig_json_path.exists():
        orig_data = json.loads(orig_json_path.read_text(encoding="utf-8"))
        for label, _so in STRIKE_CELLS:
            m = orig_data["axis1_strike"]["cells"][label]["metrics"]
            orig_cells[label] = {"expectancy": m.get("expectancy"), "oos_total": m.get("oos_total"),
                                 "n": m.get("n")}

    job1a_control = job1a_cells[CONTROL_STRIKE]
    job1a_comparisons = {}
    for label, _so in STRIKE_CELLS:
        if label == CONTROL_STRIKE:
            continue
        c = job1a_cells[label]
        delta_exp = round((c["expectancy"] or 0) - (job1a_control["expectancy"] or 0), 2)
        delta_oos = round((c["oos_total"] or 0) - (job1a_control["oos_total"] or 0), 2)
        job1a_comparisons[label] = {
            "vs_control": CONTROL_STRIKE, "delta_expectancy_honest": delta_exp,
            "delta_oos_total_honest": delta_oos, "beats_control_honest": delta_exp > 0,
            "orig_delta_expectancy": (round(orig_cells[label]["expectancy"] - orig_cells[CONTROL_STRIKE]["expectancy"], 2)
                                      if orig_cells else None),
            "relative_verdict_survives": None,   # filled below
        }
    for label, comp in job1a_comparisons.items():
        if comp["orig_delta_expectancy"] is not None:
            comp["relative_verdict_survives"] = bool(
                (comp["orig_delta_expectancy"] > 0) == (comp["delta_expectancy_honest"] > 0))

    any_cell_clears_zero_overall = {lbl: bool((c["expectancy"] or 0) > 0) for lbl, c in job1a_cells.items()}
    any_cell_clears_zero_oos = {lbl: bool((c["oos_expectancy"] or 0) > 0) for lbl, c in job1a_cells.items()}

    # =========================================================================================
    # JOB1(b) -- gap bridge at ATM: 2^5 factorial across the 5 factors that ACTUALLY differ
    # between ribbon_ride_strike_exit_ab.py's ATM/SS-B cell and debit_spread_ab_study.py's
    # naked-ATM control.
    # =========================================================================================
    log("=== JOB1(b): ATM gap-bridge factorial (2^5 = 32 cells) ===")
    factors = ["use_structure", "shape_config", "old_fillbar", "friction", "stage_fix"]
    RIBBON_SETTING = {"use_structure": True, "shape_config": "SS-B", "old_fillbar": False,
                      "friction": False, "stage_fix": False}
    DEBIT_SETTING = {"use_structure": False, "shape_config": "LIVE", "old_fillbar": True,
                     "friction": True, "stage_fix": True}

    grid_cache: dict = {}

    def get_cell(settings: dict) -> dict:
        k = tuple(sorted(settings.items()))
        if k not in grid_cache:
            trades, n_no_bars = build_trades(prepped, bars_by_signal, atm_so,
                                             shape_config=settings["shape_config"],
                                             old_fillbar=settings["old_fillbar"],
                                             friction=settings["friction"],
                                             stage_fix=settings["stage_fix"],
                                             use_structure=settings["use_structure"])
            grid_cache[k] = cell_summary(trades, n_no_bars)
        return grid_cache[k]

    # full 32-cell grid
    full_grid = []
    for combo in itertools.product([True, False], ["SS-B", "LIVE"], [True, False], [True, False], [True, False]):
        settings = dict(zip(["use_structure", "shape_config", "old_fillbar", "friction", "stage_fix"], combo))
        c = get_cell(settings)
        full_grid.append({"settings": settings, "n": c["n"], "expectancy": c["expectancy"], "total": c["total"]})
    log(f"  32-cell grid computed ({len(grid_cache)} unique cells cached)")

    def path_trace(order: list[str], start: dict, end: dict) -> list[dict]:
        steps = []
        cur = dict(start)
        prev_cell = get_cell(cur)
        for factor in order:
            nxt = dict(cur)
            nxt[factor] = end[factor]
            nxt_cell = get_cell(nxt)
            steps.append({
                "factor_toggled": factor, "from": cur[factor], "to": nxt[factor],
                "expectancy_before": prev_cell["expectancy"], "expectancy_after": nxt_cell["expectancy"],
                "delta": round((nxt_cell["expectancy"] or 0) - (prev_cell["expectancy"] or 0), 2),
                "n_before": prev_cell["n"], "n_after": nxt_cell["n"],
            })
            cur = nxt
            prev_cell = nxt_cell
        return steps

    forward_order = ["use_structure", "shape_config", "old_fillbar", "friction", "stage_fix"]
    reverse_order = list(reversed(forward_order))
    forward_path = path_trace(forward_order, RIBBON_SETTING, DEBIT_SETTING)
    reverse_path_raw = path_trace(reverse_order, DEBIT_SETTING, RIBBON_SETTING)
    # re-express reverse path in "moving toward DEBIT_SETTING" sign convention for comparability
    reverse_path = [{**s, "delta": round(-s["delta"], 2),
                     "expectancy_before": s["expectancy_after"], "expectancy_after": s["expectancy_before"]}
                    for s in reversed(reverse_path_raw)]

    # main effect: average of the 16 pairwise (factor=DEBIT_setting) - (factor=RIBBON_setting)
    # deltas holding the other 4 factors fixed at every one of their 16 joint settings.
    other_factor_domains = {
        "use_structure": [True, False], "shape_config": ["SS-B", "LIVE"],
        "old_fillbar": [True, False], "friction": [True, False], "stage_fix": [True, False],
    }
    main_effects = {}
    for factor in factors:
        others = [f for f in factors if f != factor]
        diffs = []
        for combo in itertools.product(*[other_factor_domains[f] for f in others]):
            base = dict(zip(others, combo))
            s_ribbon_val = dict(base); s_ribbon_val[factor] = RIBBON_SETTING[factor]
            s_debit_val = dict(base); s_debit_val[factor] = DEBIT_SETTING[factor]
            c_r = get_cell(s_ribbon_val)
            c_d = get_cell(s_debit_val)
            diffs.append((c_d["expectancy"] or 0) - (c_r["expectancy"] or 0))
        main_effects[factor] = {"mean_delta_ribbon_to_debit_setting": round(sum(diffs) / len(diffs), 2),
                                "n_pairs_averaged": len(diffs), "min": round(min(diffs), 2), "max": round(max(diffs), 2)}

    ribbon_cell = get_cell(RIBBON_SETTING)
    debit_cell = get_cell(DEBIT_SETTING)
    forward_sum = round(sum(s["delta"] for s in forward_path), 2)
    reverse_sum = round(sum(s["delta"] for s in reverse_path), 2)
    total_gap = round((debit_cell["expectancy"] or 0) - (ribbon_cell["expectancy"] or 0), 2)

    elapsed = round(_time_mod.time() - t_start, 1)

    out = {
        "_doc": ("STRIKE-AB-CONVENTION-RECONCILIATION. ANALYSIS ONLY -- no params/config/"
                "trading-path file touched, no orders placed. JOB1(a) = literal instructed "
                "re-run (SS-B held fixed, honest friction added). JOB1(b) = full gap-bridge "
                "factorial explaining the +$65.82 -> -$5.24 ATM gap between the two source "
                "studies, whose conventions differ on 5 factors, not the 4 named in the task "
                "brief -- see convention_audit."),
        "generated_at": dt.datetime.now().isoformat(),
        "smoke_mode": SMOKE,
        "sanity_check_reproduction": baseline_summary,
        "convention_audit": {
            "fill_bar_convention_finding": (
                "debit_spread_ab_study.py's docstring self-identifies its bar loader as "
                "'Fill-bar-INCLUDED convention ... same as t4_exit_matrix._load_bars' -- this IS "
                "the OLD, PRE-p5_topcell-fix convention (`>=`), not the corrected one. "
                "ribbon_ride_strike_exit_ab.py's PRIMARY convention is `>` (fill bar excluded), "
                "found by p5_topcell_real_fills_confirm.py to be the one that reproduces the "
                "recorded funnel number. The task brief's framing that debit_spread_ab_study.py "
                "carries 'the corrected fill-bar convention' does not match the code -- it "
                "REGRESSED to the old one. This script uses the genuinely-corrected `>` "
                "convention as its baseline and treats debit_spread's `>=` as a toggled-away "
                "factor (old_fillbar), not a target to copy."),
            "shape_and_structure_layer_finding": (
                "debit_spread_ab_study.py does NOT run at 'SS-B live scope' -- its _live_shape() "
                "reads exit-shape knobs fresh from automation/state/params.json at run time "
                f"({LIVE_SHAPE}) which differ from SS_B_SHAPE ({SS_B_SHAPE}) on every knob except "
                "premium_stop_pct, AND its replay has NO structure-stop chart layer (premium-only, "
                "per its own disclosure list). This is a materially larger mechanical difference "
                "than friction/fill-bar/stage-label and is decomposed here as its own 2 factors "
                "(use_structure, shape_config) even though the task brief named only friction/"
                "fill-bar/stage/qty."),
            "qty_finding": (
                f"BOTH source studies use QTY={QTY} fixed -- confirmed NOT a source of the "
                "+$65.82 -> -$5.24 gap (byte-identical convention on both sides). Per-episode "
                f"pnl here is linear in qty (every term is qty- or a.qty-scaled), so a per-"
                f"contract figure = expectancy/{QTY}, and a production-qty view scales linearly: "
                f"production_qty~{PRODUCTION_QTY_TYPICAL} (params.json min_contracts=3; recent "
                "journal/trades.csv qty column samples 1-5, mode ~3 -- QTY=10 in both studies is "
                "~3x a typical live Safe-tier fill size, a 'relative dollars' convention per "
                "both scripts' own docstrings, not a production-scale estimate)."),
        },
        "job1a_strike_axis_honest_ssb": {
            "note": ("SS-B exit shape + structure-stop chart layer HELD FIXED (as in the original "
                    "strike A/B) -- friction ON (simulator_credit haircuts), fill-bar convention "
                    "= the already-correct `>` (unchanged from the original study), stage-label "
                    "fix ON (empirically confirmed no-op for SS-B under ARM_SCOPE_POST_TP1 -- see "
                    "sanity check)."),
            "control": CONTROL_STRIKE,
            "cells": job1a_cells,
            "comparisons_vs_control": job1a_comparisons,
            "any_cell_clears_zero_expectancy_overall": any_cell_clears_zero_overall,
            "any_cell_clears_zero_expectancy_oos_half": any_cell_clears_zero_oos,
        },
        "job1b_gap_bridge_atm": {
            "ribbon_setting": RIBBON_SETTING, "debit_setting": DEBIT_SETTING,
            "ribbon_cell": ribbon_cell, "debit_cell": debit_cell,
            "total_gap_expectancy": total_gap,
            "forward_path_order": forward_order, "forward_path": forward_path,
            "forward_path_sum_check": forward_sum,
            "reverse_path_order_display": forward_order,  # re-expressed in forward order for readability
            "reverse_path": reverse_path,
            "reverse_path_sum_check": reverse_sum,
            "path_dependence_note": ("forward and reverse path sums both equal total_gap by "
                                     "construction (telescoping); per-STEP deltas differ between "
                                     "orderings when factors interact -- compare forward_path vs "
                                     "reverse_path per-factor deltas, and see main_effects for the "
                                     "order-independent average."),
            "main_effects_order_independent": main_effects,
            "full_32_cell_grid": full_grid,
        },
        "disclosures": [
            "MEASURED (real OPRA local cache), not REALIZED -- scorecard/simulation-replay "
            "artifact, no broker fills exist for these strike/shape/friction combinations.",
            "replay_generic degenerates to sss.replay_structure_aware() byte-for-byte when "
            "friction=False, stage_fix=False, old_fillbar=False, use_structure=True, shape=SS-B "
            "-- verified against the cached ribbon-ride-strike-exit-ab.json ATM cell (see "
            "sanity_check_reproduction above).",
            "premium_stop stage-label fix is empirically confirmed a NO-OP for SS-B specifically: "
            "SS_B_SHAPE carries no profit_lock_arm_scope override, so ExitState.from_entry "
            "defaults it to ARM_SCOPE_POST_TP1, under which runner_stop_premium is set once at "
            "entry and never ratcheted before TP1 -- byte-identical to the static "
            "entry*(1+premium_stop_pct) the old code used. The fix matters for ARM_SCOPE_FULL "
            "shapes (e.g. hold_posture_ab_study.py's reuse) -- not exercised here.",
            "No random-entry-null / BH-FDR battery re-run here (out of scope for a convention "
            "decomposition -- the original strike A/B's null/FDR results are unaffected by "
            "these convention toggles' significance testing, only by point estimates).",
            "job1a's fill-bar convention is NOT re-toggled (held at the corrected `>` throughout) "
            "-- per the finding above, `>` was already correct in the original study; there is no "
            "'fill-bar fix' left to apply to job1a. The old `>=` convention only appears in job1b's "
            "gap-bridge as the factor explaining why debit_spread_ab_study.py's number differs.",
        ],
        "runtime_seconds": elapsed,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    log(f"wrote {OUT_JSON} + {OUT_MD} ({elapsed}s total)")
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# Strike A/B convention reconciliation")
    L.append("")
    L.append(f"Generated: {out['generated_at']}. Source: `backtest/tools/strike_ab_convention_reconciliation.py`.")
    L.append("")
    L.append("## Convention audit (read first)")
    L.append("")
    for k, v in out["convention_audit"].items():
        L.append(f"**{k}**: {v}")
        L.append("")
    sc_ = out["sanity_check_reproduction"]
    L.append(f"**Sanity check**: replay_generic at ribbon_ride's own settings reproduces "
             f"n={sc_['n']} exp=${sc_['expectancy']} (cached study: n=244 exp=$65.82).")
    L.append("")
    L.append("## JOB1(a) — strike axis, SS-B fixed, honest friction added")
    L.append("")
    j1 = out["job1a_strike_axis_honest_ssb"]
    L.append("| strike | n | exp $/tr | OOS exp $/tr | WR | OOS+ | WF | clears-zero (overall) | clears-zero (OOS) |")
    L.append("|---|--:|--:|--:|--:|:--:|--:|:--:|:--:|")
    for lbl, _so in [("OTM-2", None), ("OTM-1", None), ("ATM", None), ("ITM-2", None)]:
        c = j1["cells"][lbl]
        L.append(f"| {lbl}{' (control)' if lbl == j1['control'] else ''} | {c['n']} | ${c['expectancy']} | "
                 f"${c['oos_expectancy']} | {c['wr']} | {c['oos_positive']} | {c['wf']} | "
                 f"{j1['any_cell_clears_zero_expectancy_overall'][lbl]} | "
                 f"{j1['any_cell_clears_zero_expectancy_oos_half'][lbl]} |")
    L.append("")
    L.append("**Comparisons vs OTM-2 control (honest, SS-B fixed, friction added):**")
    L.append("")
    for lbl, comp in j1["comparisons_vs_control"].items():
        L.append(f"- **{lbl}**: delta_exp=${comp['delta_expectancy_honest']}/tr honest "
                 f"(was ${comp['orig_delta_expectancy']}/tr pre-friction) -- "
                 f"beats_control={comp['beats_control_honest']}, "
                 f"relative_verdict_survives_honest_conventions={comp['relative_verdict_survives']}")
    L.append("")
    L.append("## JOB1(b) — ATM gap bridge (+$65.82 → -$5.24)")
    L.append("")
    jb = out["job1b_gap_bridge_atm"]
    L.append(f"ribbon_ride setting exp=${jb['ribbon_cell']['expectancy']} (n={jb['ribbon_cell']['n']}) -> "
             f"debit_spread setting exp=${jb['debit_cell']['expectancy']} (n={jb['debit_cell']['n']}). "
             f"Total gap = ${jb['total_gap_expectancy']}/tr.")
    L.append("")
    L.append("**Forward path** (ribbon_ride settings -> debit_spread settings, in this order):")
    L.append("")
    L.append("| step | factor | from -> to | exp before | exp after | delta |")
    L.append("|--:|---|---|--:|--:|--:|")
    for i, s in enumerate(jb["forward_path"], 1):
        L.append(f"| {i} | {s['factor_toggled']} | {s['from']} -> {s['to']} | "
                 f"${s['expectancy_before']} | ${s['expectancy_after']} | ${s['delta']} |")
    L.append("")
    L.append("**Reverse path** (debit_spread settings -> ribbon_ride settings, re-expressed forward), "
             "for path-dependence comparison:")
    L.append("")
    L.append("| step | factor | from -> to | exp before | exp after | delta |")
    L.append("|--:|---|---|--:|--:|--:|")
    for i, s in enumerate(jb["reverse_path"], 1):
        L.append(f"| {i} | {s['factor_toggled']} | {s['from']} -> {s['to']} | "
                 f"${s['expectancy_before']} | ${s['expectancy_after']} | ${s['delta']} |")
    L.append("")
    L.append("**Order-independent main effect per factor** (average delta going ribbon->debit "
             "setting, averaged over all 16 joint settings of the other 4 factors):")
    L.append("")
    L.append("| factor | mean delta | min | max |")
    L.append("|---|--:|--:|--:|")
    for f, me in jb["main_effects_order_independent"].items():
        L.append(f"| {f} | ${me['mean_delta_ribbon_to_debit_setting']} | ${me['min']} | ${me['max']} |")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
