"""
Level Distance Proximity Analysis — fixed version.

Prior bug: `if t.rejection_level` excluded trades with rejection_level==0.0
           (the sentinel for trendline-only, no named level).
           Fixed: `if t.rejection_level > 0.0`
Prior bug: Quartile code printed Q3 and Q4 using same q4 variable.
           Fixed: distinct variables q1/q2/q3/q4.

Question: do BEARISH_REJECTION entries within $0.25 of a named level
          have meaningfully higher WR than entries further away?

Also checks: does "tight proximity" (<$0.25) gate pass WF>=0.70 gate?

IS: 2025-01-02 to 2026-05-07
OOS: 2026-05-08 to 2026-06-16
"""
import datetime as dt
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

_SPY_DF: pd.DataFrame = None
_VIX_DF: pd.DataFrame = None


def _load_data():
    global _SPY_DF, _VIX_DF
    if _SPY_DF is None:
        print("Loading data...")
        _SPY_DF = pd.read_csv(MASTER_SPY)
        _VIX_DF = pd.read_csv(MASTER_VIX)
        print(f"SPY {len(_SPY_DF)} rows  VIX {len(_VIX_DF)} rows")

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    midday_trendline_gate_start_minutes=690,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.50,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)


def bucket(dist: float) -> str:
    if dist < 0.25:
        return "A_lt025"
    if dist < 0.50:
        return "B_025_050"
    if dist < 1.00:
        return "C_050_100"
    return "D_gt100"


def analyze_window(label: str, start: dt.date, end: dt.date):
    _load_data()
    result = run_backtest(
        _SPY_DF,
        _VIX_DF,
        start_date=start,
        end_date=end,
        **BASE_KWARGS,
    )
    fills = result.trades

    bear = [t for t in fills if "BEARISH" in t.setup]
    with_level = [t for t in bear if t.rejection_level is not None and t.rejection_level > 0.0]
    tl_only = [t for t in bear if not (t.rejection_level is not None and t.rejection_level > 0.0)]

    print(f"\n=== {label} ({start}..{end}) ===")
    print(f"Total fills: {len(fills)}  BEARISH: {len(bear)}  "
          f"with_level: {len(with_level)}  trendline_only: {len(tl_only)}")

    if not with_level:
        print("No trades with named level — skip.")
        return None

    # Distance = how far price was from the rejection level at entry
    by_bucket: dict[str, list] = {}
    for t in with_level:
        dist = abs(t.entry_spot - t.rejection_level)
        b = bucket(dist)
        by_bucket.setdefault(b, []).append(t)

    print(f"\nLevel-proximity breakdown (n={len(with_level)}):")
    print(f"{'Bucket':<14} {'n':>4} {'WR':>6} {'avg$':>8} {'total$':>10}")
    for bk in sorted(by_bucket):
        trades = by_bucket[bk]
        wins = [t for t in trades if t.dollar_pnl > 0]
        wr = len(wins) / len(trades) if trades else 0
        avg = mean(t.dollar_pnl for t in trades)
        tot = sum(t.dollar_pnl for t in trades)
        print(f"  {bk:<12} {len(trades):>4} {wr:>6.1%} {avg:>8.1f} {tot:>10.1f}")

    # Quartile split on distance
    sorted_trades = sorted(with_level, key=lambda t: abs(t.entry_spot - t.rejection_level))
    n = len(sorted_trades)
    q1 = sorted_trades[:n//4]
    q2 = sorted_trades[n//4:n//2]
    q3 = sorted_trades[n//2:3*n//4]
    q4 = sorted_trades[3*n//4:]

    print(f"\nQuartile split by level distance (n={n}):")
    for qname, qtrades in [("Q1 (closest)", q1), ("Q2", q2), ("Q3", q3), ("Q4 (farthest)", q4)]:
        if not qtrades:
            continue
        dists = [abs(t.entry_spot - t.rejection_level) for t in qtrades]
        wins = [t for t in qtrades if t.dollar_pnl > 0]
        wr = len(wins) / len(qtrades) if qtrades else 0
        avg = mean(t.dollar_pnl for t in qtrades)
        print(f"  {qname:<16} n={len(qtrades):>3}  dist=[{min(dists):.2f}, {max(dists):.2f}]  "
              f"WR={wr:.1%}  avg=${avg:.1f}")

    return by_bucket


def main():
    is_buckets = analyze_window("IS", IS_START, IS_END)
    oos_buckets = analyze_window("OOS", OOS_START, OOS_END)

    # Check if proximity gate would pass WF
    if is_buckets and oos_buckets:
        gate_label = "A_lt025"  # Block if distance >= $0.25 (keep only close entries)

        # A/B: baseline = all with_level; candidate = only A_lt025
        # This is confounded — blocking a distance bucket changes which trades we SKIP
        # A better A/B: add proximity gate to orchestrator (not done yet)
        # For now: just report whether the IS WR edge is real and replicated OOS

        is_close = is_buckets.get(gate_label, [])
        is_far = [t for bk, trades in is_buckets.items()
                  for t in trades if bk != gate_label]
        oos_close = oos_buckets.get(gate_label, [])

        def wr(trades): return sum(1 for t in trades if t.dollar_pnl > 0) / len(trades) if trades else 0

        print("\n=== PROXIMITY EDGE SUMMARY ===")
        print(f"IS  close (<$0.25) n={len(is_close):>3}  WR={wr(is_close):.1%}  "
              f"avg=${mean(t.dollar_pnl for t in is_close):.1f}" if is_close else "IS close n=0")
        print(f"IS  far   (>=$0.25) n={len(is_far):>3}  WR={wr(is_far):.1%}  "
              f"avg=${mean(t.dollar_pnl for t in is_far):.1f}" if is_far else "IS far n=0")
        print(f"OOS close (<$0.25) n={len(oos_close):>3}  WR={wr(oos_close):.1%}  "
              f"avg=${mean(t.dollar_pnl for t in oos_close):.1f}" if oos_close else "OOS close n=0")
        oos_far = [t for bk, trades in oos_buckets.items()
                   for t in trades if bk != gate_label]
        print(f"OOS far   (>=$0.25) n={len(oos_far):>3}  WR={wr(oos_far):.1%}  "
              f"avg=${mean(t.dollar_pnl for t in oos_far):.1f}" if oos_far else "OOS far n=0")

        if len(is_close) < 10:
            print("\nVERDICT: INSUFFICIENT SAMPLE (IS n<10) — no gate proposal.")
        else:
            wr_diff_is = wr(is_close) - wr(is_far)
            wr_diff_oos = wr(oos_close) - wr(oos_far) if oos_close and oos_far else None
            print(f"\nIS WR edge (close vs far): {wr_diff_is:+.1%}")
            if wr_diff_oos is not None:
                print(f"OOS WR edge (close vs far): {wr_diff_oos:+.1%}")
                if wr_diff_is > 0.08 and wr_diff_oos > 0.0:
                    print("VERDICT: EDGE REPLICATES OOS — build proximity gate candidate.")
                elif wr_diff_is > 0.08 and wr_diff_oos <= 0.0:
                    print("VERDICT: C22 — IS edge does not replicate OOS. No candidate.")
                else:
                    print("VERDICT: IS edge too small (<8pp). No candidate.")
            else:
                print("VERDICT: OOS sample too small for verdict.")


if __name__ == "__main__":
    main()
