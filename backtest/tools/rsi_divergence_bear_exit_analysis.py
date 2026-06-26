"""RSI divergence bull exit-enhancer analysis.

Cross-reference: does BULL RSI divergence firing within N bars of an active bear
position exit correlate with better bear exit quality?

Question: should BULL divergence be added as an early-exit signal for active bear positions?

Data:
  - BULL divergence signals: analysis/backtests/rsi-divergence-scan/results.json
  - Bear position exits: run_backtest on AGG and SAFE

Security: read-only (except output). No Alpaca calls.
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import defaultdict

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa

DATA = REPO / "data"
SCAN_PATH = REPO.parent / "analysis" / "backtests" / "rsi-divergence-scan" / "results.json"
OUT_PATH  = REPO.parent / "analysis" / "recommendations" / "rsi_div_bear_exit_analysis.json"

IS_CUTOFF  = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}

# AGG params (production post-18.0 ratification)
AGG_PARAMS = dict(
    use_real_fills=True, strike_offset=2,
    premium_stop_pct_bear=-0.07, premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.75, tp1_qty_fraction=0.50,
    runner_target_premium_pct=2.5, f9_vol_mult=0.7,
    min_triggers_bear=1, min_triggers_bull=2,
    no_trade_before=dt.time(9, 35), no_trade_window=(dt.time(11, 30), dt.time(12, 0)),
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    midday_trendline_gate=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=18.0,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.5, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 17.3, "vix_bull_hard_cap": 18.0},
)
SAFE_PARAMS = dict(
    use_real_fills=True, strike_offset=-2,
    premium_stop_pct_bear=-0.10, premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5, f9_vol_mult=0.7,
    min_triggers_bear=1, min_triggers_bull=2,
    no_trade_before=dt.time(9, 35), no_trade_window=(dt.time(11, 30), dt.time(12, 0)),
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    midday_trendline_gate=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.3, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 17.3, "vix_bull_hard_cap": 18.0},
)

BAR_MINUTES = 5   # 5-min bars


def load_bull_signals():
    raw = json.loads(SCAN_PATH.read_text())
    sigs = []
    for s in raw["signals"]:
        if s["direction"] == "BULL":
            d   = dt.datetime.strptime(f"{s['date']} {s['time']}", "%Y-%m-%d %H:%M:%S")
            sigs.append(d)
    return sorted(sigs)


def bear_trades(trades):
    return [t for t in trades if t.side == "P"]


def nearest_bull_div(exit_dt, bull_sigs, window_bars=6):
    """Return (bars_away, signal_dt) for the nearest BULL signal within window_bars,
    looking backward only (signal fires BEFORE the exit)."""
    window = dt.timedelta(minutes=window_bars * BAR_MINUTES)
    best = None
    for s in bull_sigs:
        if s > exit_dt:
            break   # sorted; no point continuing
        delta = exit_dt - s
        if delta <= window:
            if best is None or delta < best[0]:
                best = (delta, s)
    return best


def stats(seq):
    if not seq:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = list(seq)
    return {
        "n": len(pnls),
        "wr": round(sum(p > 0 for p in pnls) / len(pnls), 3),
        "avg": round(sum(pnls) / len(pnls), 1),
        "total": round(sum(pnls), 1),
    }


def analyse_account(label, params, spy_df, vix_df, is_days, oos_days, bull_sigs):
    print(f"\n{'='*60}")
    print(f"ACCOUNT: {label}")
    print(f"{'='*60}")

    for split, days in [("IS", is_days), ("OOS", oos_days)]:
        r = run_backtest(spy_df, vix_df, start_date=days[0], end_date=days[-1], **params)
        bears = bear_trades(r.trades)
        print(f"\n[{split}] Bear trades: {len(bears)}")

        co_fire = []     # bears where BULL div fired within 6 bars of exit
        no_fire = []     # bears where no BULL div near exit

        for t in bears:
            # Use exit_time_et if available, else entry + rough holding time
            try:
                xt = t.exit_time_et
            except AttributeError:
                xt = None
            if xt is None:
                no_fire.append(t.dollar_pnl)
                continue
            # Normalize tz
            if hasattr(xt, 'tzinfo') and xt.tzinfo is not None:
                xt = xt.replace(tzinfo=None)
            match = nearest_bull_div(xt, bull_sigs, window_bars=6)
            if match:
                co_fire.append((t.dollar_pnl, t, match))
            else:
                no_fire.append(t.dollar_pnl)

        sc_co = stats([x[0] for x in co_fire])
        sc_no = stats(no_fire)

        print(f"  BULL-div co-firing within 6 bars of exit: n={sc_co['n']} WR={sc_co['wr']:.1%} avg={sc_co['avg']:+.0f} total={sc_co['total']:+.0f}")
        print(f"  No BULL-div co-firing:                   n={sc_no['n']} WR={sc_no['wr']:.1%} avg={sc_no['avg']:+.0f} total={sc_no['total']:+.0f}")
        lift = sc_co['avg'] - sc_no['avg']
        print(f"  Avg P&L lift (co-fire vs no-fire): {lift:+.0f} per trade")

        if co_fire:
            print(f"\n  Co-fire detail:")
            print(f"  {'date':<10} {'exit_T':<6} {'pnl':>7}  bars_ago  signal_dt")
            for pnl, t, (delta, sig_dt) in sorted(co_fire, key=lambda x: x[1].entry_time_et):
                bars = int(delta.total_seconds() / 60 / BAR_MINUTES)
                try:
                    xt = t.exit_time_et
                    if hasattr(xt, 'tzinfo') and xt.tzinfo is not None:
                        xt = xt.replace(tzinfo=None)
                    exit_str = xt.strftime('%H:%M')
                except Exception:
                    exit_str = '??:??'
                print(f"  {str(t.entry_time_et.date()):<10} {exit_str:<6} {pnl:>+7.0f}  {bars:>4} bars  {sig_dt.strftime('%Y-%m-%d %H:%M')}")

        # Additional window sizes
        print(f"\n  Window sensitivity (co-fire WR vs no-fire WR):")
        for wbars in [2, 3, 6, 10]:
            coW = []; noW = []
            for t in bears:
                try:
                    xt = t.exit_time_et
                except AttributeError:
                    noW.append(t.dollar_pnl)
                    continue
                if xt is None:
                    noW.append(t.dollar_pnl)
                    continue
                if hasattr(xt, 'tzinfo') and xt.tzinfo is not None:
                    xt = xt.replace(tzinfo=None)
                m = nearest_bull_div(xt, bull_sigs, window_bars=wbars)
                if m:
                    coW.append(t.dollar_pnl)
                else:
                    noW.append(t.dollar_pnl)
            scW = stats(coW); snW = stats(noW)
            liftW = scW['avg'] - snW['avg']
            print(f"  w={wbars:2d}bars  co-fire: n={scW['n']:3} WR={scW['wr']:.1%} avg={scW['avg']:+.0f} | "
                  f"no-fire: n={snW['n']:3} WR={snW['wr']:.1%} avg={snW['avg']:+.0f} | lift={liftW:+.0f}")

    return {"label": label}


def main():
    print("=" * 70)
    print("RSI DIVERGENCE BULL EXIT-ENHANCER ANALYSIS")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))

    from collections import Counter
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES_SET]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]

    bull_sigs = load_bull_signals()
    print(f"BULL divergence signals loaded: {len(bull_sigs)}")
    print(f"Signal range: {bull_sigs[0].date()} -> {bull_sigs[-1].date()}")
    print(f"IS: {len(is_days)} days | OOS: {len(oos_days)} days")

    results = []
    for label, params in [("AGG", AGG_PARAMS), ("SAFE", SAFE_PARAMS)]:
        r = analyse_account(label, params, spy_df, vix_df, is_days, oos_days, bull_sigs)
        results.append(r)

    print("\n" + "=" * 70)
    print("SUMMARY & RECOMMENDATION")
    print("=" * 70)
    print("""
Evaluation criteria for adopting BULL divergence as bear early-exit signal:
  1. Co-fire exits have WORSE avg P&L than no-fire exits (signal fires on losing exits)
  2. Sufficient co-fire events (n>=10 IS, n>=3 OOS) for reliability
  3. Consistent across both accounts and both splits

If co-fire correlates with WORSE exits: BULL divergence = early exit signal (cut the loser)
If co-fire correlates with BETTER exits: BULL divergence = hold (the exit is already good)
If no correlation: BULL divergence has no predictive value for exit quality
""")

    out = {
        "task": "rsi-div-bear-exit-analysis",
        "scan_date": "2026-05-21",
        "bull_sig_count": len(bull_sigs),
        "accounts_analyzed": [r["label"] for r in results],
        "run_date": "2026-06-18",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("RSI DIVERGENCE ANALYSIS COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
