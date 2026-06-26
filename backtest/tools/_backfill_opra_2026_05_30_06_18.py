"""A1 backfill: close the OPRA real-fills blind spot 2026-05-30 -> 2026-06-18.

One-shot driver that reuses the canonical OCC-symbol builder + 8-column CSV
schema from expand_opra_cache.py, but sources daily closes from the CURRENT SPY
5m master (which extends past the stale 2026-05-12 master hardcoded there) and
authenticates with the live Safe-2 key (the old PK33J2RV... key 401s).

Pure stdlib + pandas. Writes backtest/data/options/{symbol}.csv for contracts
with bars, {symbol}.csv.empty sentinels otherwise (resume-safe). $0 cost.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from _alpaca_creds import masked, resolve_alpaca_creds

REPO = Path(__file__).resolve().parents[1]
OPTIONS_DIR = REPO / "data" / "options"
SPY_MASTER = REPO / "data" / "spy_5m_2026-05-19_2026-06-18.csv"

# Credentials are resolved lazily on the fetch path via the shared resolver —
# never hardcoded here. The resolver sources the live Safe-2 key from env or the
# project-local .mcp.json `alpaca` server block. (The old PK33J2RV... key 401s.)
URL = "https://data.alpaca.markets/v1beta1/options/bars"

START = dt.date(2026, 5, 30)
END = dt.date(2026, 6, 18)
STRIKES_HALF = 5  # matches existing cache band (11 strikes/side x 2 sides)
SLEEP = 0.30
FIELDS = ["timestamp_et", "open", "high", "low", "close", "volume", "vwap", "trade_count"]


def occ(trade_date: dt.date, strike: int, side: str) -> str:
    return f"SPY{trade_date.strftime('%y%m%d')}{side}{int(round(strike)) * 1000:08d}"


def cache_path(sym: str) -> Path:
    return OPTIONS_DIR / f"{sym}.csv"


def empty_path(sym: str) -> Path:
    return OPTIONS_DIR / f"{sym}.csv.empty"


def already(sym: str) -> bool:
    p = cache_path(sym)
    return (p.exists() and p.stat().st_size > 100) or empty_path(sym).exists()


def daily_closes() -> list[tuple[dt.date, float]]:
    df = pd.read_csv(SPY_MASTER)
    df["ts"] = pd.to_datetime(df["timestamp_et"])
    df["date"] = df["ts"].dt.date
    m = (df["date"] >= START) & (df["date"] <= END)
    g = df[m].groupby("date").agg(close=("close", "last")).reset_index()
    return [(r["date"], float(r["close"])) for _, r in g.iterrows()]


def fetch(sym: str, day: dt.date, key: str, secret: str) -> list[dict]:
    params = {
        "symbols": sym, "timeframe": "5Min",
        "start": f"{day.isoformat()}T13:30:00Z",
        "end": f"{day.isoformat()}T21:00:00Z", "limit": 200,
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


def write_cache(sym: str, rows: list[dict]) -> None:
    OPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path(sym), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    days = daily_closes()
    contracts: list[tuple[dt.date, str]] = []
    for day, close in days:
        atm = int(round(close))
        for off in range(-STRIKES_HALF, STRIKES_HALF + 1):
            for side in ("C", "P"):
                contracts.append((day, occ(day, atm + off, side)))
    todo = [(d, s) for d, s in contracts if not already(s)]
    print(f"days={len(days)} total={len(contracts)} todo={len(todo)} "
          f"cached={len(contracts) - len(todo)}")

    # Resolve creds lazily — only when there's actually a fetch to make.
    if not todo:
        print("nothing to fetch")
        return 0
    creds = resolve_alpaca_creds()
    print(f"Alpaca creds: key={masked(creds.key)} source={creds.source}")

    ok = empty = fail = 0
    errs = []
    for i, (day, sym) in enumerate(todo, 1):
        for attempt in range(1, 4):
            try:
                rows = fetch(sym, day, creds.key, creds.secret)
                if rows:
                    write_cache(sym, rows)
                    ok += 1
                    tag = f"OK {len(rows)}b"
                else:
                    empty_path(sym).write_text("", encoding="utf-8")
                    empty += 1
                    tag = "EMPTY"
                print(f"[{i}/{len(todo)}] {sym} {tag}")
                break
            except HTTPError as e:
                if e.code == 429 and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                body = e.read().decode("utf-8", "replace")[:120]
                errs.append({"sym": sym, "code": e.code, "body": body})
                fail += 1
                print(f"[{i}/{len(todo)}] {sym} FAIL {e.code} {body}")
                break
            except (URLError, TimeoutError) as e:
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                errs.append({"sym": sym, "error": repr(e)})
                fail += 1
                print(f"[{i}/{len(todo)}] {sym} URLERR {e}")
                break
        time.sleep(SLEEP)

    print(f"\nDONE ok={ok} empty={empty} fail={fail}")
    if errs:
        print("errors_sample:", json.dumps(errs[:10]))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
