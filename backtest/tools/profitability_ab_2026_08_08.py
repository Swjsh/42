"""profitability_ab_2026_08_08.py -- Runner execution of the FROZEN pre-registration
analysis/recommendations/prereg-profitability-2026-08-08.json (candidate BOLD2-QTY-NORMALIZE-V1).

Tests: does cutting bold-2's flat position size from qty=5 to target_qty in {3,4} contracts,
scoped to the 2026-07-18-onward ATM-strike-tier regime (git 718e0809), recover money from
bold-2's post-ship real-fills loss? Grid, gate battery, and population are FROZEN by the
prereg -- no knob not in that document, no post-hoc grid additions.

REAL FILLS ONLY (C1): population is reconstructed from automation/state/fills-ledger.jsonl via
exit_shape_parity_study.reconstruct_positions (arm='bold-2', engine-attributed real option
fills). NEVER lib/simulator_real.py.

DATA GAP FOUND + DOCUMENTED THIS SESSION (see `diagnose_walk_exit_manager_gap` below, run and
its real output captured in the JSON's `data_gap_diagnostic` field): the prereg's own
`cell_results_computed_this_session` used a linear premium*qty rescale, flagged in its own
`warnings` as an approximation needing a walk_exit_manager re-derivation before arming. Bold-2's
live entries are BEARISH_REJECTION_RIDE_THE_RIBBON / BULLISH_RECLAIM_RIDE_THE_RIBBON, whose real
observed stop fills (-47% to -53% of entry premium, not the -7%/-5% percent stops documented in
automation/state/aggressive/params.json) are consistent with stop_mode="structure" (v15.3
chart-stop-primary) having been active at entry -- confirmed empirically below: a
walk_exit_manager replay WITHOUT structure_stop_enabled/trigger_level (falls back to "premium"
mode, stop_pct=-0.20 from strategies.py#RIBBON_RIDE) reproduces -$128.00 on the 2026-07-23 735P
position vs the REAL fill -$305.00 -- a wrong stage (premium_stop fired 7 minutes post-entry,
not the real ~27-minute hold) and a wrong dollar figure. automation/state/aggressive/
current-position-bold.json's own schema confirms trigger_level is NOT a persisted field, and
automation/state/aggressive/decisions.jsonl (the only per-tick log with a `trigger` field) stops
at 2026-06-25 -- three weeks before the first post-ship trade. There is no historical
trigger_level available for any of the 6 post-ship (or 4 pre-ship) bold-2 positions.

RESOLUTION (not a silent workaround -- reuses production code for the one qty-dependent
mechanism, applied to REAL fill legs instead of re-deriving stage timing from bars this session
cannot faithfully model): exit_manager.ExitState.from_entry's stage TRIGGER conditions (premium
stop %, TP1 %, structure-stop crossing) are qty-INDEPENDENT -- qty only determines the
tp1_qty/runner_qty SPLIT (`tp1_qty = int(qty * tp1_qty_fraction)`, the literal production
formula, imported from em, not reimplemented) and the linear dollar-per-contract scaling. Each
of the 6 (or 10 all-time) real positions already tells us, from its OWN real exit_fills list
(reconstruct_positions' ground truth), whether the production exit core closed it in ONE leg
(pre-TP1 stop/structure-stop/time-stop -- sells the FULL open_qty regardless of qty, purely
linear rescale, exact) or TWO legs (TP1 partial + runner -- qty-rescale must re-run the REAL
int(qty*frac) split, which does NOT scale linearly). This is MORE faithful than the prereg's
flat linear rescale (it captures the production rounding truncation) and does not require the
missing trigger_level, because it never re-derives WHEN a leg fired -- only re-derives HOW MANY
CONTRACTS a real, already-observed leg would have carried at a smaller qty.

Usage: backtest/.venv/Scripts/python.exe backtest/tools/profitability_ab_2026_08_08.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "backtest" / "futures",
           REPO / "backtest" / "lib", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from exit_shape_parity_study import (  # noqa: E402
    fetch_option_bars, load_fleet_engine_fills, reconstruct_positions,
)
from battery import bh_fdr  # noqa: E402

OUT_PATH = REPO / "analysis" / "recommendations" / "profitability-ab-2026-08-08.json"
AGG_PARAMS_PATH = REPO / "automation" / "state" / "aggressive" / "params.json"

SHIP_DATE = "2026-07-18"  # git 718e0809, ATM strike-tier ship (inclusive)
GRID_TARGET_QTYS = (3, 4)          # frozen grid axis, PRIMARY (ship-eligible)
GRID_SCOPES = ("post_ship_only", "all_time_robustness_diagnostic_only")


def current_tp1_qty_fraction() -> float:
    """The LIVE production knob (automation/state/aggressive/params.json#tp1_qty_fraction),
    read fresh, never hardcoded -- this is what any FUTURE bold-2 trade under this rule would
    actually run under, which is the economically correct fraction to apply to a forward-looking
    sizing rule (not whatever fraction happened to be wired on a given historical date -- see
    module docstring)."""
    d = json.loads(AGG_PARAMS_PATH.read_text(encoding="utf-8"))
    return float(d["tp1_qty_fraction"])


def load_bold2_positions() -> list[dict]:
    """All real, engine-attributed bold-2 option positions (fills-ledger.jsonl), reconstructed
    via the repo's one definition of a position. Explicit non-default arms= call (module's own
    documented pattern for a new, separately-frozen study wanting current-day coverage)."""
    fills = load_fleet_engine_fills(arms=("bold-2",))
    return reconstruct_positions(fills)


def scope_positions(positions: list[dict], scope: str) -> list[dict]:
    if scope == "post_ship_only":
        return [p for p in positions if p["date_et"] >= SHIP_DATE]
    if scope == "all_time_robustness_diagnostic_only":
        return list(positions)
    raise ValueError(f"unknown scope {scope!r}")


def rescale_position_pnl(position: dict, target_qty: int, tp1_qty_fraction: float) -> float:
    """Re-derive ONE real position's dollar P&L at `target_qty` contracts, reusing the
    production tp1_qty=int(qty*frac) split rule for any position closed in >=2 real legs
    (TP1 + runner), and a pure linear scale for any position closed in exactly 1 real leg
    (pre-TP1 premium/structure/time stop sells the FULL open_qty regardless of qty -- see
    exit_manager.py's plan_exit_actions: those stages are SELL_ALL, not SELL tp1_qty).
    entry_price and each leg's real fill price are UNCHANGED (only the leg's QTY is
    re-derived) -- this is what a production exit_manager replay at target_qty would produce
    for these already-observed stage timings/prices."""
    entry_price = position["entry_price"]
    legs = sorted(position["exit_fills"], key=lambda f: f["ts_utc"])
    if len(legs) <= 1:
        fill_price = legs[0]["price"] if legs else entry_price
        return round((fill_price - entry_price) * target_qty * 100, 2)
    # >=2 legs: treat the FIRST (earliest) leg as the TP1 partial, everything after as the
    # runner (bold-2's real fills never show >2 legs; a 3rd+ leg's qty rides with the runner).
    tp1_leg = legs[0]
    runner_legs = legs[1:]
    tp1_qty = int(target_qty * tp1_qty_fraction)
    runner_qty = target_qty - tp1_qty
    pnl = (tp1_leg["price"] - entry_price) * tp1_qty * 100
    if runner_qty > 0 and runner_legs:
        # runner qty rides the LAST real runner leg's fill price (bold-2's real fills are
        # always exactly 2 legs for a TP1+runner position -- no 3rd-leg case observed).
        pnl += (runner_legs[-1]["price"] - entry_price) * runner_qty * 100
    return round(pnl, 2)


def _daily_baseline(positions: list[dict]) -> dict:
    out: dict = {}
    for p in positions:
        out.setdefault(p["date_et"], []).append(p)
    return out


def bootstrap_delta_pvalue(deltas: list[float], B: int = 2000, seed: int = 42) -> float:
    """One-sided PERCENTILE bootstrap on the mean per-position delta (rescaled - baseline):
    P(bootstrap mean <= 0), i.e. probability the recovery is non-positive under resampling
    of WHICH of the 6 (or 10) real positions we happened to observe. This is NOT
    battery.bootstrap_null_pvalue's random-entry null (that null doesn't apply here per the
    prereg's own null_hypothesis note -- a uniform per-trade rescale has no
    'which trades get the treatment' selection to randomize against). Deterministic seed."""
    if not deltas:
        return float("nan")
    arr = np.asarray(deltas, dtype=float)
    rng = np.random.default_rng(seed)
    boot_means = rng.choice(arr, size=(B, len(arr)), replace=True).mean(axis=1)
    p = (int(np.sum(boot_means <= 0)) + 1) / (B + 1)
    return float(p)


def run_cell(all_positions: list[dict], target_qty: int, scope: str,
             tp1_qty_fraction: float) -> dict:
    pos = scope_positions(all_positions, scope)
    n = len(pos)
    baseline_pnls = [round(p["actual_exit_pnl"], 2) for p in pos]
    rescaled_pnls = [rescale_position_pnl(p, target_qty, tp1_qty_fraction) for p in pos]
    deltas = [round(r - b, 2) for r, b in zip(rescaled_pnls, baseline_pnls)]

    baseline_net = round(sum(baseline_pnls), 2)
    rescaled_net = round(sum(rescaled_pnls), 2)
    delta_net = round(rescaled_net - baseline_net, 2)
    wins = sum(1 for b in baseline_pnls if b > 0)
    win_rate = round(wins / n, 4) if n else None

    # G2: drop best calendar day (by real baseline $), compare the DELTA ex-that-day.
    by_day = _daily_baseline(pos)
    day_totals = {d: round(sum(x["actual_exit_pnl"] for x in ps), 2) for d, ps in by_day.items()}
    best_day = max(day_totals, key=lambda d: day_totals[d]) if day_totals else None
    ex_best_pos = [p for p in pos if p["date_et"] != best_day]
    ex_best_baseline = round(sum(p["actual_exit_pnl"] for p in ex_best_pos), 2)
    ex_best_rescaled = round(sum(rescale_position_pnl(p, target_qty, tp1_qty_fraction)
                                  for p in ex_best_pos), 2)
    ex_best_delta = round(ex_best_rescaled - ex_best_baseline, 2)
    g2_pass = ex_best_delta > 0 if ex_best_pos else None

    # G4: subwindow stability -- split by date into two halves (n>=2 each to be evaluable).
    dates_sorted = sorted(day_totals.keys())
    half = len(dates_sorted) // 2
    half_a_dates, half_b_dates = set(dates_sorted[:max(half, 1)]), set(dates_sorted[max(half, 1):])
    half_a = [p for p in pos if p["date_et"] in half_a_dates]
    half_b = [p for p in pos if p["date_et"] in half_b_dates]

    def _half_stats(hp: list[dict]) -> dict:
        if len(hp) < 2:
            return {"n": len(hp), "evaluable": False}
        b = round(sum(x["actual_exit_pnl"] for x in hp), 2)
        r = round(sum(rescale_position_pnl(x, target_qty, tp1_qty_fraction) for x in hp), 2)
        return {"n": len(hp), "evaluable": True, "baseline": b, "rescaled": r,
                "delta": round(r - b, 2)}

    g4_half_a, g4_half_b = _half_stats(half_a), _half_stats(half_b)
    g4_evaluable = g4_half_a.get("evaluable") and g4_half_b.get("evaluable")

    # Per-account cut: safe-2 untouched by construction (bold-2-only rule).
    per_account = {"bold-2": {"delta": delta_net}, "safe-2": {"delta": 0.0}}
    g3_pass = delta_net >= 0 and per_account["safe-2"]["delta"] == 0.0

    bootstrap_p = bootstrap_delta_pvalue(deltas)

    g1_pass = delta_net > 0
    power_floor_pass = n >= 15

    return {
        "target_qty": target_qty, "scope": scope, "n": n,
        "n_changed_trades": n,
        "win_rate": win_rate,
        "baseline_net": baseline_net, "rescaled_net": rescaled_net, "delta_net": delta_net,
        "is_oos_split": {"IS_n": n, "OOS_n": 0,
                          "note": "OOS_forward (2026-08-10 onward) has not accrued yet -- shadow clock, not armed"},
        "drop_best_day": {"best_day": best_day, "baseline_ex_best_day": ex_best_baseline,
                           "rescaled_ex_best_day": ex_best_rescaled,
                           "delta_ex_best_day": ex_best_delta},
        "per_account_cuts": per_account,
        "subwindow_stability": {"half_a": g4_half_a, "half_b": g4_half_b,
                                 "evaluable": bool(g4_evaluable)},
        "per_position_deltas": deltas,
        "bootstrap_p_one_sided_delta_le_0": round(bootstrap_p, 4),
        "gates": {
            "G1_aggregate_positive_delta": bool(g1_pass),
            "G2_survives_drop_best_day": (bool(g2_pass) if g2_pass is not None else None),
            "G3_per_account_non_negative": bool(g3_pass),
            "G4_subwindow_stability_evaluable": bool(g4_evaluable),
            "power_floor_n_ge_15": bool(power_floor_pass),
        },
    }


def diagnose_walk_exit_manager_gap() -> dict:
    """Empirical proof (not assertion) of the trigger_level data gap: fetches real 1-min
    option bars for the FIRST post-ship exhibit (2026-07-23 735P) and drives it through the
    PRODUCTION exit_manager_walk.walk_exit_manager in premium-mode-only (the only mode
    reachable without a historical trigger_level), then diffs against the real fill. Run
    fresh every call -- no cached/hardcoded numbers. Network/data failures fail this
    diagnostic OPEN (returns a 'skipped' record), never silently claim success."""
    try:
        import datetime as dt
        import pandas as pd
        from exit_manager_walk import walk_exit_manager
    except ImportError as exc:  # pragma: no cover -- environment gap, not a math bug
        return {"ran": False, "reason": f"import failed: {exc}"}

    symbol, date_et = "SPY260723P00735000", "2026-07-23"
    entry_price, entry_et_str = 1.28, "2026-07-23 11:29:25"
    real_fill_pnl = -305.00
    try:
        bars = fetch_option_bars(symbol, date_et)
    except Exception as exc:  # noqa: BLE001 -- data fetch, fail open + disclose
        return {"ran": False, "reason": f"bar fetch failed: {exc}"}
    if not bars:
        return {"ran": False, "reason": "no bars returned (data unavailable this run)"}

    rows = [{"timestamp_et": pd.Timestamp(b["t"]).tz_convert("America/New_York").tz_localize(None),
             "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"]} for b in bars]
    opt_df = pd.DataFrame(rows)
    shape = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
             "profit_lock_mode": "trailing", "runner_target_pct": 99.0, "trail_pct": 0.15,
             "stop_mode": "structure", "catastrophe_stop_pct": -0.50}
    res = walk_exit_manager(
        symbol=symbol, side="P", entry_time_et=pd.Timestamp(entry_et_str),
        entry_premium=entry_price, qty=5, exit_shape=shape,
        structure_stop_enabled=False, trigger_level=None, strategy="gap_diagnostic",
        time_stop_et=dt.time(15, 40), opt_df=opt_df, ribbon_tick_df=None,
        five_min_spy_df=pd.DataFrame({"timestamp_et": [], "close": []}))
    return {
        "ran": True,
        "exhibit": symbol, "date_et": date_et,
        "premium_mode_fallback_pnl": res.dollar_pnl,
        "premium_mode_fallback_exit_reason": res.exit_reason,
        "real_fill_pnl": real_fill_pnl,
        "divergence": round(res.dollar_pnl - real_fill_pnl, 2),
        "conclusion": ("walk_exit_manager without a historical trigger_level does NOT "
                       "reproduce the real fill -- confirms structure-stop was live and its "
                       "trigger_level is not recoverable from any persisted state this "
                       "session found (current-position-bold.json has no trigger_level field; "
                       "decisions.jsonl's own `trigger` field stops 2026-06-25, before every "
                       "post-ship trade). Real-fills-stage rescale used instead (see module "
                       "docstring)."),
    }


def main() -> int:
    tp1_frac = current_tp1_qty_fraction()
    positions = load_bold2_positions()
    post_ship = scope_positions(positions, "post_ship_only")
    all_time = scope_positions(positions, "all_time_robustness_diagnostic_only")
    print(f"[profitability_ab] tp1_qty_fraction (live, {AGG_PARAMS_PATH.name}) = {tp1_frac}")
    print(f"[profitability_ab] bold-2 positions: post_ship_only n={len(post_ship)}, "
          f"all_time n={len(all_time)}")

    cells = {}
    for target_qty in GRID_TARGET_QTYS:
        for scope in GRID_SCOPES:
            key = f"qty{target_qty}_{scope}"
            cells[key] = run_cell(positions, target_qty, scope, tp1_frac)
            c = cells[key]
            print(f"  {key}: n={c['n']} baseline={c['baseline_net']} rescaled={c['rescaled_net']} "
                  f"delta={c['delta_net']} G1={c['gates']['G1_aggregate_positive_delta']} "
                  f"power_floor={c['gates']['power_floor_n_ge_15']}")

    # G5: BH-FDR across THIS candidate's ship-eligible cells only (family of 1 candidate, 2
    # cells) -- the prereg's full weekend cross-candidate family (bear-skip, safe-2-Wednesday
    # standdown) was not supplied to this Runner as executable artifacts, so that broader FDR
    # remains NOT RUN, disclosed explicitly, not silently narrowed and re-labeled as complete.
    ship_eligible_keys = [f"qty{q}_post_ship_only" for q in GRID_TARGET_QTYS]
    ship_eligible_pvals = [cells[k]["bootstrap_p_one_sided_delta_le_0"] for k in ship_eligible_keys]
    survive = bh_fdr(ship_eligible_pvals, alpha=0.10)
    g5_partial = {k: bool(s) for k, s in zip(ship_eligible_keys, survive)}
    for k in ship_eligible_keys:
        cells[k]["gates"]["G5_bh_fdr_q010_partial_family_of_1_candidate"] = g5_partial[k]

    power_floor_met = any(cells[k]["gates"]["power_floor_n_ge_15"] for k in ship_eligible_keys)
    ship_eligible_gates_all_pass = {
        k: all(v for gk, v in cells[k]["gates"].items() if v is not None
               and gk != "power_floor_n_ge_15")
        for k in ship_eligible_keys
    }

    if power_floor_met and all(ship_eligible_gates_all_pass.values()):
        verdict = "SHIP"
    else:
        verdict = "FREEZE-WITH-CLOCK"  # mechanical: power floor n>=15 not met (n=6 today)

    gap_diag = diagnose_walk_exit_manager_gap()

    core_book_14d_loss = -539.00  # from the task's own measured figure, quoted verbatim
    primary_cell = cells["qty3_post_ship_only"]
    what_if_last_14_days = round(core_book_14d_loss + primary_cell["delta_net"], 2)
    per_day_over_10_traded_days = round(primary_cell["delta_net"] / 10.0, 2)

    report = {
        "_doc": "Runner execution of prereg-profitability-2026-08-08.json (BOLD2-QTY-NORMALIZE-V1). "
                "REAL FILLS ONLY. Method = production tp1_qty rounding applied to REAL exit legs "
                "(see module docstring for why a full walk_exit_manager bar replay is blocked by a "
                "confirmed missing trigger_level history, and why this method is strictly more "
                "faithful than the prereg's own flagged linear-rescale approximation).",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "prereg_path": "analysis/recommendations/prereg-profitability-2026-08-08.json",
        "tp1_qty_fraction_used": tp1_frac,
        "ship_date_cutoff": SHIP_DATE,
        "population": {"post_ship_only_n": len(post_ship), "all_time_n": len(all_time)},
        "cells": cells,
        "data_gap_diagnostic": gap_diag,
        "verdict": verdict,
        "verdict_reasoning": (
            f"Mechanically computed from the gate ladder: power floor n>=15 changed trades is "
            f"{'MET' if power_floor_met else 'NOT MET'} (n={cells['qty3_post_ship_only']['n']} "
            f"today). Per the prereg's own battery, a candidate cannot SHIP without the power "
            f"floor regardless of how the other gates read -- verdict is FREEZE-WITH-CLOCK "
            f"unless n_changed_trades >= 15, matching the frozen prereg's own verdict. This "
            f"Runner independently reproduces that verdict from a MORE precise (rounding-aware, "
            f"not linear-approximated) recomputation, not merely restates it."
        ),
        "operator_bottom_line": {
            "core_book_14d_measured_loss": core_book_14d_loss,
            "primary_cell": "qty3_post_ship_only",
            "primary_cell_delta": primary_cell["delta_net"],
            "what_the_last_14_days_would_have_netted_under_this_rule": what_if_last_14_days,
            "implied_recovery_per_traded_day": per_day_over_10_traded_days,
            "still_net_negative": what_if_last_14_days < 0,
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[profitability_ab] verdict={verdict}")
    print(f"[profitability_ab] wrote {OUT_PATH}")
    print(json.dumps(report["operator_bottom_line"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
