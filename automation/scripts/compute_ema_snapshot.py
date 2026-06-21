"""compute_ema_snapshot.py

Pre-premarket snapshot: compute Saty Pivot Ribbon EMA values (fast=13, pivot=20,
slow=48) and SMA 50 from the latest SPY 5m CSV. Writes:

    automation/state/ema-snapshot.json    (authoritative snapshot for premarket)
    automation/state/today-bias.json      (patches key_levels EMA fields in-place)

Run at 08:20 ET (Gamma_EmaSnapshot), 10 min before Gamma_Premarket. Gives premarket
a reliable fallback if TradingView MCP doesn't have the Saty Pivot Ribbon loaded.

EMA periods from backtest/lib/ribbon_config.json (fingerprinted 2026-05-07):
  fast_ema=13, pivot_ema=20, slow_ema=48, sma_50=50
Price source: close. Seed: SMA-then-EMA (matches TradingView ta.ema).

Cost: $0. No LLM, no MCP, no network calls.
"""
from __future__ import annotations

import json
import sys
import datetime as dt
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "backtest" / "data"
STATE_DIR = REPO / "automation" / "state"

FAST_EMA = 13
PIVOT_EMA = 20
SLOW_EMA = 48
SMA_50 = 50
# Bars of history needed to seed EMAs reliably (2x the longest period)
MIN_BARS = SMA_50 * 4


def _parse_wall_clock(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str.slice(0, 19), format="%Y-%m-%d %H:%M:%S")


def ema(closes: pd.Series, period: int) -> pd.Series:
    """TradingView-style EMA: seed with SMA of first N bars, then EMA."""
    result = closes.copy().astype(float) * float("nan")
    seed_end = period - 1
    if seed_end >= len(closes):
        return result
    seed_val = closes.iloc[:period].mean()
    result.iloc[seed_end] = seed_val
    k = 2.0 / (period + 1)
    for i in range(seed_end + 1, len(closes)):
        result.iloc[i] = closes.iloc[i] * k + result.iloc[i - 1] * (1 - k)
    return result


def sma(closes: pd.Series, period: int) -> pd.Series:
    return closes.rolling(period).mean()


def load_latest_spy() -> pd.DataFrame | None:
    """Load the largest (most recent) SPY CSV in DATA_DIR."""
    csvs = sorted(DATA_DIR.glob("spy_5m_*.csv"), key=lambda p: p.stat().st_size, reverse=True)
    if not csvs:
        return None
    df = pd.read_csv(csvs[0])
    df["timestamp_et"] = _parse_wall_clock(df["timestamp_et"])
    df = df.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et").reset_index(drop=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    return df


def compute_snapshot(df: pd.DataFrame) -> dict:
    closes = df["close"]
    if len(closes) < MIN_BARS:
        raise ValueError(f"Only {len(closes)} bars — need {MIN_BARS} to seed EMAs reliably.")

    fast_s  = ema(closes, FAST_EMA)
    pivot_s = ema(closes, PIVOT_EMA)
    slow_s  = ema(closes, SLOW_EMA)
    sma50_s = sma(closes, SMA_50)

    last = df.iloc[-1]
    idx = len(closes) - 1

    return {
        "computed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "last_bar_timestamp": str(last["timestamp_et"]),
        "last_close": round(float(last["close"]), 2),
        "ema_fast": round(float(fast_s.iloc[idx]), 2) if pd.notna(fast_s.iloc[idx]) else None,
        "ema_pivot": round(float(pivot_s.iloc[idx]), 2) if pd.notna(pivot_s.iloc[idx]) else None,
        "ema_slow": round(float(slow_s.iloc[idx]), 2) if pd.notna(slow_s.iloc[idx]) else None,
        "sma_50": round(float(sma50_s.iloc[idx]), 2) if pd.notna(sma50_s.iloc[idx]) else None,
        "periods": {"fast_ema": FAST_EMA, "pivot_ema": PIVOT_EMA, "slow_ema": SLOW_EMA, "sma_50": SMA_50},
        "source": "computed-from-csv",
        "csv_bars": len(closes),
    }


def patch_today_bias(snap: dict) -> bool:
    """Patch today-bias.json key_levels EMA fields in-place. Returns True if patched."""
    bias_path = STATE_DIR / "today-bias.json"
    if not bias_path.exists():
        return False
    try:
        bias = json.loads(bias_path.read_bytes().decode("utf-8", errors="replace"))
        kl = bias.setdefault("key_levels", {})
        # Only patch if currently null (don't overwrite TradingView values)
        changed = False
        for field in ("ema_fast", "ema_pivot", "ema_slow", "sma_50"):
            if kl.get(field) is None and snap.get(field) is not None:
                kl[field] = snap[field]
                changed = True
        if changed:
            bias_path.write_bytes(json.dumps(bias, indent=2).encode("utf-8"))
        return changed
    except Exception as e:
        print(f"[WARN] Could not patch today-bias.json: {e}", file=sys.stderr)
        return False


def main() -> None:
    df = load_latest_spy()
    if df is None:
        print("[ERROR] No SPY CSV found in", DATA_DIR, file=sys.stderr)
        sys.exit(1)

    snap = compute_snapshot(df)

    snap_path = STATE_DIR / "ema-snapshot.json"
    snap_path.write_bytes(json.dumps(snap, indent=2).encode("utf-8"))
    print(f"[OK] ema-snapshot.json written: fast={snap['ema_fast']} pivot={snap['ema_pivot']} "
          f"slow={snap['ema_slow']} sma50={snap['sma_50']}")

    patched = patch_today_bias(snap)
    if patched:
        print("[OK] today-bias.json key_levels EMA fields patched from CSV snapshot")
    else:
        print("[INFO] today-bias.json not patched (either no file or TradingView values already populated)")


if __name__ == "__main__":
    main()
