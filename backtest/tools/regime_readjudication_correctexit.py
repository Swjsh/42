"""regime_readjudication_correctexit.py -- GOAL-REPLAY-TODAY-GREEN ITERATION 7 (rigor pass).

WHY: iteration 6 (EXIT-MANAGER-REPLAY-HARNESS) found every sim-based ribbon_ride exit study
in this codebase, including `elite_bear_level_reject_gate_ab.py` (the source of iteration-5's
regime-conditioned re-adjudication cohort for lever L1), reads exit knobs from
`simulate_trade_real`'s params.json TOP-LEVEL keys (tp1_premium_pct=0.5,
v15_profit_lock_mode="fixed", runner_max_premium_pct=2.5) instead of the REAL exit_manager's
`automation/state/fleet/strategies.py#RIBBON_RIDE.exit` shape (tp1_premium_pct=1.0,
profit_lock_mode="trailing" chandelier arm+5%/trail15%, runner_target_pct=99.0,
stop_mode="structure"). The iteration-5 "0/5 flip, recency-overfitting" verdict was therefore
computed, for L1 specifically, on a KNOWN-WRONG exit model that breakeven-zeros winners the
real engine rides. This module re-derives L1's removed-cohort P&L under the CORRECT exit
shape (`backtest/lib/exit_manager_walk.py`, built iteration 6 -- drives the REAL
`exit_manager.plan_exit_actions` decision core) and re-runs the UNCHANGED iteration-5
regime-conditioned validator to check whether the verdict survives.

SCOPE, per a code-trace audit of the other 4 parked candidates done THIS iteration: ONLY
elite-bear L1 is affected by the "wrong exit shape" bug. Traced each of the other 3
independently-scored candidates' own replay engine (fleet-strike-risky3 has no separate
cohort -- it inherits bold-strike-ATM's verdict by proxy, per WF-GATE-METHODOLOGY-2026-07-16.md's
own disposition, unchanged this iteration):

  * bold_strike_axis_deltawf.py -> bold_strike_axis_ab.py's SS_B_SHAPE (=
    structure_stop_study.SS_B_SHAPE) via strike_ab_convention_reconciliation.replay_generic,
    which calls automation/state/fleet/exit_manager.plan_exit_actions DIRECTLY -- the SAME
    real decision core exit_manager_walk.py drives, an earlier (2026-07-09), independently
    -built parallel harness, NOT simulate_trade_real. Materiality check (this iteration, via
    exit_manager.py:209-223 ExitState.from_entry): SS_B_SHAPE's premium_stop_pct=-0.50 is
    INERT whenever stop_mode resolves to "structure" (the dominant case for trigger_level
    -anchored setups) -- from_entry HARD-OVERRIDES premium_stop_pct with catastrophe_stop_pct
    in structure mode, and SS_B_SHAPE's implicit catastrophe_stop_pct (key absent -> global
    CATASTROPHE_STOP_PCT=-0.50) byte-matches the live shape's explicit catastrophe_stop_pct=
    -0.50. tp1_premium_pct (1.0), tp1_qty_fraction (0.667), profit_lock_mode ("trailing"),
    trail_pct (0.15) all match the live shape exactly. Only divergence: runner_target_pct 9.9
    vs live's 99.0 (both thresholds are >900%/session -- unreachable in 0DTE, provably
    immaterial) and the TRENDLINE-tier (no trigger_level) premium-mode fallback stop -50% vs
    live's -20% (a narrower, already-disclosed gap in ribbon_ride_strike_exit_ab.py's own
    docstring, orthogonal to this goal's flagged bug). NOT re-run this iteration.
  * zone_rejection_band_study.py's own docstring states it directly: "REPLAY reuses
    structure_stop_study.SS_B_SHAPE / replay_structure_aware ... exactly the SS-B lineage
    every study this week used" -- same lineage, same materiality argument as bold-strike
    ATM. NOT re-run this iteration.
  * pong_resting_limit_study.py's replay_exit() calls plan_exit_actions DIRECTLY (its own
    inline tick loop, never reads params.json top-level keys) with a bespoke 8-cell exit
    grid built for its OWN entry-timing A/B; BOTH control and candidate sides of its paired
    delta share the IDENTICAL exit mechanism per cell, so any shape divergence from the live
    production shape is common-mode and cancels in the delta -- the exact reasoning
    exit_variant_ab.py's own docstring uses to justify its delta-form WF. NOT re-run this
    iteration.

Re-running those 3 would not isolate "exit model" as the ONLY changed variable (the task's
explicit constraint) -- it would mean discarding each study's own established, independently
-built plan_exit_actions-driven replay engine for exit_manager_walk, a materially larger and
different change than a shape correction. SIM-EXIT-SHAPE-PARITY-AUDIT (filed separately, see
queue.md) should still formally re-verify these 3 outside this goal's scope.

METHOD for L1: reuse elite_bear_level_reject_gate_ab.py's OWN, UNCHANGED
run_backtest(**SAFE_BASE) call over the SAME full window (2025-01-02..2026-07-08) and the
SAME split_control_candidate(trades) predicate (ELITE-tier PUT entries) -- entry detection
and the block predicate are UNCHANGED, byte-identical to iteration 4/5. Only each removed
trade's dollar_pnl is re-derived, via exit_manager_walk.walk_exit_manager, under the REAL,
byte-exact automation/state/fleet/strategies.py#RIBBON_RIDE.exit.to_dict() shape
(structure_stop_enabled=True) instead of simulate_trade_real's params.json-top-level-keys
shape (profit_lock_mode="fixed").

CROSS-CHECK (fable-too-good discipline, task step 4): the SAME run_backtest(**SAFE_BASE)
call, same window, is ALSO exit_variant_ab.py's own entry population (it imports SAFE_BASE
from elite_bear_level_reject_gate_ab.py directly) -- its saved
analysis/recommendations/exit-variant-ab-wider-trail25-2026-07-17.json already contains each
of these 188 ribbon_ride trades' P&L under the IDENTICAL correct shape (control_shape ==
fleet_strategies.by_name("ribbon_ride").exit.to_dict(), zero cache_misses, generated by a
DIFFERENT script's own per-trade walk_exit_manager call). This script independently
re-derives each removed trade's P&L via a FRESH walk_exit_manager call in THIS process (never
reusing that file's numbers directly for the headline cohort) and separately cross-validates
every removed trade's fresh P&L against exit-variant-ab's saved control_pnl for the SAME
(entry_time_et, side) key -- any mismatch is reported LOUD, not averaged away. Confirms the
re-derivation is not a new wiring bug independent of the exit-shape correction itself.

ANALYSIS ONLY. No params/config/trading-path file touched, no orders placed.

Run: backtest/.venv/Scripts/python.exe backtest/tools/regime_readjudication_correctexit.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]           # backtest/
ROOT = REPO.parent                                     # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import elite_bear_level_reject_gate_ab as eb  # noqa: E402
import strategies as fleet_strategies  # noqa: E402  -- automation/state/fleet/strategies.py
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from backtest.tools.regime_classifier import RegimeCalendar  # noqa: E402
from backtest.tools.regime_conditioned_validator import validate_candidate  # noqa: E402

FULL_WINDOW_START = dt.date(2025, 1, 2)
FULL_WINDOW_END = dt.date(2026, 7, 8)
TIME_STOP_ET = dt.time(15, 40)   # matches SAFE_BASE's time_stop_minutes_before_close=20

SELF_VAL_FILE = ROOT / "analysis" / "recommendations" / "regime-conditioned-validation-2026-07-17.json"
OLD_READJUDICATION_FILE = ROOT / "analysis" / "recommendations" / "regime-conditioned-readjudication-2026-07-17.json"
CROSSCHECK_SOURCE = ROOT / "analysis" / "recommendations" / "exit-variant-ab-wider-trail25-2026-07-17.json"

OUT_JSON = ROOT / "analysis" / "recommendations" / "regime-readjudication-correctexit-2026-07-17.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "regime-readjudication-correctexit-2026-07-17.md"


def log(msg: str) -> None:
    print(f"[correctexit-readjudicate] {msg}", flush=True)


def check_gate() -> str:
    """Same gate iteration-5's readjudication used -- re-scoring after a failed
    self-validation would be the exact methodology-shopping the prereg forbids."""
    if not SELF_VAL_FILE.exists():
        raise SystemExit(f"{SELF_VAL_FILE} missing -- iteration-5 self-validation artifact required.")
    d = json.loads(SELF_VAL_FILE.read_text(encoding="utf-8"))
    verdict = d.get("self_validation_verdict")
    log(f"self_validation_verdict={verdict} (iteration-5 EARNS_RIGHTS methodology, unchanged)")
    if verdict != "EARNS_RIGHTS":
        raise SystemExit(f"ABORT: self-validation verdict is '{verdict}', not EARNS_RIGHTS.")
    return verdict


def naive_dt(ts) -> dt.datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts


def main() -> int:
    check_gate()
    log("loading SPY/VIX + running elite_bear_level_reject_gate_ab's OWN SAFE_BASE full-window "
        "backtest (byte-identical call to iteration 4/5 -- entry detection + block predicate "
        "UNCHANGED)")
    spy_df = pd.read_csv(eb.SPY_FILE)
    vix_df = pd.read_csv(eb.VIX_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    r = eb.run_backtest(spy_df, vix_df, start_date=FULL_WINDOW_START, end_date=FULL_WINDOW_END, **eb.SAFE_BASE)
    removed, kept = eb.split_control_candidate(r.trades)
    log(f"n_total_trades={len(r.trades)} n_removed(ELITE-bear)={len(removed)} n_kept={len(kept)}")

    correct_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    log(f"CORRECT exit shape (strategies.py#RIBBON_RIDE.exit.to_dict()): {correct_shape}")
    wrong_shape_note = {
        "premium_stop_pct": eb.SAFE_BASE["premium_stop_pct_bear"],
        "tp1_premium_pct": eb.SAFE_BASE["tp1_premium_pct"],
        "profit_lock_mode": eb.SAFE_BASE["profit_lock_mode"],
        "runner_target_premium_pct": eb.SAFE_BASE["runner_target_premium_pct"],
        "note": "the WRONG shape iteration 4/5 actually simulated (simulate_trade_real via SAFE_BASE)",
    }
    log(f"WRONG exit shape (SAFE_BASE, what iteration 4/5 actually used): {wrong_shape_note}")

    rows = []
    n_no_bars = 0
    for t in removed:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            n_no_bars += 1
            log(f"  SKIP {edate} {symbol}: no local OPRA cache")
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            n_no_bars += 1
            log(f"  SKIP {edate} {symbol}: no SPY 5-min rows for the day")
            continue
        entry_time_et = naive_dt(t.entry_time_et)
        entry_premium = float(t.entry_premium)
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        qty = int(t.qty)

        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et, entry_premium=entry_premium,
            qty=qty, exit_shape=correct_shape, structure_stop_enabled=True,
            trigger_level=trigger_level, strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=day_spy,
        )
        rows.append({
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "symbol": symbol, "side": t.side, "qty": qty, "trigger_level": trigger_level,
            "wrong_exit_pnl": round(float(t.dollar_pnl), 2),
            "correct_exit_pnl": res.dollar_pnl,
            "correct_exit_reason": res.exit_reason, "resolved_stop_mode": res.stop_mode,
        })

    log(f"n_replayed={len(rows)} n_no_local_bars={n_no_bars}")
    if not rows:
        log("FATAL: no removed trades replayed -- aborting")
        return 1

    # ---- CROSS-CHECK: independently-computed exit-variant-ab control_pnl for the SAME trades ----
    xref = {}
    xcheck_available = CROSSCHECK_SOURCE.exists()
    if xcheck_available:
        xdata = json.loads(CROSSCHECK_SOURCE.read_text(encoding="utf-8"))
        assert xdata.get("control_shape") == correct_shape, (
            "CROSS-CHECK PRECONDITION FAILED: exit-variant-ab's control_shape does not byte-match "
            "strategies.py#RIBBON_RIDE.exit.to_dict() read THIS run -- shape drifted, cross-check invalid.")
        for tr in xdata["trades"]:
            xref[(tr["entry_time_et"], tr["side"])] = tr["control_pnl"]
        log(f"cross-check source loaded: {CROSSCHECK_SOURCE.name} "
            f"({xdata.get('n_replayed')} trades, control_shape byte-verified match)")
    else:
        log(f"WARNING: cross-check source {CROSSCHECK_SOURCE} not found -- skipping independent parity check")

    n_xchecked = 0
    n_xmatch = 0
    xcheck_mismatches = []
    for row in rows:
        key = (row["entry_time_et"], row["side"])
        if key in xref:
            n_xchecked += 1
            match = abs(xref[key] - row["correct_exit_pnl"]) < 0.02
            if match:
                n_xmatch += 1
            else:
                xcheck_mismatches.append({**row, "exit_variant_ab_control_pnl": xref[key]})

    log(f"CROSS-CHECK: {n_xmatch}/{n_xchecked} removed trades' fresh walk_exit_manager P&L exactly "
        f"match exit-variant-ab.py's independently-computed control_pnl for the same trade "
        f"(entry_time_et, side). Mismatches: {len(xcheck_mismatches)}")
    if xcheck_mismatches:
        for m in xcheck_mismatches:
            log(f"  MISMATCH {m['entry_time_et']} {m['symbol']}: this_run=${m['correct_exit_pnl']:+.2f} "
                f"exit_variant_ab=${m['exit_variant_ab_control_pnl']:+.2f}")

    # ---- build the CORRECTED cohort (same sign convention as cohort_elite_bear(): block a
    # losing trade = positive delta) ----
    corrected_cohort = [{"date": row["date"], "pnl": -row["correct_exit_pnl"]} for row in rows]
    wrong_cohort = [{"date": row["date"], "pnl": -row["wrong_exit_pnl"]} for row in rows]

    calendar = RegimeCalendar()
    correct_result = validate_candidate(
        corrected_cohort, candidate_name="elite_bear_level_reject_gate_L1_CORRECTEXIT",
        calendar=calendar, full_window_start=FULL_WINDOW_START, full_window_end=FULL_WINDOW_END)
    # re-run the SAME validator over the SAME n rows under the WRONG shape too, so the
    # before/after comparison is apples-to-apples on the identical trade set (not iteration
    # 5's slightly different n, which came from a separately-run cohort_elite_bear() call).
    wrong_result = validate_candidate(
        wrong_cohort, candidate_name="elite_bear_level_reject_gate_L1_WRONGEXIT_same_n",
        calendar=calendar, full_window_start=FULL_WINDOW_START, full_window_end=FULL_WINDOW_END)

    log(f"WRONG-EXIT  (same n={len(rows)}): verdict={wrong_result.get('verdict')} "
        f"ladder={wrong_result.get('ladder_verdict')} bucket={wrong_result.get('target_regime_bucket')} "
        f"n_bucket={wrong_result.get('n_bucket')}")
    log(f"CORRECT-EXIT (n={len(rows)}): verdict={correct_result.get('verdict')} "
        f"ladder={correct_result.get('ladder_verdict')} bucket={correct_result.get('target_regime_bucket')} "
        f"n_bucket={correct_result.get('n_bucket')}")

    # ---- also load iteration-5's ORIGINAL result (different n -- its own independent
    # cohort_elite_bear() call, kept for the ledger table, not re-derived here) ----
    orig_result = None
    if OLD_READJUDICATION_FILE.exists():
        od = json.loads(OLD_READJUDICATION_FILE.read_text(encoding="utf-8"))
        orig_result = od.get("results", {}).get("elite_bear_level_reject_gate_L1")

    flip = (correct_result.get("verdict") == "PASS")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "gate_check": "self_validation_verdict == EARNS_RIGHTS (verified at top of main())",
        "n_total_trades": len(r.trades), "n_removed_elite_bear": len(removed),
        "n_replayed": len(rows), "n_no_local_bars": n_no_bars,
        "correct_exit_shape": correct_shape,
        "wrong_exit_shape_note": wrong_shape_note,
        "cross_check": {
            "source": str(CROSSCHECK_SOURCE), "available": xcheck_available,
            "n_checked": n_xchecked, "n_match": n_xmatch, "mismatches": xcheck_mismatches,
        },
        "trades": rows,
        "iteration5_original_result_different_n": orig_result,
        "same_n_wrong_exit_result": wrong_result,
        "same_n_correct_exit_result": correct_result,
        "flip_to_pass": flip,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")

    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"FLIP_TO_PASS: {flip}")
    return 0


def write_markdown(out: dict) -> None:
    wr = out["same_n_wrong_exit_result"]
    cr = out["same_n_correct_exit_result"]
    orig = out.get("iteration5_original_result_different_n") or {}
    xc = out["cross_check"]
    L = [
        "# ITERATION 7 -- elite-bear L1 regime-conditioned re-adjudication under the CORRECT exit shape",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/regime_readjudication_correctexit.py`.",
        "",
        f"n_total_trades={out['n_total_trades']}, n_removed(ELITE-bear PUT)={out['n_removed_elite_bear']}, "
        f"n_replayed={out['n_replayed']} (n_no_local_bars={out['n_no_local_bars']}).",
        "",
        "## Cross-check vs exit-variant-ab.py's independently-computed control_pnl",
        "",
        f"source available: {xc['available']}. n_checked={xc['n_checked']}, n_match={xc['n_match']}, "
        f"n_mismatch={len(xc['mismatches'])}.",
        "",
        "## Before / after (SAME n, SAME trades, only the exit model changed)",
        "",
        "| | WRONG exit (simulate_trade_real shape) | CORRECT exit (exit_manager_walk, strategies.py shape) |",
        "|---|---|---|",
        f"| verdict | {wr.get('verdict')} | {cr.get('verdict')} |",
        f"| ladder_verdict | {wr.get('ladder_verdict')} | {cr.get('ladder_verdict')} |",
        f"| target_regime_bucket | {wr.get('target_regime_bucket')} | {cr.get('target_regime_bucket')} |",
        f"| n_bucket | {wr.get('n_bucket')} | {cr.get('n_bucket')} |",
        f"| regime_is_delta_mean | {wr.get('regime_is_delta_mean')} | {cr.get('regime_is_delta_mean')} |",
        f"| regime_oos_delta_mean | {wr.get('regime_oos_delta_mean')} | {cr.get('regime_oos_delta_mean')} |",
        f"| wf_delta | {wr.get('wf_delta')} | {cr.get('wf_delta')} |",
        f"| gates | {wr.get('gates')} | {cr.get('gates')} |",
        f"| concentration_check | {wr.get('concentration_check')} | {cr.get('concentration_check')} |",
        "",
        "## Iteration-5's ORIGINAL result (different n -- its own independent "
        "cohort_elite_bear() call, wrong-exit shape, shown for the ledger only)",
        "",
        f"verdict={orig.get('verdict')} ladder={orig.get('ladder_verdict')} "
        f"bucket={orig.get('target_regime_bucket')} n_bucket={orig.get('n_bucket')}",
        "",
        f"**FLIP TO PASS UNDER CORRECT EXIT: {out['flip_to_pass']}**",
        "",
        "---",
        "_Source: `backtest/tools/regime_readjudication_correctexit.py`. GOAL DISPOSITION lives in "
        "`automation/overnight/GOAL-REPLAY-TODAY-GREEN.md` ITERATION 7, not this file._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
