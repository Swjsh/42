"""Scoped feasibility-grade fetch of 1DTE + 2DTE SPY option bars.

THESIS (C3/L58 theta-wall escape): the ~64 dead long-directional families lose at
0DTE because theta+delta convert SPY-price edge into negative OPTION expectancy.
That decay is expiry-specific. This tool pulls a REGIME-DIVERSE SAMPLE of the SAME
near-ATM strike band at 1DTE (enter day T, hold a T+1-expiry contract) and 2DTE
(T+2-expiry), so the same detectors can be re-priced at a fatter-theta expiry.

NOT a full backfill. Three windows (~30 trade days) x +/-STRIKES_HALF strikes x
2 sides x {1DTE,2DTE}. Stored DISTINCT from the 0DTE cache:
    backtest/data/options_1dte/{symbol}.csv   (T+1 expiry contracts)
    backtest/data/options_2dte/{symbol}.csv   (T+2 expiry contracts)

The OCC symbol encodes the EXPIRY date; the API `start/end` window is the TRADE
day T (so we capture how the next-day/2-day contract trades intraday on entry day,
INCLUDING the run into the close that precedes the overnight gap). Resume-safe:
{symbol}.csv on success, {symbol}.csv.empty sentinel on no-bars.

Pure stdlib + pandas. Reuses the working Safe-2 key via _alpaca_creds. $0 (read-only
historical market data).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _alpaca_creds import resolve_alpaca_creds  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SPY_MASTER = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
DIR_1DTE = REPO / "data" / "options_1dte"
DIR_2DTE = REPO / "data" / "options_2dte"
URL = "https://data.alpaca.markets/v1beta1/options/bars"

STRIKES_HALF = 5  # +/-$5 band, both sides -> 11 strikes/side x 2 sides
SLEEP = 0.30
FIELDS = ["timestamp_et", "open", "high", "low", "close", "volume", "vwap", "trade_count"]

# Regime-diverse trade-day windows (inclusive). Picked across 2025 + 2026.
WINDOWS = [
    ("2025-MAR", dt.date(2025, 3, 3), dt.date(2025, 3, 14)),   # choppy/declining
    ("2025-SEP", dt.date(2025, 9, 2), dt.date(2025, 9, 12)),   # grinding uptrend
    ("2026-JUN", dt.date(2026, 6, 1), dt.date(2026, 6, 16)),   # chop + sharp drop + recovery
]


def occ(expiry: dt.date, strike: int, side: str) -> str:
    return f"SPY{expiry.strftime('%y%m%d')}{side}{int(round(strike)) * 1000:08d}"


def trading_calendar() -> list[dt.date]:
    """Distinct SPY trading dates from the master, sorted ascending."""
    df = pd.read_csv(SPY_MASTER, usecols=["timestamp_et"])
    df["date"] = pd.to_datetime(df["timestamp_et"]).dt.date
    return sorted(df["date"].unique())


def daily_closes() -> dict[dt.date, float]:
    df = pd.read_csv(SPY_MASTER, usecols=["timestamp_et", "close"])
    df["date"] = pd.to_datetime(df["timestamp_et"]).dt.date
    g = df.groupby("date").agg(close=("close", "last"))
    return {d: float(c) for d, c in g["close"].items()}


def fetch(sym: str, trade_day: dt.date, key: str, secret: str) -> list[dict]:
    params = {
        "symbols": sym, "timeframe": "5Min",
        "start": f"{trade_day.isoformat()}T13:30:00Z",
        "end": f"{trade_day.isoformat()}T21:00:00Z", "limit": 200,
    }
    req = Request(URL + "?" + urlencode(params), headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
    with urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode())
    bars = payload.get("bars", {}).get(sym, []) or []
    rows = []
    for b in bars:
        ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        ts_et = ts_utc - dt.timedelta(hours=4)
        rows.append({
            "timestamp_et": ts_et.strftime("%Y-%m-%dT%H:%M:%S-04:00"),
            "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
            "volume": b["v"], "vwap": b.get("vw", b["c"]), "trade_count": b.get("n", 0),
        })
    return rows


def write_cache(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def already(path: Path) -> bool:
    return (path.exists() and path.stat().st_size > 100) or path.with_suffix(
        ".csv.empty").exists()


def main() -> int:
    cal = trading_calendar()
    cal_idx = {d: i for i, d in enumerate(cal)}
    closes = daily_closes()
    creds = resolve_alpaca_creds()
    print(f"creds source={creds.source} key={creds.key[:4]}...")

    # Build the contract job list: (dte_label, dir, trade_day, expiry, sym)
    jobs: list[tuple[int, Path, dt.date, dt.date, str]] = []
    skipped_no_expiry = 0
    for name, a, b in WINDOWS:
        for d in cal:
            if not (a <= d <= b):
                continue
            i = cal_idx[d]
            atm = int(round(closes[d]))
            for dte, outdir in ((1, DIR_1DTE), (2, DIR_2DTE)):
                if i + dte >= len(cal):
                    skipped_no_expiry += 1
                    continue
                expiry = cal[i + dte]
                for off in range(-STRIKES_HALF, STRIKES_HALF + 1):
                    for side in ("C", "P"):
                        sym = occ(expiry, atm + off, side)
                        jobs.append((dte, outdir / f"{sym}.csv", d, expiry, sym))

    todo = [j for j in jobs if not already(j[1])]
    print(f"windows={len(WINDOWS)} total_contracts={len(jobs)} "
          f"todo={len(todo)} cached={len(jobs) - len(todo)} "
          f"skipped_no_expiry={skipped_no_expiry}")

    ok = empty = fail = 0
    errs = []
    for n, (dte, path, day, expiry, sym) in enumerate(todo, 1):
        for attempt in range(1, 4):
            try:
                rows = fetch(sym, day, creds.key, creds.secret)
                if rows:
                    write_cache(path, rows)
                    ok += 1
                    tag = f"OK {len(rows)}b"
                else:
                    path.with_suffix(".csv.empty").parent.mkdir(parents=True, exist_ok=True)
                    path.with_suffix(".csv.empty").write_text("", encoding="utf-8")
                    empty += 1
                    tag = "EMPTY"
                if n % 25 == 0 or tag.startswith("OK") and n <= 5:
                    print(f"[{n}/{len(todo)}] {dte}DTE {sym} T={day} exp={expiry} {tag}")
                break
            except HTTPError as e:
                if e.code == 429 and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                body = e.read().decode("utf-8", "replace")[:120]
                errs.append({"sym": sym, "code": e.code, "body": body})
                fail += 1
                print(f"[{n}/{len(todo)}] {sym} FAIL {e.code} {body}")
                break
            except (URLError, TimeoutError) as e:
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                errs.append({"sym": sym, "error": repr(e)})
                fail += 1
                print(f"[{n}/{len(todo)}] {sym} URLERR {e}")
                break
        time.sleep(SLEEP)

    print(f"\nDONE ok={ok} empty={empty} fail={fail}")
    if errs:
        print("errors_sample:", json.dumps(errs[:10]))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
