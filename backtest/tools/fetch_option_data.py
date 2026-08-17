"""Fetch real OPRA option contract bars via Alpaca historical API.

Pre-fetches all contracts referenced by the v5 backtest + J's actual historical
trades, saves to CSV cache at `backtest/data/options/{symbol}.csv`.

The cache is the source of truth for `lib/option_pricing_real.py` — the simulator
never calls Alpaca at runtime; it reads the cached CSVs.

Usage:
    python tools/fetch_option_data.py             # fetch all
    python tools/fetch_option_data.py --check     # just verify what's cached

Output schema (per CSV):
    timestamp_et,open,high,low,close,volume,vwap,trade_count
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from zoneinfo import ZoneInfo
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from _alpaca_creds import resolve_alpaca_creds

ALPACA_DATA_URL = "https://data.alpaca.markets/v1beta1/options/bars"

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "options"

# Contracts to fetch — derived from:
#   1. analysis/backtests/production_rules_v5_*/trades.csv (engine-fired trades)
#   2. journal/trades.csv historical entries (J's actual trades, for e2e validation)
CONTRACTS = [
    # V5 engine-fired trades
    ("2026-03-18", "SPY260318P00665000"),
    ("2026-03-18", "SPY260318P00662000"),
    ("2026-03-24", "SPY260324P00653000"),
    ("2026-03-26", "SPY260326P00653000"),
    ("2026-03-30", "SPY260330P00634000"),
    ("2026-04-07", "SPY260407P00652000"),
    ("2026-04-21", "SPY260421P00705000"),
    ("2026-04-23", "SPY260423P00708000"),
    ("2026-04-28", "SPY260428P00712000"),
    ("2026-04-29", "SPY260429P00709000"),
    ("2026-05-04", "SPY260504P00719000"),
    ("2026-04-23", "SPY260423P00704000"),  # v6/v7 second-leg strike
    # J's actual trades (for e2e validation)
    ("2026-04-29", "SPY260429P00710000"),
    ("2026-05-01", "SPY260501P00721000"),
    ("2026-05-04", "SPY260504P00721000"),
    ("2026-05-07", "SPY260507C00734000"),
    # J's manual trades NOT in our journal (recovered from broker screenshot)
    ("2026-05-05", "SPY260505P00722000"),
    ("2026-05-06", "SPY260506P00730000"),
    ("2026-05-07", "SPY260507C00737000"),
]


def fetch_contract_bars(symbol: str, trade_date: str, key: str, secret: str) -> list[dict]:
    """Fetch 5-min bars for a single 0DTE contract, scoped to RTH on trade_date.

    Returns list of dicts with normalized field names.
    """
    start_utc = f"{trade_date}T13:30:00Z"   # 09:30 ET
    end_utc = f"{trade_date}T20:30:00Z"     # 16:30 ET (a bit past close)
    params = {
        "symbols": symbol,
        "timeframe": "5Min",
        "start": start_utc,
        "end": end_utc,
        "limit": 200,
    }
    url = f"{ALPACA_DATA_URL}?{urlencode(params)}"
    req = Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    })
    with urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    bars = payload.get("bars", {}).get(symbol, []) or []
    rows = []
    for b in bars:
        ts_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        # DST FIX (2026-08-12). Was `ts_utc - timedelta(hours=4)` with the comment
        # "ET = UTC-4 during EDT" -- true only during EDT. Every bar fetched for an EST month
        # (Nov-Mar) was silently written to the cache labelled ONE HOUR LATE, which shifts a
        # 09:30 open to 10:30 and makes every downstream entry/exit join wrong by a bar.
        # This is the documented DST-frame artifact class (naive joins = winter look-ahead);
        # the sibling copy in _option_bars_1min_cache.py carries the same bug and is queued.
        # ZoneInfo handles the transition dates correctly; no manual offset can.
        # BOTH HALVES must move together. The old code wrote a UTC-4 wall-clock AND a
        # hardcoded "-04:00" suffix, which is wrong-wall-clock-but-right-INSTANT in winter
        # (10:30-04:00 == 14:30Z == the true 09:30 EST bar). Fixing only the wall-clock while
        # leaving the literal suffix would have produced 09:30-04:00 == 13:30Z — a DIFFERENT,
        # one-hour-early instant, i.e. a worse bug than the one being fixed. %z emits the real
        # offset (-04:00 in EDT, -05:00 in EST), so wall-clock and instant are both correct.
        # Cache compatibility: existing winter rows parse to the SAME instant as new ones, so
        # any reader that honours the offset (e.g. et_frame / pd.to_datetime(format="mixed"))
        # is unaffected; only naive wall-clock readers change, and for those the new value is
        # the correct one. No current live data is affected — the whole real-fills population
        # is Jun-Aug (EDT), where old and new are byte-identical.
        ts_et = ts_utc.astimezone(ZoneInfo("America/New_York"))
        rows.append({
            "timestamp_et": ts_et.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":"
                            + ts_et.strftime("%z")[-2:],
            "open": b["o"],
            "high": b["h"],
            "low": b["l"],
            "close": b["c"],
            "volume": b["v"],
            "vwap": b.get("vw", b["c"]),
            "trade_count": b.get("n", 0),
        })
    return rows


def cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}.csv"


def write_cache(symbol: str, rows: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(symbol)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "timestamp_et", "open", "high", "low", "close",
            "volume", "vwap", "trade_count",
        ])
        w.writeheader()
        w.writerows(rows)


def already_cached(symbol: str) -> bool:
    p = cache_path(symbol)
    return p.exists() and p.stat().st_size > 100


def topup_from_fills_ledger(max_fetch: int = 60, sleep_s: float = 0.35) -> dict:
    """Cache every engine-filled option contract that is not cached yet. Never raises.

    WHY (2026-08-16). `CONTRACTS` above is a HARDCODED list of 19 contracts, all dated
    2026-03..05 and frozen since 2026-05-07. It has no relationship to what the live book
    actually traded, so the cache only grew when someone ran a bulk fetch by hand. On
    2026-08-16 the last cached contract was 2026-08-12 and the live fills ledger had 9
    contracts from 08-13/08-14 with no bars.

    WHAT THAT COST: `option_pricing_real.load_contract_bars` has NO fetch-on-miss -- it
    returns None -- so every consumer silently drops those fills. The stop_mode forward clock
    skipped 29 of them as `no_opra_cache` while reporting itself healthy, i.e. a prereg clock
    quietly accruing on a subset. Filling the 9 moved it 66 -> 95 trades and 3 -> 5 days in
    one run.

    A cache that only grows when a human remembers is a cache that is always two days stale
    exactly when the newest evidence matters most. This makes the top-up part of the nightly
    fold instead.

    $0: Alpaca `/v1beta1/options/bars` is free on the already-wired key (verified 2026-08-12,
    200 req/min); `max_fetch` bounds a first run or a long outage so one fire cannot stall on
    a huge backlog -- the remainder is picked up by the next fire and reported as `remaining`.
    """
    out = {"missing": 0, "fetched": 0, "failed": 0, "remaining": 0, "symbols": [],
           "deferred_same_day": 0, "failure_reasons": {}}
    try:
        ledger = ROOT.parent / "automation" / "state" / "fills-ledger.jsonl"
        if not ledger.exists():
            out["error"] = "fills-ledger.jsonl absent"
            return out
        first_date: dict[str, str] = {}
        for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if (r.get("attribution") != "engine" or not r.get("is_option")
                    or r.get("is_crypto")):
                continue
            sym, day = r.get("symbol"), r.get("date_et")
            if not sym or not day:
                continue
            if sym not in first_date or day < first_date[sym]:
                first_date[sym] = day

        missing = sorted((s, d) for s, d in first_date.items() if not already_cached(s))
        out["missing"] = len(missing)
        if not missing:
            return out

        creds = resolve_alpaca_creds()
        # SAME-DAY BARS ARE 403, MEASURED 2026-08-17. Isolated with a discriminating test:
        # 2026-08-13 and 2026-08-14 contracts returned 200 with 81 bars each, while a
        # 2026-08-17 contract returned HTTP 403 on the SAME endpoint, key and code path. So
        # the discriminator is the DAY, not the endpoint or entitlement.
        #
        # This REFINES the 2026-08-12 churn-teardown correction, which recorded
        # "/v1beta1/options/bars returns 200 at $0 -- same-day 0DTE included". True for a PAST
        # 0DTE expiry; NOT true for the current session. The nightly fold therefore cannot
        # price today's fills at 16:25 and will pick them up tomorrow -- a ONE-DAY LAG that is
        # expected, self-healing, and must not be logged as a failure or someone will chase it.
        today = dt.date.today().isoformat()
        for sym, day in missing[:max_fetch]:
            if day >= today:
                out["deferred_same_day"] += 1
                continue
            try:
                rows = fetch_contract_bars(sym, day, creds.key, creds.secret)
                if rows:
                    write_cache(sym, rows)
                    out["fetched"] += 1
                    out["symbols"].append(sym)
                else:
                    out["failed"] += 1
                    out["failure_reasons"]["empty_response"] = \
                        out["failure_reasons"].get("empty_response", 0) + 1
            except Exception as e:  # noqa: BLE001 -- one bad contract never stalls the fold
                # RECORD THE REASON. The first version counted failures without saying why,
                # which turned a diagnosable 403 into an anonymous "failed=2".
                out["failed"] += 1
                key = f"{type(e).__name__}:{str(e)[:40]}"
                out["failure_reasons"][key] = out["failure_reasons"].get(key, 0) + 1
            time.sleep(sleep_s)
        out["remaining"] = max(0, len(missing) - max_fetch)
    except Exception as e:  # noqa: BLE001 -- fail-open: this is a side-product of a fold
        out["error"] = f"{type(e).__name__}: {e}"[:200]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topup", action="store_true",
                    help="cache every engine-filled contract not yet cached (from the "
                         "live fills ledger, not the frozen CONTRACTS list)")
    ap.add_argument("--check", action="store_true",
                    help="just report cache status, no fetches")
    ap.add_argument("--force", action="store_true",
                    help="re-fetch even if cached")
    args = ap.parse_args(argv)

    if args.topup:
        res = topup_from_fills_ledger()
        print(f"topup: missing={res['missing']} fetched={res['fetched']} "
              f"failed={res['failed']} deferred_same_day={res['deferred_same_day']} "
              f"remaining={res['remaining']}"
              + (f" error={res['error']}" if res.get("error") else ""))
        if res.get("failure_reasons"):
            print(f"  failure reasons: {res['failure_reasons']}")
        if res["deferred_same_day"]:
            print("  (same-day option bars are 403 until the next session -- expected, "
                  "self-heals on tomorrow's fold)")
        for s in res["symbols"]:
            print(f"  + {s}")
        return 0

    cached = sum(1 for _, sym in CONTRACTS if already_cached(sym))
    print(f"Cache: {cached}/{len(CONTRACTS)} contracts cached at {CACHE_DIR}")

    if args.check:
        for date_str, symbol in CONTRACTS:
            status = "OK " if already_cached(symbol) else "MISS"
            path = cache_path(symbol)
            size = path.stat().st_size if path.exists() else 0
            print(f"  [{status}] {date_str}  {symbol}  {size}b")
        return 0

    creds = resolve_alpaca_creds()
    print(f"Alpaca creds: key={creds.key[:4]}... source={creds.source}")

    fetched = 0
    failed = []
    for date_str, symbol in CONTRACTS:
        if already_cached(symbol) and not args.force:
            print(f"  skip {symbol}  (cached)")
            continue
        try:
            rows = fetch_contract_bars(symbol, date_str, creds.key, creds.secret)
            if not rows:
                print(f"  WARN {symbol}  empty response")
                failed.append((symbol, "empty"))
                continue
            write_cache(symbol, rows)
            print(f"  ok   {symbol}  {len(rows)} bars")
            fetched += 1
            time.sleep(0.25)   # gentle on rate limits
        except Exception as e:
            print(f"  FAIL {symbol}  {e}")
            failed.append((symbol, str(e)))

    print(f"\nFetched {fetched} new, {len(failed)} failed")
    if failed:
        for sym, why in failed:
            print(f"  - {sym}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
