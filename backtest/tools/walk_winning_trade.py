"""Walk through J's winning trades minute-by-minute against raw chart data.

Prints a detailed timeline showing what J was seeing at each moment:
  - SPY 3-min OHLCV (resampled from 1-min)
  - Option 3-min OHLCV
  - Candlestick patterns
  - Volume vs 20-bar avg
  - J's entry and exit markers

Output is dense plain text, designed for reading + extracting strategy lessons.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HIRES = ROOT / "data" / "highres"

# (date, option_symbol, entry_time, exits, key_levels_to_watch)
TRADES = [
    {
        "date": "2026-04-29",
        "symbol": "SPY260429P00710000",
        "entry": ("10:25:51", 6, 1.67),
        "exits": [
            ("12:27:57", 5, 2.17),  # primary
            ("12:37:41", 1, 2.69),  # runner
        ],
        "levels": {711.40: "rejection level", 709.40: "PMlow target"},
        "context": "Pre-rules trade. SPY was bleeding overnight; ribbon bear-stacked; "
                   "rally to 711.40 got rejected with sell triangle print.",
    },
    {
        "date": "2026-05-01",
        "symbol": "SPY260501P00721000",
        "entry": ("13:09:13", 10, 0.46),
        "second_entry": ("13:36:11", 10, 0.19),
        "exits": [("14:47:55", 20, 0.58)],
        "levels": {723.50: "descending trendline", 721.00: "intraday level", 720.00: "round#"},
        "context": "Morning rally died at 724.80; descending trendline drew itself; "
                   "13:09 was anticipation entry (rule break); 13:36 was real trigger "
                   "at 723.20 trendline rejection.",
    },
    {
        "date": "2026-05-04",
        "symbol": "SPY260504P00721000",
        "entry": ("10:27:50", 10, 0.85),
        "exits": [
            ("11:14:05", 8, 1.51),   # TP1 — 8 of 10
            ("11:18:29", 2, 1.90),   # runner
        ],
        "levels": {721.58: "premarket level + multi-day trendline", 717.50: "next support"},
        "context": "Premarket repeatedly tested 721.58; multi-day trendline confluence; "
                   "10:27 rejection candle hit textbook; 11:00 breakdown launched the leg.",
    },
]


def load_data(symbol_root: str, date_str: str, kind: str = "SPY") -> pd.DataFrame:
    """kind = 'SPY' or 'OPT'. Loads 1-min CSV, returns DataFrame."""
    if kind == "SPY":
        path = HIRES / f"SPY_1m_{date_str}.csv"
    else:
        path = HIRES / f"{symbol_root}_1m_{date_str}.csv"
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["timestamp_et"])
    if df["ts"].dt.tz is not None:
        df["ts"] = df["ts"].dt.tz_localize(None)
    return df


def resample_3min(df_1m: pd.DataFrame, has_vwap: bool = True) -> pd.DataFrame:
    """Resample 1-min bars to 3-min."""
    df = df_1m.copy()
    df = df.set_index("ts")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    if has_vwap:
        # vwap sum is wrong; recompute
        agg["vwap"] = "mean"  # rough
    out = df.resample("3min", origin="start_day").agg(agg)
    out = out.dropna(subset=["close"])
    return out.reset_index()


def label_candle(o: float, h: float, l: float, c: float) -> str:
    """Return a short candlestick pattern name."""
    rng = h - l
    if rng <= 0:
        return "flat"
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    body_pct = body / rng
    upper_pct = upper_wick / rng
    lower_pct = lower_wick / rng
    is_red = c < o
    is_green = c > o
    if body_pct < 0.10:
        return "doji"
    # Marubozu strong continuation
    if body_pct >= 0.75 and upper_pct <= 0.10 and lower_pct <= 0.10:
        return "bear_marubozu" if is_red else "bull_marubozu"
    # Reversal: shooting star (bear), hammer (bull)
    if upper_pct >= 0.50 and lower_pct <= 0.20 and body_pct <= 0.30:
        return "shooting_star" if is_red else "inv_hammer"
    if lower_pct >= 0.50 and upper_pct <= 0.20 and body_pct <= 0.30:
        return "hammer" if is_green else "hanging_man"
    if is_red:
        return "red"
    if is_green:
        return "green"
    return "neutral"


def near_level(price: float, levels: dict, tol: float = 0.30) -> str:
    for L, label in levels.items():
        if abs(price - L) <= tol:
            return f"@{L:.2f} ({label})"
    return ""


def walk(trade: dict):
    date_str = trade["date"]
    print("\n" + "=" * 90)
    print(f"  {date_str}  ::  {trade['symbol']}")
    print(f"  CONTEXT: {trade['context']}")
    print("=" * 90)

    spy_1m = load_data("", date_str, "SPY")
    opt_1m = load_data(trade["symbol"], date_str, "OPT")

    spy_3m = resample_3min(spy_1m, has_vwap=True)
    opt_3m = resample_3min(opt_1m, has_vwap=True)

    # Compute volume baseline (20 3-min bar SMA)
    spy_3m["vol_avg20"] = spy_3m["volume"].rolling(20, min_periods=5).mean()

    # Determine windows around entry/exits
    entry_t = dt.datetime.fromisoformat(f"{date_str}T{trade['entry'][0]}")
    exit_times = [dt.datetime.fromisoformat(f"{date_str}T{e[0]}") for e in trade["exits"]]
    second_entry = trade.get("second_entry")
    if second_entry:
        exit_times.insert(0, dt.datetime.fromisoformat(f"{date_str}T{second_entry[0]}"))

    # 30 min before entry through 5 min after last exit
    window_start = entry_t - dt.timedelta(minutes=30)
    window_end = exit_times[-1] + dt.timedelta(minutes=10)

    spy_w = spy_3m[(spy_3m["ts"] >= window_start) & (spy_3m["ts"] <= window_end)].copy()
    opt_w = opt_3m[(opt_3m["ts"] >= window_start) & (opt_3m["ts"] <= window_end)].copy()

    # Merge SPY + opt by timestamp (3-min aligned)
    merged = spy_w.merge(
        opt_w[["ts", "open", "high", "low", "close", "volume"]],
        on="ts", how="left", suffixes=("_spy", "_opt"),
    )

    # Build event annotations
    events_at = {}
    e0_min = entry_t.replace(second=0)
    e0_3m = e0_min - dt.timedelta(minutes=e0_min.minute % 3)
    events_at[e0_3m] = f">>> ENTRY  {trade['entry'][1]} @ ${trade['entry'][2]:.2f}"
    if second_entry:
        e1_min = dt.datetime.fromisoformat(f"{date_str}T{second_entry[0]}").replace(second=0)
        e1_3m = e1_min - dt.timedelta(minutes=e1_min.minute % 3)
        events_at[e1_3m] = f">>> ADD    {second_entry[1]} @ ${second_entry[2]:.2f}"
    for ex_time, ex_qty, ex_px in trade["exits"]:
        ex_min = dt.datetime.fromisoformat(f"{date_str}T{ex_time}").replace(second=0)
        ex_3m = ex_min - dt.timedelta(minutes=ex_min.minute % 3)
        prev = events_at.get(ex_3m, "")
        events_at[ex_3m] = (prev + " | " if prev else "") + f"<<< SELL {ex_qty} @ ${ex_px:.2f}"

    # Header
    print(f"  3-min resample.  Window: {window_start.strftime('%H:%M')} - {window_end.strftime('%H:%M')} ET")
    print()
    hdr = (f"  {'TIME':>5}  {'SPY':>13}  {'rng':>4}  {'vol':>6}  {'v/20':>5}  "
           f"{'pattern':>14}  {'opt':>22}  level/event")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for _, row in merged.iterrows():
        ts = row["ts"]
        o, h, l, c = row["open_spy"], row["high_spy"], row["low_spy"], row["close_spy"]
        if pd.isna(c):
            continue
        rng = h - l
        vol = int(row["volume_spy"]) if not pd.isna(row["volume_spy"]) else 0
        v20 = row["vol_avg20"]
        v_ratio = (vol / v20) if v20 and v20 > 0 else 0
        pat = label_candle(o, h, l, c)
        opt_str = ""
        if not pd.isna(row.get("close_opt", float("nan"))):
            opt_o = row["open_opt"]; opt_h = row["high_opt"]
            opt_l = row["low_opt"]; opt_c = row["close_opt"]
            opt_str = f"${opt_o:.2f}-{opt_h:.2f}-{opt_l:.2f}-{opt_c:.2f}"
        level_tag = near_level(c, trade["levels"])
        ev = events_at.get(ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts, "")
        time_str = ts.strftime("%H:%M")
        print(
            f"  {time_str:>5}  {c:>7.2f} {pat[0:1]:<5}  {rng:>4.2f}  {vol:>6,}  "
            f"{v_ratio:>4.1f}x  {pat:>14}  {opt_str:>22}  {level_tag}  {ev}"
        )


def main():
    for trade in TRADES:
        walk(trade)
    print("\n" + "=" * 90)
    print("END")
    print("=" * 90)


if __name__ == "__main__":
    main()
