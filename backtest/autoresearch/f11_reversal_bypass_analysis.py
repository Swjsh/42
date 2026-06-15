"""F11 HTF-latency analysis on reversal days.

Research question:
  On "reversal days" (session low before 11:00 ET + SPY recovers >=2.00 from that low
  within 2 hours), what is the median lag between the 5m ribbon achieving BULL spread >=30c
  and the 15m HTF stack clearing from BEAR -- and how many reversal days did F11 NEVER clear?

The 15m stack is approximated by resampling 5m bars into 15m bars, then computing
EMA(9) and EMA(21). BULL = EMA9 > EMA21, BEAR = EMA9 < EMA21.

This is a *structural analysis*, not a full backtest -- we measure:
  1. Reversal day count (16 months)
  2. Per-reversal-day: lag in minutes from ribbon-BULL to HTF-BEAR-cleared
  3. Proxy WR: did SPY continue up >=1.00 in the next 12 bars (60 min) after the ribbon
     achieved BULL on a reversal day when HTF was still BEAR?
  4. OP-16 check: do J's 3 winner days (4/29, 5/01, 5/04) qualify as reversal days?
     Would F11 bypass have helped or hurt?

Usage:
    python backtest/autoresearch/f11_reversal_bypass_analysis.py
"""
from __future__ import annotations

import os
import sys
import datetime as dt
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "backtest" / "data"

# ── EMA helper (mirrors ribbon.py approach) ──────────────────────────────────

def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    """SMA-seeded EMA, NaN for warmup bars."""
    n = len(arr)
    if n < period:
        return np.full(n, np.nan)
    alpha = 2.0 / (period + 1.0)
    out = np.full(n, np.nan)
    out[period - 1] = arr[:period].mean()
    for i in range(period, n):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


