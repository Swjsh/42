"""ribbon_ride_strike_exit_ab.py -- PROFIT-P2-RIBBON-RIDE-STRIKE-AB, EXTENDED with a
same-run exit head-to-head (2026-07-11).

CONTEXT. Three evidence lines converge on "nearer strikes" for core ribbon_ride: (1) the
friction stream measured OTM-2 at ~2x ATM total friction (analysis/deep-research/
2026-07-11-friction-budget.md); (2) WP5-STRIKE-AB proved the OTM->ITM P&L gradient on real
fills for vwap_continuation and 4 other siblings, shipped -- core ribbon_ride never got it
(analysis/recommendations/WP5-STRIKE-AB-SCORECARD.md); (3) the P5 top-cell confirm found
OTM-1/stop-8%/trailing15% at LIVE (post_tp1) exp=+$25.62/tr (n=381) -- but that number rides
a just-discovered fill-bar methodology fix with two OPEN audit chips (task_4935ea80,
task_86001855), and its exit SHAPE (premium -8% stop family) competes with SS-B (structure-
stop-primary), which shipped days ago on core/fleet and has zero forward fills. Arming
either shape blind would be doctrine whiplash -- this script runs the decisive scorecard:
ONE process, TWO axes, on the SAME signal cohort, at LIVE exit_manager scope.

  AXIS 1 (strike): OTM-2 (control, current Safe tier) vs OTM-1 vs ATM vs ITM-2 -- SAME
    signals, exit shape held FIXED at SS-B (structure-stop primary + -50% catastrophe cap +
    TP1+trailing runner -- exact live params, reused unchanged from structure_stop_study.py).
  AXIS 2 (exit, at the strike winner + at the OTM-2 control): SS-B vs the P5 top-cell shape
    (OTM-1_stop-8_trailing0.15: stop-8%/tp+30%/sell50%/trailing0.15/ts10, reused verbatim from
    p5_topcell_real_fills_confirm.py's own LAYER-A shape_live dict) head-to-head on IDENTICAL
    episodes -- the honest SS-B-vs-challenger comparison that does not exist yet (the p5
    confirm's own real-fleet anchor was n=18).

REUSE, not reinvention (OP-22) -- every piece below is an EXISTING, already-tested module:
  * _signal_cache.load_or_build_signals()   -- the CANONICAL strike-independent ribbon_ride
      signal cohort (both directions, L2 gate, cap OFF; cached analysis/exit-parity/
      signal-set.json, n=250, 2025-01-06..2026-06-17). Built by T3/T4 for EXACTLY this reuse
      case ("load each signal's real cached OPRA bars per strike and replay"). This IS the
      "ribbon_ride-family signal cohort" the ticket asks for -- using it means AXIS 1 is a
      TRUE isolated-variable strike swap (same entry_spot/side/date/entry_ts at every so).
  * tw8_level_context.enrich_signals()/load_spy_full()  -- per-day-frozen trigger-level
      recovery (the SAME level-freeze convention lib/orchestrator.py used to fire the
      signals) -- gives DIRECT trigger levels (not the backward-scan heuristic LAYER-B
      anchors need), i.e. structure_stop_study's higher-fidelity "FRESH-SLICE" tier, applied
      to the full cohort instead of the 18-signal slice.
  * structure_stop_study.SS_B_SHAPE / STRUCTURE_BUFFER["SS-B"] / structure_stop_signal_time /
      replay_structure_aware / NormBar -- the CERTIFIED SS-B replay engine (already
      cross-verified against real fleet fills in PROFIT-P1, exact bit match against
      ledger-forensics). Reused UNCHANGED. replay_structure_aware degenerates to a pure
      premium/time exit when ss_time=None -- reused for BOTH shapes (SS-B: ss_time from the
      structure check; P5-challenger: ss_time always None, no chart layer) so the two exit
      shapes are replayed through the IDENTICAL bar-walk/fill-convention code path --
      genuinely apples-to-apples, not two different replay engines.
  * t4_exit_matrix.battery() -- the canonical metrics bundle (n/expectancy/wr/edge_capture_rel
      [OP-16 J-anchor no-regression, J_WINNERS/J_LOSERS] /oos_total/oos_positive/wf/wf_ge_070/
      qpf/exp_drop_top3/worst_trade/max_dd). NOTE: J_LOSERS as coded here has 3 entries (5/05,
      5/06, 5/07-734C) -- CLAUDE.md's OP-16 prose lists a 4th loser (5/07 737C) not present in
      this constant; inherited from the reused module, not modified here.
  * autoresearch.null_baseline.random_entry_null()/null_gate() -- the graduated C3/L58
      random-entry-null (20 seeds, "beat the null MAX AND drop-top-N beats the null MEAN").
      Reused via its `sim_fn` injection point: a thin adapter wraps THIS script's own
      strike+exit-shape replay so the null draws run through the SAME engine as the headline
      cells (not simulate_trade_real, which cannot express SS-B's structure layer).
  * ribbon_rejection_wick_battery.bh_fdr / FDR_ALPHA=0.10 -- reused unchanged (named
      explicitly in this session's sibling PROFIT-P3/P5 pre-registrations as the house
      BH-FDR convention for this exact research stream).
  * lib.option_pricing_real.load_contract_bars/option_symbol -- real OPRA 5-min bars,
      SIMULATOR strike convention (put=atm-so, call=atm+so; so>0=OTM, so<0=ITM), the same
      convention WP5-STRIKE-AB/p5_topcell_real_fills_confirm/t4_exit_matrix all share.

FILL-BAR CONVENTION (the open-chip sensitivity axis). p5_topcell_real_fills_confirm.py found
t4/t5/structure_stop_study's original bar loader used `>=` on entry_ts (the fill bar's OWN
high/low get checked against stop/TP1), where simulate_trade_real's real bar-walk starts ONE
BAR LATER (simulator_real.py:492, opt_idx=entry_idx_opt+1) -- switching to `>` (exclude the
fill bar) is what makes exit_manager replay reproduce the recorded funnel number. This script
therefore treats `>` as the PRIMARY convention for every headline cell, and ALSO replays every
cell's headline metrics under the OLD `>=` convention as a disclosed SENSITIVITY column -- if
a comparison's DIRECTIONAL verdict (candidate beats control, sign of the delta) flips between
the two conventions, that comparison is stamped UNSTABLE_ON_OPEN_AUDIT and excluded from the
ship list regardless of otherwise clearing the auto-ratify bar (the two open audit chips,
task_4935ea80 / task_86001855, must land before anything unstable on this toggle ships).

SCOPE: profit_lock_arm_scope="post_tp1" (LIVE) throughout -- structure_stop_study's SS_B_SHAPE
carries no override key so it already defaults to post_tp1 (ARM_SCOPE_POST_TP1); the
P5-challenger shape sets it explicitly, matching p5_topcell_real_fills_confirm.py's own
shape_live dict verbatim. ANALYSIS ONLY -- reads real OPRA local cache + params.json for
context; touches NO params/config/trading-path file; places no orders. QTY=10 fixed (t4/
p5_topcell/structure_stop_study Layer-A convention -- absolute $ are RELATIVE, not the OP-16
account-size absolute).

Run: backtest/.venv/Scripts/python.exe backtest/tools/ribbon_ride_strike_exit_ab.py [--smoke]
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time as _time_mod
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import _signal_cache as sc                                             # noqa: E402
import t4_exit_matrix as t4                                             # noqa: E402
import tw8_level_context as lc                                          # noqa: E402
import structure_stop_study as sss                                      # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol   # noqa: E402
from lib.coverage_parity import check_coverage_parity                   # noqa: E402
from exit_manager import ARM_SCOPE_POST_TP1, TIME_STOP_ET               # noqa: E402
from autoresearch.strategy_space_grind import OOS_BOUNDARY, J_WINNERS, J_LOSERS, EDGE_CAPTURE_MAX  # noqa: E402
from autoresearch.null_baseline import random_entry_null, null_gate, DEFAULT_ENTRY_GATE  # noqa: E402
from autoresearch.ribbon_rejection_wick_battery import bh_fdr, FDR_ALPHA  # noqa: E402

SMOKE = "--smoke" in sys.argv
OUT_JSON = REPO / "analysis" / "recommendations" / ("ribbon-ride-strike-exit-ab-SMOKE.json" if SMOKE
                                                     else "ribbon-ride-strike-exit-ab.json")
OUT_MD = REPO / "analysis" / "recommendations" / ("ribbon-ride-strike-exit-ab-SMOKE.md" if SMOKE
                                                   else "ribbon-ride-strike-exit-ab.md")

QTY = 10                        # t4/p5_topcell/structure_stop_study Layer-A convention
NULL_SEEDS = 3 if SMOKE else 20  # WP5/fraud_gates "~20 seeds" convention (smoke: fast check only)
TIME_STOP_LAYER = TIME_STOP_ET   # 15:50 ET
OPEN_AUDIT_CHIPS = ["task_4935ea80", "task_86001855"]

# strike cells, SIMULATOR convention (neg=ITM, 0=ATM, pos=OTM); label matches live params tier naming
STRIKE_CELLS = [("OTM-2", 2), ("OTM-1", 1), ("ATM", 0), ("ITM-2", -2)]
CONTROL_STRIKE = "OTM-2"

SS_B_SHAPE = dict(sss.SS_B_SHAPE)             # exact live params, reused unchanged
SS_B_BUFFER = sss.STRUCTURE_BUFFER["SS-B"]    # 0.0
# The P5 top-cell challenger shape (rank 1/106 among mass-grind-phase5 survivors,
# OTM-1_stop-8_trailing0.15) -- reused VERBATIM from p5_topcell_real_fills_confirm.py's own
# LAYER A shape_live dict (run_layer_a()) so this script's OTM-1/P5-challenger cell is a
# direct, comparable extension of that already-shipped result, not a re-derivation.
P5_CHALLENGER_SHAPE = {
    "premium_stop_pct": -0.08, "tp1_premium_pct": 0.30, "tp1_qty_fraction": 0.5,
    "profit_lock_mode": "trailing", "trail_pct": 0.15,
    "profit_lock_arm_scope": ARM_SCOPE_POST_TP1, "profit_lock_arm_pct": 0.0,
}

SHAPES = {"SS-B": (SS_B_SHAPE, True), "P5-CHALLENGER": (P5_CHALLENGER_SHAPE, False)}  # (shape, use_structure)


def log(msg: str) -> None:
    print(f"[strike-exit-ab] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# BAR FETCH -- generalizes p5_topcell_real_fills_confirm.py's fixed-convention loader to an
# arbitrary strike offset AND an old/new fill-bar-convention toggle (the sensitivity axis).
# ---------------------------------------------------------------------------------------------
def strike_for(entry_spot: float, side: str, so: int) -> int:
    return int(round(entry_spot)) - so if side == "P" else int(round(entry_spot)) + so


def fetch_entry_and_bars(entry_spot: float, side: str, date: dt.date, entry_ts: dt.datetime,
                         so: int, *, old_semantics: bool = False):
    """Returns (entry_premium, norm_bars) or None (no OPRA coverage at this strike/date).

    entry_premium = the first bar's OPEN at/after entry_ts (t4._load_bars / structure_stop_study
    convention: "first bar's open = fill price"). WALK bars = strictly AFTER that entry bar
    (p5_topcell's CORRECTED convention, matches simulate_trade_real's opt_idx=entry_idx_opt+1)
    unless old_semantics=True, which INCLUDES the entry bar in the walk (the pre-fix t4/t5/
    structure_stop_study convention) -- used only for the disclosed sensitivity column.
    """
    strike = strike_for(entry_spot, side, so)
    df = load_contract_bars(option_symbol(date, strike, side))
    if df is None or df.empty:
        return None
    ts = df["timestamp_et"]
    if ts.dt.tz is not None:
        ts = ts.dt.tz_localize(None)
    entry_ts_naive = entry_ts.replace(tzinfo=None) if entry_ts.tzinfo is not None else entry_ts
    entry_mask = (ts >= entry_ts_naive) & (ts.dt.date == date)
    entry_rows = df[entry_mask.values]
    if entry_rows.empty:
        return None
    entry_bar = entry_rows.iloc[0]
    entry_premium = float(entry_bar["open"])
    entry_bar_ts = entry_bar["timestamp_et"]
    if getattr(entry_bar_ts, "tzinfo", None) is not None:
        entry_bar_ts = entry_bar_ts.tz_localize(None)
    walk_mask = ((ts >= entry_bar_ts) if old_semantics else (ts > entry_bar_ts)) & (ts.dt.date == date)
    walk = df[walk_mask.values]
    if walk.empty:
        return None
    norm_bars = []
    for _, r in walk.iterrows():
        t = r["timestamp_et"]
        if getattr(t, "tzinfo", None) is not None:
            t = t.tz_localize(None)
        norm_bars.append(sss.NormBar(t.to_pydatetime() if hasattr(t, "to_pydatetime") else t,
                                     float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return entry_premium, norm_bars


# ---------------------------------------------------------------------------------------------
# SIGNAL PREP -- load cohort, enrich with DIRECT trigger levels, precompute per-signal ss_time
# ONCE (strike-independent -- the chart-level breach clock does not depend on which contract
# you hold, so all 4 strike cells under SS-B share the identical ss_time per signal).
# ---------------------------------------------------------------------------------------------
def load_cohort():
    raw = sc.load_or_build_signals()
    signals = raw["signals"] if isinstance(raw, dict) else raw
    if SMOKE:
        signals = signals[:40]
    enriched, spy_full = lc.enrich_signals(signals, sc.START, sc.END)
    spy_by_date = {d: g.reset_index(drop=True) for d, g in spy_full.groupby("date")}
    n_trig = sum(1 for s in enriched if s.get("trigger_level") is not None)
    log(f"cohort: {len(enriched)} signals ({sc.START}..{sc.END}), {n_trig} with a recoverable "
        f"trigger_level ({round(100*n_trig/len(enriched),1)}%) -- the rest fall back to "
        f"premium-only SS-B (catastrophe cap, no chart layer), per structure_stop_study's "
        f"documented fallback contract")
    prepped = []
    for s in enriched:
        date = dt.date.fromisoformat(s["date"])
        entry_ts = dt.datetime.fromisoformat(s["entry_ts"])
        spy_lifetime = spy_by_date.get(date)
        ss_time = None
        if spy_lifetime is not None and s.get("trigger_level") is not None:
            sub = spy_lifetime[spy_lifetime["timestamp_et"] >= entry_ts]
            ss_time = sss.structure_stop_signal_time(sub, s["side"], s["trigger_level"], SS_B_BUFFER)
        prepped.append({**s, "date_obj": date, "entry_ts_obj": entry_ts, "ss_time": ss_time})
    return prepped, spy_full, spy_by_date


# ---------------------------------------------------------------------------------------------
# ONE CELL: (strike so, exit shape) x (fill-bar convention) -> trades list
# ---------------------------------------------------------------------------------------------
def replay_cell(prepped: list[dict], so: int, shape: dict, use_structure: bool,
                *, old_semantics: bool = False) -> tuple[list[dict], int]:
    trades, n_no_bars = [], 0
    for s in prepped:
        fetched = fetch_entry_and_bars(float(s["entry_spot"]), s["side"], s["date_obj"],
                                       s["entry_ts_obj"], so, old_semantics=old_semantics)
        if fetched is None:
            n_no_bars += 1
            continue
        entry_premium, norm_bars = fetched
        ss_time = s["ss_time"] if use_structure else None
        r = sss.replay_structure_aware(entry_premium, s["side"], QTY, norm_bars, ss_time,
                                       shape, TIME_STOP_LAYER)
        trades.append({"date": s["date_obj"], "direction": s["direction"], "side": s["side"],
                       "pnl": r["pnl"], "structure_fired": r["structure_fired"]})
    return trades, n_no_bars


def top3_day_share(trades: list[dict]) -> float | None:
    by_day: dict = {}
    for t in trades:
        by_day.setdefault(t["date"], 0.0)
        by_day[t["date"]] += t["pnl"]
    total = sum(by_day.values())
    if not total:
        return None
    top3 = sum(sorted(by_day.values(), reverse=True)[:3])
    return round(top3 / total, 3)


def both_halves(trades: list[dict]) -> dict:
    """Chronological first-half/second-half split (fleet_exit_parity_per_arm.py convention)
    -- feeds sub_window_stable."""
    ordered = sorted(trades, key=lambda t: t["date"])
    n = len(ordered)
    mid = n // 2
    first, second = ordered[:mid], ordered[mid:]
    f_tot = round(sum(t["pnl"] for t in first), 2)
    s_tot = round(sum(t["pnl"] for t in second), 2)
    return {"first_half": {"n": len(first), "total": f_tot},
           "second_half": {"n": len(second), "total": s_tot},
           "both_positive": bool(first and second and f_tot > 0 and s_tot > 0)}


# ---------------------------------------------------------------------------------------------
# RANDOM-ENTRY NULL -- adapts autoresearch.null_baseline.random_entry_null via its sim_fn
# injection point so the coin-flip draws run through THIS script's SS-B/P5-challenger replay
# engine (simulate_trade_real cannot express the structure-stop layer).
# ---------------------------------------------------------------------------------------------
def make_null_sim_fn(so: int, shape: dict, use_structure: bool, spy_by_date: dict):
    def _sim(entry_bar_idx, entry_bar, spy_df, ribbon_df, rejection_level, triggers_fired,
             side, qty, setup, premium_stop_pct, strike_offset):
        entry_ts = entry_bar["timestamp_et"]
        if hasattr(entry_ts, "to_pydatetime"):
            entry_ts = entry_ts.to_pydatetime()
        if getattr(entry_ts, "tzinfo", None) is not None:
            entry_ts = entry_ts.replace(tzinfo=None)
        date = entry_ts.date()
        entry_spot = float(entry_bar["close"])
        fetched = fetch_entry_and_bars(entry_spot, side, date, entry_ts, strike_offset)
        if fetched is None:
            return None
        entry_premium, norm_bars = fetched
        ss_time = None
        if use_structure and rejection_level is not None:
            day_bars = spy_by_date.get(date)
            if day_bars is not None:
                sub = day_bars[day_bars["timestamp_et"] >= entry_ts]
                ss_time = sss.structure_stop_signal_time(sub, side, float(rejection_level), SS_B_BUFFER)
        r = sss.replay_structure_aware(entry_premium, side, qty, norm_bars, ss_time, shape, TIME_STOP_LAYER)
        return SimpleNamespace(dollar_pnl=r["pnl"])
    return _sim


def run_null(so: int, shape: dict, use_structure: bool, spy_full: pd.DataFrame,
            spy_by_date: dict, trades: list[dict]) -> dict:
    n_call = sum(1 for t in trades if t["side"] == "C")
    n_put = sum(1 for t in trades if t["side"] == "P")
    sim_fn = make_null_sim_fn(so, shape, use_structure, spy_by_date)
    return random_entry_null(
        rth=spy_full, n_signals=len(trades), n_call=n_call, n_put=n_put,
        strike_offset=so, premium_stop_pct=shape.get("premium_stop_pct", -0.5),
        qty=QTY, entry_gate=DEFAULT_ENTRY_GATE, seeds=NULL_SEEDS,
        setup="RIBBON_RIDE_STRIKE_EXIT_AB_NULL", sim_fn=sim_fn,
    )


def empirical_p_null(real_per_trade, null_by_seed: list[float]) -> float:
    """Add-one empirical p-value (Davison & Hinkley convention) from the null's per-seed means:
    fraction of null seeds whose per-trade mean is >= the real cell's expectancy, +1/+1
    smoothed so p is never exactly 0. Distinct from ribbon_rejection_wick_battery.bootstrap_p
    (which resamples individual trade-level P&L from a pooled null trade set) -- this null is
    constructed at the SEED level (random_entry_null's own convention, matching WP5/fraud_gates'
    established methodology for this exact research stream) -- disclosed, not silently conflated."""
    if real_per_trade is None or not null_by_seed:
        return 1.0
    ge = sum(1 for v in null_by_seed if v >= real_per_trade)
    return round((1 + ge) / (1 + len(null_by_seed)), 4)


# ---------------------------------------------------------------------------------------------
# ONE FULL CELL (headline + sensitivity + null + p_null) -- the unit both axes are built from.
# ---------------------------------------------------------------------------------------------
def build_cell(cell_id: str, so: int, strike_label: str, exit_label: str, shape: dict,
              use_structure: bool, prepped: list[dict], spy_full: pd.DataFrame,
              spy_by_date: dict) -> dict:
    t0 = _time_mod.time()
    trades, n_no_bars = replay_cell(prepped, so, shape, use_structure, old_semantics=False)
    b = t4.battery(trades)
    b["top3_day_share"] = top3_day_share(trades)
    bh = both_halves(trades)
    b["sub_window_stable"] = bh["both_positive"]
    b["both_halves"] = {"first": bh["first_half"], "second": bh["second_half"]}

    # sensitivity column: OLD fill-bar convention, headline metrics only (no shortcut on
    # the disclosed toggle check; a second full null/BH-FDR pass is NOT run here -- the task
    # scopes the sensitivity column to "top-line cells", i.e. headline numbers, not the
    # entire battery a second time).
    trades_old, n_no_bars_old = replay_cell(prepped, so, shape, use_structure, old_semantics=True)
    b_old = t4.battery(trades_old)

    null = run_null(so, shape, use_structure, spy_full, spy_by_date, trades)
    gate = null_gate(b.get("expectancy"), b.get("exp_drop_top3"), null)
    p_null = empirical_p_null(b.get("expectancy"), null.get("per_trade_by_seed", []))

    elapsed = round(_time_mod.time() - t0, 1)
    log(f"{cell_id}: n={b.get('n')} (dropped {n_no_bars} no-bars) exp=${b.get('expectancy')} "
        f"OOS=${b.get('oos_total')} wf={b.get('wf')} qpf={b.get('qpf')} "
        f"edge_capture_rel={b.get('edge_capture_rel')} null_pass={gate.get('null_pass')} "
        f"p_null={p_null} sensitivity(old)_exp=${b_old.get('expectancy')} ({elapsed}s)")

    return {
        "cell_id": cell_id, "strike_label": strike_label, "so_simulator_convention": so,
        "exit_label": exit_label, "n_no_local_bars": n_no_bars,
        "metrics": b,
        "sensitivity_old_fillbar_convention": {
            "n": b_old.get("n"), "n_no_local_bars": n_no_bars_old,
            "expectancy": b_old.get("expectancy"), "wr": b_old.get("wr"),
            "oos_total": b_old.get("oos_total"), "oos_positive": b_old.get("oos_positive"),
            "wf": b_old.get("wf"), "edge_capture_rel": b_old.get("edge_capture_rel"),
        },
        "null": {"seeds": null.get("seeds"), "n_eligible": null.get("n_eligible"),
                 "n_drawn": null.get("n_drawn"), "per_trade_mean": null.get("per_trade_mean"),
                 "per_trade_max": null.get("per_trade_max")},
        "null_gate": gate, "p_null": p_null,
    }


# ---------------------------------------------------------------------------------------------
# COMPARISON HELPERS
# ---------------------------------------------------------------------------------------------
def auto_ratify_flags(cell: dict) -> dict:
    """OP-11: auto-ratify requires OOS_positive AND WF>=0.70 AND sub_window_stable AND
    anchor_no_regression (evaluated per-cell here; anchor_no_regression is filled in by the
    caller, which knows the relevant control)."""
    m = cell["metrics"]
    return {
        "oos_positive": bool(m.get("oos_positive")),
        "wf_ge_070": bool(m.get("wf_ge_070")),
        "sub_window_stable": bool(m.get("sub_window_stable")),
    }


def verdict_flip(headline_delta: float | None, sensitivity_delta: float | None) -> bool:
    """True iff the SIGN of the comparison delta flips between the corrected and old fill-bar
    conventions (the UNSTABLE_ON_OPEN_AUDIT check)."""
    if headline_delta is None or sensitivity_delta is None:
        return False
    return (headline_delta > 0) != (sensitivity_delta > 0)


def compare(candidate: dict, control: dict, label: str) -> dict:
    cand_exp = candidate["metrics"].get("expectancy")
    ctl_exp = control["metrics"].get("expectancy")
    cand_oos = candidate["metrics"].get("oos_total")
    ctl_oos = control["metrics"].get("oos_total")
    cand_ecr = candidate["metrics"].get("edge_capture_rel")
    ctl_ecr = control["metrics"].get("edge_capture_rel")
    delta_exp = round(cand_exp - ctl_exp, 2) if (cand_exp is not None and ctl_exp is not None) else None
    delta_oos = round(cand_oos - ctl_oos, 2) if (cand_oos is not None and ctl_oos is not None) else None
    old_cand_exp = candidate["sensitivity_old_fillbar_convention"].get("expectancy")
    old_ctl_exp = control["sensitivity_old_fillbar_convention"].get("expectancy")
    old_delta = (round(old_cand_exp - old_ctl_exp, 2)
                if (old_cand_exp is not None and old_ctl_exp is not None) else None)
    unstable = verdict_flip(delta_exp, old_delta)
    anchor_no_regression = bool(cand_ecr is not None and ctl_ecr is not None and cand_ecr >= ctl_ecr)
    flags = auto_ratify_flags(candidate)
    # OPTION-CACHE-ITM-COVERAGE-GAP (2026-08-02/03): the OPRA disk cache's missing-bar rate
    # widens monotonically with distance from OTM-2 (real illiquidity, not a fetch bug) --
    # a strike-axis delta compared across cells with a materially different missing-bar rate
    # is comparing non-matched populations, silently. Gate it: coverage must be comparable
    # (default <=5pp spread) before a delta is trustworthy, regardless of the other flags.
    coverage_parity = check_coverage_parity([
        {"cell_id": candidate["cell_id"], "n_no_local_bars": candidate.get("n_no_local_bars", 0),
         "n_total_attempted": candidate["metrics"].get("n", 0) + candidate.get("n_no_local_bars", 0)},
        {"cell_id": control["cell_id"], "n_no_local_bars": control.get("n_no_local_bars", 0),
         "n_total_attempted": control["metrics"].get("n", 0) + control.get("n_no_local_bars", 0)},
    ])
    clears_auto_ratify = bool(delta_exp is not None and delta_exp > 0 and flags["oos_positive"]
                              and flags["wf_ge_070"] and flags["sub_window_stable"]
                              and anchor_no_regression and not unstable
                              and coverage_parity["parity_ok"])
    if unstable:
        ship_or_wait = "WAIT_OPEN_AUDIT_CHIPS"
    elif not coverage_parity["parity_ok"]:
        ship_or_wait = "WAIT_COVERAGE_GAP"
    elif clears_auto_ratify:
        ship_or_wait = "SHIP"
    else:
        ship_or_wait = "WAIT_EVIDENCE"
    return {
        "label": label, "candidate": candidate["cell_id"], "control": control["cell_id"],
        "delta_expectancy": delta_exp, "delta_oos_total": delta_oos,
        "candidate_beats_control": bool(delta_exp is not None and delta_exp > 0),
        "sensitivity_delta_expectancy_old_convention": old_delta,
        "unstable_on_open_audit": unstable,
        "anchor_no_regression_op16": anchor_no_regression,
        "candidate_edge_capture_rel": cand_ecr, "control_edge_capture_rel": ctl_ecr,
        "auto_ratify_flags": flags,
        "coverage_parity": coverage_parity,
        "clears_auto_ratify_bar": clears_auto_ratify,
        "ship_or_wait": ship_or_wait,
    }


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    t_start = _time_mod.time()
    log(f"{'SMOKE MODE' if SMOKE else 'FULL RUN'} -- loading signal cohort")
    prepped, spy_full, spy_by_date = load_cohort()

    # ---- AXIS 1: strike, SS-B fixed ----
    log("=== AXIS 1: strike (SS-B fixed) ===")
    axis1_cells = {}
    for label, so in STRIKE_CELLS:
        cell_id = f"{label}/SS-B"
        axis1_cells[label] = build_cell(cell_id, so, label, "SS-B", SS_B_SHAPE, True,
                                        prepped, spy_full, spy_by_date)

    control = axis1_cells[CONTROL_STRIKE]
    candidates = {lbl: c for lbl, c in axis1_cells.items() if lbl != CONTROL_STRIKE}
    axis1_comparisons = {lbl: compare(c, control, f"{lbl} vs {CONTROL_STRIKE} (SS-B fixed)")
                         for lbl, c in candidates.items()}
    # winner selection rule: highest OOS expectancy among the 3 candidates (OP-32 emphasizes
    # OOS as the primary forward-looking read; ties broken by full-sample expectancy).
    winner_label = max(candidates,
                       key=lambda lbl: (candidates[lbl]["metrics"].get("oos_total") is not None,
                                        candidates[lbl]["metrics"].get("oos_total") or -1e18,
                                        candidates[lbl]["metrics"].get("expectancy") or -1e18))
    winner_so = dict(STRIKE_CELLS)[winner_label]
    log(f"AXIS 1 winner (by OOS total, tie-break full expectancy): {winner_label} "
        f"(OOS_total=${candidates[winner_label]['metrics'].get('oos_total')}, "
        f"beats control: {axis1_comparisons[winner_label]['candidate_beats_control']})")

    # ---- AXIS 2: exit shape, at OTM-2 control + the axis-1 strike winner ----
    log("=== AXIS 2: exit shape (P5-challenger vs SS-B), at OTM-2 control + strike winner ===")
    axis2_strikes = {CONTROL_STRIKE: dict(STRIKE_CELLS)[CONTROL_STRIKE]}
    if winner_label != CONTROL_STRIKE:
        axis2_strikes[winner_label] = winner_so
    axis2_cells = {}
    for label, so in axis2_strikes.items():
        cell_id = f"{label}/P5-CHALLENGER"
        axis2_cells[label] = build_cell(cell_id, so, label, "P5-CHALLENGER", P5_CHALLENGER_SHAPE,
                                        False, prepped, spy_full, spy_by_date)

    axis2_comparisons = {}
    for label in axis2_strikes:
        ss_b_cell = axis1_cells[label]           # already computed in axis 1
        p5_cell = axis2_cells[label]
        axis2_comparisons[label] = compare(p5_cell, ss_b_cell,
                                           f"P5-CHALLENGER vs SS-B (at {label})")

    # ---- BH-FDR across every unique cell computed this run ----
    all_cells = list(axis1_cells.values()) + list(axis2_cells.values())
    bh_input = [{"p_null": c["p_null"]} for c in all_cells]
    n_comparisons = len(bh_input)
    bh_fdr(bh_input, alpha=FDR_ALPHA)
    for c, b in zip(all_cells, bh_input):
        c["bh_fdr_survivor"] = b["bh_fdr_survivor"]
        c["bh_rank"] = b["bh_rank"]
    log(f"BH-FDR (alpha={FDR_ALPHA}) across {n_comparisons} cells: "
        f"{sum(1 for c in all_cells if c['bh_fdr_survivor'])} survivors")

    ship = [v for v in list(axis1_comparisons.values()) + list(axis2_comparisons.values())
           if v["ship_or_wait"] == "SHIP"]
    wait_audit = [v for v in list(axis1_comparisons.values()) + list(axis2_comparisons.values())
                 if v["ship_or_wait"] == "WAIT_OPEN_AUDIT_CHIPS"]
    wait_evidence = [v for v in list(axis1_comparisons.values()) + list(axis2_comparisons.values())
                     if v["ship_or_wait"] == "WAIT_EVIDENCE"]

    out = {
        "_doc": ("PROFIT-P2-RIBBON-RIDE-STRIKE-AB (extended: strike x exit head-to-head). "
                "ANALYSIS/SCORECARD ONLY -- no params/config/trading-path file touched, no "
                "orders placed. MEASURED tier: real OPRA local 5-min trade bars "
                "(backtest/data/options/*.csv) replayed through the LIVE exit_manager decision "
                "core (plan_exit_actions / structure_stop_study.replay_structure_aware) -- NOT "
                "live broker fills. Touch-based stop/TP resolution on 5-min bars (1-min "
                "intrabar timing not modeled), same disclosed gap as every T4/T5/"
                "structure_stop_study/p5_topcell_real_fills_confirm replay in this repo."),
        "generated_at": dt.datetime.now().isoformat(),
        "smoke_mode": SMOKE,
        "signal_cohort": {
            "source": "_signal_cache.load_or_build_signals() (analysis/exit-parity/signal-set.json)",
            "window": f"{sc.START}..{sc.END}", "n_raw": len(prepped),
            "n_call_bull": sum(1 for s in prepped if s["side"] == "C"),
            "n_put_bear": sum(1 for s in prepped if s["side"] == "P"),
            "n_with_recoverable_trigger_level": sum(1 for s in prepped if s["ss_time"] is not None
                                                    or s.get("trigger_level") is not None),
        },
        "shapes": {"SS-B": {**SS_B_SHAPE, "structure_buffer": SS_B_BUFFER,
                            "note": "reused unchanged from structure_stop_study.py; exact live params"},
                  "P5-CHALLENGER": {**P5_CHALLENGER_SHAPE,
                                    "note": ("reused verbatim from p5_topcell_real_fills_confirm.py's "
                                            "LAYER A shape_live dict (rank 1/106 P5 survivor, "
                                            "OTM-1_stop-8_trailing0.15)")}},
        "oos_boundary": str(OOS_BOUNDARY),
        "op16_anchor": {"j_winners": [[str(d), s, p] for d, s, p in J_WINNERS],
                        "j_losers": [[str(d), s, p] for d, s, p in J_LOSERS],
                        "edge_capture_max": EDGE_CAPTURE_MAX,
                        "note": ("edge_capture_rel = winner_day_pnl_sum - loser_day_loss_penalty "
                                "(t4_exit_matrix.battery), QTY=10 fixed -- RELATIVE not the OP-16 "
                                "account-size absolute. J_LOSERS as coded here has 3 entries; "
                                "CLAUDE.md OP-16 prose lists a 4th (5/07 737C) not present in the "
                                "reused constant -- inherited, not modified here.")},
        "axis1_strike": {
            "control": CONTROL_STRIKE, "winner": winner_label,
            "selection_rule": "max OOS total pnl among candidates, tie-break full-sample expectancy",
            "cells": axis1_cells, "comparisons": axis1_comparisons,
        },
        "axis2_exit": {
            "strikes_tested": list(axis2_strikes.keys()), "cells": axis2_cells,
            "comparisons": axis2_comparisons,
            "note": ("P5-CHALLENGER shape parameters held FIXED across strikes (only the "
                    "underlying strike/contract varies) -- an isolated-variable exit-axis test, "
                    "mirroring axis 1's own isolated-variable strike test."),
        },
        "bh_fdr": {"alpha": FDR_ALPHA, "n_comparisons": n_comparisons,
                  "n_survivors": sum(1 for c in all_cells if c["bh_fdr_survivor"]),
                  "method": "benjamini-hochberg (ribbon_rejection_wick_battery.bh_fdr, reused unchanged)"},
        "ship_vs_wait": {
            "ship_per_op11_auto_ratify": ship,
            "wait_on_open_audit_chips": wait_audit,
            "wait_more_evidence": wait_evidence,
            "open_audit_chips_blocking": OPEN_AUDIT_CHIPS,
        },
        "disclosures": [
            "MEASURED (real OPRA) not REALIZED (no broker fills exist for these strike/exit "
            "combinations) -- this is a scorecard/simulation-replay artifact, per OP-33 labeled "
            "as such throughout; arming anything is a SEPARATE step this script does not take.",
            "Signal cohort is the FULL _signal_cache population (n as reported above), NOT "
            "re-detected per strike -- axis 1 is a true isolated-variable strike swap. Per-cell "
            "n differs slightly only where a given strike/date combination has no cached OPRA "
            "file (n_no_local_bars, disclosed per cell) -- exactly the same disclosed coverage-gap "
            "pattern WP5-STRIKE-AB and p5_topcell_real_fills_confirm.py already use.",
            "Trigger-level recovery is DIRECT (tw8_level_context.enrich_signal, the same per-day "
            "level-freeze convention lib/orchestrator.py used to fire these signals), NOT the "
            "backward-scan heuristic real-fills anchors need -- higher fidelity than a fleet-fills "
            "LAYER B, matching structure_stop_study's own FRESH-SLICE tier. Signals with no "
            "recoverable trigger_level fall back to SS-B's premium-only catastrophe-cap behavior "
            "(never dropped), per structure_stop_study's documented contract.",
            "Sensitivity column (OLD `>=` fill-bar convention) is HEADLINE METRICS ONLY (n/"
            "expectancy/wr/oos/edge_capture_rel via t4.battery) -- the random-entry-null and "
            "BH-FDR were NOT re-run a second time under the old convention (out of the stated "
            "'top-line cells' scope; would double an already substantial compute budget for a "
            "check whose purpose is a directional-verdict-flip flag, not a second full battery).",
            "Random-entry null is SEED-LEVEL (random_entry_null: 20 deterministic seeds, each "
            "drawing n_signals random RTH entries with the real cell's call/put mix, replayed "
            "through the SAME strike+exit-shape engine via a custom sim_fn) -- this is the "
            "established WP5/fraud_gates convention for this exact research stream, DISTINCT from "
            "ribbon_rejection_wick_battery.bootstrap_p's individual-trade-level bootstrap; p_null "
            "here is an add-one empirical p-value over the 20 seed-level means, not a bootstrap "
            "p-value -- disclosed, not conflated.",
            "drop-top-3 (not drop-top-5) is this script's concentration-robustness convention, "
            "matching t4_exit_matrix/structure_stop_study/fleet_exit_parity_per_arm (the "
            "structure-stop research lineage this ticket extends) -- distinct from fraud_gates/"
            "null_baseline's drop-top-5 convention (the vwap_continuation/edgehunt research "
            "lineage). null_gate() receives exp_drop_top3 as its drop-top5_per_trade argument "
            "(functionally: 'the day-concentration-robust per-trade number', regardless of "
            "whether 3 or 5 days were dropped) -- not re-computed as a top-5 variant here.",
            "sub_window_stable = both chronological halves (fleet_exit_parity_per_arm.py "
            "convention) show positive total pnl -- the OP-11 'sub_window_stable' gate leg.",
            "QTY=10 fixed (t4/p5_topcell/structure_stop_study Layer-A convention) -- absolute $ "
            "figures are RELATIVE-to-shape-comparison, not the OP-16 account-size absolute.",
            f"Open audit chips blocking any UNSTABLE_ON_OPEN_AUDIT verdict from shipping: "
            f"{', '.join(OPEN_AUDIT_CHIPS)} (the fill-bar methodology fix itself, per the task brief).",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    log(f"wrote {OUT_JSON} + {OUT_MD} ({round(_time_mod.time()-t_start,1)}s total)")
    log(f"SHIP: {len(ship)} | WAIT_OPEN_AUDIT_CHIPS: {len(wait_audit)} | "
        f"WAIT_EVIDENCE: {len(wait_evidence)}")
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# RIBBON-RIDE STRIKE x EXIT A/B — PROFIT-P2 (extended)")
    L.append("")
    L.append(f"Generated: {out['generated_at']}. Source: `backtest/tools/ribbon_ride_strike_exit_ab.py`.")
    if out["smoke_mode"]:
        L.append("")
        L.append("**SMOKE MODE RUN — reduced signal count + seeds, for pipeline verification only, "
                 "NOT a decision-grade result.**")
    L.append("")
    sc_ = out["signal_cohort"]
    L.append(f"**Signal cohort:** {sc_['source']}, window {sc_['window']}, n={sc_['n_raw']} "
             f"(call/bull={sc_['n_call_bull']}, put/bear={sc_['n_put_bear']}).")
    L.append("")
    L.append("## AXIS 1 — strike (SS-B exit shape fixed)")
    L.append("")
    a1 = out["axis1_strike"]
    L.append(f"Control: **{a1['control']}**. Winner (by OOS total, tie-break full expectancy): "
             f"**{a1['winner']}**.")
    L.append("")
    L.append("| strike | n | exp $/tr | WR | OOS total | OOS+ | WF | qpf | edge_capture_rel | "
             "top3-day% | null_pass | p_null | bh_survivor |")
    L.append("|---|--:|--:|--:|--:|:--:|--:|--:|--:|--:|:--:|--:|:--:|")
    for lbl, _so in [("OTM-2", None), ("OTM-1", None), ("ATM", None), ("ITM-2", None)]:
        c = a1["cells"][lbl]
        m = c["metrics"]
        L.append(f"| {lbl}{' (control)' if lbl==a1['control'] else ''} | {m.get('n')} | "
                 f"${m.get('expectancy')} | {m.get('wr')} | ${m.get('oos_total')} | "
                 f"{m.get('oos_positive')} | {m.get('wf')} | {m.get('qpf')} | "
                 f"{m.get('edge_capture_rel')} | {c['metrics'].get('top3_day_share')} | "
                 f"{c['null_gate'].get('null_pass')} | {c['p_null']} | {c['bh_fdr_survivor']} |")
    L.append("")
    L.append("**Comparisons vs control:**")
    L.append("")
    for lbl, comp in a1["comparisons"].items():
        L.append(f"- **{comp['label']}**: delta_exp=${comp['delta_expectancy']}/tr, "
                 f"delta_OOS=${comp['delta_oos_total']}, beats_control={comp['candidate_beats_control']}, "
                 f"anchor_no_regression={comp['anchor_no_regression_op16']}, "
                 f"unstable_on_toggle={comp['unstable_on_open_audit']} "
                 f"(sensitivity delta=${comp['sensitivity_delta_expectancy_old_convention']}), "
                 f"**{comp['ship_or_wait']}**")
    L.append("")
    L.append("## AXIS 2 — exit shape (P5-CHALLENGER vs SS-B), at OTM-2 control + strike winner")
    L.append("")
    a2 = out["axis2_exit"]
    L.append("| strike | shape | n | exp $/tr | WR | OOS total | OOS+ | WF | edge_capture_rel | "
             "null_pass | p_null | bh_survivor |")
    L.append("|---|---|--:|--:|--:|--:|:--:|--:|--:|:--:|--:|:--:|")
    for lbl in a2["strikes_tested"]:
        ssb = out["axis1_strike"]["cells"][lbl]
        p5c = a2["cells"][lbl]
        for tag, c in (("SS-B", ssb), ("P5-CHALLENGER", p5c)):
            m = c["metrics"]
            L.append(f"| {lbl} | {tag} | {m.get('n')} | ${m.get('expectancy')} | {m.get('wr')} | "
                     f"${m.get('oos_total')} | {m.get('oos_positive')} | {m.get('wf')} | "
                     f"{m.get('edge_capture_rel')} | {c['null_gate'].get('null_pass')} | "
                     f"{c['p_null']} | {c['bh_fdr_survivor']} |")
    L.append("")
    L.append("**Comparisons (P5-CHALLENGER vs SS-B, same strike, identical episodes):**")
    L.append("")
    for lbl, comp in a2["comparisons"].items():
        L.append(f"- **{comp['label']}**: delta_exp=${comp['delta_expectancy']}/tr "
                 f"(P5-challenger minus SS-B), beats_SSB={comp['candidate_beats_control']}, "
                 f"anchor_no_regression={comp['anchor_no_regression_op16']}, "
                 f"unstable_on_toggle={comp['unstable_on_open_audit']} "
                 f"(sensitivity delta=${comp['sensitivity_delta_expectancy_old_convention']}), "
                 f"**{comp['ship_or_wait']}**")
    L.append("")
    L.append(f"## BH-FDR (alpha={out['bh_fdr']['alpha']}, {out['bh_fdr']['n_comparisons']} cells compared)")
    L.append("")
    L.append(f"{out['bh_fdr']['n_survivors']}/{out['bh_fdr']['n_comparisons']} cells survive BH-FDR.")
    L.append("")
    L.append("## Ship vs wait")
    L.append("")
    sv = out["ship_vs_wait"]
    L.append(f"- **SHIP (clears OP-11 auto-ratify, stable on toggle):** {len(sv['ship_per_op11_auto_ratify'])}")
    for v in sv["ship_per_op11_auto_ratify"]:
        L.append(f"  - {v['label']}: delta_exp=${v['delta_expectancy']}/tr")
    L.append(f"- **WAIT — open audit chips ({', '.join(sv['open_audit_chips_blocking'])}) must land first "
             f"(verdict UNSTABLE on the fill-bar toggle):** {len(sv['wait_on_open_audit_chips'])}")
    for v in sv["wait_on_open_audit_chips"]:
        L.append(f"  - {v['label']}: delta_exp=${v['delta_expectancy']}/tr "
                 f"(sensitivity delta=${v['sensitivity_delta_expectancy_old_convention']})")
    L.append(f"- **WAIT — more evidence needed (does not clear auto-ratify):** {len(sv['wait_more_evidence'])}")
    for v in sv["wait_more_evidence"]:
        flags = v["auto_ratify_flags"]
        failed = [k for k, val in flags.items() if not val]
        if not v["candidate_beats_control"]:
            failed.append("candidate_does_not_beat_control")
        if not v["anchor_no_regression_op16"]:
            failed.append("anchor_regression_op16")
        L.append(f"  - {v['label']}: delta_exp=${v['delta_expectancy']}/tr, fails: {failed}")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
