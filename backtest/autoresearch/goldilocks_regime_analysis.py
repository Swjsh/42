"""
GOLDILOCKS Regime Classifier Analysis

Hypothesis: Profitable periods for BEARISH_REVERSAL share one pattern — VIX declining
from a prior spike. This creates a "Goldilocks" environment: market is choppy/at resistance
(VIX elevated enough to suppress runaway rallies), but not in free-fall panic.

Classifier: GOLDILOCKS = (prior_5d_VIX_max > 30) AND (today_VIX < prior_5d_VIX_max * 0.65)

Prior_5d_VIX_max = max of the 5 PRIOR daily VIX closes (no look-ahead).
Decay threshold 0.65 = current VIX must be at most 65% of the spike peak.

Test: do the 3 good IS clusters (Q3-25 BoJ, Feb-26 correction, OOS May-26) all fall into
GOLDILOCKS? Do the 3 catastrophic months (Apr-26, Mar-26, Mar-25) fall into NOT_GOLDILOCKS?

Runs PURE ANALYSIS (read-only). Does not modify params.json or heartbeat.md.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt
import collections

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

# Production params (post-Rank-31, post-L117)
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


def _load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    spy = pd.read_csv(SPY_FILE)
    vix = pd.read_csv(VIX_FILE)
    return spy, vix


def _build_vix_daily(vix_df: pd.DataFrame) -> dict[dt.date, float]:
    """Daily VIX close (last bar of each day) — no look-ahead."""
    ts = pd.to_datetime(vix_df["timestamp_et"], utc=True)
    vix_df = vix_df.copy()
    vix_df["_date"] = ts.dt.date
    by_day = vix_df.groupby("_date")["close"].last()
    return {d: float(c) for d, c in by_day.items()}


def _goldilocks(today: dt.date, vix_daily: dict[dt.date, float],
                spike_threshold: float = 30.0, decay_pct: float = 0.65) -> tuple[bool, str]:
    """
    Returns (is_goldilocks, reason_str).
    prior_5d = max(VIX closes from the 5 trading days BEFORE today).
    GOLDILOCKS = prior_5d_max > spike_threshold AND today_vix < prior_5d_max * decay_pct
    """
    all_dates = sorted(vix_daily.keys())
    today_vix = vix_daily.get(today, None)
    if today_vix is None:
        return False, "NO_VIX_TODAY"

    prior_dates = [d for d in all_dates if d < today][-5:]
    if len(prior_dates) < 3:
        return False, "INSUFFICIENT_PRIOR_DATA"

    prior_vix_vals = [vix_daily[d] for d in prior_dates if d in vix_daily]
    if not prior_vix_vals:
        return False, "NO_PRIOR_VIX"

    prior_5d_max = max(prior_vix_vals)
    decay_floor = prior_5d_max * decay_pct

    has_spike = prior_5d_max > spike_threshold
    is_declining = today_vix < decay_floor

    if has_spike and is_declining:
        return True, f"GOLDILOCKS: prior_max={prior_5d_max:.1f} today={today_vix:.1f} floor={decay_floor:.1f}"
    elif not has_spike:
        return False, f"NO_SPIKE: prior_max={prior_5d_max:.1f}<{spike_threshold}"
    else:
        return False, f"NOT_DECLINING: today={today_vix:.1f}>={decay_floor:.1f} (prior_max={prior_5d_max:.1f})"


def _run_window(spy_df: pd.DataFrame, vix_df: pd.DataFrame,
                start: dt.date, end: dt.date, label: str) -> list:
    result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **BASE)
    return result.trades


def _monthly_stats(trades: list, vix_daily: dict, label: str) -> None:
    by_month: dict[str, list] = collections.defaultdict(list)
    for t in trades:
        d = t.entry_time_et.date()
        m = d.strftime("%Y-%m")
        by_month[m].append(t.dollar_pnl)

    print(f"\n{label} — Monthly P&L breakdown with GOLDILOCKS tag:")
    print(f"{'Month':>10}  {'n':>5}  {'P&L':>10}  {'WR%':>6}  {'GL?':>15}  Reason")
    print("-" * 95)

    total_gl_n, total_gl_pnl = 0, 0.0
    total_no_n, total_no_pnl = 0, 0.0

    for m in sorted(by_month.keys()):
        pnls = by_month[m]
        n = len(pnls)
        total_pnl = sum(pnls)
        wr = sum(1 for p in pnls if p > 0) / n * 100 if n > 0 else 0

        # representative date = 15th of that month
        yr, mo = int(m[:4]), int(m[5:7])
        rep_date = dt.date(yr, mo, 15)
        is_gl, reason = _goldilocks(rep_date, vix_daily)
        tag = "GOLDILOCKS" if is_gl else "NOT"

        flag = " *** CATASTROPHIC" if total_pnl < -2000 else (" *** STRONG" if total_pnl > 2000 else "")
        print(f"{m:>10}  {n:>5}  {total_pnl:>+10.0f}  {wr:>5.1f}%  {tag:>15}  {reason[:40]}{flag}")

        if is_gl:
            total_gl_n += n
            total_gl_pnl += total_pnl
        else:
            total_no_n += n
            total_no_pnl += total_pnl

    print()
    print(f"  GOLDILOCKS months:  n={total_gl_n:>4}  total_pnl={total_gl_pnl:>+9.0f}")
    print(f"  NOT months:         n={total_no_n:>4}  total_pnl={total_no_pnl:>+9.0f}")
    if total_gl_n > 0 and total_no_n > 0:
        avg_gl = total_gl_pnl / total_gl_n
        avg_no = total_no_pnl / total_no_n
        print(f"  Avg per trade:      GL={avg_gl:>+7.1f}    NOT={avg_no:>+7.1f}   ratio={avg_gl/avg_no:.2f}x")


def _size_simulation(trades: list, vix_daily: dict, size_mult: float = 1.5) -> None:
    """Simulate 1.5× sizing when GOLDILOCKS, 1× otherwise. Pure P&L arithmetic."""
    base_pnl = sum(t.dollar_pnl for t in trades)
    sized_pnl = 0.0
    gl_count, no_count = 0, 0
    for t in trades:
        d = t.entry_time_et.date()
        is_gl, _ = _goldilocks(d, vix_daily)
        mult = size_mult if is_gl else 1.0
        sized_pnl += t.dollar_pnl * mult
        if is_gl:
            gl_count += 1
        else:
            no_count += 1

    delta = sized_pnl - base_pnl
    print(f"\n  SIZING SIMULATION ({size_mult}× when GOLDILOCKS):")
    print(f"    base_pnl={base_pnl:>+9.2f}  sized_pnl={sized_pnl:>+9.2f}  delta={delta:>+9.2f}")
    print(f"    GOLDILOCKS trades: {gl_count}  NOT trades: {no_count}")
    print(f"    Note: This assumes sizing up doesn't change which trades fill or exit times.")


def _print_trade_detail(trades: list, vix_daily: dict, label: str) -> None:
    print(f"\n{label} — Trade-level GOLDILOCKS tags:")
    print(f"{'Date':>12}  {'P&L':>10}  {'Exit':>30}  GL?")
    print("-" * 75)
    for t in trades:
        d = t.entry_time_et.date()
        is_gl, _ = _goldilocks(d, vix_daily)
        tag = "GL" if is_gl else "--"
        pnl = t.dollar_pnl
        ex = (t.exit_reason.name if t.exit_reason else "?")[:28]
        print(f"{str(d):>12}  {pnl:>+10.2f}  {ex:>30}  {tag}")


if __name__ == "__main__":
    print("=" * 95)
    print("GOLDILOCKS REGIME CLASSIFIER ANALYSIS")
    print("Hypothesis: prior_5d_VIX_max > 30 AND today_VIX < prior_max × 0.65 = profitable regime")
    print("=" * 95)

    print("\n[1/3] Loading data...")
    spy_df, vix_df = _load_data()
    vix_daily = _build_vix_daily(vix_df)
    print(f"  VIX daily dates: {min(vix_daily.keys())} to {max(vix_daily.keys())}  ({len(vix_daily)} days)")

    print("\n[2/3] Running IS backtest (2025-01-02 to 2026-05-07)...")
    is_trades = _run_window(spy_df, vix_df, IS_START, IS_END, "IS")
    is_pnl = sum(t.dollar_pnl for t in is_trades)
    print(f"  IS: n={len(is_trades)}  pnl={is_pnl:+.2f}")

    print("\n[3/3] Running OOS backtest (2026-05-08 to 2026-05-22)...")
    oos_trades = _run_window(spy_df, vix_df, OOS_START, OOS_END, "OOS")
    oos_pnl = sum(t.dollar_pnl for t in oos_trades)
    print(f"  OOS: n={len(oos_trades)}  pnl={oos_pnl:+.2f}")

    # ── Monthly breakdown ─────────────────────────────────────────────────────
    _monthly_stats(is_trades, vix_daily, "IS")
    _monthly_stats(oos_trades, vix_daily, "OOS")

    # ── Trade-level OOS detail ─────────────────────────────────────────────────
    _print_trade_detail(oos_trades, vix_daily, "OOS")

    # ── Sizing simulation ─────────────────────────────────────────────────────
    print("\n" + "=" * 95)
    print("SIZING SIMULATION — what if we scaled 1.5× in GOLDILOCKS regime?")
    _size_simulation(is_trades, vix_daily, 1.5)
    _size_simulation(oos_trades, vix_daily, 1.5)

    # ── Threshold sweep ───────────────────────────────────────────────────────
    print("\n" + "=" * 95)
    print("THRESHOLD SWEEP — prior_5d_max threshold [25, 30, 35, 40] × decay [0.60, 0.65, 0.70]")
    print(f"{'spike_thr':>10}  {'decay':>6}  {'GL_n':>5}  {'GL_pnl':>10}  {'NO_n':>5}  {'NO_pnl':>10}  GL_avg  NO_avg")
    print("-" * 80)
    for spike_thr in [25.0, 28.0, 30.0, 33.0, 35.0, 40.0]:
        for decay in [0.60, 0.65, 0.70, 0.75]:
            gl_n, gl_pnl = 0, 0.0
            no_n, no_pnl = 0, 0.0
            for t in is_trades:
                d = t.entry_time_et.date()
                is_gl, _ = _goldilocks(d, vix_daily, spike_thr, decay)
                if is_gl:
                    gl_n += 1
                    gl_pnl += t.dollar_pnl
                else:
                    no_n += 1
                    no_pnl += t.dollar_pnl
            avg_gl = gl_pnl / gl_n if gl_n > 0 else 0
            avg_no = no_pnl / no_n if no_n > 0 else 0
            print(f"{spike_thr:>10.0f}  {decay:>6.2f}  {gl_n:>5}  {gl_pnl:>+10.0f}  {no_n:>5}  {no_pnl:>+10.0f}  "
                  f"{avg_gl:>+7.1f}  {avg_no:>+7.1f}")

    print("\nANALYSIS COMPLETE.")
