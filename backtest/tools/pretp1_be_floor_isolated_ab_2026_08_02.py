"""pretp1_be_floor_isolated_ab_2026_08_02.py -- PRETP1-BE-FLOOR-ISOLATED pre-registered A/B
scorecard, ITERATION 4 of the exit-leak arm axis. Run EXACTLY per
analysis/recommendations/prereg-pretp1-be-floor-isolated-2026-08-02.json (frozen before any
computation below ran, commit `5dda3acf`, predates this runner).

WHY THIS EXISTS: iteration 3 (backtest/tools/be_floor_ab_2026_07_29.py) tried to test "a
breakeven floor instead of a trail" via profit_lock_mode="fixed" + profit_lock_arm_scope="full",
but that combination is CONFOUNDED -- "fixed" mode is read by BOTH the pre-TP1 arm branch AND
the post-TP1 runner branch, so it silently disables post-TP1 15%-trailing for any trade that
reaches TP1. 25 of 27 degraded runner-cohort trades in iteration 3 were THAT mechanism, not the
pre-TP1 whipsaw the hypothesis targeted. This iteration uses a NEW, structurally independent
knob shipped this same fire -- exit_manager.ExitState.pre_tp1_be_floor_arm_pct (commit
`ad675965`) -- that arms a BE-floor-ONLY scratch pre-TP1 while profit_lock_mode STAYS
"trailing" throughout, so the post-TP1 chandelier (the +$15,774.05/35-for-35 runner engine) is
PROVABLY untouched (see automation/state/fleet/test_exit_manager.py's
test_pre_tp1_isolated_floor_post_tp1_trailing_byte_identical_to_control).

METHOD (non-negotiable, reuses iteration 1's machinery via `import ... as ab1`, does not
rewrite it): same frozen 190-trade population (engine-fullhist-replay-2026-07-23.json), entries
UNCHANGED, exits re-derived ONLY through backtest/lib/exit_manager_walk.walk_exit_manager
driving the REAL plan_exit_actions core (never simulate_trade_real -- 2026-07-09 sim-parity
scar). entry+1 convention. Real-OPRA-only P&L, synthetic excluded. CONTROL must reconcile
byte-for-byte against the source population, exactly as iterations 1-3 required.

4 CELLS (frozen, no sweep beyond the 3 pre-registered arm_pct points, each a ONE-KEY change):
  CONTROL : live config as-is (pre_tp1_be_floor_arm_pct=None/absent)
  P1      : pre_tp1_be_floor_arm_pct=0.30
  P2      : pre_tp1_be_floor_arm_pct=0.50  (THE named prediction-to-beat cell)
  P3      : pre_tp1_be_floor_arm_pct=0.70
Dose-response axis ordering (ascending arm_pct): P1(0.30) < P2(0.50) < P3(0.70).

GATES (frozen, see prereg's `gates_frozen`): G1-G6, same rubric as iteration 3 (this file's own
numbering). G4 additionally reports, for every degraded runner-cohort trade, whether it is
mechanism (a) pretp1_roundtrip_to_entry (expected/possible) or (b) posttp1_lost_trailing_
protection -- which should be STRUCTURALLY IMPOSSIBLE this iteration (profit_lock_mode stays
"trailing" throughout, TP1 unconditionally resets state the same way regardless of this knob);
any occurrence of (b) is flagged as a knob-isolation red flag, not silently averaged in.

OUTPUTS: analysis/recommendations/pretp1-be-floor-isolated-ab-2026-08-02.{json,md}.

ANALYSIS ONLY: writes only to analysis/recommendations/. Never touches exit_manager.py,
strategies.py, params.json, accounts.json, or any trading-path file (exit_manager.py's own
mechanism change was already shipped + guard-tested + committed as a SEPARATE prior commit,
`ad675965`, before this pre-reg was even frozen). No broker imports, no network calls.

Run: backtest/.venv/Scripts/python.exe backtest/tools/pretp1_be_floor_isolated_ab_2026_08_02.py
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

PREREG = REPO / "analysis" / "recommendations" / "prereg-pretp1-be-floor-isolated-2026-08-02.json"
SOURCE_REPLAY = ab1.SOURCE_REPLAY                    # SAME frozen 190-trade population
SPY_FILE = ab1.SPY_FILE

OUT_JSON = REPO / "analysis" / "recommendations" / "pretp1-be-floor-isolated-ab-2026-08-02.json"
OUT_MD = REPO / "analysis" / "recommendations" / "pretp1-be-floor-isolated-ab-2026-08-02.md"

TIME_STOP_ET = ab1.TIME_STOP_ET                      # 15:40, matches SAFE_BASE's convention

TODAY_SYMBOL = ab1.TODAY_SYMBOL
TODAY_ENTRY_PREMIUM = ab1.TODAY_ENTRY_PREMIUM
TODAY_QTY = ab1.TODAY_QTY
TODAY_TRIGGER_LEVEL = ab1.TODAY_TRIGGER_LEVEL
TODAY_SIDE = ab1.TODAY_SIDE

ANCHOR_RUNNER_N = ab1.ANCHOR_RUNNER_N
ANCHOR_RUNNER_PNL = ab1.ANCHOR_RUNNER_PNL

# Dose-response axis, ASCENDING by arm_pct (alphabetical cell order matches this time).
CELL_NAMES = ("P1", "P2", "P3")
CELL_ARM_PCT = {"P1": 0.30, "P2": 0.50, "P3": 0.70}
DOSE_ORDER = ("P1", "P2", "P3")  # 0.30, 0.50, 0.70 ascending
CELL_N_KEYS_CHANGED = {"CONTROL": 0, "P1": 1, "P2": 1, "P3": 1}
CELLS_GATED_ON_G6 = CELL_NAMES

DOSE_RESPONSE_EQUAL_TOL = 1.0
DOSE_RESPONSE_SPIKE_MATERIAL = 250.0


def log(msg: str) -> None:
    print(f"[pretp1-be-floor-isolated-ab] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# PURE HELPERS (unit-tested in backtest/tests/test_pretp1_be_floor_isolated_ab.py)
# ---------------------------------------------------------------------------------------------
def build_cells(control_shape: dict) -> dict:
    """The 4 cells frozen in the prereg. Each P-cell is a FRESH dict copy of control_shape with
    EXACTLY 1 key changed (pre_tp1_be_floor_arm_pct) -- profit_lock_mode/profit_lock_arm_scope/
    trail_pct/tp1_premium_pct/tp1_qty_fraction/catastrophe_stop_pct/stop_mode/runner_target_pct
    never move. Never aliases control_shape (coding-style: immutability)."""
    cells = {"CONTROL": dict(control_shape)}
    for name in CELL_NAMES:
        cells[name] = dict(control_shape, pre_tp1_be_floor_arm_pct=CELL_ARM_PCT[name])
    return cells


def reached_tp1(legs: list) -> bool:
    """True if any leg of this walk was the TP1 partial fill (stage=='tp1')."""
    return any(getattr(leg, "stage", None) == "tp1" for leg in legs)


def runner_mechanism(exit_reason: str, cell_reached_tp1: bool) -> str:
    """Classifies WHY a cell's terminal exit differs from an 'ideal' trailing ride, for the G4
    per-trade breakdown. Only meaningful/reported for trades in the runner cohort. Mechanism
    (b) 'posttp1_lost_trailing_protection' should be STRUCTURALLY IMPOSSIBLE this iteration
    (profit_lock_mode stays 'trailing' throughout) -- reported anyway, as a knob-isolation
    red flag if it ever appears (never silently swallowed)."""
    r = exit_reason or ""
    if r.startswith("profit_lock_floor"):
        return "pretp1_roundtrip_to_entry"
    if cell_reached_tp1:
        return "posttp1_KNOB_ISOLATION_VIOLATION_lost_trailing_protection"
    if r.startswith("premium_stop"):
        return "pretp1_catastrophe_or_other_stop"
    if r.startswith("structure_stop"):
        return "pretp1_structure_stop"
    if r.startswith("time_stop"):
        return "pretp1_time_stop"
    if r.startswith("ribbon_flip"):
        return "pretp1_ribbon_flip"
    return "other:" + r


def assess_dose_response(low: float, mid: float, high: float, label: str) -> dict:
    """Same coherence rubric as iterations 2-3: monotone-improving / monotone-worsening / flat
    = COHERENT; a lone spike at the MIDDLE-ordered point beyond a material band vs both
    neighbors = INCOHERENT/NOISE; anything else non-monotone = irregular/INCOHERENT."""
    tol = DOSE_RESPONSE_EQUAL_TOL
    non_decreasing = (mid >= low - tol) and (high >= mid - tol)
    non_increasing = (mid <= low + tol) and (high <= mid + tol)
    if non_decreasing and non_increasing:
        shape, coherent = "flat", True
    elif non_decreasing:
        shape, coherent = "monotonic_improving_with_higher_arm_pct", True
    elif non_increasing:
        shape, coherent = "monotonic_worsening_with_higher_arm_pct", True
    else:
        m = DOSE_RESPONSE_SPIKE_MATERIAL
        spike_high = (mid > low + m) and (mid > high + m)
        spike_low = (mid < low - m) and (mid < high - m)
        if spike_high or spike_low:
            shape, coherent = "non_monotonic_spike_at_mid_NOISE", False
        else:
            shape, coherent = "irregular_non_monotonic", False
    return {"label": label, "values": {"P1_arm0.30": low, "P2_arm0.50": mid, "P3_arm0.70": high},
            "shape": shape, "coherent": coherent}


def decide_arming(cell_reports: dict, dose_response_runner: dict, dose_response_aggregate: dict) -> dict:
    """G5 is evaluated FIRST and GLOBALLY. If the runner-cohort axis is incoherent, ARM
    NOTHING outright. If G4 fails uniformly across all three cells, that is named as the
    binding cause. Otherwise pick the best-clearing cell, tie-break to the LOWER arm_pct."""
    g4_deltas = {c: cell_reports[c]["g4_runner_cohort_no_regression"]["delta"] for c in CELL_NAMES}
    g4_all_fail = all(not cell_reports[c]["g4_runner_cohort_no_regression"]["pass"] for c in CELL_NAMES)
    aggregate_note = ""
    if not dose_response_aggregate["coherent"]:
        aggregate_note = (
            f" G5 note: the AGGREGATE axis is non-monotonic ('{dose_response_aggregate['shape']}', "
            f"values {dose_response_aggregate['values']}) -- any lone positive cell on that axis "
            "is NOISE per the pre-reg's own dose-response criterion and must not be read as "
            "favoring that cell.")

    if not dose_response_runner["coherent"]:
        return {
            "decision": "ARM_NOTHING", "cell": None,
            "reason": (f"G5 FAILS globally -- runner-cohort dose-response shape is "
                       f"'{dose_response_runner['shape']}' (values {dose_response_runner['values']}), "
                       "not the monotone axis the pre-reg required; per the frozen "
                       "dose_response_requirement, any positive individual cell under this shape "
                       f"is treated as NOISE and arming is refused regardless of G1-G4/G6.{aggregate_note}"),
        }
    if g4_all_fail:
        return {
            "decision": "ARM_NOTHING", "cell": None,
            "reason": (f"G4 (runner-cohort hard veto) FAILS UNIFORMLY across all three cells "
                       f"(delta: P1={_fmt_money(g4_deltas['P1'])}, P2={_fmt_money(g4_deltas['P2'])}, "
                       f"P3={_fmt_money(g4_deltas['P3'])}) -- this alone is sufficient to ARM "
                       "NOTHING per the non-negotiable G4 veto, regardless of G1-G3/G6/G5. The "
                       f"runner-cohort axis IS coherent ('{dose_response_runner['shape']}', values "
                       f"{dose_response_runner['values']}).{aggregate_note}"),
        }
    candidates = [c for c in CELL_NAMES if cell_reports[c]["clears_all_required_gates"]]
    if not candidates:
        return {"decision": "ARM_NOTHING", "cell": None,
                "reason": f"G5 coherent, but no cell cleared all required per-cell gates (G1-G4,G6).{aggregate_note}"}
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
    """G1-G4,G6 -- per-cell. G5 (dose-response) is computed separately in main() (global)."""
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

    mechanism_counts: dict = {}
    mechanism_trades: list = []
    knob_isolation_violations = 0
    for i in runner_idx:
        cpnl = rows[i][cell_name]["dollar_pnl"]
        ctlpnl = rows[i]["CONTROL"]["dollar_pnl"]
        if cpnl >= ctlpnl - 0.005:
            continue  # not degraded -- not part of the breakdown
        mech = rows[i][cell_name]["runner_mechanism"]
        mechanism_counts[mech] = mechanism_counts.get(mech, 0) + 1
        if "KNOB_ISOLATION_VIOLATION" in mech:
            knob_isolation_violations += 1
        mechanism_trades.append({"date": rows[i]["date"], "symbol": rows[i]["symbol"],
                                 "control_pnl": ctlpnl, "cell_pnl": cpnl,
                                 "delta": round(cpnl - ctlpnl, 2), "mechanism": mech,
                                 "exit_reason": rows[i][cell_name]["exit_reason"]})

    today_ctl = today_results["CONTROL"]["dollar_pnl"]
    today_cell = today_results[cell_name]["dollar_pnl"]
    today_delta = round(today_cell - today_ctl, 2)
    g6_gated = cell_name in CELLS_GATED_ON_G6
    g6 = (today_delta > 50.0) if g6_gated else None  # "materially" -- >$50 swing on a 5-lot

    required_gates = [g1, g2, g3, g4] + ([g6] if g6_gated else [])
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
            "n_unchanged": n_runner_unchanged, "pass": g4,
            "mechanism_breakdown_of_worse_trades": mechanism_counts,
            "knob_isolation_violations": knob_isolation_violations,
            "worse_trades_detail": sorted(mechanism_trades, key=lambda t: t["delta"]),
        },
        "g6_today_trade": {
            "gated": g6_gated, "control_pnl": today_ctl, "cell_pnl": today_cell,
            "delta": today_delta, "cell_exit_reason": today_results[cell_name]["exit_reason"],
            "pass": g6},
        "clears_all_required_gates": clears_all,
    }


def _fmt_money(v) -> str:
    return f"${v:+,.2f}"


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
        f"(entries UNCHANGED -- exit-only test, SAME population as iterations 1-3)")

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
            cell_reached_tp1 = reached_tp1(res.legs)
            row[cell_name] = {
                "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
                "resolved_stop_mode": res.stop_mode, "hold_minutes": res.hold_minutes,
                "family": ab1.exit_family(res.exit_reason, res.stop_mode),
                "reached_tp1": cell_reached_tp1,
                "runner_mechanism": runner_mechanism(res.exit_reason, cell_reached_tp1),
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

    runner_idx = [i for i, r in enumerate(rows) if r["CONTROL"]["family"] == "RUNNER_TRAIL"]
    runner_control_sum = round(sum(rows[i]["CONTROL"]["dollar_pnl"] for i in runner_idx), 2)
    log(f"runner cohort: n={len(runner_idx)} control_pnl_sum=${runner_control_sum} "
        f"(anchor: n={ANCHOR_RUNNER_N} pnl=${ANCHOR_RUNNER_PNL})")

    ticks = ab1.load_today_bold_ticks()
    log(f"today's trade: {len(ticks)} real recorded live ticks loaded for {TODAY_SYMBOL}")
    today_results = {cell_name: ab1.replay_today_trade(shape, ticks) for cell_name, shape in cells.items()}

    cell_reports = {}
    for cell_name in CELL_NAMES:
        cell_reports[cell_name] = compute_cell_gates(
            rows, cell_name, runner_idx, runner_control_sum, today_results)

    runner_deltas = {c: cell_reports[c]["g4_runner_cohort_no_regression"]["delta"] for c in CELL_NAMES}
    aggregate_deltas = {c: cell_reports[c]["g1_positive_aggregate"]["delta"] for c in CELL_NAMES}
    dose_response_runner = assess_dose_response(
        runner_deltas["P1"], runner_deltas["P2"], runner_deltas["P3"], "runner_cohort_delta (deciding)")
    dose_response_aggregate = assess_dose_response(
        aggregate_deltas["P1"], aggregate_deltas["P2"], aggregate_deltas["P3"], "aggregate_delta (cross-check)")
    log(f"G5 dose-response (runner, deciding): {dose_response_runner['shape']} "
        f"coherent={dose_response_runner['coherent']}")
    log(f"G5 dose-response (aggregate, cross-check): {dose_response_aggregate['shape']} "
        f"coherent={dose_response_aggregate['coherent']}")

    total_isolation_violations = sum(
        cell_reports[c]["g4_runner_cohort_no_regression"]["knob_isolation_violations"]
        for c in CELL_NAMES)
    if total_isolation_violations:
        log(f"*** KNOB ISOLATION VIOLATION: {total_isolation_violations} runner-cohort trades "
            "showed posttp1_lost_trailing_protection under a knob that should be structurally "
            "incapable of causing it -- INVESTIGATE BEFORE TRUSTING THIS SCORECARD ***")

    verdict = decide_arming(cell_reports, dose_response_runner, dose_response_aggregate)

    total_elapsed = time.time() - t0
    write_scorecard(prereg, rows, cells, control_shape, runner_idx, runner_control_sum,
                     today_results, cell_reports, dose_response_runner, dose_response_aggregate,
                     verdict, n_no_opra, n_no_spy_day, n_control_mismatch, ticks, total_elapsed,
                     total_isolation_violations)
    return 0


def write_scorecard(prereg, rows, cells, control_shape, runner_idx, runner_control_sum,
                    today_results, cell_reports, dose_response_runner, dose_response_aggregate,
                    verdict, n_no_opra, n_no_spy_day, n_control_mismatch, ticks, total_elapsed,
                    total_isolation_violations) -> None:
    out = {
        "_doc": __doc__,
        "prereg_id": prereg["prereg_id"],
        "prereg_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "iteration": 4,
        "prior_iterations": [
            {"file": "analysis/recommendations/exit-armscope-tp1-ab-2026-07-28.md",
             "verdict": "ARM_NOTHING -- G4 runner-cohort veto: -$7,758.85 at arm_pct=0.05 (trailing mode)"},
            {"file": "analysis/recommendations/exit-armpct-ab-2026-07-28.md",
             "verdict": "ARM_NOTHING -- G4 fails uniformly 0.20/0.30/0.40 (trailing mode); "
                        "damage shrinks monotonically but never turns positive"},
            {"file": "analysis/recommendations/be-floor-ab-2026-07-29.md",
             "verdict": "ARM_NOTHING -- CONFOUNDED: 'fixed' mode silently disabled post-TP1 "
                        "trailing (25/27 degraded-trade mechanism), not a clean pre-TP1-only test"},
        ],
        "generated_at": dt.datetime.now().isoformat(),
        "runtime_seconds": round(total_elapsed, 1),
        "total_knob_isolation_violations": total_isolation_violations,
        "population": {
            "source": str(SOURCE_REPLAY.relative_to(REPO)).replace("\\", "/"),
            "n_trades_source": len(rows), "n_excluded_no_opra_cache": n_no_opra,
            "n_excluded_no_spy_day": n_no_spy_day,
            "n_control_mismatch_vs_source": n_control_mismatch,
            "note": "entries UNCHANGED from CONTROL (exit-only A/B); real-OPRA-only P&L; SAME "
                    "190-trade population as iterations 1-3.",
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
                           "as iterations 1-3: ab1.load_today_bold_ticks / ab1.replay_today_trade)"),
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
            f"**VERDICT: ARM {v['cell']}** (arm_pct={g['arm_pct']:.0%}, isolated pre-TP1 BE "
            f"floor, {out['cells'][v['cell']]}) -- G5 dose-response coherent "
            f"({dr['runner_cohort_deciding']['shape']}); clears all required gates: aggregate "
            f"{_fmt_money(g['g1_positive_aggregate']['delta'])}, runner cohort "
            f"{_fmt_money(g['g4_runner_cohort_no_regression']['delta'])}, today's trade "
            f"{_fmt_money(g['g6_today_trade']['delta'])} swing "
            f"({_fmt_money(g['g6_today_trade']['control_pnl'])} -> "
            f"{_fmt_money(g['g6_today_trade']['cell_pnl'])})."
        )
    else:
        verdict_line = f"**VERDICT: ARM NOTHING** -- {v['reason']}"

    L = [
        "# PRETP1-BE-FLOOR-ISOLATED A/B scorecard -- ITERATION 4 -- 2026-08-02",
        "",
        verdict_line,
        "",
        f"Pre-reg: `{out['prereg_file']}`. Generated {out['generated_at']}. "
        f"Runtime {out['runtime_seconds']}s.",
        "",
        f"**Knob-isolation check: {out['total_knob_isolation_violations']} violations** "
        "(should be 0 -- profit_lock_mode stays 'trailing' throughout this iteration, so "
        "no runner-cohort trade should ever show mechanism (b) posttp1_lost_trailing_protection; "
        "a nonzero count here is a red flag on the knob's isolation, checked before trusting "
        "the rest of this scorecard).",
        "",
        "Prior iterations (all ARM_NOTHING):",
    ]
    for pi in out["prior_iterations"]:
        L.append(f"- `{pi['file']}` -- {pi['verdict']}")
    L += [
        "",
        "## Population",
        "",
        f"- Source (entries UNCHANGED, exit-only test, SAME population as iterations 1-3): "
        f"`{out['population']['source']}`",
        f"- N trades: {out['population']['n_trades_source']} "
        f"(excluded no-OPRA={out['population']['n_excluded_no_opra_cache']}, "
        f"no-SPY-day={out['population']['n_excluded_no_spy_day']})",
        f"- CONTROL reconciliation vs source replay: "
        f"{out['population']['n_control_mismatch_vs_source']} mismatches "
        f"(must be 0 for this scorecard to be trusted)",
        "",
        "## Per-cell G1-G6 verdict table",
        "",
        "| Gate | P1 (arm=0.30) | P2 (arm=0.50) | P3 (arm=0.70) |",
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
        ("G6 today's trade", lambda g: (f"{_fmt_money(g['g6_today_trade']['delta'])} "
                                          f"{'PASS' if g['g6_today_trade']['pass'] else 'FAIL'}")),
        ("CLEARS G1-G4,G6", lambda g: "YES" if g["clears_all_required_gates"] else "no"),
    ]
    for label, fn in rows_spec:
        L.append(f"| {label} | {fn(gates['P1'])} | {fn(gates['P2'])} | {fn(gates['P3'])} |")
    L.append(f"| **G5 dose-response (GLOBAL)** | colspan: shape=`{dr['runner_cohort_deciding']['shape']}` "
              f"({'COHERENT' if dr['runner_cohort_deciding']['coherent'] else 'INCOHERENT -- NOISE'}) | | |")

    L += [
        "",
        "## G5 dose-response detail (ascending arm_pct: P1 0.30 < P2 0.50 < P3 0.70)",
        "",
        f"Runner-cohort delta by threshold (deciding axis): "
        f"P1(0.30)={_fmt_money(dr['runner_cohort_deciding']['values']['P1_arm0.30'])}, "
        f"P2(0.50)={_fmt_money(dr['runner_cohort_deciding']['values']['P2_arm0.50'])}, "
        f"P3(0.70)={_fmt_money(dr['runner_cohort_deciding']['values']['P3_arm0.70'])} "
        f"-> shape = **{dr['runner_cohort_deciding']['shape']}** "
        f"({'COHERENT' if dr['runner_cohort_deciding']['coherent'] else 'INCOHERENT'})",
        "",
        f"Aggregate delta by threshold (cross-check): "
        f"P1(0.30)={_fmt_money(dr['aggregate_crosscheck']['values']['P1_arm0.30'])}, "
        f"P2(0.50)={_fmt_money(dr['aggregate_crosscheck']['values']['P2_arm0.50'])}, "
        f"P3(0.70)={_fmt_money(dr['aggregate_crosscheck']['values']['P3_arm0.70'])} "
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
        "### G4 mechanism breakdown of DEGRADED runner-cohort trades",
        "",
        "Mechanism (b) posttp1_lost_trailing_protection should be STRUCTURALLY IMPOSSIBLE this "
        "iteration (profit_lock_mode stays 'trailing' throughout) -- flagged loudly, not "
        "silently averaged in, if it ever appears.",
        "",
        "| Cell | pretp1_roundtrip_to_entry | KNOB ISOLATION VIOLATIONS (should be 0) | other |",
        "|---|---|---|---|",
    ]
    for cell in CELL_NAMES:
        mb = gates[cell]["g4_runner_cohort_no_regression"]["mechanism_breakdown_of_worse_trades"]
        a = mb.get("pretp1_roundtrip_to_entry", 0)
        viol = gates[cell]["g4_runner_cohort_no_regression"]["knob_isolation_violations"]
        other = sum(v for k, v in mb.items()
                    if k not in ("pretp1_roundtrip_to_entry",) and "KNOB_ISOLATION_VIOLATION" not in k)
        L.append(f"| {cell} | {a} | {viol} | {other} |")

    L += [
        "",
        "### Worst-degraded runner-cohort trades (top 10 by |delta|, any cell)",
        "",
        "| Cell | Date | Symbol | Mechanism | CONTROL | Cell | Delta |",
        "|---|---|---|---|---|---|---|",
    ]
    all_worse = []
    for cell in CELL_NAMES:
        for wt in gates[cell]["g4_runner_cohort_no_regression"]["worse_trades_detail"]:
            all_worse.append((cell, wt))
    all_worse.sort(key=lambda cw: cw[1]["delta"])
    for cell, wt in all_worse[:10]:
        L.append(f"| {cell} | {wt['date']} | {wt['symbol']} | {wt['mechanism']} | "
                 f"{_fmt_money(wt['control_pnl'])} | {_fmt_money(wt['cell_pnl'])} | {_fmt_money(wt['delta'])} |")

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
        "- This is a STRUCTURALLY CLEANER test than iteration 3 -- pre_tp1_be_floor_arm_pct is "
        "a NEW, independent knob (never sets profit_lock_armed, never touches profit_lock_mode) "
        "-- but the mechanism-isolation claim is itself verified empirically above (knob "
        "isolation violations, should be 0), not just assumed from the code read.",
        "- G6 (today's trade) is reconstructed from real live tick data (core-decisions.jsonl), "
        "NOT an OPRA bar replay -- no same-day cache exists for 2026-07-28. Signal-level, "
        "disclosed, SAME loader as iterations 1-3. ribbon_flip_back held False throughout "
        "(not logged per-tick) -- immaterial, the real exit was structure_stop.",
        "- The 190-trade population is Safe-account (core_safe) RIDE_THE_RIBBON entries only, "
        "same scope as iterations 1-3. Today's motivating trade was Bold -- the exit SHAPE is "
        "shared across accounts so the mechanism finding transfers, but the aggregate dollar "
        "figures are a Safe-account-only estimate of effect size.",
        "- G4's 'no regression' bar is cohort-AGGREGATE, not per-trade -- see the N worse/N "
        "better/N unchanged columns for the per-trade distribution within a cell, and the "
        "mechanism breakdown table for WHY each worse trade degraded.",
        "- G5 is evaluated on the runner-cohort delta axis as the deciding number (per the task "
        "brief); the aggregate-delta axis is reported as a cross-check.",
        "- Multiplicity: this is the FOURTH arm-axis cell tested on this book this week "
        "(iterations 1-3 counted a large cumulative cell count before this run). If this "
        "iteration also fails, the profit-lock-mechanism axis is exhausted per the pre-reg's "
        "own arming_rule -- the queue item's next candidate is THETA-NOT-GIVEBACK "
        "(hold-time/underlying-stall class), not another profit-lock variant.",
        "- kill_criteria_post_arm (per the frozen pre-reg): forward 10 sessions or n>=8 fills; "
        "if realized expectancy is worse than the counterfactual control behavior, revert.",
        "",
        "---",
        f"_Source: `backtest/tools/pretp1_be_floor_isolated_ab_2026_08_02.py` (extends "
        f"`backtest/tools/exit_armscope_ab_2026_07_28.py`, iteration 1; gate pattern reused "
        f"from `backtest/tools/be_floor_ab_2026_07_29.py`, iteration 3). Full trade-level JSON: "
        f"`analysis/recommendations/pretp1-be-floor-isolated-ab-2026-08-02.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
