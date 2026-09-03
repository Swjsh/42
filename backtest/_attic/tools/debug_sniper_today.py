"""Debug: why didn't SNIPER fire on today's 740.79 ATH break?"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(r"C:\Users\jackw\Desktop\42") / "backtest"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO.parent))

import pandas as pd
import pytz

from autoresearch import runner as ar_runner
from lib.sniper_detector import (
    SniperParams,
    compute_levels,
    detect_sniper_break,
)

ET = pytz.timezone("America/New_York")
today = dt.date(2026, 5, 13)

# Load with yfinance top-up (mirror of watcher_live)
spy_full, vix_full = ar_runner.load_data(today - dt.timedelta(days=7), today)
spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"], utc=True)
spy_full["timestamp_et"] = spy_full["timestamp_et"].dt.tz_convert(ET).dt.tz_localize(None)
spy_full["date"] = spy_full["timestamp_et"].dt.date

# yfinance top-up for today
import yfinance as yf

df = yf.download("SPY", start=today - dt.timedelta(days=2), end=today + dt.timedelta(days=1),
                 interval="5m", auto_adjust=False, progress=False, prepost=False)
if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
    df.columns = df.columns.get_level_values(0)
df = df.reset_index()
df = df.rename(columns={df.columns[0]: "timestamp_et", "Open": "open", "High": "high",
                        "Low": "low", "Close": "close", "Volume": "volume"})
ts = df["timestamp_et"]
if hasattr(ts.iloc[0], "tzinfo") and ts.iloc[0].tzinfo is not None:
    df["timestamp_et"] = ts.dt.tz_convert(ET).dt.tz_localize(None)
df = df[df["timestamp_et"].dt.date == today]
df["date"] = df["timestamp_et"].dt.date

spy_full = pd.concat([spy_full, df[["timestamp_et", "open", "high", "low", "close", "volume", "date"]]],
                    ignore_index=True)
ts = pd.to_datetime(spy_full["timestamp_et"], utc=True, errors="coerce")
spy_full["timestamp_et"] = ts.dt.tz_convert(ET).dt.tz_localize(None)
spy_full = spy_full.drop_duplicates(subset=["timestamp_et"], keep="last").sort_values("timestamp_et").reset_index(drop=True)
spy_full["date"] = spy_full["timestamp_et"].dt.date

rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
              & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)

today_bars = rth[rth["timestamp_et"].dt.date == today].reset_index(drop=True)
print(f"rth total len: {len(rth)}, today bars: {len(today_bars)}")
print()
print("today's last 6 bars:")
print(today_bars.tail(6)[["timestamp_et", "open", "high", "low", "close", "volume"]].to_string())
print()

# Run SNIPER detector at each recent today bar
p = SniperParams(vol_mult=1.1, body_min_cents=0.02, min_stars=2,
                proximity_dollars=1.5, require_break_above_open=True)

for i in range(max(0, len(today_bars) - 6), len(today_bars)):
    bar = today_bars.iloc[i]
    # locate in rth
    matches = rth.index[rth["timestamp_et"] == bar["timestamp_et"]]
    if len(matches) == 0:
        continue
    bar_idx_full = int(matches[-1])
    levels = compute_levels(rth, bar["timestamp_et"], p)
    signal = detect_sniper_break(bar, bar_idx_full, rth, levels, p)
    ts_str = bar["timestamp_et"].strftime("%H:%M")
    o, h, l, c, v = bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]
    print(f"{ts_str} O={o:.2f} H={h:.2f} L={l:.2f} C={c:.2f} V={v:.0f} -> "
          f"signal={signal.direction if signal else 'NONE'}", end="")
    if signal:
        print(f" level={signal.level.label}@{signal.level.price:.2f} vol_ratio={signal.vol_ratio:.2f}")
    else:
        # Why no signal? Print levels seen
        rel_levels = [L for L in levels if abs(L.price - c) < p.proximity_dollars]
        print(f" | levels_near: {[(L.label, L.price, L.stars) for L in rel_levels]}")

print()
print("All compute_levels output (latest bar):")
last_bar = today_bars.iloc[-1]
levels = compute_levels(rth, last_bar["timestamp_et"], p)
for L in levels:
    print(f"  {L.label} @ {L.price:.2f} stars={L.stars} tier={L.tier}")
