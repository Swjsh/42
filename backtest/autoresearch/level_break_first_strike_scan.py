"""level_break_first_strike_scan.py

Research scan for the LEVEL_BREAK_FIRST_STRIKE setup proposal (chef-inbox 2026-05-19).
Evaluates whether allowing bear entries at confirmed level breaks with MIXED ribbon
(not full BEAR stack) shows positive edge over the 16-month SPY history.

Trigger conditions (all required):
  1. Bar closes <= named_level - BREAK_CENTS (level breakdown confirmed)
  2. Volume >= VOL_MULT x 20-bar avg
  3. Ribbon MIXED (stack not BULL/BEAR, MIN_SPREAD_MIXED_CENTS <= spread < MAX_SPREAD_MIXED_CENTS)
  4. Time >= ENTRY_GATE_ET
  5. VIX direction = rising or flat (diff > -VIX_FALLING_DEADBAND)

Win definition: low of any of the next 3 bars <= bar.close - WIN_DROP_CENTS

Guard rails (J's non-negotiable):
  - 5/05, 5/06, 5/07 loser days must NOT fire with this trigger

Version history:
  v1 (2026-05-19): MIN_SPREAD_MIXED_CENTS=0 (no floor). Result: 34 signals, 50% WR.
                   Guard rail FAIL — 5/07 fires twice (spread 9.8c + 11.1c, both < 12c).
  v2 (2026-05-19): MIN_SPREAD_MIXED_CENTS=12 (guard rail fix). To run v2:
                   Set MIN_SPREAD_MIXED_CENTS=12 below and re-run. Expected: 26 signals,
                   50% WR, 5/07=0 signals (guard rail PASS). 5/04 loses 09:50 WIN but
                   keeps the key 11:15 WIN (+132c). Also test MIN_SPREAD=20 for ">20c"
                   tier isolation (4W/5 = 80% WR in v1).

Output:
  analysis/recommendations/level_break_first_strike_scan.json

Usage:
  python backtest/autoresearch/level_break_first_strike_scan.py
  # To run v2 guard-rail-fixed version: set MIN_SPREAD_MIXED_CENTS=12 below.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from lib.ribbon import compute_ribbon
from lib.levels import detect_levels_at_bar

# ── Tunable parameters ──────────────────────────────────────────────────────
BREAK_CENTS = 20          # bar.close must be >= 20c below the level
VOL_MULT = 1.5            # volume threshold multiplier vs 20-bar avg
MIN_SPREAD_MIXED_CENTS = 0    # ribbon spread floor (v1=0 no floor; v2=12 guard-rail fix)
MAX_SPREAD_MIXED_CENTS = 30  # ribbon spread must be < 30c to be "transitioning"
ENTRY_GATE_ET = dt.time(9, 45)  # no entries before 09:45 ET
WIN_DROP_CENTS = 50       # price must drop >= 50c within 3 bars to count as win
VIX_FALLING_DEADBAND = 0.10   # VIX diff < -0.10 = falling hard = block
VIX_LOOKBACK_BARS = 3    # compare vix_now vs vix N bars ago

# J's source-of-truth days
J_LOSER_DAYS = {"2026-05-05", "2026-05-06", "2026-05-07"}
J_WINNER_DAYS = {"2026-04-29", "2026-05-01", "2026-05-04"}
ALL_J_DAYS = J_LOSER_DAYS | J_WINNER_DAYS

# Data paths
SPY_PATH = REPO / "data" / "spy_5m_2025-01-01_2026-05-15.csv"
VIX_PATH = REPO / "data" / "vix_5m_2025-01-01_2026-05-15.csv"
OUT_PATH = ROOT / "analysis" / "recommendations" / "level_break_first_strike_scan.json"

SCAN_START = dt.date(2025, 1, 15)  # allow ribbon warmup from Jan 2


def _rth_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only RTH bars 09:30-16:00 ET."""
    t = df["timestamp_et"].dt.time
    return df[(t >= dt.time(9, 30)) & (t < dt.time(16, 0))].copy()


def _load_vix_daily_opens(vix_df: pd.DataFrame) -> dict[str, float]:
    """Compute per-day open VIX (first RTH bar) for direction tracking."""
    vix_rth = _rth_filter(vix_df)
    vix_rth = vix_rth.copy()
    vix_rth["date"] = vix_rth["timestamp_et"].dt.date.astype(str)
    return vix_rth.groupby("date")["open"].first().to_dict()


