"""
SPY overnight gap gate A/B scorecard.

Hypothesis: BEARISH_REVERSAL setups underperform on days with a large positive
overnight gap (today_open - prev_close > X%). Extended gap-up opens = price already
extended; mean-reversion back up less likely to sustain; bear entries in first hour
run into gap-fill buyers.

Mechanism: compute (spy_open - spy_prev_close) / spy_prev_close for each trade date.
Bucket by gap size. Test blocking bear entries when gap > threshold.

Corrected baseline (through Rank 35):
  block_level_rejection=True + block_elite_bull (VIX15-17.5) +
  premium_stop_pct_bear=-0.10 + vix_bull_max=18.0 + time_stop_minutes_before_close=20
  + tp1_qty_fraction=0.667 + no_trade_before=09:35 + midday_trendline_gate=True
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_S = dt.date(2025, 1, 2)
IS_E = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 16)

BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)


def _compute_daily_gaps(spy_df: pd.DataFrame) -> dict:
    """Compute overnight gap % for each RTH date.

    gap_pct = (first_9:30_bar_open - prior_day_last_bar_close) / prior_day_last_bar_close * 100
    """
    spy = spy_df.copy()
    # Parse timestamp — handle both tz-aware and tz-naive
    spy["ts"] = pd.to_datetime(spy.iloc[:, 0], utc=True, errors="coerce")
    if spy["ts"].isna().all():
        spy["ts"] = pd.to_datetime(spy.iloc[:, 0], errors="coerce")

    # Convert to ET
    try:
        spy["ts_et"] = spy["ts"].dt.tz_convert("America/New_York")
    except Exception:
        spy["ts_et"] = spy["ts"]

    spy["date"] = spy["ts_et"].dt.date
    spy["hour"] = spy["ts_et"].dt.hour
    spy["minute"] = spy["ts_et"].dt.minute

    # Close column — try to find it
    close_col = None
    for c in spy.columns:
        if str(c).lower() == "close":
            close_col = c
            break
    if close_col is None:
        # Try positional — OHLCV
        close_col = spy.columns[4]

    open_col = None
    for c in spy.columns:
        if str(c).lower() == "open":
            open_col = c
            break
    if open_col is None:
        open_col = spy.columns[1]

    # RTH open bar (09:30 ET) for each date
    rth_open = spy[(spy["hour"] == 9) & (spy["minute"] == 30)].copy()
    rth_open = rth_open.groupby("date")[open_col].first()

    # Prior day RTH close = last bar before 16:00 ET
    rth_bars = spy[(spy["hour"] >= 9) & (spy["hour"] < 16)].copy()
    rth_close = rth_bars.groupby("date")[close_col].last()

    # Gap: align rth_open[d] with rth_close[d-1]
    dates = sorted(set(rth_open.index) & set(rth_close.index))
    gaps = {}
    for i in range(1, len(dates)):
        d = dates[i]
        d_prev = dates[i - 1]
        if d in rth_open.index and d_prev in rth_close.index:
            today_open = rth_open[d]
            prev_close = rth_close[d_prev]
            if prev_close > 0:
                gaps[d] = (today_open - prev_close) / prev_close * 100.0

    return gaps


def gap_bucket(gap_pct: float) -> str:
    if gap_pct < -1.0:
        return "GAP_DN>1%"
    elif gap_pct < -0.3:
        return "GAP_DN 0.3-1%"
    elif gap_pct < 0.0:
        return "FLAT_DN"
    elif gap_pct < 0.3:
        return "FLAT_UP"
    elif gap_pct < 0.7:
        return "GAP_UP 0.3-0.7%"
    elif gap_pct < 1.0:
        return "GAP_UP 0.7-1%"
    else:
        return "GAP_UP>1%"


def analyze_gap_breakdown(spy_df: pd.DataFrame, vix_df: pd.DataFrame,
                           daily_gaps: dict, start: dt.date, end: dt.date,
                           label: str) -> tuple:
    result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **BASE_KWARGS)
    total_pnl = sum(t.dollar_pnl for t in result.trades)
    n = len(result.trades)
    print(f"\n=== {label} BASELINE ===")
    print(f"  n_trades={n} pnl={total_pnl:+.0f}")

    # Bucket trades by entry date gap
    buckets: dict = {}
    no_gap_dates = 0
    for t in result.trades:
        entry_time = getattr(t, "entry_time_et", None)
        if entry_time is None:
            no_gap_dates += 1
            continue
        if hasattr(entry_time, "date"):
            d = entry_time.date()
        else:
            try:
                d = pd.to_datetime(entry_time).date()
            except Exception:
                no_gap_dates += 1
                continue
        gap = daily_gaps.get(d)
        if gap is None:
            no_gap_dates += 1
            continue
        bkt = gap_bucket(gap)
        buckets.setdefault(bkt, []).append((t, gap))

    print(f"\n  By overnight gap bucket (trades matched={n - no_gap_dates}, unmatched={no_gap_dates}):")
    bkt_order = ["GAP_DN>1%", "GAP_DN 0.3-1%", "FLAT_DN", "FLAT_UP",
                 "GAP_UP 0.3-0.7%", "GAP_UP 0.7-1%", "GAP_UP>1%"]
    for bkt in bkt_order:
        trades = buckets.get(bkt, [])
        if not trades:
            continue
        bkt_pnl = sum(t.dollar_pnl for t, _ in trades)
        wins = sum(1 for t, _ in trades if t.dollar_pnl > 0)
        wr = wins / len(trades) if trades else 0
        avg = bkt_pnl / len(trades)
        print(f"    {bkt:<20}: n={len(trades):3d} WR={wr:.0%} pnl={bkt_pnl:+.0f} avg={avg:+.0f}")

    return result, buckets


def run_gap_threshold_sweep(spy_df: pd.DataFrame, vix_df: pd.DataFrame,
                             daily_gaps: dict) -> list:
    """Block bear trades when gap_pct >= threshold. Test range of thresholds."""
    print("\n\n=== GAP GATE THRESHOLD SWEEP (IS) ===")
    base = run_backtest(spy_df, vix_df, start_date=IS_S, end_date=IS_E, **BASE_KWARGS)
    base_pnl = sum(t.dollar_pnl for t in base.trades)
    print(f"BASE: n={len(base.trades)} pnl={base_pnl:+.0f}")

    thresholds = [0.3, 0.5, 0.7, 1.0, 1.5]
    results = []
    for thresh in thresholds:
        blocked_pnl = 0
        n_blocked = 0
        for t in base.trades:
            entry_time = getattr(t, "entry_time_et", None)
            if entry_time is None:
                continue
            if hasattr(entry_time, "date"):
                d = entry_time.date()
            else:
                try:
                    d = pd.to_datetime(entry_time).date()
                except Exception:
                    continue
            gap = daily_gaps.get(d, 0.0)
            side = getattr(t, "side", "?")
            # Only block BEAR entries (puts) on gap-up days
            if side == "P" and gap >= thresh:
                blocked_pnl += t.dollar_pnl
                n_blocked += 1
        cand_pnl = base_pnl - blocked_pnl
        delta = cand_pnl - base_pnl
        status = "POS" if delta > 0 else "NEG"
        print(f"  gap>={thresh:.1f}%: blocked n={n_blocked:3d} pnl={blocked_pnl:+.0f} delta={delta:+.0f} [{status}]")
        results.append({"threshold": thresh, "n_blocked": n_blocked,
                        "blocked_pnl": blocked_pnl, "is_delta": delta})
    return results


def run_full_ab(spy_df: pd.DataFrame, vix_df: pd.DataFrame,
                daily_gaps: dict, threshold: float) -> dict:
    """Full IS + OOS + sub-window A/B for bear-only gap gate."""
    print(f"\n\n=== FULL A/B: block BEAR trades when gap >= {threshold:.1f}% ===")

    def candidate_delta(result):
        blocked_pnl = 0
        n_blocked = 0
        for t in result.trades:
            entry_time = getattr(t, "entry_time_et", None)
            if entry_time is None:
                continue
            if hasattr(entry_time, "date"):
                d = entry_time.date()
            else:
                try:
                    d = pd.to_datetime(entry_time).date()
                except Exception:
                    continue
            gap = daily_gaps.get(d, 0.0)
            side = getattr(t, "side", "?")
            if side == "P" and gap >= threshold:
                blocked_pnl += t.dollar_pnl
                n_blocked += 1
        return -blocked_pnl, n_blocked

    is_base = run_backtest(spy_df, vix_df, start_date=IS_S, end_date=IS_E, **BASE_KWARGS)
    is_base_pnl = sum(t.dollar_pnl for t in is_base.trades)
    is_delta, is_n_blocked = candidate_delta(is_base)

    oos_base = run_backtest(spy_df, vix_df, start_date=OOS_S, end_date=OOS_E, **BASE_KWARGS)
    oos_base_pnl = sum(t.dollar_pnl for t in oos_base.trades)
    oos_delta, oos_n_blocked = candidate_delta(oos_base)

    n_is = len(is_base.trades)
    n_oos = len(oos_base.trades)
    print(f"  IS:  n={n_is} base={is_base_pnl:+.0f} n_blocked={is_n_blocked} delta={is_delta:+.0f}")
    print(f"  OOS: n={n_oos} base={oos_base_pnl:+.0f} n_blocked={oos_n_blocked} delta={oos_delta:+.0f}")

    wf = None
    if is_n_blocked > 0 and oos_n_blocked > 0 and is_delta != 0:
        wf_norm = (oos_delta / n_oos) / (is_delta / n_is)
        wf = wf_norm
        print(f"  WF_norm={wf:.3f} (gate=0.70)")
    elif is_n_blocked > 0 and oos_n_blocked == 0:
        print(f"  WARNING: n_oos_blocked=0 — WF inconclusive")
    else:
        print(f"  WARNING: is_n_blocked={is_n_blocked} — insufficient IS data")

    # Sub-windows
    windows = [
        ("W1_2025H1", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
        ("W2_2025H2", dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
        ("W3_Q12026", dt.date(2026, 1, 2), dt.date(2026, 3, 31)),
        ("W4_Apr26",  dt.date(2026, 4, 1), dt.date(2026, 5, 7)),
    ]
    print(f"\n  IS sub-windows:")
    hurt = 0
    for name, ws, we in windows:
        wr = run_backtest(spy_df, vix_df, start_date=ws, end_date=we, **BASE_KWARGS)
        sw_delta, sw_blocked = candidate_delta(wr)
        verdict = "HELP" if sw_delta > 0 else "FLAT" if sw_delta == 0 else "HURT"
        if verdict == "HURT":
            hurt += 1
        print(f"    {name}: n_blocked={sw_blocked} delta={sw_delta:+.0f} -> {verdict}")
    print(f"  SW hurt: {hurt}/4 (gate: <=1)")

    oos_pos = oos_delta > 0
    sw_ok = hurt <= 1
    print(f"\n  VERDICT: OOS_pos={oos_pos} SW_ok={sw_ok} WF={'PASS' if wf and wf >= 0.70 else 'FAIL'} ({wf:.3f if wf else 'N/A'})")
    if oos_pos and sw_ok and (wf is None or wf >= 0.70):
        print(f"  -> CANDIDATE: block bear entries when gap >= {threshold:.1f}%")
    elif oos_pos and sw_ok:
        print(f"  -> ECONOMIC SIGNAL (OOS positive, SW ok, WF structural n_oos_blocked={oos_n_blocked})")
    else:
        print(f"  -> REJECT")

    return {"threshold": threshold, "is_delta": is_delta, "oos_delta": oos_delta,
            "is_n_blocked": is_n_blocked, "oos_n_blocked": oos_n_blocked,
            "wf": wf, "sw_hurt": hurt}


def main():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    print("Computing daily gaps...")
    daily_gaps = _compute_daily_gaps(spy)
    print(f"  {len(daily_gaps)} trading dates with gap data")

    # Quick distribution
    gaps_list = list(daily_gaps.values())
    pos_gaps = [g for g in gaps_list if g > 0.3]
    neg_gaps = [g for g in gaps_list if g < -0.3]
    big_pos = [g for g in gaps_list if g > 0.7]
    print(f"  gap>0.3%: {len(pos_gaps)} days | gap>0.7%: {len(big_pos)} days | gap<-0.3%: {len(neg_gaps)} days")

    # Step 1: breakdown analysis
    analyze_gap_breakdown(spy, vix, daily_gaps, IS_S, IS_E, "IS")
    analyze_gap_breakdown(spy, vix, daily_gaps, OOS_S, OOS_E, "OOS")

    # Step 2: threshold sweep
    sweep = run_gap_threshold_sweep(spy, vix, daily_gaps)

    # Step 3: full A/B for best positive IS threshold
    print("\n\nSweep summary:")
    best = max(sweep, key=lambda r: r["is_delta"])
    for r in sweep:
        status = "POS" if r["is_delta"] > 0 else "NEG"
        print(f"  gap>={r['threshold']:.1f}%: n_blocked={r['n_blocked']:3d} IS_delta={r['is_delta']:+.0f} [{status}]")

    print(f"\nBest IS candidate: gap>={best['threshold']:.1f}% (IS_delta={best['is_delta']:+.0f})")

    if best["is_delta"] > 0 and best["n_blocked"] >= 3:
        run_full_ab(spy, vix, daily_gaps, best["threshold"])
    else:
        print("No viable IS candidate (IS negative or n_blocked < 3). Gap gate does not help.")


if __name__ == "__main__":
    main()