def _ribbon_5m(closes: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute 5m ribbon: fast(13), pivot(20), slow(48) + spread_cents.

    Returns (fast, pivot, slow, spread_cents) arrays, NaN for warmup.
    Matches periods from backtest/lib/ribbon_config.json.
    """
    fast = _ema(closes, 13)
    pivot = _ema(closes, 20)
    slow = _ema(closes, 48)
    with np.errstate(invalid="ignore"):
        spread = (np.maximum(fast, np.maximum(pivot, slow))
                  - np.minimum(fast, np.minimum(pivot, slow))) * 100.0  # cents
    return fast, pivot, slow, spread


def _htf_15m_stack(closes_5m: np.ndarray) -> np.ndarray:
    """Approximate 15m HTF EMA9/EMA21 stack using resampled closes.

    Returns an array aligned to the 5m bar index, carrying forward the most
    recent 15m bar's stack classification: 'BULL' | 'BEAR' | 'MIXED' | 'WARMUP'.
    """
    n = len(closes_5m)
    # Build 15m bar closes: every 3rd 5m bar (bar index 2, 5, 8, ...)
    bar_15m_idx = list(range(2, n, 3))  # index of the closing bar for each 15m period
    if len(bar_15m_idx) < 2:
        return np.array(["WARMUP"] * n, dtype=object)

    closes_15m = closes_5m[bar_15m_idx]
    ema9 = _ema(closes_15m, 9)
    ema21 = _ema(closes_15m, 21)

    # Build stack label per 15m bar
    stacks_15m = []
    for i in range(len(closes_15m)):
        if np.isnan(ema9[i]) or np.isnan(ema21[i]):
            stacks_15m.append("WARMUP")
        elif ema9[i] > ema21[i]:
            stacks_15m.append("BULL")
        elif ema9[i] < ema21[i]:
            stacks_15m.append("BEAR")
        else:
            stacks_15m.append("MIXED")

    # Forward-fill: each 15m label applies from the closing bar through the next 3 5m bars
    result = np.array(["WARMUP"] * n, dtype=object)
    for j, bar5_idx in enumerate(bar_15m_idx):
        label = stacks_15m[j]
        start = bar5_idx
        end = bar_15m_idx[j + 1] if j + 1 < len(bar_15m_idx) else n
        result[start:end] = label

    return result


# ── Data loading ──────────────────────────────────────────────────────────────

def load_full_history() -> pd.DataFrame:
    """Load the broadest available SPY 5m history, append any newer incremental file."""
    # Prefer the single large file that covers most of the range
    candidates = sorted(DATA_DIR.glob("spy_5m_*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No spy_5m_*.csv found under {DATA_DIR}")

    # Pick the file with the most rows (best coverage)
    best = max(candidates, key=lambda p: p.stat().st_size)
    df = pd.read_csv(best)
    df["ts"] = pd.to_datetime(df["timestamp_et"], format="mixed", utc=True)
    df = df.sort_values("ts").reset_index(drop=True)

    # Top-up with any file that has bars after the best file's end
    best_end = df["ts"].max()
    for p in candidates:
        if p == best:
            continue
        tmp = pd.read_csv(p)
        tmp["ts"] = pd.to_datetime(tmp["timestamp_et"], format="mixed", utc=True)
        new_bars = tmp[tmp["ts"] > best_end]
        if len(new_bars) > 0:
            df = pd.concat([df, new_bars], ignore_index=True)
            best_end = df["ts"].max()

    df = df.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    # Convert to Eastern time (tz-aware)
    import pytz
    ET = pytz.timezone("America/New_York")
    df["ts_et"] = df["ts"].dt.tz_convert(ET)
    return df


# ── Day-level analysis ────────────────────────────────────────────────────────

ET_OPEN  = dt.time(9, 30)
ET_START = dt.time(9, 35)
ET_CUT   = dt.time(15, 0)   # no entries after 15:00

REVERSAL_LOW_BEFORE  = dt.time(11, 0)
REVERSAL_RECOVERY    = 2.00    # SPY must recover >=2.00 from session low
REVERSAL_WINDOW_HRS  = 2.0    # recovery must happen within 2 hours of the session low

RIBBON_SPREAD_MIN    = 30.0   # cents -- same as F6 threshold
BYPASS_SPREAD_MIN    = 60.0   # cents -- tighter guard for the proposed bypass
PROXY_WIN_DOLLARS    = 1.00   # SPY must move >=1.00 up in next 60 min to count as "win"
PROXY_BARS_AHEAD     = 12     # 12 bars x 5 min = 60 min look-ahead for win proxy


def analyse_day(day_df: pd.DataFrame, date_str: str) -> Optional[dict]:
    """Analyse one trading day for reversal characteristics and F11 latency.

    Returns a result dict or None if the day doesn't qualify as a reversal day.
    """
    day_df = day_df.copy().reset_index(drop=True)
    closes = day_df["close"].values
    n = len(closes)

    # Guard: need enough warmup bars for ribbon + HTF computation
    if n < 50:
        return None

    # Compute 5m ribbon
    fast, pivot, slow, spread = _ribbon_5m(closes)
    stack_5m = np.array(["WARMUP"] * n, dtype=object)
    for i in range(n):
        if np.isnan(fast[i]) or np.isnan(pivot[i]) or np.isnan(slow[i]):
            stack_5m[i] = "WARMUP"
        elif fast[i] > pivot[i] > slow[i]:
            stack_5m[i] = "BULL"
        elif fast[i] < pivot[i] < slow[i]:
            stack_5m[i] = "BEAR"
        else:
            stack_5m[i] = "MIXED"

    # Compute approximate 15m HTF stack
    htf_stack = _htf_15m_stack(closes)

    # ── Identify if this is a reversal day ──────────────────────────────────
    # RTH only: 09:30-16:00 ET
    rth_mask = np.array([
        ET_OPEN <= row.ts_et.time() < dt.time(16, 0)
        for _, row in day_df.iterrows()
    ])
    pre_1100_mask = np.array([
        row.ts_et.time() < REVERSAL_LOW_BEFORE
        for _, row in day_df.iterrows()
    ])
    rth_pre_1100 = rth_mask & pre_1100_mask

    if rth_pre_1100.sum() == 0:
        return None

    # Session low set before 11:00 ET
    pre1100_closes = closes[rth_pre_1100]
    session_low = float(pre1100_closes.min())
    low_bar_idx = int(np.where(rth_pre_1100)[0][np.argmin(pre1100_closes)])
    low_time = day_df.iloc[low_bar_idx]["ts_et"]

    # Check recovery: does SPY reach session_low + REVERSAL_RECOVERY within 2 hours?
    recovery_target = session_low + REVERSAL_RECOVERY
    window_end = low_time + dt.timedelta(hours=REVERSAL_WINDOW_HRS)

    recovery_mask = np.array([
        (low_time < row.ts_et <= window_end) and (row.close >= recovery_target)
        for _, row in day_df.iterrows()
    ])
    if not recovery_mask.any():
        return None  # Not a reversal day

    recovery_bar_idx = int(np.where(recovery_mask)[0][0])
    recovery_time = day_df.iloc[recovery_bar_idx]["ts_et"]
    actual_recovery = float(day_df.iloc[recovery_bar_idx]["close"]) - session_low

    # ── From the recovery bar onward (to 15:00 ET), find first tick where ──
    # ribbon is BULL + spread >= 30c, AND check when HTF clears BEAR
    post_recovery = np.zeros(n, dtype=bool)
    for i in range(n):
        t = day_df.iloc[i]["ts_et"].time()
        if i >= recovery_bar_idx and ET_START <= t < ET_CUT:
            post_recovery[i] = True

    first_ribbon_bull_idx = None  # first bar where 5m ribbon BULL >= 30c spread
    htf_clear_idx = None          # first bar where HTF is no longer BEAR after ribbon BULL

    for i in range(n):
        if not post_recovery[i]:
            continue
        if stack_5m[i] == "BULL" and spread[i] >= RIBBON_SPREAD_MIN:
            if first_ribbon_bull_idx is None:
                first_ribbon_bull_idx = i
            # Now check if HTF has cleared BEAR
            if htf_stack[i] != "BEAR" and htf_clear_idx is None:
                htf_clear_idx = i

    # If ribbon never went BULL post-recovery, this day is not informative
    if first_ribbon_bull_idx is None:
        return {
            "date": date_str,
            "session_low": session_low,
            "low_time": str(low_time.time())[:5],
            "recovery": actual_recovery,
            "recovery_time": str(recovery_time.time())[:5],
            "is_reversal": True,
            "ribbon_bull_before_cut": False,
            "htf_clear_before_cut": False,
            "lag_minutes": None,
            "proxy_win": None,
            "entry_price": None,
            "fwd_move": None,
        }

    ribbon_bull_time = day_df.iloc[first_ribbon_bull_idx]["ts_et"]

    # HTF lag computation
    lag_minutes = None
    htf_clear_time_str = "NEVER"
    if htf_clear_idx is not None:
        htf_clear_time = day_df.iloc[htf_clear_idx]["ts_et"]
        lag_minutes = (htf_clear_time - ribbon_bull_time).total_seconds() / 60.0
        htf_clear_time_str = str(htf_clear_time.time())[:5]
    elif first_ribbon_bull_idx is not None:
        # HTF remained BEAR through the entire post-recovery tradeable window
        # Measure potential lag until 15:00 ET (last bar in window)
        last_in_window = None
        for i in range(n - 1, -1, -1):
            if post_recovery[i]:
                last_in_window = i
                break
        if last_in_window is not None:
            last_time = day_df.iloc[last_in_window]["ts_et"]
            lag_minutes = (last_time - ribbon_bull_time).total_seconds() / 60.0

    # ── Proxy WR at the first ribbon-BULL bar (bypass scenario) ─────────────
    # "Win" = SPY closes >= entry + PROXY_WIN_DOLLARS within next 12 bars
    proxy_win = None
    entry_price = None
    fwd_move = None
    if first_ribbon_bull_idx is not None:
        entry_price = float(day_df.iloc[first_ribbon_bull_idx]["close"])
        fwd_end = min(first_ribbon_bull_idx + PROXY_BARS_AHEAD, n)
        if fwd_end > first_ribbon_bull_idx:
            fwd_closes = closes[first_ribbon_bull_idx + 1:fwd_end]
            if len(fwd_closes) > 0:
                fwd_move = float(fwd_closes.max()) - entry_price
                proxy_win = fwd_move >= PROXY_WIN_DOLLARS

    # ── Does the bypass guard (spread>=60c) apply at the first ribbon-BULL bar? ─
    bypass_guard_met = (
        first_ribbon_bull_idx is not None
        and spread[first_ribbon_bull_idx] >= BYPASS_SPREAD_MIN
    )

    return {
        "date": date_str,
        "session_low": round(session_low, 2),
        "low_time": str(low_time.time())[:5],
        "recovery": round(actual_recovery, 2),
        "recovery_time": str(recovery_time.time())[:5],
        "is_reversal": True,
        "ribbon_bull_time": str(ribbon_bull_time.time())[:5] if first_ribbon_bull_idx else None,
        "ribbon_bull_spread_c": round(float(spread[first_ribbon_bull_idx]), 1) if first_ribbon_bull_idx is not None else None,
        "htf_bear_at_ribbon_bull": (htf_stack[first_ribbon_bull_idx] == "BEAR") if first_ribbon_bull_idx is not None else None,
        "htf_clear_time": htf_clear_time_str,
        "htf_clear_before_cut": htf_clear_idx is not None,
        "lag_minutes": round(lag_minutes, 0) if lag_minutes is not None else None,
        "bypass_guard_met": bypass_guard_met,
        "entry_price": entry_price,
        "fwd_move": round(fwd_move, 2) if fwd_move is not None else None,
        "proxy_win": proxy_win,
    }


# ── OP-16 check: J's 3 winner days ───────────────────────────────────────────

J_WINNER_DAYS = {
    "2026-04-29": {"ticker": "710P", "pnl": 342},
    "2026-05-01": {"ticker": "721P", "pnl": 470},
    "2026-05-04": {"ticker": "721P", "pnl": 730},
}
J_LOSER_DAYS = {
    "2026-05-05": {"ticker": "722P", "pnl": -260},
    "2026-05-06": {"ticker": "730P", "pnl": -300},
    "2026-05-07-a": {"ticker": "734C", "pnl": -45},
    "2026-05-07-b": {"ticker": "737C", "pnl": -120},
}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import pytz
    ET = pytz.timezone("America/New_York")

    print("Loading SPY 5m history...")
    df = load_full_history()
    print(f"  Loaded {len(df)} bars from {df['ts_et'].min().date()} to {df['ts_et'].max().date()}")

    # Group by trading date (ET date at open)
    df["date_str"] = df["ts_et"].apply(lambda x: x.strftime("%Y-%m-%d"))
    all_dates = sorted(df["date_str"].unique())
    print(f"  {len(all_dates)} trading days in dataset")

    results = []
    all_days = []

    for date_str in all_dates:
        day_df = df[df["date_str"] == date_str].reset_index(drop=True)
        res = analyse_day(day_df, date_str)
        if res is not None and res["is_reversal"]:
            results.append(res)
        all_days.append((date_str, res))

    # ── Summary stats ─────────────────────────────────────────────────────────
    total_days = len(all_dates)
    reversal_days = len(results)

    ribbon_bull_days = [r for r in results if r.get("ribbon_bull_time") is not None]
    htf_bear_at_bull = [r for r in ribbon_bull_days if r.get("htf_bear_at_ribbon_bull")]
    htf_never_clear  = [r for r in htf_bear_at_bull if not r["htf_clear_before_cut"]]
    htf_eventually   = [r for r in htf_bear_at_bull if r["htf_clear_before_cut"]]

    lags = [r["lag_minutes"] for r in htf_eventually if r["lag_minutes"] is not None]
    median_lag = float(np.median(lags)) if lags else None
    mean_lag   = float(np.mean(lags)) if lags else None
    p75_lag    = float(np.percentile(lags, 75)) if lags else None

    # Proxy WR on bypass scenario (HTF was BEAR but ribbon BULL)
    bypass_candidates = [r for r in htf_bear_at_bull if r.get("proxy_win") is not None]
    bypass_guard_candidates = [r for r in bypass_candidates if r.get("bypass_guard_met")]
    proxy_wins_all   = sum(1 for r in bypass_candidates if r["proxy_win"])
    proxy_wins_guard = sum(1 for r in bypass_guard_candidates if r["proxy_win"])
    proxy_wr_all   = proxy_wins_all / len(bypass_candidates) if bypass_candidates else None
    proxy_wr_guard = proxy_wins_guard / len(bypass_guard_candidates) if bypass_guard_candidates else None

    # OP-16 check on J's winner days
    j_winner_check = {}
    for j_date, info in J_WINNER_DAYS.items():
        match = next((r for r in results if r["date"] == j_date), None)
        j_winner_check[j_date] = {
            "is_reversal": match is not None,
            "detail": match,
            "j_trade": info,
        }

    # Also check loser days -- would bypass have hurt?
    j_loser_check = {}
    for j_key, info in J_LOSER_DAYS.items():
        j_date = j_key[:10]  # strip -a/-b suffix
        match = next((r for r in results if r["date"] == j_date), None)
        j_loser_check[j_key] = {
            "is_reversal": match is not None,
            "detail": match,
            "j_trade": info,
        }

    # ── Print full report ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("F11 HTF LATENCY ANALYSIS -- REVERSAL DAYS")
    print("=" * 70)
    print(f"Dataset: {total_days} trading days")
    print(f"Reversal days (low<11am, recovery>=$2.00 in 2h): {reversal_days}")
    print(f"  Reversal rate: {reversal_days/total_days:.1%}")
    print()
    print(f"Of {reversal_days} reversal days:")
    print(f"  Ribbon went BULL post-recovery: {len(ribbon_bull_days)}")
    print(f"  HTF was BEAR when ribbon first hit BULL: {len(htf_bear_at_bull)}")
    print(f"  HTF eventually cleared (before 15:00 ET): {len(htf_eventually)}")
    print(f"  HTF NEVER cleared: {len(htf_never_clear)}  <- F11 blocked all afternoon")
    print()
    print("HTF clear lag (minutes after ribbon first achieved BULL):")
    if lags:
        print(f"  Median: {median_lag:.0f} min  |  Mean: {mean_lag:.0f} min  |  P75: {p75_lag:.0f} min")
        print(f"  Range: {min(lags):.0f}--{max(lags):.0f} min")
    else:
        print("  Insufficient data")
    print()
    print("Proxy WR on bypass scenario (next 60min SPY move >=$1.00):")
    if bypass_candidates:
        print(f"  No guard (all HTF-BEAR + ribbon-BULL): {proxy_wins_all}/{len(bypass_candidates)} = {proxy_wr_all:.1%}")
    if bypass_guard_candidates:
        print(f"  With spread>=60c guard:              {proxy_wins_guard}/{len(bypass_guard_candidates)} = {proxy_wr_guard:.1%}")
    print()
    print("OP-16 CHECK -- J's 3 WINNER DAYS:")
    for j_date, chk in j_winner_check.items():
        is_rev = chk["is_reversal"]
        d = chk["detail"]
        info = chk["j_trade"]
        print(f"  {j_date} ({info['ticker']}, +${info['pnl']}):")
        if not is_rev:
            print(f"    NOT a reversal day -> bypass would not apply")
        else:
            htf_bear = d.get("htf_bear_at_ribbon_bull", "N/A")
            htf_never = not d.get("htf_clear_before_cut", True)
            print(f"    IS reversal day (recovery={d['recovery']:.2f}, low@{d['low_time']})")
            print(f"    HTF BEAR when ribbon BULL: {htf_bear}")
            if htf_bear:
                print(f"    HTF clear time: {d['htf_clear_time']}  (lag={d['lag_minutes']:.0f}min)")
                if htf_never:
                    print(f"    ** F11 would have blocked the WHOLE session -- bypass helps")
                else:
                    print(f"    F11 cleared in time -- bypass not needed, no harm")

    print()
    print("OP-16 CHECK -- J's LOSER DAYS (would bypass have hurt?):")
    for j_key, chk in j_loser_check.items():
        is_rev = chk["is_reversal"]
        d = chk["detail"]
        info = chk["j_trade"]
        j_date = j_key[:10]
        print(f"  {j_key} ({info['ticker']}, ${info['pnl']}):")
        if not is_rev:
            print(f"    NOT a reversal day -> bypass would not fire")
        else:
            htf_bear = d.get("htf_bear_at_ribbon_bull", "N/A")
            print(f"    IS reversal day (recovery={d['recovery']:.2f})")
            print(f"    HTF BEAR when ribbon BULL: {htf_bear}")
            if htf_bear:
                print(f"    ** Bypass COULD have allowed false entry -- this is a risk day")

    print()
    print("SAMPLE REVERSAL DAYS (first 20):")
    print(f"{'Date':<12} {'Low':>7} {'LowT':>6} {'Rec':>6} {'RecT':>6} "
          f"{'RibbT':>6} {'Spr':>5} {'HTFBear':>7} {'HTFClr':>7} {'Lag':>6} {'FwdMv':>7} {'Win':>4}")
    for r in results[:20]:
        print(f"  {r['date']:<10} "
              f"{r['session_low']:>7.2f} "
              f"{r['low_time']:>6} "
              f"{r['recovery']:>6.2f} "
              f"{r['recovery_time']:>6} "
              f"{str(r.get('ribbon_bull_time','--')):>6} "
              f"{str(r.get('ribbon_bull_spread_c','--')):>5} "
              f"{'Y' if r.get('htf_bear_at_ribbon_bull') else 'N':>7} "
              f"{str(r.get('htf_clear_time','--')):>7} "
              f"{str(r.get('lag_minutes','--')):>6} "
              f"{str(r.get('fwd_move','--')):>7} "
              f"{'Y' if r.get('proxy_win') else ('N' if r.get('proxy_win') is False else '--'):>4}")

    # Build summary dict for candidate file
    summary = {
        "total_trading_days": total_days,
        "reversal_days": reversal_days,
        "reversal_rate_pct": round(100.0 * reversal_days / total_days, 1),
        "ribbon_bull_post_recovery": len(ribbon_bull_days),
        "htf_bear_when_ribbon_bull": len(htf_bear_at_bull),
        "htf_eventually_cleared": len(htf_eventually),
        "htf_never_cleared": len(htf_never_clear),
        "median_lag_min": median_lag,
        "mean_lag_min": round(mean_lag, 0) if mean_lag else None,
        "p75_lag_min": round(p75_lag, 0) if p75_lag else None,
        "bypass_candidates_no_guard": len(bypass_candidates),
        "bypass_proxy_wr_no_guard": round(proxy_wr_all * 100, 1) if proxy_wr_all else None,
        "bypass_candidates_with_guard": len(bypass_guard_candidates),
        "bypass_proxy_wr_with_guard": round(proxy_wr_guard * 100, 1) if proxy_wr_guard else None,
        "j_winner_check": j_winner_check,
        "j_loser_check": j_loser_check,
        "reversal_day_list": results,
    }

    return summary


if __name__ == "__main__":
    summary = main()