def scan(spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> dict:
    """Main scan loop. Returns structured results."""
    spy_df = spy_df.copy()
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"], utc=True).dt.tz_convert(
        "America/New_York").dt.tz_localize(None)

    vix_df = vix_df.copy()
    vix_df["timestamp_et"] = pd.to_datetime(vix_df["timestamp_et"], utc=True).dt.tz_convert(
        "America/New_York").dt.tz_localize(None)

    # Merge VIX close onto spy bars by timestamp (nearest on-bar)
    spy_df["date"] = spy_df["timestamp_et"].dt.date
    spy_df["time"] = spy_df["timestamp_et"].dt.time
    vix_df["date"] = vix_df["timestamp_et"].dt.date

    # VIX: index by timestamp for fast lookup
    vix_close_by_ts = vix_df.set_index("timestamp_et")["close"].to_dict()

    def _vix_at(ts: pd.Timestamp) -> Optional[float]:
        return vix_close_by_ts.get(ts)

    # Compute full ribbon over all SPY closes
    print("Computing ribbon over full SPY history...")
    ribbon_df = compute_ribbon(spy_df["close"])

    # Cache per-day levels (expensive, run once per day)
    print("Computing levels per trading day...")
    rth = _rth_filter(spy_df)
    trading_days = sorted(rth["date"].unique())
    trading_days = [d for d in trading_days if d >= SCAN_START]
    print(f"  {len(trading_days)} trading days in scan window")

    # Per-day: get first RTH bar index for level computation
    day_first_bar_idx: dict[str, int] = {}
    for d in trading_days:
        day_bars = spy_df[spy_df["date"] == d]
        if day_bars.empty:
            continue
        day_first_bar_idx[str(d)] = day_bars.index[0]

    signals: list[dict] = []

    for day in trading_days:
        day_str = str(day)
        if day_str not in day_first_bar_idx:
            continue

        # Compute levels ONCE per day (at first RTH bar)
        first_idx = day_first_bar_idx[day_str]
        first_ts = spy_df.loc[first_idx, "timestamp_et"]
        try:
            level_set = detect_levels_at_bar(spy_df, first_idx, first_ts)
        except Exception as e:
            continue
        active_levels = level_set.active
        if not active_levels:
            continue

        # Get RTH bars for this day
        day_spy = spy_df[(spy_df["date"] == day) & (spy_df["time"] >= dt.time(9, 30)) &
                         (spy_df["time"] < dt.time(16, 0))]
        if len(day_spy) < 5:
            continue

        # Per-bar scan
        day_spy_list = list(day_spy.itertuples())
        for i, row in enumerate(day_spy_list):
            bar_time = row.time
            if bar_time < ENTRY_GATE_ET:
                continue
            if i + 3 >= len(day_spy_list):
                break  # need 3 forward bars for outcome check

            # Ribbon check: MIXED stack + spread in [MIN_SPREAD, MAX_SPREAD) window
            try:
                ribbon_row = ribbon_df.loc[row.Index]
            except KeyError:
                continue
            if ribbon_row["stack"] != "MIXED":
                continue
            spread = float(ribbon_row["spread_cents"])
            if spread >= MAX_SPREAD_MIXED_CENTS:
                continue
            if MIN_SPREAD_MIXED_CENTS > 0 and spread < MIN_SPREAD_MIXED_CENTS:
                continue

            # Volume check: >= 1.5x 20-bar avg
            bar_global_idx = spy_df.index.get_loc(row.Index)
            if bar_global_idx < 20:
                continue
            prior_20_vols = spy_df.iloc[bar_global_idx - 20: bar_global_idx]["volume"].values
            if len(prior_20_vols) == 0:
                continue
            vol_avg_20 = float(prior_20_vols.mean())
            if vol_avg_20 <= 0 or float(row.volume) < VOL_MULT * vol_avg_20:
                continue

            bar_close = float(row.close)

            # Level break check: close <= level - BREAK_CENTS/100
            threshold = BREAK_CENTS / 100.0
            broken_levels = [lvl for lvl in active_levels if bar_close <= lvl - threshold]
            if not broken_levels:
                continue

            # VIX direction: must be rising or flat (not falling hard)
            bar_ts = row.timestamp_et
            vix_now = _vix_at(bar_ts)
            if vix_now is None:
                continue
            prior_vix_ts = bar_ts - pd.Timedelta(minutes=5 * VIX_LOOKBACK_BARS)
            vix_prior = _vix_at(prior_vix_ts)
            if vix_prior is None:
                vix_prior = vix_now
            vix_diff = vix_now - vix_prior
            if vix_diff < -VIX_FALLING_DEADBAND:
                continue  # falling hard — skip

            # Outcome: did price drop >= 50c within next 3 bars?
            future_bars = day_spy_list[i + 1: i + 4]
            min_future_low = min(b.low for b in future_bars) if future_bars else bar_close
            win = bool(min_future_low <= bar_close - WIN_DROP_CENTS / 100.0)
            max_adverse = float(max(b.high for b in future_bars)) - bar_close if future_bars else 0
            min_favorable = bar_close - min_future_low

            nearest_level = min(broken_levels, key=lambda lvl: abs(lvl - bar_close))
            signals.append({
                "date": day_str,
                "time": bar_time.strftime("%H:%M"),
                "bar_close": round(bar_close, 2),
                "level": round(nearest_level, 2),
                "break_below": round(nearest_level - bar_close, 2),
                "ribbon_stack": ribbon_row["stack"],
                "ribbon_spread_cents": round(spread, 1),
                "volume": int(row.volume),
                "vol_mult": round(float(row.volume) / vol_avg_20, 2),
                "vix_now": round(vix_now, 2),
                "vix_diff": round(vix_diff, 2),
                "win": win,
                "min_favorable_cents": round(min_favorable * 100, 1),
                "max_adverse_cents": round(max_adverse * 100, 1),
                "is_j_loser_day": day_str in J_LOSER_DAYS,
                "is_j_winner_day": day_str in J_WINNER_DAYS,
            })

    # Aggregate stats
    n_total = len(signals)
    n_wins = sum(1 for s in signals if s["win"])
    wr = round(n_wins / n_total, 3) if n_total > 0 else 0

    j_loser_fires = [s for s in signals if s["is_j_loser_day"]]
    j_winner_fires = [s for s in signals if s["is_j_winner_day"]]
    loser_day_guard_pass = len(j_loser_fires) == 0

    # Per-day aggregation
    daily_stats: dict[str, dict] = {}
    for s in signals:
        d = s["date"]
        if d not in daily_stats:
            daily_stats[d] = {"n": 0, "wins": 0, "dates": d}
        daily_stats[d]["n"] += 1
        daily_stats[d]["wins"] += 1 if s["win"] else 0

    # Days with signals
    n_days_with_signal = len(daily_stats)
    avg_signals_per_day = round(n_total / n_days_with_signal, 2) if n_days_with_signal > 0 else 0

    # Month-level dedup: how many signals per month?
    from collections import Counter
    month_counts = Counter(s["date"][:7] for s in signals)
    avg_per_month = round(n_total / len(month_counts), 1) if month_counts else 0

    # ── Regime concentration check (L46 in LESSONS-LEARNED.md) ──────────────
    # Flag if setup is firing in regime-specific clusters rather than across full history.
    months_with_signal = len(month_counts)
    n_scan_months = len(set(d[:7] for d in (str(dd) for dd in trading_days)))
    months_coverage_pct = round(100 * months_with_signal / n_scan_months, 1) if n_scan_months > 0 else 0

    # Quarter-level concentration: what % of signals came from the busiest single quarter?
    quarter_counts: Counter = Counter()
    for s in signals:
        yr, mo_s = s["date"][:4], s["date"][5:7]
        q = f"{yr}-Q{(int(mo_s) - 1) // 3 + 1}"
        quarter_counts[q] += 1
    top_quarter = quarter_counts.most_common(1)[0] if quarter_counts else ("none", 0)
    top_quarter_pct = round(100 * top_quarter[1] / n_total, 1) if n_total > 0 else 0
    regime_concentrated = top_quarter_pct > 50  # >50% from one quarter = regime-specific flag

    # Spread-tier win rates (helps identify guard-rail-safe sub-tiers)
    tier_results: dict[str, dict] = {"lt12": {"n": 0, "w": 0}, "12_to_20": {"n": 0, "w": 0}, "gt20": {"n": 0, "w": 0}}
    for s in signals:
        sp = s["ribbon_spread_cents"]
        tier = "lt12" if sp < 12 else ("12_to_20" if sp <= 20 else "gt20")
        tier_results[tier]["n"] += 1
        if s["win"]:
            tier_results[tier]["w"] += 1
    spread_tier_wr = {
        t: round(v["w"] / v["n"], 3) if v["n"] > 0 else None
        for t, v in tier_results.items()
    }
    spread_tier_counts = {t: v["n"] for t, v in tier_results.items()}

    return {
        "parameters": {
            "break_cents": BREAK_CENTS,
            "vol_mult": VOL_MULT,
            "min_spread_mixed_cents": MIN_SPREAD_MIXED_CENTS,
            "max_spread_mixed_cents": MAX_SPREAD_MIXED_CENTS,
            "entry_gate_et": str(ENTRY_GATE_ET),
            "win_drop_cents": WIN_DROP_CENTS,
            "vix_falling_deadband": VIX_FALLING_DEADBAND,
            "vix_lookback_bars": VIX_LOOKBACK_BARS,
        },
        "aggregate": {
            "n_total_signals": n_total,
            "n_wins": n_wins,
            "win_rate": wr,
            "n_trading_days": len(trading_days),
            "n_days_with_signal": n_days_with_signal,
            "avg_signals_per_signal_day": avg_signals_per_day,
            "avg_signals_per_month": avg_per_month,
            "loser_day_guard_pass": loser_day_guard_pass,
            # Regime concentration metrics (L46 — check before concluding on win rate)
            "months_with_signal": months_with_signal,
            "months_coverage_pct": months_coverage_pct,
            "top_quarter": top_quarter[0],
            "top_quarter_signal_pct": top_quarter_pct,
            "regime_concentrated_flag": regime_concentrated,
            # Spread tier breakdown (guard rail analysis)
            "spread_tier_win_rates": spread_tier_wr,
            "spread_tier_counts": spread_tier_counts,
        },
        "j_source_of_truth": {
            "loser_day_fires": j_loser_fires,
            "winner_day_fires": j_winner_fires,
            "guard_pass": loser_day_guard_pass,
        },
        "monthly_signal_counts": dict(sorted(month_counts.items())),
        "signals": signals[:500],  # cap for JSON size
        "total_signals_before_cap": n_total,
    }


