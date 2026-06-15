"""Show every trendline projecting near $736 at 5/8 14:55 ET."""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path
import pandas as pd
import pytz

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from lib.trendlines import detect_trendlines  # noqa: E402

spy = pd.read_csv(REPO / "data" / "spy_5m_2026-04-08_2026-05-08.csv")
spy["timestamp_et"] = spy["timestamp_et"].astype(str).str.replace("T", " ", regex=False)
spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"], utc=True, errors="coerce")
spy = spy.dropna(subset=["timestamp_et"]).reset_index(drop=True)
spy["timestamp_et"] = spy["timestamp_et"].dt.tz_convert(pytz.timezone("America/New_York")).dt.tz_localize(None)
spy["date"] = spy["timestamp_et"].dt.date

target = pd.Timestamp("2026-05-08 14:55:00")
target_ts = int(target.timestamp())

# Use last 2 sessions of RTH bars
rth = spy[(spy["timestamp_et"].dt.time >= dt.time(9, 30))
          & (spy["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
eligible_dates = sorted(rth["date"].unique())[-2:]
window = rth[(rth["date"].isin(eligible_dates)) & (rth["timestamp_et"] <= target)].copy()
window["timestamp_unix"] = window["timestamp_et"].astype("int64") // 1_000_000_000

for mt in (2, 3, 4):
    lines = detect_trendlines(window, min_touches=mt)
    nearby = [line for line in lines if abs(line.price_at(target_ts) - 736.0) <= 1.0]
    print(f"\nmin_touches={mt}: total={len(lines)} nearby_736={len(nearby)}")
    for line in sorted(nearby, key=lambda l: l.price_at(target_ts)):
        proj = line.price_at(target_ts)
        anchors = line.anchor_points
        anchor_dates = [dt.datetime.fromtimestamp(a[0]).strftime("%m-%d %H:%M") for a in anchors]
        print(f"  {line.direction:11s} ${line.slope_per_hour():+.3f}/hr  proj@1455=${proj:.2f}  touches={line.touch_count}  r²={line.r_squared:.2f}")
        print(f"    anchors: {list(zip(anchor_dates, [round(a[1],2) for a in anchors]))}")

# Also check: what would J's manual line predict (cross-session ascending)?
import math
y1 = 729.75
y2 = 734.70
t1 = pd.Timestamp("2026-05-07 14:30:00").timestamp()
t2 = pd.Timestamp("2026-05-08 09:30:00").timestamp()
slope = (y2 - y1) / (t2 - t1)
proj_at_1455 = y2 + slope * (target_ts - t2)
print(f"\nJ's mental line (5/7 14:30 729.75 -> 5/8 09:30 734.70):")
print(f"  Slope: ${slope*3600:.3f}/hr")
print(f"  Projection at 5/8 14:55: ${proj_at_1455:.2f}")
