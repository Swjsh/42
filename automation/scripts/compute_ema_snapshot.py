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

FIX 2026-06-28: select CSV by end-date parsed from filename (not st_size).
  st_size selected spy_5m_2025-01-01_2026-06-18.csv (large old file) over the
  smaller but newer spy_5m_2026-05-19_2026-06-26.csv -> 10-day-stale EMAs.
  Filename pattern: spy_5m_{start}_{end}[_suffix].csv — sort by parsed end-date.
"""
from __future__ import annotations

import json
import re
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

# Spot-deviation guard: if the snapshot's last_close deviates by more than this
# fraction from the live sight-beacon spot, the snapshot is stale / wrong CSV.
SPOT_DEVIATION_MAX = 0.03  # 3%

# Regex to extract the end-date from spy_5m_{start}_{end}[_suffix].csv
_CSV_END_DATE_RE = re.compile(r"spy_5m_\d{4}-\d{2}-\d{2}_(\d{4}-\d{2}-\d{2})")


def _csv_end_date(p: Path) -> dt.date:
    """Return the end-date from a spy_5m filename, or date.min if unparseable."""
    m = _CSV_END_DATE_RE.search(p.stem)
    if m:
        try:
            return dt.date.fromisoformat(m.group(1))
        except ValueError:
            pass
    return dt.date.min


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
    """Load the SPY CSV with the newest end-date in DATA_DIR.

    FIX 2026-06-28: previously sorted by st_size (file size), which selected a
    large historical file (spy_5m_2025-01-01_2026-06-18.csv) over a smaller but
    newer file (spy_5m_2026-05-19_2026-06-26.csv) and injected 10-day-old EMAs.
    Now sorts by the end-date parsed from the filename instead.
    """
    csvs = sorted(DATA_DIR.glob("spy_5m_*.csv"), key=_csv_end_date, reverse=True)
    if not csvs:
        return None
    chosen = csvs[0]
    print(f"[INFO] Selected CSV by end-date: {chosen.name} (end={_csv_end_date(chosen)})",
          file=sys.stderr)
    df = pd.read_csv(chosen)
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


def _spot_deviation_ok(snap: dict, beacon_path: Path | None = None) -> bool:
    """Return True if snap.last_close is within SPOT_DEVIATION_MAX of the sight-beacon spot.

    If the beacon file is missing/stale/unreadable the check passes (fail-open).
    Called by patch_today_bias before patching so a stale-CSV snapshot never
    silently contaminates today-bias with 10-day-old EMA values.
    """
    if beacon_path is None:
        beacon_path = STATE_DIR / "sight-beacon.json"
    last_close = snap.get("last_close")
    if last_close is None:
        return True  # no close to check; let downstream catch it
    try:
        beacon = json.loads(beacon_path.read_bytes().decode("utf-8", errors="replace"))
        spot = beacon.get("spy")
        if spot is None or spot <= 0:
            return True  # beacon has no valid spot; fail-open
        deviation = abs(last_close - spot) / spot
        if deviation > SPOT_DEVIATION_MAX:
            print(
                f"[WARN] EMA snapshot spot-deviation too large: "
                f"last_close={last_close} beacon_spot={spot} "
                f"deviation={deviation:.2%} > {SPOT_DEVIATION_MAX:.0%} — "
                f"snapshot NOT patched into today-bias (likely stale CSV)",
                file=sys.stderr,
            )
            return False
        return True
    except Exception as e:
        print(f"[WARN] spot-deviation check skipped (beacon read error): {e}", file=sys.stderr)
        return True  # fail-open


def patch_today_bias(snap: dict, beacon_path: Path | None = None) -> bool:
    """Patch today-bias.json key_levels EMA fields in-place. Returns True if patched.

    Spot-deviation guard: if snap.last_close deviates >3% from the live
    sight-beacon spot, the patch is rejected (stale CSV guard).
    beacon_path is injectable for tests; defaults to automation/state/sight-beacon.json.
    """
    bias_path = STATE_DIR / "today-bias.json"
    if not bias_path.exists():
        return False
    if not _spot_deviation_ok(snap, beacon_path):
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
