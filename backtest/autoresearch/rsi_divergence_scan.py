"""rsi_divergence_scan.py — Stage-1 RSI divergence watcher scanner.

Detects classic 5m RSI divergences on SPY:
  BEAR: price makes higher swing high, RSI makes lower swing high → fade the momentum
  BULL: price makes lower swing low, RSI makes higher swing low → fade the weakness

Win definition: next WIN_BARS bars contain a close in the signal direction by
WIN_MOVE_CENTS from the signal bar close.

Output: analysis/backtests/rsi-divergence-scan/results.json
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ── Parameters ────────────────────────────────────────────────────────────────
RSI_PERIOD: int = 14
SWING_LOOKBACK: int = 5          # bars to look back for prior swing high/low
MIN_SWING_SIZE: float = 0.30     # price swing minimum (SPY $)
MIN_RSI_DIVERGENCE: float = 2.0  # RSI must diverge by at least 2 points
ENTRY_TIME_START = dt.time(9, 40)
ENTRY_TIME_END   = dt.time(15, 0)
WIN_BARS: int = 6                 # check N bars after signal
WIN_MOVE_CENTS: float = 0.25     # close must move ≥25c in signal direction to WIN
COOLDOWN_BARS: int = 10          # min bars between same-direction signals

DATA_FILE = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-19_merged.csv"

J_ANCHOR_DAYS = {
    "winners": ["2025-04-29", "2025-05-01", "2025-05-04"],
    "losers":  ["2025-05-05", "2025-05-06", "2025-05-07"],
}


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _find_prior_swing(series: pd.Series, idx: int, direction: str, lookback: int) -> tuple[int, float] | None:
    """Find the most recent swing high (direction='high') or low (direction='low')."""
    start = max(0, idx - lookback - SWING_LOOKBACK)
    end   = idx - 2  # at least 2 bars back for confirmation
    if end <= start:
        return None
    window = series.iloc[start:end + 1]
    if direction == "high":
        peak_pos = window.idxmax()
    else:
        peak_pos = window.idxmin()
    return peak_pos, series.loc[peak_pos]


def scan(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["ts"] = pd.to_datetime(df["timestamp_et"])
    df["date"] = df["ts"].dt.date.astype(str)
    df["time"] = df["ts"].dt.time

    # RTH filter
    df = df[(df["time"] >= ENTRY_TIME_START) & (df["time"] <= ENTRY_TIME_END)].copy()
    df = df.reset_index(drop=True)

    df["rsi"] = _rsi(df["close"])
    df = df.dropna(subset=["rsi"]).reset_index(drop=True)

    signals: list[dict] = []
    last_bear_idx = -COOLDOWN_BARS
    last_bull_idx = -COOLDOWN_BARS

    for i in range(SWING_LOOKBACK + RSI_PERIOD, len(df) - WIN_BARS):
        bar = df.iloc[i]
        close_i = bar["close"]
        rsi_i   = bar["rsi"]

        # ── BEARISH DIVERGENCE ────────────────────────────────────────────────
        if i - last_bear_idx >= COOLDOWN_BARS:
            prior = _find_prior_swing(df["high"], i, "high", SWING_LOOKBACK)
            if prior is not None:
                prior_idx, prior_high = prior
                prior_rsi = df.loc[prior_idx, "rsi"]
                if (close_i > prior_high + MIN_SWING_SIZE and          # price HH
                        rsi_i < prior_rsi - MIN_RSI_DIVERGENCE):       # RSI LH
                    # Check win: next WIN_BARS bars close <= entry - WIN_MOVE_CENTS
                    future = df.iloc[i + 1 : i + 1 + WIN_BARS]
                    win = any(row["close"] <= close_i - WIN_MOVE_CENTS for _, row in future.iterrows())
                    signals.append({
                        "direction": "BEAR",
                        "date": bar["date"],
                        "time": str(bar["time"]),
                        "bar_idx": int(i),
                        "entry_close": round(close_i, 2),
                        "rsi": round(rsi_i, 1),
                        "prior_high": round(prior_high, 2),
                        "prior_rsi": round(prior_rsi, 1),
                        "price_divergence": round(close_i - prior_high, 2),
                        "rsi_divergence": round(rsi_i - prior_rsi, 1),
                        "win": win,
                    })
                    last_bear_idx = i

        # ── BULLISH DIVERGENCE ────────────────────────────────────────────────
        if i - last_bull_idx >= COOLDOWN_BARS:
            prior = _find_prior_swing(df["low"], i, "low", SWING_LOOKBACK)
            if prior is not None:
                prior_idx, prior_low = prior
                prior_rsi = df.loc[prior_idx, "rsi"]
                if (close_i < prior_low - MIN_SWING_SIZE and            # price LL
                        rsi_i > prior_rsi + MIN_RSI_DIVERGENCE):        # RSI HL
                    future = df.iloc[i + 1 : i + 1 + WIN_BARS]
                    win = any(row["close"] >= close_i + WIN_MOVE_CENTS for _, row in future.iterrows())
                    signals.append({
                        "direction": "BULL",
                        "date": bar["date"],
                        "time": str(bar["time"]),
                        "bar_idx": int(i),
                        "entry_close": round(close_i, 2),
                        "rsi": round(rsi_i, 1),
                        "prior_low": round(prior_low, 2),
                        "prior_rsi": round(prior_rsi, 1),
                        "price_divergence": round(prior_low - close_i, 2),
                        "rsi_divergence": round(rsi_i - prior_rsi, 1),
                        "win": win,
                    })
                    last_bull_idx = i

    return signals


def _anchor_stats(signals: list[dict], day: str) -> dict | None:
    day_sigs = [s for s in signals if s["date"] == day]
    if not day_sigs:
        return None
    wins = sum(1 for s in day_sigs if s["win"])
    return {"n": len(day_sigs), "wins": wins, "wr_pct": round(100 * wins / len(day_sigs), 1),
            "signals": [f"{s['direction']}@{s['time']}" for s in day_sigs]}


def main() -> None:
    print("[rsi-div] Loading SPY 5m data...")
    df = pd.read_csv(DATA_FILE)
    print(f"[rsi-div] {len(df):,} bars, scanning...")

    signals = scan(df)

    bear = [s for s in signals if s["direction"] == "BEAR"]
    bull = [s for s in signals if s["direction"] == "BULL"]

    bear_wr = 100 * sum(s["win"] for s in bear) / max(1, len(bear))
    bull_wr = 100 * sum(s["win"] for s in bull) / max(1, len(bull))

    print("\nRESULTS")
    print(f"BEAR divergence: N={len(bear)}, WR={bear_wr:.1f}%")
    print(f"BULL divergence: N={len(bull)}, WR={bull_wr:.1f}%")

    print("\nJ ANCHOR DAYS")
    anchor_results = {}
    for label, days in J_ANCHOR_DAYS.items():
        for day in days:
            stats = _anchor_stats(signals, day)
            anchor_results[day] = {"label": label, **(stats or {"n": 0, "wins": 0, "wr_pct": None, "signals": []})}
            status = "WINNER" if label == "winners" else "LOSER"
            if stats:
                print(f"  [{status}] {day}: N={stats['n']} WR={stats['wr_pct']}% | {stats['signals']}")
            else:
                print(f"  [{status}] {day}: NO SIGNALS")

    months: dict[str, list] = {}
    for s in signals:
        m = s["date"][:7]
        months.setdefault(m, []).append(s)
    print("\nMONTHLY BREAKDOWN")
    for m in sorted(months):
        sigs = months[m]
        wr = 100 * sum(s["win"] for s in sigs) / len(sigs)
        print(f"  {m}: N={len(sigs)} WR={wr:.1f}%")

    out_dir = ROOT / "analysis" / "backtests" / "rsi-divergence-scan"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "scan_date": dt.date.today().isoformat(),
        "parameters": {
            "rsi_period": RSI_PERIOD,
            "swing_lookback": SWING_LOOKBACK,
            "min_swing_size": MIN_SWING_SIZE,
            "min_rsi_divergence": MIN_RSI_DIVERGENCE,
            "win_bars": WIN_BARS,
            "win_move_cents": WIN_MOVE_CENTS,
            "cooldown_bars": COOLDOWN_BARS,
        },
        "summary": {
            "bear_n": len(bear), "bear_wr_pct": round(bear_wr, 1),
            "bull_n": len(bull), "bull_wr_pct": round(bull_wr, 1),
            "total_n": len(signals),
        },
        "anchor_days": anchor_results,
        "monthly_breakdown": {m: {"n": len(v), "wr_pct": round(100 * sum(s["win"] for s in v) / len(v), 1)}
                              for m, v in sorted(months.items())},
        "signals": signals,
    }
    out = out_dir / "results.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\n[rsi-div] Saved to {out}")


if __name__ == "__main__":
    main()
