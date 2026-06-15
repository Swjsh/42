"""Extract clean per-day market facts for the missed days from the verified
Alpaca SPY 5m CSV + reconstructed VIX, plus the engine decision density per day.
Writes ONE JSON the synthesis + journal-backfill steps consume (avoids re-deriving
and avoids cross-turn render garbling)."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

REPO = Path(r"C:\Users\jackw\Desktop\42")
DATA = REPO / "backtest" / "data"
OUT = REPO / "analysis" / "backtests" / "_missed_week_facts.json"

spy = pd.read_csv(DATA / "spy_5m_2026-05-19_2026-05-29.csv")
vix = pd.read_csv(DATA / "vix_5m_2026-05-19_2026-05-29.csv")
for df in (spy, vix):
    df["ts"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df["d"] = df["ts"].dt.date.astype(str)
    df["t"] = df["ts"].dt.time

dec = pd.read_csv(REPO / "analysis" / "backtests" / "missed_week_2026-05-26_29" / "decisions.csv")
dec["ts"] = pd.to_datetime(dec["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
dec["d"] = dec["ts"].dt.date.astype(str)

RTH_LO, RTH_HI = pd.to_datetime("09:30").time(), pd.to_datetime("16:00").time()
MISSED = ["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"]
PRIOR_CLOSE = {  # RTH close of the prior trading day (from same CSV)
}

facts = {}
# prior closes for gap calc
all_days = sorted(spy["d"].unique())
closes = {}
for d in all_days:
    r = spy[(spy["d"] == d) & (spy["t"] >= RTH_LO) & (spy["t"] < RTH_HI)]
    if len(r):
        closes[d] = float(r.sort_values("ts").iloc[-1]["close"])

for i, d in enumerate(MISSED):
    rth = spy[(spy["d"] == d) & (spy["t"] >= RTH_LO) & (spy["t"] < RTH_HI)].sort_values("ts")
    if rth.empty:
        facts[d] = {"note": "NO RTH DATA"}
        continue
    o = float(rth.iloc[0]["open"]); c = float(rth.iloc[-1]["close"])
    hi = float(rth["high"].max()); lo = float(rth["low"].min())
    hi_t = rth.loc[rth["high"].idxmax(), "t"].strftime("%H:%M")
    lo_t = rth.loc[rth["low"].idxmin(), "t"].strftime("%H:%M")
    vrth = vix[(vix["d"] == d) & (vix["t"] >= RTH_LO) & (vix["t"] < RTH_HI)].sort_values("ts")
    vix_o = float(vrth.iloc[0]["close"]) if len(vrth) else None
    vix_hi = float(vrth["high"].max()) if len(vrth) else None
    vix_lo = float(vrth["low"].min()) if len(vrth) else None
    # prior RTH close
    prior_days = [x for x in all_days if x < d and x in closes]
    prior_c = closes[prior_days[-1]] if prior_days else None
    dd = dec[dec["d"] == d]
    facts[d] = {
        "rth_open": round(o, 2), "rth_close": round(c, 2),
        "rth_high": round(hi, 2), "rth_high_t": hi_t,
        "rth_low": round(lo, 2), "rth_low_t": lo_t,
        "net_change": round(c - o, 2),
        "range": round(hi - lo, 2),
        "prior_rth_close": round(prior_c, 2) if prior_c else None,
        "gap": round(o - prior_c, 2) if prior_c else None,
        "direction": "UP" if c > o else ("DOWN" if c < o else "FLAT"),
        "vix_open": round(vix_o, 2) if vix_o else None,
        "vix_high": round(vix_hi, 2) if vix_hi else None,
        "vix_low": round(vix_lo, 2) if vix_lo else None,
        "vix_regime": ("LOW" if (vix_o or 99) < 15 else "MID" if (vix_o or 99) <= 22 else "HIGH"),
        "bars_evaluated": int(len(dd)),
        "max_bear_score": int(dd["bear_score"].max()) if len(dd) else 0,
        "bars_score_ge7": int((dd["bear_score"] >= 7).sum()) if len(dd) else 0,
        "bars_passed": int(dd["passed"].sum()) if len(dd) else 0,
    }

OUT.write_text(json.dumps(facts, indent=2))
print(json.dumps(facts, indent=2))
