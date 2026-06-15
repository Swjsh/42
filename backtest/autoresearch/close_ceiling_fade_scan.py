"""close_ceiling_fade_scan.py

Research scan for the CLOSE_CEILING_FADE setup (L59, 2026-05-20).

J identified the pattern live: 6 SPY bars tested PM ceiling 740.49 without a single
close above → 14:40 bar closed at 740.72 (fake breakout) → 14:45 reversed on higher
vol (C:739.77, vol:45K). The close-ceiling distribution pattern gates the breakout as
a bull trap.

Trigger conditions (all required):
  1. N >= N_MIN consecutive bars with bar.high >= resistance_level AND bar.close < resistance_level
     (distribution: bulls pushing, bears absorbing, no close above)
  2. Current bar closes ABOVE resistance_level (the "fake breakout" bar)
  3. Time >= ENTRY_TIME_START and <= ENTRY_TIME_END
  4. Cooldown: >= COOLDOWN_MINUTES since last signal for same level

Win definition:
  Next WIN_BARS_LOOKBACK bars: at least one bar's close < (resistance_level - WIN_REVERT_CENTS)
  i.e., price reverts back below the level (breakout fails, bears win)

Resistance level proxy:
  PDH (prior day RTH high) — always a named level, consistently drawn, ★★ strength.
  Note: this UNDERSTIMATES the real edge because many close-ceiling events happen at
  intraday session levels (PM ceiling, VWAP, etc.) that require key-levels.json archive.

Output:
  analysis/recommendations/close_ceiling_fade_scan.json

Usage:
  python backtest/autoresearch/close_ceiling_fade_scan.py
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
sys.path.insert(0, str(ROOT))

# ── Tunable parameters ──────────────────────────────────────────────────────
N_MIN_STREAK: int = 3          # minimum consecutive distribution bars before signal fires
ENTRY_TIME_START: dt.time = dt.time(9, 45)   # skip the opening range
ENTRY_TIME_END: dt.time = dt.time(14, 30)    # avoid late theta drag
COOLDOWN_MINUTES: int = 45    # min gap between signals on the same level
WIN_BARS_LOOKBACK: int = 3     # check this many bars after entry for reversal
WIN_REVERT_CENTS: float = 0.20 # close must drop >= 20c below level to count WIN
LEVEL_TOLERANCE: float = 0.02  # bar.high must be within 2c of PDH to "test" it

# ── Modes ────────────────────────────────────────────────────────────────────
# "pdh" = prior day RTH high (original — only 2 signals in 344 days, too rare)
# "morning_high" = current day's morning high (09:30-11:30 ET) as afternoon resistance
# "prior_pm_high" = prior day's PM high (13:00-16:00 ET) as a PM ceiling proxy
# "structural" = structural ceiling: rolling N-bar window where all highs cluster at same level
SCAN_MODE: str = "structural"  # switch to test different level proxies

# Structural mode parameters
STRUCTURAL_WINDOW: int = 6        # look back this many bars to find the structural ceiling
STRUCTURAL_TIGHT_CENTS: float = 0.40  # ceiling highs must cluster within this range

# ── Data path ────────────────────────────────────────────────────────────────
SPY_CSV = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-19_merged.csv"
# Fall back to smaller file if merged not available
SPY_CSV_FALLBACK = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-15.csv"
OUT_PATH = ROOT / "analysis" / "recommendations" / "close_ceiling_fade_scan.json"

# ── J loser days (guard rail — must NOT fire on these) ───────────────────────
LOSER_DAYS = {"2026-05-05", "2026-05-06", "2026-05-07"}


def _load_spy(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Normalize timestamp column
    ts_col = next((c for c in df.columns if "time" in c.lower() or c == "timestamp"), df.columns[0])
    df = df.rename(columns={ts_col: "ts"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"])
    df["ts_et"] = df["ts"].dt.tz_convert("America/New_York")
    df["date"] = df["ts_et"].dt.date
    df["time"] = df["ts_et"].dt.time
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close", "high", "low"])
    return df.sort_values("ts_et").reset_index(drop=True)


def _is_rth(t: dt.time) -> bool:
    return dt.time(9, 30) <= t < dt.time(16, 0)


def scan_day_structural(
    day_bars: pd.DataFrame,
    day_str: str,
    last_signal_time: Optional[dt.datetime],
) -> tuple[list[dict], Optional[dt.datetime]]:
    """Structural ceiling scan — no fixed level; derives ceiling from rolling window.

    For each bar, looks back STRUCTURAL_WINDOW bars and checks if:
    1. All prior-window bars have high within STRUCTURAL_TIGHT_CENTS of each other (clustered ceiling)
    2. All prior-window closes are below the ceiling (distribution only, no close-above)
    3. Current bar closes above the ceiling (fake breakout)

    This captures the pattern without requiring a specific named level.
    """
    signals: list[dict] = []
    bars = day_bars.reset_index(drop=True)

    for i in range(STRUCTURAL_WINDOW, len(bars)):
        row = bars.iloc[i]
        t = row["time"]
        if not _is_rth(t):
            continue
        if t < ENTRY_TIME_START or t > ENTRY_TIME_END:
            continue

        # Rolling window: prior STRUCTURAL_WINDOW bars
        window = bars.iloc[max(0, i - STRUCTURAL_WINDOW) : i]
        if len(window) < N_MIN_STREAK:
            continue

        ceiling = float(window["high"].max())
        floor_high = float(window["high"].min())

        # Gate 1: All highs must cluster within STRUCTURAL_TIGHT_CENTS (same ceiling)
        if (ceiling - floor_high) > STRUCTURAL_TIGHT_CENTS:
            continue

        # Gate 2: All closes must be BELOW the ceiling (no close-above in window)
        # Allow small tolerance: close < ceiling - 0.05
        if (window["close"] >= ceiling - 0.05).any():
            continue

        # Gate 3: MINIMUM N_MIN_STREAK bars in the window must have tested the ceiling
        # (high within LEVEL_TOLERANCE of ceiling)
        tests_count = (window["high"] >= ceiling - LEVEL_TOLERANCE).sum()
        if tests_count < N_MIN_STREAK:
            continue

        # Gate 4: Current bar closes ABOVE the ceiling (fake breakout)
        bar_close = float(row["close"])
        if bar_close <= ceiling:
            continue

        # Cooldown check
        bar_ts = bars.at[i, "ts_et"]
        if last_signal_time is not None:
            elapsed = (bar_ts - last_signal_time).total_seconds() / 60.0
            if elapsed < COOLDOWN_MINUTES:
                continue

        signals.append({
            "date": day_str,
            "time": t.strftime("%H:%M"),
            "bar_idx": int(i),
            "streak": int(tests_count),
            "structural_window": STRUCTURAL_WINDOW,
            "resistance_level": round(ceiling, 2),
            "ceiling_range_cents": round(ceiling - floor_high, 2),
            "entry_close": round(bar_close, 2),
            "breakout_above_level_by": round(bar_close - ceiling, 2),
            "direction": "short",
            "side": "P",
            "signal_type": "CLOSE_CEILING_STRUCTURAL_FAKE_BREAKOUT",
            "loser_day_guard": day_str in LOSER_DAYS,
            "win": None,
        })
        last_signal_time = bar_ts

    return signals, last_signal_time


def scan_day(
    day_bars: pd.DataFrame,
    pdh: float,
    day_str: str,
    last_signal_time: Optional[dt.datetime],
) -> tuple[list[dict], Optional[dt.datetime]]:
    """Scan a single RTH session for close-ceiling → fake breakout signals.

    Returns (signals_list, updated_last_signal_time).
    """
    signals: list[dict] = []
    streak: int = 0          # consecutive distribution bars
    distributing: bool = False  # whether we're in a distribution window at PDH

    for i, row in day_bars.iterrows():
        t = row["time"]
        if not _is_rth(t):
            continue

        bar_high = row["high"]
        bar_close = row["close"]
        bar_open = row["open"]
        bar_vol = row.get("volume", 50_000)

        # ── Check if this bar tests the resistance level ─────────────────────
        # "tests" = bar.high is within TOLERANCE of PDH or above it
        tests_level = bar_high >= (pdh - LEVEL_TOLERANCE)
        closes_below = bar_close < pdh
        closes_above = bar_close > pdh

        if tests_level and closes_below:
            # Distribution bar: bull pushed to/above level but sellers closed it below
            streak += 1
            distributing = True
        elif closes_above and distributing and streak >= N_MIN_STREAK:
            # Fake breakout bar: after N>=3 distribution bars, price closes above PDH
            if t < ENTRY_TIME_START or t > ENTRY_TIME_END:
                streak = 0
                distributing = False
                continue

            # Cooldown check
            bar_ts = row["ts_et"] if hasattr(row, "ts_et") else day_bars.at[i, "ts_et"]
            if last_signal_time is not None:
                elapsed = (bar_ts - last_signal_time).total_seconds() / 60.0
                if elapsed < COOLDOWN_MINUTES:
                    streak = 0
                    distributing = False
                    continue

            signals.append({
                "date": day_str,
                "time": t.strftime("%H:%M"),
                "bar_idx": int(i),
                "streak": streak,
                "resistance_level": round(pdh, 2),
                "entry_close": round(bar_close, 2),
                "breakout_above_level_by": round(bar_close - pdh, 2),
                "direction": "short",
                "side": "P",
                "signal_type": "CLOSE_CEILING_FAKE_BREAKOUT",
                "loser_day_guard": day_str in LOSER_DAYS,
                "win": None,  # filled in below
            })
            last_signal_time = bar_ts
            streak = 0
            distributing = False
        elif not tests_level or closes_above:
            # Level not tested or closed above — reset streak
            streak = 0
            distributing = False

    return signals, last_signal_time


def grade_signals(signals: list[dict], day_bars: pd.DataFrame, level_override: Optional[float] = None) -> None:
    """Fill in win/loss for each signal using the next WIN_BARS_LOOKBACK bars.

    level_override: if provided, use this as the WIN threshold level for all signals.
    Otherwise, each signal uses its own resistance_level field.
    """
    bar_list = day_bars[day_bars["time"].apply(_is_rth)].reset_index(drop=True)

    for sig in signals:
        entry_time_str = sig["time"]
        matches = bar_list[bar_list["time"].apply(lambda t: t.strftime("%H:%M")) == entry_time_str]
        if matches.empty:
            sig["win"] = None
            continue
        li = int(matches.index[0])

        # Look ahead WIN_BARS_LOOKBACK bars
        lookahead = bar_list.iloc[li + 1 : li + 1 + WIN_BARS_LOOKBACK]
        if lookahead.empty:
            sig["win"] = None
            continue

        # Use per-signal resistance_level for grading (works for both fixed and structural modes)
        level = level_override if level_override is not None else sig["resistance_level"]
        win_threshold = level - WIN_REVERT_CENTS
        closed_back_below = (lookahead["close"] < win_threshold).any()
        sig["win"] = bool(closed_back_below)
        sig["max_drop_from_level"] = round(float(level - lookahead["low"].min()), 2)
        sig["bars_to_revert"] = int((lookahead["close"] < win_threshold).idxmax() - li) if closed_back_below else None


def _morning_high(day_rth: pd.DataFrame) -> Optional[float]:
    """High of the first 2 hours of RTH (09:30-11:30 ET)."""
    morning = day_rth[day_rth["time"].apply(lambda t: dt.time(9, 30) <= t < dt.time(11, 30))]
    if morning.empty:
        return None
    return float(morning["high"].max())


def _prior_pm_high(prior_rth: pd.DataFrame) -> Optional[float]:
    """High of the prior day's PM session (13:00-16:00 ET) — PM ceiling proxy."""
    pm = prior_rth[prior_rth["time"].apply(lambda t: dt.time(13, 0) <= t < dt.time(16, 0))]
    if pm.empty:
        return None
    return float(pm["high"].max())


