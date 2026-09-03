"""
C14 BATCH 9: Final two unswept knobs.

1. vol_baseline_bars (prod=20) — window for 20-bar SMA of volume used in Filter 9+10.
   Lower = faster adaptation to volume regime; higher = more stable baseline.
   Key: `vol_baseline_20bar()` uses prior `VOL_BASELINE_BARS` bars before each entry bar.

2. vix_declining_required_bear (prod=False) — require VIX declining for BEAR entries.
   Per L93: "if a VIX gate is needed, test DECLINING direction only" (escalating = wrong for BEARISH_REVERSAL).
   L115 wired but only tested MA cross approach, not the simple bool gate.
   The simple bool: vix_now < vix_prior (same-day direction test).

Security: read-only. No Alpaca calls.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _anchor_ok(trades, base_by_date):
    by_date = {}
    for t in trades:
        d = _date(t)
        by_date[d] = by_date.get(d, 0.0) + t.dollar_pnl
    for d in J_WINNERS:
        bp = base_by_date.get(d, 0.0)
        cp = by_date.get(d, 0.0)
        if bp > 0 and cp < bp * 0.90:
            return False
    return True


def _wf(is_delta, n_is, oos_delta, n_oos):
    if is_delta == 0 or n_oos == 0 or n_is == 0:
        return 0.0
    return (oos_delta / n_oos) / (is_delta / n_is)


if __name__ == "__main__":
    print("=" * 95)
    print("C14 BATCH 9: vol_baseline_bars + vix_declining_required_bear SWEEP")
    print("=" * 95)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[0] BASELINE (vol_baseline_bars=20, vix_declining_required_bear=False)...")
    base_is  = run_backtest(spy_df, vix_df, start_date=IS_START,  end_date=IS_END,  **BASE)
    base_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_by_date = {}
    for t in base_is.trades:
        d = _date(t)
        base_by_date[d] = base_by_date.get(d, 0.0) + t.dollar_pnl
    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    print(f"  IS n={n_is} pnl={base_is_pnl:+.0f}")
    print(f"  OOS n={n_oos} pnl={base_oos_pnl:+.0f}")

    # ============================================================
    # SWEEP 1: vol_baseline_bars
    # ============================================================
    print("\n" + "=" * 95)
    print("SWEEP 1: vol_baseline_bars (prod=20)")
    print("  Mechanism: SMA window for 'average volume' in Filter 9 (breakdown) + Filter 10 (buyer pressure).")
    print("  Smaller = faster to adapt when volume regime shifts; larger = slower/more stable baseline.")
    print(f"\n  {'bars':>6}  {'IS_n':>5}  {'IS_pnl':>9}  {'IS_delta':>9}  "
          f"{'OOS_n':>5}  {'OOS_pnl':>9}  {'OOS_delta':>10}  {'WF_norm':>8}  {'anchor':>6}  Verdict")
    print("  " + "-" * 82)

    v1_results = []
    for bars in [5, 10, 15, 20, 30, 40, 60]:
        ovr = {"vol_baseline_bars": bars}
        is_r  = run_backtest(spy_df, vix_df, start_date=IS_START,  end_date=IS_END,  params_overrides=ovr, **BASE)
        oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, params_overrides=ovr, **BASE)
        is_p  = _pnl(is_r.trades)
        oos_p = _pnl(oos_r.trades)
        is_d  = is_p - base_is_pnl
        oos_d = oos_p - base_oos_pnl
        wf    = _wf(is_d, n_is, oos_d, n_oos)
        anchor = _anchor_ok(is_r.trades, base_by_date)
        verdict = "PASS" if (oos_d > 0 and wf >= 0.70 and anchor) else ("OOS+" if oos_d > 0 else "FAIL")
        tag = " <-- prod" if bars == 20 else ""
        print(f"  {bars:>6}  {len(is_r.trades):>5}  {is_p:>+9.0f}  {is_d:>+9.0f}  "
              f"{len(oos_r.trades):>5}  {oos_p:>+9.0f}  {oos_d:>+10.0f}  {wf:>8.3f}  "
              f"{'OK' if anchor else 'FAIL':>6}  {verdict}{tag}")
        v1_results.append((bars, len(is_r.trades), is_p, is_d, len(oos_r.trades), oos_p, oos_d, wf, anchor, verdict))

    # ============================================================
    # SWEEP 2: vix_declining_required_bear
    # ============================================================
    print("\n" + "=" * 95)
    print("SWEEP 2: vix_declining_required_bear (prod=False)")
    print("  Mechanism: if True, BEAR entries only allowed when VIX is falling (vix_now < vix_prior).")
    print("  Per L93: test DECLINING direction only for BEARISH_REVERSAL (not escalating).")
    print("  WARNING: VIX declining means BEAR entries fire in 'calming down' regime -> J anchor days.")
    print(f"\n  {'bool':>8}  {'IS_n':>5}  {'IS_pnl':>9}  {'IS_delta':>9}  "
          f"{'OOS_n':>5}  {'OOS_pnl':>9}  {'OOS_delta':>10}  {'WF_norm':>8}  {'anchor':>6}  Verdict")
    print("  " + "-" * 85)

    v2_results = []
    for required in [False, True]:
        ovr = {"vix_declining_required_bear": required}
        is_r  = run_backtest(spy_df, vix_df, start_date=IS_START,  end_date=IS_END,  params_overrides=ovr, **BASE)
        oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, params_overrides=ovr, **BASE)
        is_p  = _pnl(is_r.trades)
        oos_p = _pnl(oos_r.trades)
        is_d  = is_p - base_is_pnl
        oos_d = oos_p - base_oos_pnl
        wf    = _wf(is_d, n_is, oos_d, n_oos)
        anchor = _anchor_ok(is_r.trades, base_by_date)
        verdict = "PASS" if (oos_d > 0 and wf >= 0.70 and anchor) else ("OOS+" if oos_d > 0 else "FAIL")
        tag = " <-- prod" if not required else ""
        print(f"  {str(required):>8}  {len(is_r.trades):>5}  {is_p:>+9.0f}  {is_d:>+9.0f}  "
              f"{len(oos_r.trades):>5}  {oos_p:>+9.0f}  {oos_d:>+10.0f}  {wf:>8.3f}  "
              f"{'OK' if anchor else 'FAIL':>6}  {verdict}{tag}")
        # Print anchor day detail for True case to understand which OOS trades get filtered
        if required:
            by_date = {}
            for t in oos_r.trades:
                d = _date(t)
                by_date[d] = by_date.get(d, 0.0) + t.dollar_pnl
            base_oos_by_date = {}
            for t in base_oos.trades:
                d = _date(t)
                base_oos_by_date[d] = base_oos_by_date.get(d, 0.0) + t.dollar_pnl
            for d in sorted(J_WINNERS):
                bp = base_oos_by_date.get(d, 0.0)
                cp = by_date.get(d, 0.0)
                status = "OK" if cp >= bp * 0.90 else "REGRESSED"
                if bp != 0 or cp != 0:
                    print(f"    anchor {d}: base={bp:+.0f} cand={cp:+.0f} {status}")
        v2_results.append((required, len(is_r.trades), is_p, is_d, len(oos_r.trades), oos_p, oos_d, wf, anchor, verdict))

    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "=" * 95)
    print("SUMMARY")
    all_pass = [(f"vol_baseline_bars={r[0]}", r[3], r[6], r[7])
                for r in v1_results if r[9] == "PASS"]
    all_pass += [(f"vix_declining_required_bear={r[0]}", r[3], r[6], r[7])
                 for r in v2_results if r[9] == "PASS"]
    if all_pass:
        print(f"\n  PASS candidates ({len(all_pass)}):")
        for label, is_d, oos_d, wf in all_pass:
            print(f"    {label}: IS_delta={is_d:+.0f} OOS_delta={oos_d:+.0f} WF={wf:.3f}")
        best = max(all_pass, key=lambda r: r[2])
        print(f"\n  BEST: {best[0]} (OOS_delta={best[2]:+.0f})")
    else:
        print("\n  No PASS candidates. Both production defaults confirmed.")
        oos_pos = [(f"vol_baseline_bars={r[0]}", r[3], r[6], r[7])
                   for r in v1_results if r[6] > 0]
        oos_pos += [(f"vix_declining={r[0]}", r[3], r[6], r[7])
                    for r in v2_results if r[6] > 0]
        if oos_pos:
            print("\n  OOS+ (WF insufficient, informational):")
            for label, is_d, oos_d, wf in sorted(oos_pos, key=lambda r: r[2], reverse=True):
                print(f"    {label}: IS_delta={is_d:+.0f} OOS_delta={oos_d:+.0f} WF={wf:.3f}")

    print("\nANALYSIS COMPLETE.")
