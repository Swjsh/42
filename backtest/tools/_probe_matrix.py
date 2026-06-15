import sys, datetime as dt
from pathlib import Path
import pandas as pd
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
DATA = REPO / "data"; ABT = REPO.parent / "analysis" / "backtests"
out = []

spy = pd.read_csv(DATA / "spy_5m_2026-05-19_2026-05-29.csv")
spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"], format="ISO8601")
rth = spy[(spy["timestamp_et"].dt.time >= dt.time(9,30)) & (spy["timestamp_et"].dt.time < dt.time(16,0))].reset_index(drop=True)
out.append(f"rth rows: {len(rth)} | tz: {rth['timestamp_et'].dt.tz}")
out.append(f"rth dates: {sorted(set(rth['timestamp_et'].dt.date.astype(str)))}")

df = pd.read_csv(ABT / "missed_week_bold" / "trades.csv")
df["date"] = df["date"].astype(str)
calls = df[df["c_or_p"] == "C"]
out.append(f"bold call rows total: {len(calls)}")
out.append(f"bold call dates: {sorted(set(calls['date']))}")
mdates = {"2026-05-26","2026-05-27","2026-05-28","2026-05-29"}
matched = 0
for _, r in calls.iterrows():
    if r["date"] not in mdates:
        out.append(f"  SKIP (not missed-day): {r['date']} {r['time_entry']}")
        continue
    ft = str(r["time_entry"])
    t = dt.time.fromisoformat(ft if len(ft) > 5 else ft + ":00")
    m = rth[(rth["timestamp_et"].dt.date.astype(str) == r["date"]) & (rth["timestamp_et"].dt.time == t)]
    out.append(f"  {r['date']} {ft} (t={t}) -> matched {len(m)} idx={list(m.index)[:1]}")
    if len(m):
        matched += 1
out.append(f"TOTAL matched: {matched}")
(REPO / "data" / "_probe.txt").write_text("\n".join(out), encoding="utf-8")
print("done")
