"""
BEARISH_REVERSAL_BYPASS Phase 1: IS validation 2025-01 to 2025-09.

Cook queue task e670b8f0. Spec: docs/BEARISH-REVERSAL-BYPASS-SPEC.md

Tests whether include_first_hour_high=True + bearish_reversal_bypass=True
generates at least N>=15 new bypass entries with WR>=0.50 in the clean
2025-01 to 2025-09 IS window (before any ENFORCED gates existed).

Uses AGG params from agg_fhh_bypass.py (no block_conf_lvl gates) for
cleaner signal isolation.

Security: read-only. No Alpaca calls. No params.json writes (IS-only phase).
"""
from __future__ import annotations
import sys
import json
import datetime as dt
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START = dt.date(2025, 1,  2)
IS_END   = dt.date(2025, 9, 30)

TARGET_N  = 15
TARGET_WR = 0.50

AGG_BASE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.07,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
)
AGG_OVR = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}


def _run(spy_df, vix_df, use_fhh=False, use_bypass=False):
    return run_backtest(
        spy_df, vix_df,
        start_date=IS_START, end_date=IS_END,
        include_first_hour_high=use_fhh,
        include_bearish_reversal_bypass=use_bypass,
        params_overrides=dict(AGG_OVR),
        **AGG_BASE_KW,
    )


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _time(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.strftime("%H:%M")


if __name__ == "__main__":
    print("=" * 80)
    print("BEARISH_REVERSAL_BYPASS — Phase 1 IS backtest")
    print(f"Window: {IS_START} to {IS_END}")
    print("=" * 80)

    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print(f"\n[Baseline: FHH=False, bypass=False]")
    base = _run(spy_df, vix_df, False, False)
    base_pnl = _pnl(base.trades)
    base_et  = {t.entry_time_et for t in base.trades}
    print(f"  IS n={len(base.trades)} pnl={base_pnl:+,.0f}")

    print(f"\n[Candidate: FHH=True, bypass=True]")
    cand = _run(spy_df, vix_df, True, True)
    cand_pnl = _pnl(cand.trades)
    print(f"  IS n={len(cand.trades)} pnl={cand_pnl:+,.0f}")

    # Identify bypass-only entries
    bypass_trades = [t for t in cand.trades if t.entry_time_et not in base_et]
    n_bypass = len(bypass_trades)
    n_wins   = sum(1 for t in bypass_trades if t.dollar_pnl > 0)
    n_loss   = n_bypass - n_wins
    wr       = n_wins / n_bypass if n_bypass > 0 else 0.0
    tot_pnl  = sum(t.dollar_pnl for t in bypass_trades)
    avg_pnl  = tot_pnl / n_bypass if n_bypass > 0 else 0.0

    print(f"\n{'='*80}")
    print(f"  BYPASS-ONLY entries: n={n_bypass}  WR={wr:.1%}  avg={avg_pnl:+.0f}  total={tot_pnl:+,.0f}")
    print(f"  Target: N>={TARGET_N}, WR>={TARGET_WR:.0%}")
    n_ok  = n_bypass >= TARGET_N
    wr_ok = wr >= TARGET_WR
    print(f"  N target:  {'PASS' if n_ok  else 'FAIL'}  ({n_bypass}/{TARGET_N})")
    print(f"  WR target: {'PASS' if wr_ok else 'FAIL'}  ({wr:.1%}/{TARGET_WR:.0%})")
    print(f"{'='*80}")

    if bypass_trades:
        print(f"\n[All bypass trades (sorted by pnl)]")
        print(f"  {'Date':12} {'Time':6} {'PnL':>8}  {'Exit'}")
        print("  " + "-" * 55)
        for t in sorted(bypass_trades, key=lambda x: -x.dollar_pnl):
            exit_r = getattr(t, "exit_reason", "?")
            print(f"  {str(_date(t)):12} {_time(t):6} {t.dollar_pnl:>+8.0f}  {exit_r}")

    # By month breakdown
    from collections import defaultdict
    by_month: dict[str, list] = defaultdict(list)
    for t in bypass_trades:
        key = _date(t).strftime("%Y-%m")
        by_month[key].append(t)

    if by_month:
        print(f"\n[By month]")
        print(f"  {'Month':8} {'n':>4} {'WR':>7} {'Total':>10} {'Avg':>8}")
        print("  " + "-" * 42)
        for m in sorted(by_month):
            ts  = by_month[m]
            mn  = len(ts)
            mw  = sum(1 for t in ts if t.dollar_pnl > 0)
            mwr = mw / mn if mn else 0.0
            mtp = sum(t.dollar_pnl for t in ts)
            print(f"  {m:8} {mn:>4} {mwr:>6.1%} {mtp:>+10,.0f} {mtp/mn:>+8.0f}")

    # Overall IS delta
    is_delta = cand_pnl - base_pnl
    print(f"\n[Overall IS impact]")
    print(f"  Baseline pnl: {base_pnl:+,.0f}")
    print(f"  Candidate pnl: {cand_pnl:+,.0f}")
    print(f"  IS delta: {is_delta:+,.0f}")

    phase1_pass = n_ok and wr_ok
    verdict = "PHASE_1_PASS" if phase1_pass else "PHASE_1_FAIL"
    print(f"\n  >>> {verdict} <<<")
    if phase1_pass:
        print("  -> Proceed to Phase 2: run agg_fhh_bypass.py for full IS+OOS validation")
    else:
        print("  -> Setup class does not meet signal threshold in 2025-01 to 2025-09")

    # Save results
    out_path = ROOT / "analysis" / "recommendations" / "bearish_reversal_bypass_is.json"
    result = {
        "task_id": "e670b8f0",
        "spec": "docs/BEARISH-REVERSAL-BYPASS-SPEC.md",
        "is_start": str(IS_START),
        "is_end": str(IS_END),
        "account": "AGG (params from agg_fhh_bypass.py baseline)",
        "baseline": {"n": len(base.trades), "pnl": round(base_pnl, 2)},
        "candidate": {"n": len(cand.trades), "pnl": round(cand_pnl, 2), "is_delta": round(is_delta, 2)},
        "bypass_entries": {
            "n": n_bypass,
            "wins": n_wins,
            "losses": n_loss,
            "wr": round(wr, 4),
            "total_pnl": round(tot_pnl, 2),
            "avg_pnl": round(avg_pnl, 2),
        },
        "targets": {"min_n": TARGET_N, "min_wr": TARGET_WR},
        "gates": {"n_ok": n_ok, "wr_ok": wr_ok},
        "verdict": verdict,
        "trades": [
            {
                "date": str(_date(t)),
                "time": _time(t),
                "pnl": round(t.dollar_pnl, 2),
                "exit_reason": str(getattr(t, "exit_reason", "?")),
            }
            for t in sorted(bypass_trades, key=lambda x: str(_date(x)))
        ],
        "by_month": {
            m: {
                "n": len(ts),
                "wr": round(sum(1 for t in ts if t.dollar_pnl > 0) / len(ts), 4) if ts else 0,
                "total_pnl": round(sum(t.dollar_pnl for t in ts), 2),
            }
            for m, ts in sorted(by_month.items())
        },
    }
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nSaved: {out_path}")
    print("ANALYSIS COMPLETE.")
