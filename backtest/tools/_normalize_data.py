"""Robustly re-normalize the missed-week SPY+VIX CSVs to a single uniform timestamp
format (space sep, -04:00), coercing any mix of T/space via utc=True. Verifies 8 RTH
days survive. This is the permanent fix for the mixed-format truncation that made the
sniper matrix see only the warmup days."""
import datetime as dt
from pathlib import Path
import pandas as pd

DATA = Path(r"C:\Users\jackw\Desktop\42\backtest\data")
out = []
for kind in ["spy", "vix"]:
    p = DATA / f"{kind}_5m_2026-05-19_2026-05-29.csv"
    df = pd.read_csv(p)
    n0 = len(df)
    ts = pd.to_datetime(df["timestamp_et"], utc=True, format="mixed")  # tolerate T AND space
    bad = int(ts.isna().sum())
    ts_et = ts.dt.tz_convert("America/New_York")
    df["timestamp_et"] = ts_et.dt.strftime("%Y-%m-%d %H:%M:%S-04:00")
    df.to_csv(p, index=False)
    # verify
    chk = pd.read_csv(p)
    cts = pd.to_datetime(chk["timestamp_et"], format="ISO8601")
    rth = chk[(cts.dt.time >= dt.time(9, 30)) & (cts.dt.time < dt.time(16, 0))]
    rdays = sorted(set(cts[(cts.dt.time >= dt.time(9, 30)) & (cts.dt.time < dt.time(16, 0))].dt.date.astype(str)))
    out.append(f"{kind}: rows={n0} unparseable={bad} | RTH rows={len(rth)} | RTH days={rdays}")

(DATA / "_normalize.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
