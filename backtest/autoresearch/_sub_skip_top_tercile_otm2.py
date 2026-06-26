"""SUBTRACTIVE-SHIP re-verify: skip_top_tercile_only across strike tiers (ITM-2 + OTM-2).

WHAT THIS IS
────────────
The selection campaign proved that ADDITIVE confluence (stack more confirmations) is DEAD
on 0DTE. The ONE win was SUBTRACTIVE: ``skip_top_tercile_only`` -- abstain from the proven
vwap_continuation entries when the entry VIX is in the worst (top, expanding-window) tercile,
base-size everywhere else. At the SURVIVOR strike (strike_offset=-2 / ITM-2) it cleared all
8 mandatory gates with OOS +$142.54/tr and maxDD only -$423.84
(``analysis/recommendations/sel-regime_conditional_vwap_sizing.json#schedules.skip_top_tercile_only``).

This script RE-VERIFIES that winner head-to-toe and asks the C29 question that the campaign
left open: gates ratified on ONE strike tier (ITM-2) do NOT automatically transfer to another
(OTM-2). Safe-2 is a $2K account whose ACTUAL tier per CLAUDE.md v15 is OTM-2 (strike_offset=+2).
So the ship-or-not decision for Safe-2 hinges on whether the subtraction HOLDS at OTM-2.

WE RUN ``skip_top_tercile_only`` at TWO strike offsets, each through ALL 8 gates:
  * strike_offset = -2  (ITM-2)  -> reproduce the campaign winner exactly (regression check)
  * strike_offset = +2  (OTM-2)  -> Safe-2's actual $2K tier (the SHIP decision per C29)

NO DRIFT (C14): the detector, the real-fills sim (``simulate_base``), the causal expanding-
window tercile schedule (``sched_skip_top_tercile_only``), the metrics, the random-entry null
(``random_null``) and the no-truncation check (``no_truncation_check``) are all IMPORTED
BYTE-FOR-BYTE from the campaign harness ``_sel_regime_conditional_vwap_sizing``. The ONLY thing
this script varies is the module-level ``STRIKE_OFFSET`` (read at call time inside
``simulate_base``/``random_null`` via ``target = atm - STRIKE_OFFSET``), which we set per run.
That isolates the strike-tier effect with zero code divergence from the ratified campaign.

THE 8 MANDATORY GATES (anti-2.10, NO cherry-pick -- ALL must hold at each strike):
  1. OOS(2026) per-trade > 0
  2. positive_quarters >= 4/6
  3. top5_day_pct < 200%
  4. n_trades >= 20
  5. drop-top-5-days total > 0          (edge survives removing the 5 best days)
  6. IS(2025) half per-trade > 0        (reject the IS-neg/OOS-pos single-regime artifact)
  7. beats random-entry null            (real total > 20-seed random-entry-null mean; L172)
  8. no-truncation                      (overall sign holds -8% -> chart-stop-only -0.99; L171)

These are EXACTLY the 8 gates the campaign harness's ``evaluate_schedule`` already computes; we
re-use that evaluator verbatim so the verdict logic cannot drift either.

Pure Python, $0 (no LLM in the sim loop). No live orders. Markets closed.

Writes analysis/recommendations/sub-skip_top_tercile_otm2.json.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sub_skip_top_tercile_otm2.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

# IMPORT the campaign harness as a module so we can flip its STRIKE_OFFSET per run and
# re-use every piece of its (already-ratified) machinery byte-for-byte. No re-derivation.
import autoresearch._sel_regime_conditional_vwap_sizing as camp  # noqa: E402
from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "sub-skip_top_tercile_otm2.json"

SCHED_NAME = "skip_top_tercile_only"
STRIKE_RUNS = [
    (-2, "ITM-2", "reproduce_campaign_winner"),
    (+2, "OTM-2", "safe2_actual_2k_tier_C29"),
]


def _run_one_strike(strike_offset, signals, spy, ribbon, vix):
    """Run FLAT_baseline + skip_top_tercile_only at one strike offset, all 8 gates.

    Flips the campaign module's module-level STRIKE_OFFSET (read at call time inside
    simulate_base / random_null) so the strike tier is the ONLY thing that changes.
    Returns the schedule's full evaluation block + the flat baseline for vs_flat context.
    """
    saved = camp.STRIKE_OFFSET
    camp.STRIKE_OFFSET = strike_offset
    try:
        # Base survivor stream at every SIM_QTYS (3 and 6), exact per-qty real fills.
        base_rows, cov = camp.simulate_base(signals, spy, ribbon, vix, qtys=camp.SIM_QTYS)
        # Chart-stop-only stream for the no-truncation gate (pre-simmed once).
        base_chart, cov_chart = camp.simulate_base(
            signals, spy, ribbon, vix, qtys=camp.SIM_QTYS, premium_stop_pct=-0.99)
        # FLAT baseline (for vs_flat deltas + context) then the subtraction schedule.
        flat_eval = camp.evaluate_schedule(
            "FLAT_baseline", base_rows, base_chart, signals, spy, ribbon, vix, {})
        flat_m = flat_eval["metrics"]
        sub_eval = camp.evaluate_schedule(
            SCHED_NAME, base_rows, base_chart, signals, spy, ribbon, vix, flat_m)
    finally:
        camp.STRIKE_OFFSET = saved
    return {
        "strike_offset": strike_offset,
        "base_coverage": cov,
        "chartstop_coverage": cov_chart,
        "FLAT_baseline": flat_eval,
        SCHED_NAME: sub_eval,
    }


def main() -> int:
    print("[sub-skip_top_tercile] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = camp._normalize_spy(spy_raw)
    vix = camp._align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[sub-skip_top_tercile] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    print("[sub-skip_top_tercile] computing ribbon ...", flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # Detect the survivor signal set ONCE (byte-for-byte campaign detector). The signal
    # stream is strike-independent, so the SAME signals feed every strike run.
    signals = camp.detect_signals(days)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[sub-skip_top_tercile] survivor signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    runs = {}
    for so, tier, purpose in STRIKE_RUNS:
        print(f"\n[sub-skip_top_tercile] === strike_offset={so:+d} ({tier}: {purpose}) ===",
              flush=True)
        runs[tier] = {"purpose": purpose, **_run_one_strike(so, signals, spy, ribbon, vix)}
        ev = runs[tier][SCHED_NAME]
        m = ev["metrics"]
        g = ev["gates"]
        print(f"  n={m.get('n')} total=${m.get('total_dollar')} exp=${m.get('exp_dollar')} "
              f"oos_exp=${m.get('oos_exp')} (oos_n={m.get('oos_n')}) is_exp=${m.get('is_exp')}",
              flush=True)
        print(f"  posQ={m.get('positive_quarters')} top5%={m.get('top5_day_pct')} "
              f"drop5_total=${m.get('drop_top5_days_total')} maxDD=${m.get('max_drawdown_dollars')} "
              f"({m.get('max_drawdown_pct_of_2k')}% of $2K) worst=${m.get('worst_single_trade_dollars')}",
              flush=True)
        print(f"  null: real=${ev['null']['real_total']} vs nullmean=${ev['null']['null_mean_total']} "
              f"beats={ev['null']['beats_null']} (pctile={ev['null']['real_pctile_vs_null']})", flush=True)
        print(f"  notrunc: prem_total=${m.get('total_dollar')} chartstop_total="
              f"${ev['no_truncation'].get('chartstop_total_dollar')} "
              f"truncation_safe={g.get('truncation_safe')}", flush=True)
        print(f"  GATES: {g}  -> {'CLEARS-ALL-8' if ev['clears_all_gates'] else 'FAILS'}",
              flush=True)

    # ── Cross-tier verdict (C29): does the subtraction HOLD at OTM-2? ─────────────
    itm = runs["ITM-2"][SCHED_NAME]
    otm = runs["OTM-2"][SCHED_NAME]
    itm_clears = bool(itm["clears_all_gates"])
    otm_clears = bool(otm["clears_all_gates"])
    holds_at_otm2 = otm_clears
    reproduces_campaign = bool(itm_clears and itm["metrics"].get("oos_exp", 0) > 0)
    ship_ready = bool(reproduces_campaign and holds_at_otm2)

    summary = {
        "hypothesis": "skip_top_tercile_only (subtractive abstention) re-verified across strike tiers",
        "kind": "subtractive-SHIP re-verify",
        "thesis": ("RE-VERIFY the campaign's lone SUBTRACTIVE winner -- abstain from "
                   "vwap_continuation entries when entry VIX is in the worst (top, expanding-"
                   "window) VIX tercile -- at the SURVIVOR strike (ITM-2, reproduce) AND at "
                   "Safe-2's actual $2K OTM-2 tier (the ship decision per C29). Additive "
                   "confluence is dead on 0DTE; the edge improves by SUBTRACTION."),
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "detector": ("BYTE-FOR-BYTE j_daily_pattern_ratify.detect_j_vwap_continuation "
                     "(imported from the campaign harness); live port = "
                     "backtest/lib/watchers/vwap_continuation_watcher.py"),
        "fills_authority": ("real OPRA via lib.simulator_real.simulate_trade_real (C1); "
                            "premium_stop_pct=-0.08, v15 default exits, nearest-cached strike snap<=4"),
        "no_drift_note": ("simulate_base / sched_skip_top_tercile_only / metrics / random_null / "
                          "no_truncation_check / evaluate_schedule are ALL imported verbatim from "
                          "_sel_regime_conditional_vwap_sizing; ONLY module STRIKE_OFFSET is flipped "
                          "per run (-2 then +2). Zero re-derivation (C14)."),
        "strike_offset_convention": ("VERIFIED simulator_real.py L356-364: puts strike=atm-offset, "
                                     "calls strike=atm+offset => NEGATIVE offset = ITM, POSITIVE = OTM "
                                     "for BOTH sides (anti-pattern 2.2 cleared)"),
        "oos_split": f"IS=2025 / OOS={camp.OOS_YEAR} (calendar-year)",
        "causal_regime": (f"expanding-window VIX terciles over PRIOR entries only; "
                          f"warmup={camp.WARMUP_TRADES} trades; NO look-ahead (L14/L34/L57)"),
        "schedule_tested": SCHED_NAME,
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "gates_required": {
            "1_oos_per_trade_positive": "> 0",
            "2_positive_quarters_ge_4": ">= 4/6",
            "3_top5_day_lt_200": "< 200%",
            "4_n_ge_20": ">= 20",
            "5_drop_top5_days_positive": "> 0 after removing 5 best days",
            "6_is_half_positive": "IS(2025) per-trade exp > 0",
            "7_beats_random_null": f"real total > mean of {camp.NULL_SEEDS}-seed random-entry null (L172)",
            "8_truncation_safe": "overall sign does NOT invert at chart-stop-only -0.99 (L171)",
        },
        "runs_by_strike": runs,
        "cross_tier_verdict": {
            "itm2_clears_all_gates": itm_clears,
            "otm2_clears_all_gates": otm_clears,
            "reproduces_campaign_at_itm2": reproduces_campaign,
            "holds_at_otm2": holds_at_otm2,
            "ship_ready_for_safe2": ship_ready,
            "itm2_oos_per_trade": itm["metrics"].get("oos_exp"),
            "otm2_oos_per_trade": otm["metrics"].get("oos_exp"),
            "itm2_max_drawdown": itm["metrics"].get("max_drawdown_dollars"),
            "otm2_max_drawdown": otm["metrics"].get("max_drawdown_dollars"),
            "c29_note": ("C29: gates ratified on one strike tier do NOT transfer automatically; "
                         "the OTM-2 run is the binding ship decision for the $2K Safe-2 account."),
        },
        "wiring_if_holds": {
            "where": "automation/prompts/heartbeat.md -- the VWAP_CONTINUATION entry block",
            "param_source": "automation/state/params.json (Safe) / automation/state/aggressive/params.json (Bold)",
            "flag": "j_vwap_cont_skip_top_vix_tercile",
            "semantics": ("BEFORE arming a vwap_continuation entry, compute the expanding-window "
                          "VIX tercile boundaries over the entry-VIX of ALL PRIOR vwap_continuation "
                          "entries this account has taken (persisted causal state; warmup "
                          f"{camp.WARMUP_TRADES} entries -> no abstention until then). If the CURRENT "
                          "entry VIX > the top (2/3) tercile boundary, ABSTAIN (skip the entry, log "
                          "as a regime-abstention WATCH_ONLY decision). Otherwise enter at base size. "
                          "This is a PURE subtraction -- no size-up leg, base qty everywhere it does "
                          "not skip -- so it stays inside the 30% per-trade cap (unlike the 2x "
                          "schedules) and is Safe-2-compatible at OTM-2."),
            "state_needed": ("persist per-account rolling list of prior vwap_continuation entry-VIX "
                             "values (the causal tercile window) in the loop-state JSON so the "
                             "expanding-window boundary is reproducible tick-to-tick across restarts."),
            "strike_tier_caveat": ("WIRE ONLY IF the OTM-2 run clears all 8 gates -- Safe-2 trades "
                                   "OTM-2 (strike_offset=+2), not the ITM-2 survivor strike (C29)."),
        },
        "DISCLOSURE": {
            "no_cherry_pick": ("ALL 8 mandatory gates reported at BOTH strikes; a strike that fails "
                               "any gate is reported clears_all_gates=false (anti-pattern 2.10)."),
            "per_trade": "expectancy (oos_exp / exp_dollar) reported, not WR alone (OP-14)",
            "is_oos": f"IS=2025 vs OOS={camp.OOS_YEAR} per strike (OP-20)",
            "concentration": "top5_day_pct + drop-top-5-days total per strike (OP-20 #5)",
            "fraud_gates": ("random-entry null (20 seeds, same days/sides, total-P&L basis) + "
                            "no-truncation (overall sign must hold -8% -> chart-stop-only)."),
            "c29": "gates do NOT transfer across strike tiers; OTM-2 is the binding Safe-2 decision.",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58).",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[sub-skip_top_tercile] wrote {OUT}", flush=True)

    print("\n=== SKIP_TOP_TERCILE_ONLY CROSS-STRIKE VERDICT ===")
    for tier in ("ITM-2", "OTM-2"):
        ev = runs[tier][SCHED_NAME]
        m = ev["metrics"]
        print(f"[{tier}] clears_all_8={ev['clears_all_gates']}  n={m.get('n')} "
              f"oos_exp=${m.get('oos_exp')} is_exp=${m.get('is_exp')} "
              f"posQ={m.get('positive_quarters')} top5%={m.get('top5_day_pct')} "
              f"maxDD=${m.get('max_drawdown_dollars')}")
    cv = summary["cross_tier_verdict"]
    print(f"reproduces_campaign(ITM-2)={cv['reproduces_campaign_at_itm2']}  "
          f"holds_at_OTM2={cv['holds_at_otm2']}  SHIP_READY_SAFE2={cv['ship_ready_for_safe2']}")
    if ship_ready:
        print("-> SHIP: wire j_vwap_cont_skip_top_vix_tercile into the heartbeat "
              "VWAP_CONTINUATION block (see wiring_if_holds).")
    else:
        print("-> DO NOT ship to Safe-2 at OTM-2: subtraction does not hold at the $2K tier "
              "(C29). ITM-2/Bold-tier only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
