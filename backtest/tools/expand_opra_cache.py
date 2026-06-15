"""Expand OPRA cache to cover the full SPY 0DTE backtest window.

Goal: enough coverage so `simulator_real.py` can replace BS sim entirely on
the 2025-01-01 → 2026-05-12 window.

Coverage:
  - For every trading day in [start, end] (inclusive) we have a SPY bar in
    `data/spy_5m_2025-01-01_2026-05-12.csv` for, we fetch 0DTE option bars at
    strikes `round(daily_close) + offset` for `offset ∈ {-5..+5}`, both call and
    put sides. That covers SNIPER's `strike_offset=+2` (ITM-2) trades plus all
    adjacent strikes a sub-strategy could pick.

Persistence:
  - Each contract written to `backtest/data/options/{symbol}.csv` matching the
    existing 8-column schema produced by `fetch_option_data.py`:
        timestamp_et, open, high, low, close, volume, vwap, trade_count

Resume safety:
  - A contract is considered cached if its CSV exists and is >100 bytes.
  - Empty Alpaca responses are written as 0-byte sentinel files
    (`{symbol}.csv.empty`) so the next run skips them.

Rate-limit budget:
  - Alpaca free tier: ~200 req/min on options/v1beta1.
  - We default to `--sleep 0.30` (≈200 req/min) + Alpaca latency ≈ 250 req/min
    realistic. Tighten with `--sleep 0.20` only if needed.

Progress reporting:
  - `backtest/tools/_state/opra_ingest_progress.json` rewritten every N
    contracts (default 25) with: total_needed, cached, fetched_this_run,
    errors, last_update, current_date, eta_minutes.
  - Also `--log-file` option for verbose append-only line-per-contract log.

Usage:
    python tools/expand_opra_cache.py --start 2025-01-01 --end 2026-05-12
    python tools/expand_opra_cache.py --start 2025-06-15 --end 2025-06-15 --strikes-half 2  # smoke test
    python tools/expand_opra_cache.py --plan-only  # print plan + estimate, no fetches
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "data"
OPTIONS_DIR = DATA_DIR / "options"
STATE_DIR = Path(__file__).resolve().parent / "_state"
PROGRESS_FILE = STATE_DIR / "opra_ingest_progress.json"

SPY_5M_MASTER = DATA_DIR / "spy_5m_2025-01-01_2026-05-12.csv"

ALPACA_KEY = os.environ.get("ALPACA_API_KEY", "PK33J2RV4PNIY6TCOLUG3WYGRX")
ALPACA_SECRET = os.environ.get(
    "ALPACA_API_SECRET", "FxbJshSbhJ8Rn7KPENssS4eWsLpxCyYeyxavxywV9Bbs"
)
ALPACA_OPTIONS_URL = "https://data.alpaca.markets/v1beta1/options/bars"

# OCC symbol builder matches lib/option_pricing_real.py exactly so consumer can
# load anything we write.
def option_symbol(trade_date: dt.date, strike: int, side: str) -> str:
    yymmdd = trade_date.strftime("%y%m%d")
    s = side.upper()
    assert s in ("C", "P"), f"side must be C or P, got {side}"
    return f"SPY{yymmdd}{s}{int(round(strike)) * 1000:08d}"


def cache_path(symbol: str) -> Path:
    return OPTIONS_DIR / f"{symbol}.csv"


def empty_sentinel(symbol: str) -> Path:
    return OPTIONS_DIR / f"{symbol}.csv.empty"


def already_cached(symbol: str) -> bool:
    p = cache_path(symbol)
    if p.exists() and p.stat().st_size > 100:
        return True
    return empty_sentinel(symbol).exists()


def load_trading_days(start: dt.date, end: dt.date) -> list[tuple[dt.date, float]]:
    """Return list of (date, daily_close) using the SPY master CSV.

    `daily_close` defines our strike center: round(close) ± half-window.
    """
    if not SPY_5M_MASTER.exists():
        raise FileNotFoundError(
            f"Master SPY 5m file not found at {SPY_5M_MASTER}. "
            f"Run tools/extend_data_v2.py first."
        )
    df = pd.read_csv(SPY_5M_MASTER)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    df["date"] = df["timestamp_et"].dt.date
    mask = (df["date"] >= start) & (df["date"] <= end)
    df = df[mask]
    daily = df.groupby("date").agg(close=("close", "last")).reset_index()
    return [(row["date"], float(row["close"])) for _, row in daily.iterrows()]


def build_contract_list(
    trading_days: Iterable[tuple[dt.date, float]],
    strikes_half: int,
) -> list[tuple[dt.date, str]]:
    """Cartesian product: for each day, ±strikes_half from round(close), call+put."""
    contracts: list[tuple[dt.date, str]] = []
    for trade_date, close in trading_days:
        atm = int(round(close))
        for offset in range(-strikes_half, strikes_half + 1):
            strike = atm + offset
            for side in ("C", "P"):
                sym = option_symbol(trade_date, strike, side)
                contracts.append((trade_date, sym))
    return contracts


def fetch_contract_bars(symbol: str, trade_date: dt.date, timeout: int = 30) -> list[dict]:
    """Fetch RTH 5-min bars for a single 0DTE contract. Empty list = no bars."""
    # Note: ET = UTC-4 during EDT (March 9 → Nov 1 in 2025 + 2026).
    # ET = UTC-5 during EST. Using UTC-4 window covers RTH in both cases —
    # the API filter is in UTC, and 13:30 UTC == 09:30 ET (EDT) or 08:30 ET (EST).
    # We want bars in the RTH range, so use a wider safety window UTC.
    start_utc = f"{trade_date.isoformat()}T13:30:00Z"
    end_utc = f"{trade_date.isoformat()}T21:00:00Z"
    params = {
        "symbols": symbol,
        "timeframe": "5Min",
        "start": start_utc,
        "end": end_utc,
        "limit": 200,
    }
    url = f"{ALPACA_OPTIONS_URL}?{urlencode(params)}"
    req = Request(
        url,
        headers={
            "APCA-API-KEY-ID": ALPACA_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET,
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    bars = payload.get("bars", {}).get(symbol, []) or []
    rows: list[dict] = []
    for b in bars:
        ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        # ET offset: simple heuristic matching existing cache format.
        # During EDT (March-Nov), ET = UTC-4. During EST (Nov-March), ET = UTC-5.
        # Existing CSVs use -04:00 even for EST dates (March 18 = EDT, but earlier
        # cached writes assumed -04:00). To stay consistent, use -04:00 always —
        # the consumer pd.to_datetime parses the offset and the simulator uses
        # tz_localize(None) anyway.
        ts_et = ts_utc - dt.timedelta(hours=4)
        rows.append(
            {
                "timestamp_et": ts_et.strftime("%Y-%m-%dT%H:%M:%S-04:00"),
                "open": b["o"],
                "high": b["h"],
                "low": b["l"],
                "close": b["c"],
                "volume": b["v"],
                "vwap": b.get("vw", b["c"]),
                "trade_count": b.get("n", 0),
            }
        )
    return rows


def write_cache(symbol: str, rows: list[dict]) -> None:
    OPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(symbol)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp_et",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "vwap",
                "trade_count",
            ],
        )
        w.writeheader()
        w.writerows(rows)


def write_empty_sentinel(symbol: str) -> None:
    OPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    empty_sentinel(symbol).write_text("", encoding="utf-8")


def write_progress(progress: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Expand OPRA cache for full backtest window.")
    ap.add_argument("--start", required=True, help="Start date YYYY-MM-DD (inclusive)")
    ap.add_argument("--end", required=True, help="End date YYYY-MM-DD (inclusive)")
    ap.add_argument(
        "--strikes-half",
        type=int,
        default=5,
        help="Strikes either side of ATM (default 5 = 11 strikes per day)",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.30,
        help="Seconds to sleep between requests (default 0.30 = ~200 req/min)",
    )
    ap.add_argument(
        "--plan-only",
        action="store_true",
        help="Print plan and ETA, then exit without fetching",
    )
    ap.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Optional path to append per-contract result lines",
    )
    ap.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Write progress JSON every N contracts (default 25)",
    )
    ap.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Retries per contract on HTTP errors (default 3)",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    if start > end:
        logger.error("start must be <= end")
        return 2

    trading_days = load_trading_days(start, end)
    contracts = build_contract_list(trading_days, args.strikes_half)
    cached_now = sum(1 for _, sym in contracts if already_cached(sym))
    to_fetch = [(d, s) for d, s in contracts if not already_cached(s)]

    eta_seconds = len(to_fetch) * (args.sleep + 0.25)  # +0.25s avg request latency
    eta_minutes = eta_seconds / 60.0

    plan = {
        "start": args.start,
        "end": args.end,
        "trading_days": len(trading_days),
        "strikes_half": args.strikes_half,
        "total_contracts": len(contracts),
        "already_cached": cached_now,
        "to_fetch": len(to_fetch),
        "sleep_seconds": args.sleep,
        "eta_minutes": round(eta_minutes, 1),
        "estimated_cost_usd": 0.0,  # pure Python + Alpaca free tier
    }
    logger.info("PLAN: %s", json.dumps(plan))

    if args.plan_only:
        return 0

    if eta_minutes > 240:
        logger.error(
            "ETA %.1f min > 4h budget. Either tighten window, raise --sleep "
            "(if rate limits allow), or split into multiple runs. Aborting.",
            eta_minutes,
        )
        return 3

    log_fh = None
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_path, "a", encoding="utf-8")

    fetched_this_run = 0
    errors: list[dict] = []
    started_at = dt.datetime.now(dt.timezone.utc)

    def update_progress(current_date: dt.date | None = None) -> None:
        elapsed = (dt.datetime.now(dt.timezone.utc) - started_at).total_seconds()
        done = fetched_this_run + len(errors)
        rate = (done / elapsed) if elapsed > 0 else 0.0
        remaining = max(0, len(to_fetch) - done)
        eta_remaining = remaining / rate if rate > 0 else 0.0
        write_progress(
            {
                "start": args.start,
                "end": args.end,
                "total_contracts_needed": len(contracts),
                "cached_before_run": cached_now,
                "to_fetch": len(to_fetch),
                "fetched_this_run": fetched_this_run,
                "errors_count": len(errors),
                "errors_sample": errors[-5:],
                "last_update": dt.datetime.now(dt.timezone.utc).isoformat(),
                "current_date": current_date.isoformat() if current_date else None,
                "elapsed_seconds": int(elapsed),
                "eta_seconds_remaining": int(eta_remaining),
                "status": "running",
            }
        )

    update_progress()

    try:
        for i, (trade_date, symbol) in enumerate(to_fetch, 1):
            attempt = 0
            while True:
                attempt += 1
                try:
                    rows = fetch_contract_bars(symbol, trade_date)
                    if rows:
                        write_cache(symbol, rows)
                        msg = f"OK   {symbol}  {len(rows)} bars"
                    else:
                        write_empty_sentinel(symbol)
                        msg = f"EMPTY {symbol}  no bars in window"
                    fetched_this_run += 1
                    logger.info("[%d/%d] %s", i, len(to_fetch), msg)
                    if log_fh:
                        log_fh.write(
                            f"{dt.datetime.now(dt.timezone.utc).isoformat()} {msg}\n"
                        )
                        log_fh.flush()
                    break
                except HTTPError as e:
                    body = e.read().decode("utf-8", errors="replace")[:200]
                    if e.code == 429:
                        # Rate-limit. Back off then retry.
                        backoff = min(60, 2 ** attempt)
                        logger.warning(
                            "[%d/%d] 429 %s — backing off %ds (attempt %d)",
                            i, len(to_fetch), symbol, backoff, attempt,
                        )
                        time.sleep(backoff)
                        if attempt < args.max_retries:
                            continue
                    err = {"symbol": symbol, "date": trade_date.isoformat(),
                           "http_code": e.code, "body": body}
                    errors.append(err)
                    logger.error("[%d/%d] HTTPError %d %s: %s",
                                 i, len(to_fetch), e.code, symbol, body)
                    if log_fh:
                        log_fh.write(f"{dt.datetime.now(dt.timezone.utc).isoformat()} FAIL {symbol} {e.code} {body}\n")
                        log_fh.flush()
                    break
                except (URLError, TimeoutError) as e:
                    if attempt < args.max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    errors.append({"symbol": symbol, "date": trade_date.isoformat(),
                                   "error": repr(e)})
                    logger.error("[%d/%d] URLError %s: %s", i, len(to_fetch), symbol, e)
                    break
                except Exception as e:  # noqa: BLE001
                    errors.append({"symbol": symbol, "date": trade_date.isoformat(),
                                   "error": repr(e)})
                    logger.error("[%d/%d] %s: %s", i, len(to_fetch), symbol, e)
                    break

            if i % args.progress_every == 0:
                update_progress(current_date=trade_date)
            time.sleep(args.sleep)

        # Final progress
        final = {
            "start": args.start,
            "end": args.end,
            "total_contracts_needed": len(contracts),
            "cached_before_run": cached_now,
            "to_fetch": len(to_fetch),
            "fetched_this_run": fetched_this_run,
            "errors_count": len(errors),
            "errors_sample": errors[-10:],
            "last_update": dt.datetime.now(dt.timezone.utc).isoformat(),
            "current_date": None,
            "elapsed_seconds": int(
                (dt.datetime.now(dt.timezone.utc) - started_at).total_seconds()
            ),
            "eta_seconds_remaining": 0,
            "status": "completed",
        }
        write_progress(final)
        logger.info("DONE: %s", json.dumps(final))
        return 0
    finally:
        if log_fh:
            log_fh.close()


if __name__ == "__main__":
    sys.exit(main())
