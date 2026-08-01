"""One-off: fill the VIX gap yfinance's 1h endpoint can't reach.

Context (OPRA backfill 2026-07-31, analysis/deep-research/OPRA-BACKFILL-2026-07-31.md):
extend_data_v2.py's VIX fetch uses yfinance 1h bars, but yfinance's intraday (1h)
history is capped at "within the last 730 days" of the CALL date, not the query
range. Today (2026-07-31) that boundary lands at 2024-07-31 — so 1h VIX for
2024-08-01..2024-12-31 fetched clean via the normal path, but 2024-01-18
(true OPRA floor) .. 2024-07-30 cannot get 1h data no matter how the request is
windowed.

Fallback: yfinance DAILY VIX (no such lookback cap) for the gap, one row per
trading day at the 09:30 ET session anchor (DST-aware offset). This is
DELIBERATELY a lower-fidelity proxy — daily O/H/L/C only, no intraday VIX
shape — and is written to its own file, NEVER merged into the vix_5m_* hourly
chain, so no consumer silently gets hourly-shaped data that's actually daily.
Register any consumption of this file in markdown/infra/DATA-PROVENANCE.md.

Output: backtest/data/vix_daily_proxy_2024-01-18_2024-07-30.csv
Schema: timestamp_et, open, high, low, close, volume (volume always 0 — VIX is
an index, no real volume, consistent with the existing vix_5m_* files).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"

START = dt.date(2024, 1, 18)
END = dt.date(2024, 7, 30)
ET = ZoneInfo("America/New_York")


def main() -> int:
    df = yf.download(
        "^VIX",
        start=START.isoformat(),
        end=(END + dt.timedelta(days=1)).isoformat(),
        interval="1d",
        progress=False,
        auto_adjust=False,
    )
    if df.empty:
        print("ERROR: empty yfinance daily VIX response")
        return 1
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    df.columns = [str(c).lower() for c in df.columns]

    rows = []
    for _, r in df.iterrows():
        d = r["date"]
        if hasattr(d, "date"):
            d = d.date()
        # 09:30 ET session-open anchor, DST-correct offset per date.
        anchor = dt.datetime.combine(d, dt.time(9, 30), tzinfo=ET)
        rows.append(
            {
                "timestamp_et": anchor.strftime("%Y-%m-%d %H:%M:%S%z"),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": 0,
            }
        )

    out = DATA / f"vix_daily_proxy_{START.isoformat()}_{END.isoformat()}.csv"
    out_df = pd.DataFrame(rows)
    out_df.to_csv(out, index=False)
    print(f"wrote {len(rows)} rows -> {out.name}")
    print(f"span: {rows[0]['timestamp_et']} .. {rows[-1]['timestamp_et']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
