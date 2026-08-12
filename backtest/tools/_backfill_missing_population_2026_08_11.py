"""One-off backfill: fetch OPRA 5-min bars for every real-fills population position whose
contract is NOT in the cache (92 of 274 rows as of 2026-08-11 — gaps at 07-16, 07-20..07-23,
08-11 and partials elsewhere). Same read-only pattern as _fetch_late_entry_contracts_2026_07_23.py
(fetch_option_data.py + _alpaca_creds.py, options/bars endpoint) — no order placement.

Run: backtest/.venv/Scripts/python.exe backtest/tools/_backfill_missing_population_2026_08_11.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in ("tools", "lib", ""):
    sys.path.insert(0, str(REPO / p) if p else str(REPO))

from fetch_option_data import fetch_contract_bars, write_cache, already_cached  # noqa: E402
from _alpaca_creds import resolve_alpaca_creds  # noqa: E402
from ladder_population_killcheck import load_positions  # noqa: E402


def main() -> int:
    creds = resolve_alpaca_creds()
    print(f"Alpaca creds source={creds.source}")
    # unique (date, symbol) pairs missing from cache, oldest first
    seen: set[str] = set()
    targets: list[tuple[str, str]] = []
    for q in sorted(load_positions(), key=lambda r: r["date"]):
        sym = q["symbol"]
        if sym in seen:
            continue
        seen.add(sym)
        if not already_cached(sym):
            targets.append((q["date"], sym))
    print(f"{len(targets)} uncached contracts to fetch")
    ok = empty = err = 0
    for date_str, symbol in targets:
        try:
            rows = fetch_contract_bars(symbol, date_str, creds.key, creds.secret)
        except Exception as e:  # noqa: BLE001 — loud per-contract, keep sweeping (C7)
            print(f"  ERR  {symbol} {type(e).__name__}: {e}")
            err += 1
            continue
        if not rows:
            print(f"  EMPTY {symbol} ({date_str})")
            empty += 1
            continue
        write_cache(symbol, rows)
        print(f"  ok   {symbol} {len(rows)} bars")
        ok += 1
    print(f"\nDONE: {ok} fetched, {empty} empty, {err} errors")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
