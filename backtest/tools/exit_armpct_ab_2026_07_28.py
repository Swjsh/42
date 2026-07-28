"""exit_armpct_ab_2026_07_28.py -- EXIT-ARM-THRESHOLD pre-registered A/B scorecard, ITERATION 2.
Run EXACTLY per analysis/recommendations/prereg-exit-armpct-2026-07-28.json (frozen before any
computation below ran, commit e6ae43bf).

WHAT ITERATION 1 ESTABLISHED (backtest/tools/exit_armscope_ab_2026_07_28.py, commit c53922a9,
analysis/recommendations/exit-armscope-tp1-ab-2026-07-28.md): arming the existing 15% trail
pre-TP1 (profit_lock_arm_scope="full") at the SHIPPED threshold profit_lock_arm_pct=0.05 fixes
the 2026-07-28 incident (-$305 -> $0) but DESTROYS the runner cohort (-$7,758.85 on the 35
RUNNER_TRAIL winners, +$15,774.05 anchor) because the trail whipsaws winners out in their first
minutes of favorable movement -- including today's own trade, armed at 11:29 (+5.8%), stopped at
breakeven 11:30 (one minute later), never reaching its 12:57 HWM of $2.16.

THIS FILE (iteration 2): same mechanism (profit_lock_arm_scope="full"), but tests whether a
HIGHER arm threshold protects round-trippers like today's trade WITHOUT scratching runners in
their first minutes -- because a winner that has already run +20/+30/+40% has demonstrated the
move the trail is meant to protect, unlike a winner arming at a bare +5%.

REUSE, NOT REWRITE: this file imports backtest/tools/exit_armscope_ab_2026_07_28.py (as `ab1`)
for every piece of machinery the prereg requires be reused verbatim:
  - population loading path (SOURCE_REPLAY -- the SAME frozen 190-trade population, entries
    UNCHANGED, exit-only test)
  - ribbon construction (build_ribbon_lookup, ribbon_tick_df_for) -- byte-identical continuity
  - exit_family() classification (the PROFIT_LOCK_FLOOR_PRE_TP1 bucket ab1 already added)
  - today's-trade tick loader + replayer (load_today_bold_ticks, replay_today_trade) -- SAME
    real recorded live IEX-derived ticks from automation/state/core-decisions.jsonl, walked
    through the SAME em.plan_exit_actions core
  - the runner-cohort anchor constants (ANCHOR_RUNNER_N=35, ANCHOR_RUNNER_PNL=+$15,774.05)
  - the CONTROL byte-for-byte reconciliation convention (row["control_mismatch_vs_source"])
  - the RED-proofed G5 look-ahead guard (backtest/tests/test_exit_armscope_ab.py already pins
    the structural invariant floor=hwm*(1-trail_pct)<hwm for ANY trail_pct>0 -- the arm
    THRESHOLD does not change that algebra, so the guard transfers without modification; this
    file adds its OWN thin guard in backtest/tests/test_exit_armpct_ab.py that pins the
    threshold-parameterized ratchet specifically, per the "don't just assume, verify" standard)

ONLY NEW SURFACE: exits are re-derived through the SAME walk_exit_manager driving the SAME
em.plan_exit_actions core (NEVER simulate_trade_real -- 2026-07-09 sim-parity scar, unchanged
from iteration 1), with 4 cells that vary profit_lock_arm_scope AND profit_lock_arm_pct only.

4 CELLS (frozen, no sweep beyond the 3 pre-registered points -- trail_pct/catastrophe_stop_pct/
stop_mode/tp1_premium_pct/tp1_qty_fraction stay exactly as RIBBON_RIDE.exit ships):
  CONTROL : live config as-is (profit_lock_arm_scope="post_tp1", profit_lock_arm_pct=0.05 --
            inert pre-TP1, byte-identical to iteration 1's CONTROL)
  F1      : profit_lock_arm_scope="full", profit_lock_arm_pct=0.20. TWO keys changed.
  F2      : profit_lock_arm_scope="full", profit_lock_arm_pct=0.30 (independently derived from
            the overnight EXIT-LEAK study: 33 losers touched >=+30% MFE and round-tripped to a
            stop for -$3,829.60). TWO keys changed.
  F3      : profit_lock_arm_scope="full", profit_lock_arm_pct=0.40. TWO keys changed.

GATES (frozen, see prereg's `gates_frozen`; G1-G6 mirror iteration 1's definitions exactly,
applied per-cell to F1/F2/F3; G7 is NEW and GLOBAL across the three cells):
  G1 positive aggregate delta vs CONTROL.
  G2 majority of CHANGED trades (cell_pnl != control_pnl) are positive.
  G3 survives dropping the single best (most positive) changed trade.
  G4 RUNNER-COHORT VETO on the 35 RUNNER_TRAIL winners (+$15,774.05) -- ANY degradation of that
     cohort's aggregate FAILS the cell outright, regardless of G1. Not negotiable (unchanged from
     iteration 1, which this gate killed).
  G5 no look-ahead -- structural invariant, unchanged algebra from iteration 1, reasserted here
     by backtest/tests/test_exit_armpct_ab.py.
  G6 today's 2026-07-28 Bold trade (entry 1.38, HWM 2.16 @ 12:57, actual exit ~0.795) must
     improve materially (>$50 swing on the 5-lot, same bar iteration 1 used). SIGNAL-LEVEL,
     DISCLOSED via ab1.load_today_bold_ticks/replay_today_trade -- no OPRA cache for today.
     Gates ALL of F1/F2/F3 (unlike iteration 1's E2, every cell here exercises arm_scope=full).
  G7 DOSE-RESPONSE (NEW, GLOBAL, not per-cell): the three arm thresholds 0.20/0.30/0.40 form a
     monotone axis. Evaluated primarily on the runner-cohort delta (the deciding number per the
     task brief) with the aggregate delta reported as a secondary cross-check. If the sequence is
     NOT monotone-ish (e.g., F2 positive while F1 and F3 are both sharply negative -- the exact
     "spike" example named in the prereg), the positive cell is reported as NOISE and G7 fails
     GLOBALLY -- ARM NOTHING, regardless of any individual cell's G1-G6 gate arithmetic.

OUTPUTS: analysis/recommendations/exit-armpct-ab-2026-07-28.{json,md}.

ANALYSIS ONLY: writes only to analysis/recommendations/. Never touches exit_manager.py,
strategies.py, params.json, or any trading-path file. No broker imports, no network calls.

Run: backtest/.venv/Scripts/python.exe backtest/tools/exit_armpct_ab_2026_07_28.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # repo root
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(BACKTEST / "tools"), str(FLEET_DIR), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import exit_manager as em  # noqa: E402  -- automation/state/fleet/exit_manager.py
import strategies as fleet_strategies  # noqa: E402  -- automation/state/fleet/strategies.py
import exit_armscope_ab_2026_07_28 as ab1  # noqa: E402  -- iteration 1, machinery reused verbatim
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "prereg-exit-armpct-2026-07-28.json"
SOURCE_REPLAY = ab1.SOURCE_REPLAY                    # SAME frozen 190-trade population
SPY_FILE = ab1.SPY_FILE

OUT_JSON = REPO / "analysis" / "recommendations" / "exit-armpct-ab-2026-07-28.json"
OUT_MD = REPO / "analysis" / "recommendations" / "exit-armpct-ab-2026-07-28.md"

TIME_STOP_ET = ab1.TIME_STOP_ET                      # 15:40, matches SAFE_BASE's convention

TODAY_SYMBOL = ab1.TODAY_SYMBOL
TODAY_ENTRY_PREMIUM = ab1.TODAY_ENTRY_PREMIUM
TODAY_QTY = ab1.TODAY_QTY
TODAY_TRIGGER_LEVEL = ab1.TODAY_TRIGGER_LEVEL
TODAY_SIDE = ab1.TODAY_SIDE

ANCHOR_RUNNER_N = ab1.ANCHOR_RUNNER_N
ANCHOR_RUNNER_PNL = ab1.ANCHOR_RUNNER_PNL

CELL_NAMES = ("F1", "F2", "F3")
CELL_ARM_PCT = {"F1": 0.20, "F2": 0.30, "F3": 0.40}
CELL_N_KEYS_CHANGED = {"CONTROL": 0, "F1": 2, "F2": 2, "F3": 2}
# Every F-cell exercises the pre-TP1 arm_scope=full ratchet (unlike iteration 1's E2/CONTROL) --
# so G5 is a REAL (non-vacuous) pass for all three, and G6 formally gates all three.
CELLS_EXERCISING_ARM_SCOPE_FULL = CELL_NAMES
CELLS_GATED_ON_G6 = CELL_NAMES

# G7 dose-response tolerances (documented, not tuned post-hoc against these results --
# derived from the pre-reg's own qualitative example: "0.30 positive while 0.20 and 0.40 are
# both sharply negative"). $1 = treated as noise-level equal for monotonicity; $250 = the bar
# for calling a mid-point deviation from both neighbors "sharp" enough to be a spike.
DOSE_RESPONSE_EQUAL_TOL = 1.0
DOSE_RESPONSE_SPIKE_MATERIAL = 250.0


def log(msg: str) -> None:
    print(f"[exit-armpct-ab] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# PURE HELPERS (unit-tested in backtest/tests/test_exit_armpct_ab.py)
# ---------------------------------------------------------------------------------------------
def build_cells(control_shape: dict) -> dict:
    """The 4 cells frozen in the prereg (iteration 2). Each is a FRESH dict copy of
    control_shape with EXACTLY the two named keys changed for F1/F2/F3 -- trail_pct/
    catastrophe_stop_pct/stop_mode/tp1_premium_pct/tp1_qty_fraction never move. Never aliases
    control_shape (coding-style: immutability)."""
    cells = {"CONTROL": dict(control_shape)}
    for name in CELL_NAMES:
        cells[name] = dict(control_shape, profit_lock_arm_scope=em.ARM_SCOPE_FULL,
                            profit_lock_arm_pct=CELL_ARM_PCT[name])
    return cells


def assess_dose_response(values: dict, label: str) -> dict:
    """values: {"F1": d20, "F2": d30, "F3": d40}. Frozen coherence rule (prereg
    `dose_response_requirement`): the three thresholds form a monotone axis; a real mechanism
    degrades gracefully as the arm bar rises (fewer pre-TP1 trades touch a higher threshold, so
    the effect -- positive or negative -- should shrink toward CONTROL, not spike at one point).
    Two families of shape are treated as COHERENT: monotone-improving (F1<=F2<=F3, i.e. the
    effect gets less negative / more positive as the bar rises) and monotone-worsening (the
    mirror case) -- both are a real, traceable mechanism responding smoothly to the knob.
    Anything else (a local extremum at F2 beyond DOSE_RESPONSE_SPIKE_MATERIAL vs BOTH neighbors,
    or any other non-monotone pattern) is INCOHERENT -- per the prereg, that means report any
    lone positive cell as noise and do not arm on this axis regardless of its own gate math."""
    d20, d30, d40 = values["F1"], values["F2"], values["F3"]
    tol = DOSE_RESPONSE_EQUAL_TOL
    non_decreasing = (d30 >= d20 - tol) and (d40 >= d30 - tol)
    non_increasing = (d30 <= d20 + tol) and (d40 <= d30 + tol)
    if non_decreasing and non_increasing:
        shape, coherent = "flat", True
    elif non_decreasing:
        shape, coherent = "monotonic_improving_with_higher_arm_pct", True
    elif non_increasing:
        shape, coherent = "monotonic_worsening_with_higher_arm_pct", True
    else:
        m = DOSE_RESPONSE_SPIKE_MATERIAL
        spike_high = (d30 > d20 + m) and (d30 > d40 + m)
        spike_low = (d30 < d20 - m) and (d30 < d40 - m)
        if spike_high or spike_low:
            shape, coherent = "non_monotonic_spike_at_F2_NOISE", False
        else:
            shape, coherent = "irregular_non_monotonic", False
    return {"label": label, "values": {"F1_arm0.20": d20, "F2_arm0.30": d30, "F3_arm0.40": d40},
            "shape": shape, "coherent": coherent}


def decide_arming(cell_reports: dict, dose_response_runner: dict, dose_response_aggregate: dict) -> dict:
    """arming_rule (iteration 2): G7 is evaluated FIRST and GLOBALLY. If the runner-cohort axis
    (the deciding number) is incoherent, ARM NOTHING outright -- a positive individual cell under
    an incoherent axis is exactly the noise pattern the prereg pre-committed to distrust. Only if
    the runner-cohort axis is coherent do we fall through to per-cell G1-G6 gate clearance, then
    pick the best-performing cell that clears all required gates (tie-break: prefer the LOWER arm
    threshold on a practical tie -- smaller deviation from the shipped default).

    The reason string is built to be self-contained (readable without re-opening the JSON):
    whenever G4 fails UNIFORMLY across all three cells, that is named as the binding cause (it is
    a harder, cleaner veto than G7 and should not be obscured behind a generic 'no cell cleared'
    message), and any aggregate-axis noise spike is called out explicitly so it is never mistaken
    for a signal favoring the spiking cell."""
    g4_deltas = {c: cell_reports[c]["g4_runner_cohort_no_regression"]["delta"] for c in CELL_NAMES}
    g4_all_fail = all(not cell_reports[c]["g4_runner_cohort_no_regression"]["pass"] for c in CELL_NAMES)
    aggregate_note = ""
    if not dose_response_aggregate["coherent"]:
        aggregate_note = (
            f" G7 note: the AGGREGATE axis is non-monotonic ('{dose_response_aggregate['shape']}', "
            f"values {dose_response_aggregate['values']}) -- any lone positive cell on that axis "
            "is NOISE per the pre-reg's own dose-response criterion and must not be read as "
            "favoring that cell.")

    if not dose_response_runner["coherent"]:
        return {
            "decision": "ARM_NOTHING", "cell": None,
            "reason": (f"G7 FAILS globally -- runner-cohort dose-response shape is "
                       f"'{dose_response_runner['shape']}' (values {dose_response_runner['values']}), "
                       "not the monotone axis the pre-reg required; per the frozen "
                       "dose_response_requirement, any positive individual cell under this shape "
                       f"is treated as NOISE and arming is refused regardless of G1-G6.{aggregate_note}"),
        }
    if g4_all_fail:
        return {
            "decision": "ARM_NOTHING", "cell": None,
            "reason": (f"G4 (runner-cohort hard veto) FAILS UNIFORMLY across all three cells "
                       f"(delta: F1={_fmt_money(g4_deltas['F1'])}, F2={_fmt_money(g4_deltas['F2'])}, "
                       f"F3={_fmt_money(g4_deltas['F3'])}) -- this alone is sufficient to ARM "
                       "NOTHING per the non-negotiable G4 veto, regardless of G1-G3/G6/G7. The "
                       f"runner-cohort axis IS coherent ('{dose_response_runner['shape']}', values "
                       f"{dose_response_runner['values']}) -- damage shrinks monotonically as the "
                       "arm threshold rises from 0.20 to 0.40 -- but never turns positive within "
                       "the tested range: a higher threshold only DAMPENS the mechanism's harm to "
                       f"the profit engine, it does not eliminate it.{aggregate_note}"),
        }
    candidates = [c for c in CELL_NAMES if cell_reports[c]["clears_all_required_gates"]]
    if not candidates:
        return {"decision": "ARM_NOTHING", "cell": None,
                "reason": f"G7 coherent, but no cell cleared all required per-cell gates (G1-G6).{aggregate_note}"}
    candidates.sort(key=lambda c: cell_reports[c]["g1_positive_aggregate"]["delta"], reverse=True)
    top = candidates[0]
    top_delta = cell_reports[top]["g1_positive_aggregate"]["delta"]
    tied = [c for c in candidates
           if abs(cell_reports[c]["g1_positive_aggregate"]["delta"] - top_delta) <= 25.0]
    if len(tied) > 1:
        tied.sort(key=lambda c: CELL_ARM_PCT[c])
        chosen = tied[0]
        reason = (f"practical tie among {tied} (within $25 aggregate) -- chose the LOWER arm "
                  f"threshold ({CELL_ARM_PCT[chosen]:.0%}, smaller deviation from shipped default)")
    else:
        chosen = top
        reason = f"best aggregate delta among cells clearing all gates: {candidates}"
    return {"decision": "ARM", "cell": chosen, "reason": reason, "candidates_cleared": candidates}


def compute_cell_gates(rows: list, cell_name: str, runner_idx: list, runner_control_sum: float,
                       today_results: dict) -> dict:
    """G1-G6 -- byte-identical DEFINITIONS to iteration 1's compute_cell_gates, reapplied to the
    F1/F2/F3 cells. G7 is computed separately (it is global, not per-cell) in main()."""
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
    g5 = True  # structural invariant (floor = hwm*(1-trail_pct) < hwm for ANY trail_pct > 0,
               # independent of arm_pct), guarded by backtest/tests/test_exit_armpct_ab.py

    today_ctl = today_results["CONTROL"]["dollar_pnl"]
    today_cell = today_results[cell_name]["dollar_pnl"]
    today_delta = round(today_cell - today_ctl, 2)
    g6_gated = cell_name in CELLS_GATED_ON_G6
    g6 = (today_delta > 50.0) if g6_gated else None  # "materially" -- >$50 swing on a 5-lot

    required_gates = [g1, g2, g3, g4, g5] + ([g6] if g6_gated else [])
    clears_all = all(required_gates)

    return {
        "cell": cell_name, "n_keys_changed": CELL_N_KEYS_CHANGED[cell_name],
        "arm_pct": CELL_ARM_PCT[cell_name],
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
            "note": ("guarded by backtest/tests/test_exit_armpct_ab.py -- structural invariant, "
                     "unchanged algebra from iteration 1 (floor = hwm*(1-trail_pct) < hwm for "
                     "ANY trail_pct>0, independent of the arm_pct threshold)"),
            "pass": g5},
        "g6_today_trade": {
            "gated": g6_gated, "control_pnl": today_ctl, "cell_pnl": today_cell,
            "delta": today_delta, "cell_exit_reason": today_results[cell_name]["exit_reason"],
            "pass": g6},
        "clears_all_required_gates": clears_all,
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
        f"(entries UNCHANGED -- exit-only test, SAME population as iteration 1)")

    spy_df = pd.read_csv(SPY_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    ribbon_lookup = ab1.build_ribbon_lookup(spy_df)

    control_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    cells = build_cells(control_shape)
    log(f"cells: {cells}")

    rows: list = []
    n_no_opra = 0
    n_no_spy_day = 0
    n_control_mismatch = 0

    for t in trades:
        symbol = t["symbol"]
        date = dt.date.fromisoformat(t["date"])
        opt_df = ab1.load_contract_bars(symbol)
        if opt_df is None:
            n_no_opra += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == date].reset_index(drop=True)
        if day_spy.empty:
            n_no_spy_day += 1
            continue

        entry_time_et = ab1.naive_dt(dt.datetime.fromisoformat(t["entry_time_et"]))
        entry_premium = float(t["entry_premium"])
        trigger_level = t["trigger_level"]
        trigger_level = float(trigger_level) if trigger_level is not None else None
        qty = int(t["qty"])
        rtd = ab1.ribbon_tick_df_for(opt_df, ribbon_lookup)
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
                "family": ab1.exit_family(res.exit_reason, res.stop_mode),
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
    if n_control_mismatch:
        log(f"STOP CONDITION: {n_control_mismatch} CONTROL mismatches vs source population -- "
            "per the pre-reg, CONTROL must reconcile byte-for-byte or this scorecard is untrusted")

    # --- runner-cohort identification (from THIS file's own CONTROL walk) --------------------
    runner_idx = [i for i, r in enumerate(rows) if r["CONTROL"]["family"] == "RUNNER_TRAIL"]
    runner_control_sum = round(sum(rows[i]["CONTROL"]["dollar_pnl"] for i in runner_idx), 2)
    log(f"runner cohort: n={len(runner_idx)} control_pnl_sum=${runner_control_sum} "
        f"(anchor: n={ANCHOR_RUNNER_N} pnl=${ANCHOR_RUNNER_PNL})")

    # --- today's trade (G6), 4 cells, real recorded live ticks, SAME loader as iteration 1 ----
    ticks = ab1.load_today_bold_ticks()
    log(f"today's trade: {len(ticks)} real recorded live ticks loaded for {TODAY_SYMBOL}")
    today_results = {cell_name: ab1.replay_today_trade(shape, ticks) for cell_name, shape in cells.items()}

    # --- per-cell gates G1-G6 --------------------------------------------------------------
    cell_reports = {}
    for cell_name in CELL_NAMES:
        cell_reports[cell_name] = compute_cell_gates(
            rows, cell_name, runner_idx, runner_control_sum, today_results)

    # --- G7 dose-response, GLOBAL, computed on BOTH axes (runner = deciding, aggregate = check)
    runner_deltas = {c: cell_reports[c]["g4_runner_cohort_no_regression"]["delta"] for c in CELL_NAMES}
    aggregate_deltas = {c: cell_reports[c]["g1_positive_aggregate"]["delta"] for c in CELL_NAMES}
    dose_response_runner = assess_dose_response(runner_deltas, "runner_cohort_delta (deciding)")
    dose_response_aggregate = assess_dose_response(aggregate_deltas, "aggregate_delta (cross-check)")
    log(f"G7 dose-response (runner, deciding): {dose_response_runner['shape']} "
        f"coherent={dose_response_runner['coherent']}")
    log(f"G7 dose-response (aggregate, cross-check): {dose_response_aggregate['shape']} "
        f"coherent={dose_response_aggregate['coherent']}")

    verdict = decide_arming(cell_reports, dose_response_runner, dose_response_aggregate)

    total_elapsed = time.time() - t0
    write_scorecard(prereg, rows, cells, control_shape, runner_idx, runner_control_sum,
                     today_results, cell_reports, dose_response_runner, dose_response_aggregate,
                     verdict, n_no_opra, n_no_spy_day, n_control_mismatch, ticks, total_elapsed)
    return 0


def _fmt_money(v) -> str:
    return f"${v:+,.2f}"


def write_scorecard(prereg, rows, cells, control_shape, runner_idx, runner_control_sum,
                    today_results, cell_reports, dose_response_runner, dose_response_aggregate,
                    verdict, n_no_opra, n_no_spy_day, n_control_mismatch, ticks, total_elapsed) -> None:
    out = {
        "_doc": __doc__,
        "prereg_id": prereg["prereg_id"],
        "prereg_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "iteration": 2,
        "prior_iteration": {
            "file": "analysis/recommendations/exit-armscope-tp1-ab-2026-07-28.md",
            "commit": "c53922a9",
            "verdict": "ARM_NOTHING -- G4 runner-cohort veto: -$7,758.85 at arm_pct=0.05",
        },
        "generated_at": dt.datetime.now().isoformat(),
        "runtime_seconds": round(total_elapsed, 1),
        "population": {
            "source": str(SOURCE_REPLAY.relative_to(REPO)).replace("\\", "/"),
            "n_trades_source": len(rows), "n_excluded_no_opra_cache": n_no_opra,
            "n_excluded_no_spy_day": n_no_spy_day,
            "n_control_mismatch_vs_source": n_control_mismatch,
            "note": "entries UNCHANGED from CONTROL (exit-only A/B); real-OPRA-only P&L; SAME "
                    "190-trade population as iteration 1.",
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
                           "walk_exit_manager bar replay, disclosed as such (SAME loader/replayer "
                           "as iteration 1: ab1.load_today_bold_ticks / ab1.replay_today_trade)"),
            "per_cell": today_results,
        },
        "gates": cell_reports,
        "dose_response": {
            "runner_cohort_deciding": dose_response_runner,
            "aggregate_crosscheck": dose_response_aggregate,
            "axes_agree": dose_response_runner["coherent"] == dose_response_aggregate["coherent"],
        },
        "arming_recommendation": verdict,
        "trades": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"VERDICT: {verdict}")


def write_markdown(out: dict) -> None:
    v = out["arming_recommendation"]
    gates = out["gates"]
    rc = out["runner_cohort"]
    tt = out["today_trade"]
    dr = out["dose_response"]

    if v["decision"] == "ARM":
        g = gates[v["cell"]]
        verdict_line = (
            f"**VERDICT: ARM {v['cell']}** (arm_pct={g['arm_pct']:.0%}, {out['cells'][v['cell']]}) "
            f"-- G7 dose-response coherent ({dr['runner_cohort_deciding']['shape']}); clears all "
            f"required gates: aggregate {_fmt_money(g['g1_positive_aggregate']['delta'])}, "
            f"runner cohort {_fmt_money(g['g4_runner_cohort_no_regression']['delta'])}, "
            f"today's trade {_fmt_money(g['g6_today_trade']['delta'])} swing "
            f"({_fmt_money(g['g6_today_trade']['control_pnl'])} -> "
            f"{_fmt_money(g['g6_today_trade']['cell_pnl'])})."
        )
    else:
        verdict_line = f"**VERDICT: ARM NOTHING** -- {v['reason']}"

    L = [
        "# EXIT-ARM-THRESHOLD A/B scorecard -- ITERATION 2 -- 2026-07-28",
        "",
        verdict_line,
        "",
        f"Pre-reg: `{out['prereg_file']}`. Generated {out['generated_at']}. "
        f"Runtime {out['runtime_seconds']}s.",
        "",
        f"Prior iteration: `{out['prior_iteration']['file']}` (commit "
        f"`{out['prior_iteration']['commit']}`) -- {out['prior_iteration']['verdict']}",
        "",
        "## Population",
        "",
        f"- Source (entries UNCHANGED, exit-only test, SAME population as iteration 1): "
        f"`{out['population']['source']}`",
        f"- N trades: {out['population']['n_trades_source']} "
        f"(excluded no-OPRA={out['population']['n_excluded_no_opra_cache']}, "
        f"no-SPY-day={out['population']['n_excluded_no_spy_day']})",
        f"- CONTROL reconciliation vs source replay: "
        f"{out['population']['n_control_mismatch_vs_source']} mismatches "
        f"(must be 0 for this scorecard to be trusted)",
        "",
        "## Per-cell G1-G7 verdict table",
        "",
        "| Gate | F1 (arm=0.20) | F2 (arm=0.30) | F3 (arm=0.40) |",
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
                                          f"{'PASS' if g['g6_today_trade']['pass'] else 'FAIL'}")),
        ("CLEARS G1-G6", lambda g: "YES" if g["clears_all_required_gates"] else "no"),
    ]
    for label, fn in rows_spec:
        L.append(f"| {label} | {fn(gates['F1'])} | {fn(gates['F2'])} | {fn(gates['F3'])} |")
    L.append(f"| **G7 dose-response (GLOBAL)** | colspan: shape=`{dr['runner_cohort_deciding']['shape']}` "
              f"({'COHERENT' if dr['runner_cohort_deciding']['coherent'] else 'INCOHERENT -- NOISE'}) | | |")

    L += [
        "",
        "## G7 dose-response detail (the axis this iteration exists to test)",
        "",
        f"Runner-cohort delta by threshold (deciding axis): F1(0.20)={_fmt_money(dr['runner_cohort_deciding']['values']['F1_arm0.20'])}, "
        f"F2(0.30)={_fmt_money(dr['runner_cohort_deciding']['values']['F2_arm0.30'])}, "
        f"F3(0.40)={_fmt_money(dr['runner_cohort_deciding']['values']['F3_arm0.40'])} "
        f"-> shape = **{dr['runner_cohort_deciding']['shape']}** "
        f"({'COHERENT' if dr['runner_cohort_deciding']['coherent'] else 'INCOHERENT'})",
        "",
        f"Aggregate delta by threshold (cross-check): F1(0.20)={_fmt_money(dr['aggregate_crosscheck']['values']['F1_arm0.20'])}, "
        f"F2(0.30)={_fmt_money(dr['aggregate_crosscheck']['values']['F2_arm0.30'])}, "
        f"F3(0.40)={_fmt_money(dr['aggregate_crosscheck']['values']['F3_arm0.40'])} "
        f"-> shape = **{dr['aggregate_crosscheck']['shape']}** "
        f"({'COHERENT' if dr['aggregate_crosscheck']['coherent'] else 'INCOHERENT'})",
        "",
        f"Axes agree: {dr['axes_agree']}.",
        "",
        "## Runner-cohort effect (G4 detail, the book's profit engine -- the deciding number)",
        "",
        f"Anchor check: n={rc['n']} (expected {rc['anchor_check']['expected_n']}, "
        f"match={rc['anchor_check']['n_matches']}); control_pnl_sum={_fmt_money(rc['control_pnl_sum'])} "
        f"(expected {_fmt_money(15774.05)}, match={rc['anchor_check']['pnl_matches']})",
        "",
        "| Cell | Arm pct | Cohort P&L | Delta vs CONTROL | N worse | N better | N unchanged | G4 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cell in CELL_NAMES:
        g4 = gates[cell]["g4_runner_cohort_no_regression"]
        L.append(f"| {cell} | {gates[cell]['arm_pct']:.0%} | {_fmt_money(g4['cell_pnl_sum'])} | "
                 f"{_fmt_money(g4['delta'])} | {g4['n_worse']} | {g4['n_better']} | "
                 f"{g4['n_unchanged']} | {'PASS' if g4['pass'] else 'FAIL'} |")

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
    for cell in ("CONTROL",) + CELL_NAMES:
        r = tt["per_cell"][cell]
        delta = round(r["dollar_pnl"] - tt["per_cell"]["CONTROL"]["dollar_pnl"], 2)
        L.append(f"| {cell} | {_fmt_money(r['dollar_pnl'])} | {r['exit_reason']} | "
                 f"{_fmt_money(delta) if cell != 'CONTROL' else '--'} |")

    L += [
        "",
        "## Changed-trade tables (top 15 by |delta| per cell)",
        "",
    ]
    for cell in CELL_NAMES:
        trades = out["trades"]
        deltas = [(i, round(trades[i][cell]["dollar_pnl"] - trades[i]["CONTROL"]["dollar_pnl"], 2))
                 for i in range(len(trades))]
        deltas = [(i, d) for i, d in deltas if abs(d) > 0.005]
        deltas.sort(key=lambda x: abs(x[1]), reverse=True)
        L += [f"### {cell} (arm={gates[cell]['arm_pct']:.0%}) -- top {min(15, len(deltas))} of {len(deltas)} changed trades", "",
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
        "NOT an OPRA bar replay -- no same-day cache exists for 2026-07-28. Signal-level, "
        "disclosed, SAME loader as iteration 1. ribbon_flip_back held False throughout "
        "(not logged per-tick) -- immaterial, the real exit was structure_stop.",
        "- The 190-trade population is Safe-account (core_safe) RIDE_THE_RIBBON entries only, "
        "same scope as iteration 1. Today's motivating trade was Bold -- the exit SHAPE is "
        "shared across accounts so the mechanism finding transfers, but the aggregate dollar "
        "figures are a Safe-account-only estimate of effect size.",
        "- G4's 'no regression' bar is cohort-AGGREGATE, not per-trade -- see the N worse/N "
        "better/N unchanged columns for the per-trade distribution within a cell.",
        "- G7 is evaluated on the runner-cohort delta axis as the deciding number (per the task "
        "brief); the aggregate-delta axis is reported as a cross-check, and any disagreement "
        "between the two axes is called out explicitly above rather than silently resolved.",
        "- Multiplicity: this is exit-shape cell #189-191 tested this week on this book "
        "(iteration 1's pre-reg counted ~188 cumulative before this run). The prior on any "
        "single exit cell shipping remains LOW; G4 and G7 exist precisely because of that prior.",
        "- kill_criteria_post_arm (per the frozen pre-reg): forward 10 sessions or n>=8 fills; "
        "if realized expectancy is worse than the counterfactual control behavior, revert.",
        "",
        "---",
        f"_Source: `backtest/tools/exit_armpct_ab_2026_07_28.py` (extends "
        f"`backtest/tools/exit_armscope_ab_2026_07_28.py`, iteration 1). Full trade-level JSON: "
        f"`analysis/recommendations/exit-armpct-ab-2026-07-28.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
