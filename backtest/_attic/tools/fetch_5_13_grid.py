"""One-shot fetch of OPRA bars for 5/13/2026 across the variant strike grid.

Strikes 735..745 for both calls + puts (covers ITM-2 to OTM-4 of $739 spot
plus a buffer). Writes to backtest/data/options/SPY260513{C|P}{strike*1000}.csv.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO.parent))

from backtest.tools.fetch_option_data import (
    already_cached,
    fetch_contract_bars,
    write_cache,
)


TARGET_DATE = "2026-05-13"
STRIKES = list(range(735, 746))  # 735..745 inclusive
SIDES = ("C", "P")


def _symbol(strike: int, side: str) -> str:
    return f"SPY260513{side}{strike * 1000:08d}"


def main() -> int:
    fetched = 0
    failed: list[tuple[str, str]] = []
    skipped = 0
    for strike in STRIKES:
        for side in SIDES:
            sym = _symbol(strike, side)
            if already_cached(sym):
                skipped += 1
                continue
            try:
                rows = fetch_contract_bars(sym, TARGET_DATE)
                if not rows:
                    print(f"  WARN {sym}  empty response")
                    failed.append((sym, "empty"))
                    continue
                write_cache(sym, rows)
                print(f"  ok   {sym}  {len(rows)} bars")
                fetched += 1
                time.sleep(0.20)
            except Exception as exc:  # noqa: BLE001
                print(f"  FAIL {sym}  {exc}")
                failed.append((sym, str(exc)))
    print(f"\nFetched {fetched} new, skipped {skipped} cached, {len(failed)} failed")
    if failed:
        for sym, why in failed:
            print(f"  - {sym}: {why}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