def main() -> int:
    print(f"Loading SPY ({SPY_PATH.name})...")
    spy_df = pd.read_csv(SPY_PATH)
    print(f"Loading VIX ({VIX_PATH.name})...")
    vix_df = pd.read_csv(VIX_PATH)
    print(f"  SPY: {len(spy_df):,} rows  VIX: {len(vix_df):,} rows")

    print("\nRunning LEVEL_BREAK_FIRST_STRIKE scan...")
    result = scan(spy_df, vix_df)

    agg = result["aggregate"]
    jst = result["j_source_of_truth"]
    print(f"\n=== RESULTS ===")
    print(f"  Total signals: {agg['n_total_signals']} over {agg['n_trading_days']} days")
    print(f"  Win rate: {agg['win_rate']:.1%}  ({agg['n_wins']} wins)")
    print(f"  Signal frequency: {agg['avg_signals_per_month']:.1f}/month")
    print(f"  Loser day guard: {'PASS' if agg['loser_day_guard_pass'] else 'FAIL'}")
    # Regime concentration (L46 — show before drawing WR conclusions)
    print(f"\n=== REGIME CONCENTRATION (L46) ===")
    print(f"  Months with signal: {agg['months_with_signal']} ({agg['months_coverage_pct']:.0f}% of scan window)")
    regime_flag = "WARN - REGIME CONCENTRATED" if agg['regime_concentrated_flag'] else "OK"
    print(f"  Top quarter: {agg['top_quarter']} ({agg['top_quarter_signal_pct']:.0f}% of all signals) [{regime_flag}]")
    print(f"  Spread tier WR: <12c={agg['spread_tier_win_rates']['lt12']} n={agg['spread_tier_counts']['lt12']} | "
          f"12-20c={agg['spread_tier_win_rates']['12_to_20']} n={agg['spread_tier_counts']['12_to_20']} | "
          f">20c={agg['spread_tier_win_rates']['gt20']} n={agg['spread_tier_counts']['gt20']}")
    if jst["loser_day_fires"]:
        for f in jst["loser_day_fires"]:
            print(f"    LOSER DAY FIRE: {f['date']} {f['time']} close={f['bar_close']} level={f['level']}")
    if jst["winner_day_fires"]:
        print(f"\n  Winner day captures:")
        for f in jst["winner_day_fires"]:
            print(f"    {f['date']} {f['time']} close={f['bar_close']} level={f['level']} "
                  f"vol_mult={f['vol_mult']}x win={f['win']}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n  Written: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
