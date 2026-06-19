"""
VIX-Conditional Premium Stop Sweep — BEARISH_REVERSAL

Hypothesis: The -20% premium stop misfires in VIX>30 environments because initial
bounces are larger (high-vol intraday swings), triggering the stop before the
directional move continues. Relaxing the stop only in VIX>30 environments
should reduce per-trade losses on catastrophic days (Apr 2026, Liberation Day)
while keeping normal-VIX protection intact.

Method:
  - Sweep premium_stop_pct_bear from -0.10 to -0.40 globally.
  - For each stop, split trade P&L by VIX regime: VIX>30 days vs VIX<=30 days.
  - Key question: At what stop level do HIGH-VIX days improve WITHOUT degrading
    LOW-VIX days? That's the signal for a VIX-conditional stop approach.
  - Run the same analysis on OOS. Compute WF for high-VIX and low-VIX separately.

Security: Read-only on all production state. No Alpaca calls. Free tier only.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backtest.lib.orchestrator import run_backtest
from backtest.lib.anchor_check import anchor_no_regression  # L160 sign-correct G5

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

VIX_HIGH_THR = 30.0  # the "catastrophic" regime threshold

# Production params (post-Rank-31, excluding the stop we're sweeping)
BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)

BEAR_STOPS = [-0.10, -0.15, -0.20, -0.25, -0.30, -0.35, -0.40]

# J anchor days for regression check
J_WINNERS  = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS   = {dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 5, 7)}


def _load_daily_vix(vix_file: pathlib.Path) -> dict[dt.date, float]:
    """Return {date: vix_close} from VIX 5m data (use 09:35 bar as 'daily VIX')."""
    df = pd.read_csv(vix_file)
    # utc=True handles mixed EST/EDT offsets; convert to ET then strip tz for naive datetimes
    df["timestamp_et"] = (
        pd.to_datetime(df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    df["date"]   = df["timestamp_et"].dt.date
    df["hour"]   = df["timestamp_et"].dt.hour
    df["minute"] = df["timestamp_et"].dt.minute
    # Use 09:35 bar (first complete RTH bar) as the daily VIX reading
    morning = df[(df["hour"] == 9) & (df["minute"] == 35)].copy()
    daily = morning.groupby("date")["close"].first()
    return daily.to_dict()


def _tz_key(t):
    et = t.entry_time_et
    if getattr(et, "tzinfo", None) is not None:
        return et.replace(tzinfo=None)
    return et


def _split_by_vix(trades: list, daily_vix: dict) -> tuple[list, list]:
    """Return (high_vix_trades, low_vix_trades) split at VIX_HIGH_THR."""
    hi, lo = [], []
    for t in trades:
        d = _tz_key(t).date()
        vix = daily_vix.get(d, None)
        if vix is None:
            lo.append(t)  # no VIX data — default to low
        elif vix > VIX_HIGH_THR:
            hi.append(t)
        else:
            lo.append(t)
    return hi, lo


def _pnl_summary(trades: list, label: str) -> dict:
    if not trades:
        return {"label": label, "n": 0, "pnl": 0.0, "wr": 0.0}
    pnl = sum(t.dollar_pnl for t in trades)
    wr  = sum(1 for t in trades if t.dollar_pnl > 0) / len(trades)
    return {"label": label, "n": len(trades), "pnl": round(pnl, 2), "wr": round(wr, 3)}


def _anchor_pnl(trades: list, anchor_dates: set) -> float:
    return sum(
        t.dollar_pnl
        for t in trades
        if _tz_key(t).date() in anchor_dates
    )


if __name__ == "__main__":
    print("=" * 110)
    print("VIX-CONDITIONAL PREMIUM STOP SWEEP — BEARISH_REVERSAL")
    print(f"  VIX high-regime threshold: > {VIX_HIGH_THR}")
    print(f"  Bear stop sweep: {BEAR_STOPS}")
    print("=" * 110)

    print("\n[1/4] Loading data...")
    spy_df  = pd.read_csv(SPY_FILE)
    vix_df  = pd.read_csv(VIX_FILE)
    daily_vix = _load_daily_vix(VIX_FILE)

    hi_vix_days = {d for d, v in daily_vix.items() if v > VIX_HIGH_THR}
    print(f"  High-VIX days in data: {len(hi_vix_days)}")
    if hi_vix_days:
        sample = sorted(hi_vix_days)[:5]
        print(f"  Sample: {sample}")

    # ── IS baseline (stop=-0.20) ──────────────────────────────────────────────
    print("\n[2/4] Running IS baseline (bear_stop=-0.20)...")
    base_result = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                               premium_stop_pct_bear=-0.20, **BASE)
    base_trades = base_result.trades
    base_hi, base_lo = _split_by_vix(base_trades, daily_vix)
    base_hi_pnl = sum(t.dollar_pnl for t in base_hi)
    base_lo_pnl = sum(t.dollar_pnl for t in base_lo)
    base_tot    = base_hi_pnl + base_lo_pnl
    print(f"  IS total: n={len(base_trades)} pnl={base_tot:+.2f}")
    print(f"  IS high-VIX (>{VIX_HIGH_THR}): n={len(base_hi)} pnl={base_hi_pnl:+.2f}")
    print(f"  IS low-VIX:  n={len(base_lo)} pnl={base_lo_pnl:+.2f}")

    # ── OOS baseline ─────────────────────────────────────────────────────────
    print("\n[3/4] Running OOS baseline (bear_stop=-0.20)...")
    oos_base_result = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                                   premium_stop_pct_bear=-0.20, **BASE)
    oos_base_trades = oos_base_result.trades
    oos_base_hi, oos_base_lo = _split_by_vix(oos_base_trades, daily_vix)
    oos_base_hi_pnl = sum(t.dollar_pnl for t in oos_base_hi)
    oos_base_lo_pnl = sum(t.dollar_pnl for t in oos_base_lo)
    oos_base_tot    = oos_base_hi_pnl + oos_base_lo_pnl
    print(f"  OOS total: n={len(oos_base_trades)} pnl={oos_base_tot:+.2f}")
    print(f"  OOS high-VIX: n={len(oos_base_hi)} pnl={oos_base_hi_pnl:+.2f}")
    print(f"  OOS low-VIX:  n={len(oos_base_lo)} pnl={oos_base_lo_pnl:+.2f}")

    # ── Stop sweep ────────────────────────────────────────────────────────────
    print("\n[4/4] Sweeping bear stop values...")
    print(f"\n{'Stop':>8}  {'IS_hi_VIX':>11}  {'IS_lo_VIX':>11}  {'IS_total':>10}  {'IS_delta':>9}  "
          f"{'OOS_hi':>9}  {'OOS_lo':>9}  {'OOS_tot':>9}  {'OOS_delta':>10}  {'WF':>6}  Verdict")
    print("-" * 130)

    # Print baseline row
    print(f"{'BASELINE':>8}  {base_hi_pnl:>+11.0f}  {base_lo_pnl:>+11.0f}  {base_tot:>+10.0f}  {'—':>9}  "
          f"{oos_base_hi_pnl:>+9.0f}  {oos_base_lo_pnl:>+9.0f}  {oos_base_tot:>+9.0f}  {'—':>10}  {'—':>6}  —")

    results = []
    for stop in BEAR_STOPS:
        if stop == -0.20:
            continue  # already printed as baseline

        is_r   = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                              premium_stop_pct_bear=stop, **BASE)
        is_all = is_r.trades
        is_hi, is_lo = _split_by_vix(is_all, daily_vix)
        is_hi_pnl = sum(t.dollar_pnl for t in is_hi)
        is_lo_pnl = sum(t.dollar_pnl for t in is_lo)
        is_tot    = is_hi_pnl + is_lo_pnl
        is_delta  = is_tot - base_tot

        oos_r   = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                               premium_stop_pct_bear=stop, **BASE)
        oos_all = oos_r.trades
        oos_hi, oos_lo = _split_by_vix(oos_all, daily_vix)
        oos_hi_pnl = sum(t.dollar_pnl for t in oos_hi)
        oos_lo_pnl = sum(t.dollar_pnl for t in oos_lo)
        oos_tot    = oos_hi_pnl + oos_lo_pnl
        oos_delta  = oos_tot - oos_base_tot

        wf = oos_delta / is_delta if is_delta != 0 else float("inf")
        verdict = "PASS" if (oos_delta > 0 and wf >= 0.70) else ""
        if is_delta < 0 and oos_delta < 0:
            verdict = "BOTH_NEG"

        print(f"{stop:>8.2f}  {is_hi_pnl:>+11.0f}  {is_lo_pnl:>+11.0f}  {is_tot:>+10.0f}  {is_delta:>+9.0f}  "
              f"{oos_hi_pnl:>+9.0f}  {oos_lo_pnl:>+9.0f}  {oos_tot:>+9.0f}  {oos_delta:>+10.0f}  {wf:>6.3f}  {verdict}")

        results.append({
            "stop": stop,
            "is_hi": is_hi_pnl, "is_lo": is_lo_pnl, "is_tot": is_tot, "is_delta": is_delta,
            "oos_hi": oos_hi_pnl, "oos_lo": oos_lo_pnl, "oos_tot": oos_tot, "oos_delta": oos_delta,
            "wf": wf, "verdict": verdict,
        })

    # ── Anchor-day regression check ───────────────────────────────────────────
    print("\n" + "=" * 110)
    print("J ANCHOR-DAY REGRESSION CHECK (BASELINE vs best stop candidates)")

    for r in sorted(results, key=lambda x: x["oos_delta"], reverse=True)[:3]:
        stop = r["stop"]
        is_r = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                            premium_stop_pct_bear=stop, **BASE)
        is_trades = is_r.trades
        w_pnl = _anchor_pnl(is_trades, J_WINNERS)
        l_pnl = _anchor_pnl(is_trades, J_LOSERS)
        base_w = _anchor_pnl(base_trades, J_WINNERS)
        base_l = _anchor_pnl(base_trades, J_LOSERS)
        print(f"\n  stop={stop:+.2f}: winners={w_pnl:+.0f} (base={base_w:+.0f}, delta={w_pnl-base_w:+.0f})  "
              f"losers={l_pnl:+.0f} (base={base_l:+.0f}, delta={l_pnl-base_l:+.0f})")
        # L160: sign-correct anchor-no-regression on BOTH sides. The broken
        # `base * 0.90` form inverts for negative baselines (losers are negative,
        # and J-winner anchors can be negative in some regimes). "No regression"
        # = candidate is at most 10% worse than baseline in absolute dollars, which
        # reads correctly for winners (don't shrink) and losers (don't deepen).
        anchor_ok = (anchor_no_regression(base_w, w_pnl, 0.10)
                     and anchor_no_regression(base_l, l_pnl, 0.10))
        print(f"    Anchor {'OK' if anchor_ok else 'REGRESSION'}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 110)
    print("SUMMARY")
    passes = [r for r in results if r["verdict"] == "PASS"]
    if passes:
        best = max(passes, key=lambda r: r["oos_delta"])
        print(f"  PASS candidates: {len(passes)}")
        print(f"  Best: stop={best['stop']:+.2f}  OOS_delta={best['oos_delta']:+.0f}  WF={best['wf']:.3f}")
        print(f"  -> Consider VIX-conditional stop: use {best['stop']:+.2f} when daily VIX > {VIX_HIGH_THR}")
    else:
        print("  No PASS candidates — wider stops do not generalize.")
        print("  -> Per-day kill switch remains the correct and sufficient high-VIX protection.")
        print("  -> Hypothesis REFUTED: stop-width is not the primary driver of catastrophic losses.")

    print("\nANALYSIS COMPLETE.")