def main() -> None:
    # ── Load data ────────────────────────────────────────────────────────────
    csv_path = SPY_CSV if SPY_CSV.exists() else SPY_CSV_FALLBACK
    if not csv_path.exists():
        print(f"ERROR: SPY CSV not found at {csv_path}")
        sys.exit(1)
    print(f"Loading {csv_path.name} ...")
    df = _load_spy(csv_path)

    all_signals: list[dict] = []
    trading_days = sorted(df["date"].unique())
    print(f"Scanning {len(trading_days)} trading days (mode={SCAN_MODE}) ...")

    last_signal_time: Optional[dt.datetime] = None

    for idx, day in enumerate(trading_days):
        day_str = str(day)
        day_bars = df[df["date"] == day].copy()

        rth_bars = day_bars[day_bars["time"].apply(_is_rth)].copy()
        if rth_bars.empty:
            continue

        # ── Derive resistance level based on mode ────────────────────────────
        if SCAN_MODE == "pdh":
            if idx == 0:
                continue
            prior_day = trading_days[idx - 1]
            prior_rth = df[df["date"] == prior_day]
            prior_rth = prior_rth[prior_rth["time"].apply(_is_rth)]
            if prior_rth.empty:
                continue
            level = float(prior_rth["high"].max())
            scan_bars = rth_bars
        elif SCAN_MODE == "morning_high":
            # Use morning high as afternoon resistance; only scan afternoon bars
            level = _morning_high(rth_bars)
            if level is None:
                continue
            # Only look for distribution/breakout in the afternoon (11:30-14:30 ET)
            scan_bars = rth_bars[rth_bars["time"].apply(lambda t: dt.time(11, 30) <= t <= ENTRY_TIME_END)].copy()
        elif SCAN_MODE == "prior_pm_high":
            if idx == 0:
                continue
            prior_day = trading_days[idx - 1]
            prior_rth_df = df[df["date"] == prior_day]
            prior_rth_df = prior_rth_df[prior_rth_df["time"].apply(_is_rth)]
            if prior_rth_df.empty:
                continue
            level = _prior_pm_high(prior_rth_df)
            if level is None:
                continue
            scan_bars = rth_bars
        elif SCAN_MODE == "structural":
            # Structural mode: no fixed level — derive ceiling from rolling window
            day_signals, last_signal_time = scan_day_structural(rth_bars, day_str, last_signal_time)
            if day_signals:
                grade_signals(day_signals, rth_bars)  # each signal uses its own resistance_level
                all_signals.extend(day_signals)
            if (idx + 1) % 50 == 0:
                print(f"  {idx + 1}/{len(trading_days)} days scanned, {len(all_signals)} signals so far ...")
            continue
        else:
            raise ValueError(f"Unknown SCAN_MODE: {SCAN_MODE}")

        day_signals, last_signal_time = scan_day(scan_bars, level, day_str, last_signal_time)
        if day_signals:
            # For grading, always use full rth_bars (exits can happen after entry)
            grade_signals(day_signals, rth_bars, level)
            all_signals.extend(day_signals)

        if (idx + 1) % 50 == 0:
            print(f"  {idx + 1}/{len(trading_days)} days scanned, {len(all_signals)} signals so far ...")

    # ── Aggregate stats ──────────────────────────────────────────────────────
    completed = [s for s in all_signals if s["win"] is not None]
    wins = [s for s in completed if s["win"]]
    losses = [s for s in completed if not s["win"]]

    wr = len(wins) / len(completed) if completed else 0.0
    avg_streak = np.mean([s["streak"] for s in all_signals]) if all_signals else 0.0
    avg_drop = np.mean([s.get("max_drop_from_level", 0) for s in completed]) if completed else 0.0

    # Streak breakdown
    streak_breakdown: dict[str, dict] = {}
    for s in completed:
        k = str(s["streak"])
        if k not in streak_breakdown:
            streak_breakdown[k] = {"total": 0, "wins": 0}
        streak_breakdown[k]["total"] += 1
        if s["win"]:
            streak_breakdown[k]["wins"] += 1
    for v in streak_breakdown.values():
        v["wr_pct"] = round(100 * v["wins"] / v["total"], 1) if v["total"] > 0 else None

    # Loser day check
    loser_day_fires = [s for s in all_signals if s["loser_day_guard"]]

    # Time breakdown
    time_breakdown: dict[str, dict] = {}
    for s in completed:
        h = s["time"][:2]  # "10", "11", etc.
        bucket = f"{h}:00"
        if bucket not in time_breakdown:
            time_breakdown[bucket] = {"total": 0, "wins": 0}
        time_breakdown[bucket]["total"] += 1
        if s["win"]:
            time_breakdown[bucket]["wins"] += 1
    for v in time_breakdown.values():
        v["wr_pct"] = round(100 * v["wins"] / v["total"], 1) if v["total"] > 0 else None

    level_proxy_desc = {
        "pdh": "PDH (prior day RTH high)",
        "morning_high": "Morning high (09:30-11:30 ET RTH high, tested in 11:30-14:30 afternoon window)",
        "prior_pm_high": "Prior PM high (prior day 13:00-16:00 ET high)",
    }.get(SCAN_MODE, SCAN_MODE)

    result = {
        "scan_date": str(dt.date.today()),
        "scan_mode": SCAN_MODE,
        "scan_type": "CLOSE_CEILING_FAKE_BREAKOUT_BEAR",
        "level_proxy": level_proxy_desc,
        "note": (
            "Level proxy is an approximation. The real pattern fires at named ★★+ carry/resistance "
            "levels from key-levels.json (which changes daily). PDH mode: too rare (N=2). "
            "morning_high mode: tests if morning high holds as afternoon resistance — "
            "a common intraday resistance-to-support-test pattern."
        ),
        "parameters": {
            "n_min_streak": N_MIN_STREAK,
            "entry_time_start": ENTRY_TIME_START.strftime("%H:%M"),
            "entry_time_end": ENTRY_TIME_END.strftime("%H:%M"),
            "cooldown_minutes": COOLDOWN_MINUTES,
            "win_bars_lookback": WIN_BARS_LOOKBACK,
            "win_revert_cents": WIN_REVERT_CENTS,
            "level_tolerance": LEVEL_TOLERANCE,
        },
        "n_signals": len(all_signals),
        "n_completed": len(completed),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "wr_pct": round(100 * wr, 1),
        "avg_streak_bars": round(float(avg_streak), 1),
        "avg_max_drop_from_level": round(float(avg_drop), 2),
        "loser_day_fires": len(loser_day_fires),
        "loser_day_details": [{"date": s["date"], "time": s["time"]} for s in loser_day_fires],
        "by_streak": streak_breakdown,
        "by_hour": time_breakdown,
        "guard_rail": "PASS" if len(loser_day_fires) == 0 else f"FAIL — {len(loser_day_fires)} fires on loser days",
        "op21_economics_gate": "PASS" if wr >= 0.50 else "FAIL",
        "signals": all_signals[:50],  # first 50 for review
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nResults: {len(all_signals)} signals, {len(completed)} completed, WR={100*wr:.1f}%")
    print(f"  Streak breakdown: {streak_breakdown}")
    print(f"  Loser day fires: {len(loser_day_fires)} ({result['guard_rail']})")
    print(f"  OP-21 economics gate: {result['op21_economics_gate']}")
    print(f"\nOutput: {OUT_PATH}")


if __name__ == "__main__":
    main()
