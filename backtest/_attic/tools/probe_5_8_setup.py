"""One-off probe: at 5/8 14:55 ET, what trendlines did the detector find,
and which (if any) would have produced a TRENDLINE_BREAK_RETEST trigger?
"""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from lib.trendlines import detect_trendlines  # noqa: E402
from lib.levels import _detect_from_history  # noqa: E402

spy_csv = sorted((REPO / "data").glob("spy_5m_*.csv"))[-1]
spy = pd.read_csv(spy_csv)
spy["timestamp_et"] = spy["timestamp_et"].astype(str).str.replace("T", " ", regex=False)
spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"], utc=True, errors="coerce")
spy = spy.dropna(subset=["timestamp_et"]).reset_index(drop=True)
import pytz
spy["timestamp_et"] = spy["timestamp_et"].dt.tz_convert(pytz.timezone("America/New_York")).dt.tz_localize(None)
spy["date"] = spy["timestamp_et"].dt.date

target_ts = dt.datetime(2026, 5, 8, 14, 55)
target_match = spy[spy["timestamp_et"] == target_ts]
if target_match.empty:
    print(f"Bar at {target_ts} not found in CSV; CSV last row: {spy.iloc[-1]['timestamp_et']}")
    sys.exit(1)

target_idx_full = int(target_match.index[0])
print(f"Found 14:55 bar at idx {target_idx_full}: {dict(spy.iloc[target_idx_full])}")
prior_bar = spy.iloc[target_idx_full - 1]
print(f"Prior bar (14:50): close={prior_bar['close']}")
print(f"Current bar (14:55): close={spy.iloc[target_idx_full]['close']}")

# Run detection on last 2 sessions of RTH bars
rth = spy[(spy["timestamp_et"].dt.time >= dt.time(9, 30))
          & (spy["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
target_rth_match = rth[rth["timestamp_et"] == target_ts]
if target_rth_match.empty:
    print(f"\nERROR: 14:55 bar not in RTH-filtered data")
    sys.exit(1)
target_rth_idx = int(target_rth_match.index[0])
print(f"\n14:55 RTH idx: {target_rth_idx}")

eligible_dates = sorted(rth["date"].unique())[-2:]
window = rth[(rth["date"].isin(eligible_dates)) & (rth["timestamp_et"] <= target_ts)].copy()
window["timestamp_unix"] = window["timestamp_et"].astype("int64") // 1_000_000_000
print(f"Detection window: {len(window)} bars, {eligible_dates}")

lines = detect_trendlines(window)
print(f"\nDetected {len(lines)} trendlines:")
for line in lines:
    proj = line.price_at(int(target_ts.timestamp()))
    print(f"  {line.direction:11s} slope=${line.slope_per_hour():+.3f}/hr  price@14:55=${proj:.2f}  touches={line.touch_count}  r²={line.r_squared:.2f}")

prior_close = float(prior_bar["close"])
cur_close = float(spy.iloc[target_idx_full]["close"])
cur_ts = int(target_ts.timestamp())

# Convert ET-naive to UTC-aware for comparison
print(f"\nChecking break condition: prior_close={prior_close} cur_close={cur_close}")
for line in lines:
    line_now = line.price_at(cur_ts)
    line_prior = line.price_at(cur_ts - 300)
    above_prior = prior_close > line_prior
    above_now = cur_close > line_now
    crossed = above_prior != above_now
    cross_dollars = abs(line_now - cur_close) if crossed else 0
    print(f"  {line.direction:11s} prior_above={above_prior}  now_above={above_now}  crossed={crossed}  cross_$={cross_dollars:.2f}")

# Active levels at 14:55
levels = _detect_from_history(spy[spy["timestamp_et"] <= target_ts].copy(), target_ts.date())
nonround = [L for L in levels.active if abs(L - round(L)) > 0.01]
print(f"\nActive levels (non-round): {sorted(nonround)}")
print(f"All active levels: {sorted(levels.active)}")
