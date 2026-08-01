"""OPRA backfill: 2024-01-18 (verified true floor, see probe below) .. 2024-12-31.

Context (analysis/deep-research/OPRA-BACKFILL-2026-07-31.md): the backtest
population was capped at 390 trading days (2025-01-02..2026-07-29) by the OPRA
option-quote cache, not by SPY-bar availability. `_probe_opra_floor.py` binary
searched Alpaca's actual SPY 0DTE option-bar history on the existing paper key
and found the true floor is **2024-01-18** (2024-01-16 and 2024-01-17 return
zero bars across a +/-10 strike net; 2024-01-18 onward returns bars reliably).

Reuses the SAME OCC-symbol builder / fetch_contract_bars / write_cache /
write_empty_sentinel / already_cached functions as expand_opra_cache.py (same
auth path via _alpaca_creds.resolve_alpaca_creds, same 8-column CSV schema) —
this does NOT introduce a new fetch or auth path, and does NOT modify
expand_opra_cache.py (whose resolve_spy_master() globs `spy_5m_2025-01-01_*`
and must keep resolving the SAME file it always has for any other in-flight
caller). Strike centering here instead reads the newly-built extended master
`data/spy_5m_2024-01-18_2026-07-22.csv` (2024 segment = Alpaca IEX via
extend_data_v2.py, identical feed to the 2025 masters it was merged onto —
no feed seam).

Usage:
    python tools/_backfill_opra_2024_01_18_2024_12_31.py --plan-only
    python tools/_backfill_opra_2024_01_18_2024_12_31.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from expand_opra_cache import (  # noqa: E402
    already_cached,
    fetch_contract_bars,
    option_symbol,
    write_cache,
    write_empty_sentinel,
)
from _alpaca_creds import masked, resolve_alpaca_creds  # noqa: E402

DATA_DIR = REPO / "data"
MASTER = DATA_DIR / "spy_5m_2024-01-18_2026-07-22.csv"
PROGRESS_FILE = Path(__file__).resolve().parent / "_state" / "opra_backfill_2024_progress.json"

START = dt.date(2024, 1, 18)
END = dt.date(2024, 12, 31)
STRIKES_HALF = 5  # matches existing cache band (11 strikes/side x 2 sides)


def load_trading_days() -> list[tuple[dt.date, float]]:
    df = pd.read_csv(MASTER)
    df["ts"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df["date"] = df["ts"].dt.date
    mask = (df["date"] >= START) & (df["date"] <= END)
    g = df[mask].groupby("date").agg(close=("close", "last")).reset_index()
    return [(r["date"], float(r["close"])) for _, r in g.iterrows()]


def build_contracts(days: list[tuple[dt.date, float]]) -> list[tuple[dt.date, str]]:
    contracts = []
    for day, close in days:
        atm = int(round(close))
        for off in range(-STRIKES_HALF, STRIKES_HALF + 1):
            for side in ("C", "P"):
                contracts.append((day, option_symbol(day, atm + off, side)))
    return contracts


def write_progress(payload: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.30, help="Seconds between requests (~200/min)")
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args(argv)

    days = load_trading_days()
    contracts = build_contracts(days)
    to_fetch = [(d, s) for d, s in contracts if not already_cached(s)]
    print(f"Trading days: {len(days)}  ({days[0][0]} .. {days[-1][0]})")
    print(f"Total contracts: {len(contracts)}  Already cached: {len(contracts) - len(to_fetch)}  To fetch: {len(to_fetch)}")
    eta_min = len(to_fetch) * (args.sleep + 0.25) / 60.0
    print(f"ETA: {eta_min:.1f} min")

    if args.plan_only:
        return 0

    creds = resolve_alpaca_creds()
    print(f"Alpaca creds: key={masked(creds.key)} source={creds.source}")

    fetched, empty, errors = 0, 0, []
    started = dt.datetime.now(dt.timezone.utc)
    for i, (trade_date, symbol) in enumerate(to_fetch, 1):
        attempt = 0
        while True:
            attempt += 1
            try:
                rows = fetch_contract_bars(symbol, trade_date, creds.key, creds.secret)
                if rows:
                    write_cache(symbol, rows)
                    fetched += 1
                    if i % 50 == 0 or i <= 5:
                        print(f"[{i}/{len(to_fetch)}] OK    {symbol}  {len(rows)} bars")
                else:
                    write_empty_sentinel(symbol)
                    empty += 1
                    if i % 50 == 0:
                        print(f"[{i}/{len(to_fetch)}] EMPTY {symbol}")
                break
            except HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:200]
                if e.code == 429 and attempt < 5:
                    backoff = min(60, 2 ** attempt)
                    print(f"[{i}/{len(to_fetch)}] 429 {symbol} — backoff {backoff}s (attempt {attempt})")
                    time.sleep(backoff)
                    continue
                errors.append({"symbol": symbol, "date": trade_date.isoformat(), "http_code": e.code, "body": body})
                print(f"[{i}/{len(to_fetch)}] FAIL  {symbol}  HTTP {e.code}: {body}")
                break
            except (URLError, TimeoutError) as e:
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                errors.append({"symbol": symbol, "date": trade_date.isoformat(), "error": repr(e)})
                print(f"[{i}/{len(to_fetch)}] FAIL  {symbol}  {e}")
                break
        if i % 25 == 0 or i == len(to_fetch):
            elapsed = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
            rate = i / elapsed if elapsed > 0 else 0
            remaining = (len(to_fetch) - i) / rate if rate > 0 else 0
            write_progress({
                "job": "opra_backfill_2024_01_18_2024_12_31",
                "total_contracts": len(contracts),
                "already_cached_before": len(contracts) - len(to_fetch),
                "to_fetch": len(to_fetch),
                "fetched_this_run": fetched,
                "empty_this_run": empty,
                "errors_count": len(errors),
                "errors_sample": errors[-5:],
                "elapsed_seconds": int(elapsed),
                "eta_seconds_remaining": int(remaining),
                "current_index": i,
                "last_update": dt.datetime.now(dt.timezone.utc).isoformat(),
                "status": "running" if i < len(to_fetch) else "completed",
            })
        time.sleep(args.sleep)

    print(f"\nDone. fetched={fetched} empty={empty} errors={len(errors)}")
    if errors:
        for e in errors[:10]:
            print(" -", e)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
