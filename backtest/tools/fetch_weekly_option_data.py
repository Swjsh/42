"""Ingest DAILY option bars for the weekly-options lane's basket — liquidity-filtered.

Phase 3 of the weekly-lane night run (see markdown/planning/WEEKLY-OPTIONS-PROGRAM.md §9b).
This is the data foundation for the multi-day backtest and the expiry (which-Friday) shootout.

WHY THE LIQUIDITY PRE-FILTER IS LOAD-BEARING (direct broker evidence, 2026-08-18)
--------------------------------------------------------------------------------
A live probe of Alpaca's expired-contract bars established that coverage is *volume-gated,
not date-gated*:

  NVDA251107C00185000 (ATM, OI 13,857)  -> COMPLETE 11-session daily series, real OHLCV
  NVDA251107C00070000 (deep ITM, OI 40) -> 7 sparse bars
  GLD260202C00290000  (deep ITM, OI 1)  -> 2 bars over the same window

So fetching every listed strike would fill the dataset with 2-bar phantom series that a
multi-day walk would silently treat as real price paths. We therefore screen contracts by
open interest BEFORE spending a request on their bars. This is not a shortcut: it is the same
liquidity filter the live entry gate applies (params.json entry.liquidity_gate), so the
backtest population matches the tradeable population by construction.

EXPIRY-DAY BARS ARE PATHOLOGICAL AND ARE FLAGGED, NOT DROPPED
-------------------------------------------------------------
The same probe: NVDA251107C00185000's expiry-day bar printed low=0.07 on 381,495 contracts of
volume while closing at 3.20. Modeling an exit fill against that bar's low would invent a price
no one could have gotten. Every row carries `is_expiry_day` so the walk can exclude or specially
handle it — we flag rather than drop so the honest record stays intact.

TIMEZONE: bar timestamps arrive UTC-stamped from Alpaca. We store the ORIGINAL UTC string plus
a derived ET date computed via zoneinfo (DST-correct). The repo has a documented DST-frame scar
(a fixed -04:00 assumption created winter look-ahead) — never hardcode an offset here.

$0: uses the already-wired paper key via _alpaca_creds (market-data auth only). Places no orders.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Iterable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _alpaca_creds import masked, resolve_alpaca_creds  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = REPO_ROOT / "backtest" / "data" / "weekly-options"
MANIFEST = OUT_ROOT / "_manifest.jsonl"
PARAMS = REPO_ROOT / "automation" / "state" / "weekly" / "params.json"

# The contracts endpoint lives on the TRADING API, which is host-partitioned by account type:
# a paper key (PK...) 401s against api.alpaca.markets and must use paper-api.alpaca.markets.
# The market-DATA host below is shared and accepts the paper key either way — which is exactly
# why the bars call worked while this one did not (observed live, 2026-08-18).
CONTRACTS_URL = "https://paper-api.alpaca.markets/v2/options/contracts"
BARS_URL = "https://data.alpaca.markets/v1beta1/options/bars"
ET = ZoneInfo("America/New_York")

# Screening floor. Contracts below this open interest are not fetched at all — see the
# module docstring for the measured reason. Deliberately a constant, not a tunable: this is a
# data-hygiene threshold, not a strategy parameter, and it must not drift per-run.
MIN_OPEN_INTEREST = 250

CSV_COLUMNS = [
    "contract", "root", "expiry", "strike", "right",
    "bar_utc", "bar_date_et", "is_expiry_day",
    "open", "high", "low", "close", "volume", "trade_count", "vwap",
]


class IngestError(RuntimeError):
    """Raised so a bad run fails LOUD rather than writing a plausible-looking empty cache."""


def _get(url: str, params: dict, key: str, secret: str, *, timeout: int = 30) -> dict:
    req = Request(
        f"{url}?{urlencode(params)}",
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
    )
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        raise IngestError(f"HTTP {e.code} from {url}: {body}") from e
    except URLError as e:
        raise IngestError(f"network failure reaching {url}: {e.reason}") from e


def iter_contracts(
    root: str, start: dt.date, end: dt.date, key: str, secret: str,
) -> Iterator[dict]:
    """Yield BOTH expired and still-listed contracts for `root` expiring in [start, end]."""
    for status in ("inactive", "active"):
        page: str | None = None
        while True:
            params = {
                "underlying_symbols": root,
                "status": status,
                "expiration_date_gte": start.isoformat(),
                "expiration_date_lte": end.isoformat(),
                "limit": 10000,
            }
            if page:
                params["page_token"] = page
            payload = _get(CONTRACTS_URL, params, key, secret)
            for c in payload.get("option_contracts") or []:
                yield c
            page = payload.get("next_page_token")
            if not page:
                break


def screen(contracts: Iterable[dict], min_oi: int = MIN_OPEN_INTEREST) -> list[dict]:
    """Keep only contracts with real open interest. See docstring: coverage is volume-gated."""
    kept = []
    for c in contracts:
        raw_oi = c.get("open_interest")
        if raw_oi in (None, ""):
            continue
        try:
            oi = int(float(raw_oi))
        except (TypeError, ValueError):
            continue
        if oi >= min_oi:
            c["_oi"] = oi
            kept.append(c)
    return kept


def fetch_bars(
    symbols: list[str], start: dt.date, end: dt.date, key: str, secret: str,
) -> dict[str, list[dict]]:
    """Daily bars for up to 100 contracts per request (Alpaca's documented symbol cap)."""
    out: dict[str, list[dict]] = {}
    for i in range(0, len(symbols), 100):
        chunk = symbols[i : i + 100]
        page: str | None = None
        while True:
            params = {
                "symbols": ",".join(chunk),
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": 10000,
                "sort": "asc",
            }
            if page:
                params["page_token"] = page
            payload = _get(BARS_URL, params, key, secret)
            for sym, bars in (payload.get("bars") or {}).items():
                out.setdefault(sym, []).extend(bars)
            page = payload.get("next_page_token")
            if not page:
                break
        time.sleep(0.2)  # courtesy spacing; well inside the documented rate limit
    return out


def _bar_date_et(bar_utc: str) -> dt.date:
    """UTC bar stamp -> ET calendar date, DST-correct via zoneinfo (never a fixed offset)."""
    ts = dt.datetime.fromisoformat(bar_utc.replace("Z", "+00:00"))
    return ts.astimezone(ET).date()


def rows_for(contract: dict, bars: list[dict]) -> list[dict]:
    expiry = dt.date.fromisoformat(contract["expiration_date"])
    rows = []
    for b in bars:
        bar_utc = b["t"]
        d = _bar_date_et(bar_utc)
        rows.append({
            "contract": contract["symbol"],
            "root": contract["root_symbol"],
            "expiry": expiry.isoformat(),
            "strike": contract["strike_price"],
            "right": contract["type"],
            "bar_utc": bar_utc,
            "bar_date_et": d.isoformat(),
            "is_expiry_day": int(d == expiry),
            "open": b.get("o"), "high": b.get("h"), "low": b.get("l"), "close": b.get("c"),
            "volume": b.get("v"), "trade_count": b.get("n"), "vwap": b.get("vw"),
        })
    return rows


def write_contract_csv(root: str, contract_symbol: str, rows: list[dict]) -> Path:
    d = OUT_ROOT / root
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{contract_symbol}.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


# A contract's price path lives BEFORE its expiry, so the bar-fetch window must start earlier
# than the expiry-selection window. Ingesting with both windows equal silently truncated 275
# contracts (2.4%) to their expiry-day bar only, on the first real run — they looked "covered"
# in the manifest while carrying no usable path. Caught by the post-ingest artifact hunt,
# 2026-08-18. 45 days comfortably spans a monthly contract's tradeable life.
BAR_LOOKBACK_DAYS = 45


def ingest_root(
    root: str, start: dt.date, end: dt.date, key: str, secret: str, *, min_oi: int,
) -> dict:
    bars_start = start - dt.timedelta(days=BAR_LOOKBACK_DAYS)
    screened = screen(iter_contracts(root, start, end, key, secret), min_oi=min_oi)
    if not screened:
        raise IngestError(
            f"{root}: zero contracts cleared the OI>={min_oi} screen for "
            f"{start}..{end}. Refusing to write an empty cache that would look like a "
            f"successful run. Widen the window, lower --min-oi, or check the credentials."
        )
    by_symbol = {c["symbol"]: c for c in screened}
    bars = fetch_bars(list(by_symbol), bars_start, end, key, secret)

    contracts_with_bars = 0
    total_rows = 0
    single_bar_contracts = 0
    for sym, contract in by_symbol.items():
        got = bars.get(sym) or []
        if not got:
            continue
        rows = rows_for(contract, got)
        write_contract_csv(root, sym, rows)
        contracts_with_bars += 1
        total_rows += len(rows)
        if len(rows) <= 2:
            single_bar_contracts += 1

    if contracts_with_bars == 0:
        raise IngestError(
            f"{root}: screened {len(by_symbol)} contracts but NONE returned bars. "
            f"That is an API/credential problem, not an empty market — failing loud."
        )

    return {
        "root": root,
        "expiry_window_start": start.isoformat(),
        "bars_window_start": bars_start.isoformat(),
        "window_end": end.isoformat(),
        "min_open_interest": min_oi,
        "contracts_screened": len(by_symbol),
        "contracts_with_bars": contracts_with_bars,
        "coverage_ratio": round(contracts_with_bars / len(by_symbol), 4),
        "total_bar_rows": total_rows,
        "thin_contracts_le_2_bars": single_bar_contracts,
        "generated_at_et": dt.datetime.now(ET).isoformat(timespec="seconds"),
        "_coverage_note": (
            "coverage_ratio is specific to THIS root/window/min_oi. Do NOT quote it as a "
            "global coverage number — coverage is volume-gated, so it moves with the strike "
            "population sampled."
        ),
    }


def active_basket() -> list[str]:
    cfg = json.loads(PARAMS.read_text(encoding="utf-8"))
    basket = cfg.get("universe", {}).get("active") or []
    if not basket:
        raise IngestError(f"no universe.active symbols in {PARAMS}")
    return basket


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--roots", help="comma-separated (default: params.json universe.active)")
    ap.add_argument("--start", required=True, help="expiry window start YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="expiry window end YYYY-MM-DD")
    ap.add_argument("--min-oi", type=int, default=MIN_OPEN_INTEREST)
    args = ap.parse_args(argv)

    roots = [r.strip().upper() for r in args.roots.split(",")] if args.roots else active_basket()
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    if end < start:
        print(f"ERROR: --end {end} precedes --start {start}", file=sys.stderr)
        return 2

    creds = resolve_alpaca_creds()
    print(f"[creds] source={creds.source} key={masked(creds.key)}", file=sys.stderr)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    summaries = []
    failures = []
    for root in roots:
        try:
            s = ingest_root(root, start, end, creds.key, creds.secret, min_oi=args.min_oi)
        except IngestError as e:
            failures.append(f"{root}: {e}")
            print(f"[FAIL] {e}", file=sys.stderr)
            continue
        summaries.append(s)
        with MANIFEST.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(s) + "\n")
        print(
            f"[ok] {root}: {s['contracts_with_bars']}/{s['contracts_screened']} contracts "
            f"({s['coverage_ratio']:.0%}) -> {s['total_bar_rows']} rows "
            f"({s['thin_contracts_le_2_bars']} thin)",
            file=sys.stderr,
        )

    if not summaries:
        print("ERROR: every root failed — nothing ingested.", file=sys.stderr)
        return 1
    if failures:
        print(f"WARNING: {len(failures)} root(s) failed: {failures}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
