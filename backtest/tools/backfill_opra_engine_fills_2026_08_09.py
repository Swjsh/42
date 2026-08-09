"""Backfill the OPRA 5-min cache for engine fills that every study has been silently excluding.

WHY: the entry-quality ledger's real broker fills are the highest-value evidence this program
has, and a slice of them is dropped from EVERY study for one boring reason -- no cached option
bars. Observed this session: the entry x exit matrix excluded 16 events, the stop_mode shadow
clock's smoke run skipped 20. Each exclusion is a real trade whose exit counterfactual cannot
be priced, so it silently shrinks n on every forward clock and every retrospective battery at
once. Fixing it is a cheap multiplier on all future evidence rather than a new hypothesis.

REUSE, DO NOT RE-IMPLEMENT: this calls fetch_option_data.py's OWN fetch_contract_bars /
write_cache / already_cached. That module's main() drives a HARDCODED CONTRACTS list, which is
why it never picked these up -- the fetch logic is fine, only its input list was fixed. Writing
a second fetcher would risk a resolution mismatch: the cache is 5-MINUTE (option_pricing_real
raises NotImplementedError for anything else), while the 1-min fetcher used elsewhere in this
family would silently poison it.

IDEMPOTENT + SAFE: skips anything already cached, never overwrites, and only ever ADDS files
for symbols that appear in the real fill ledger.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "backtest"), str(REPO / "backtest" / "tools"),
           str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LEDGER = REPO / "analysis" / "entry-quality" / "entry-quality-ledger.json"
REPORT = REPO / "analysis" / "recommendations" / "opra-backfill-2026-08-09.json"


def main() -> int:
    import fetch_option_data as fod
    from _alpaca_creds import resolve_alpaca_creds

    events = json.loads(LEDGER.read_text(encoding="utf-8"))["events"]
    fills = [e for e in events if e.get("is_option") and e.get("side") == "buy"]
    # symbol -> its trade date (0DTE, so the fill date IS the contract's only session)
    want: dict[str, str] = {}
    for e in fills:
        want.setdefault(e["symbol"], e["date_et"])

    missing = {s: d for s, d in want.items() if not fod.already_cached(s)}
    print(f"[opra-backfill] {len(want)} distinct contracts in the fill ledger, "
          f"{len(missing)} NOT cached", flush=True)
    if not missing:
        REPORT.write_text(json.dumps({"missing": 0, "fetched": 0, "failed": []}, indent=1),
                          encoding="utf-8")
        print("[opra-backfill] nothing to do")
        return 0

    creds = resolve_alpaca_creds()
    fetched, failed, empty = [], [], []
    for i, (sym, date_et) in enumerate(sorted(missing.items()), 1):
        try:
            rows = fod.fetch_contract_bars(sym, date_et, creds.key, creds.secret)
        except Exception as e:  # noqa: BLE001 -- one bad contract must not abort the sweep
            failed.append({"symbol": sym, "date": date_et, "error": f"{type(e).__name__}: {e}"[:160]})
            print(f"  [{i}/{len(missing)}] {sym} FAILED {type(e).__name__}", flush=True)
            continue
        if not rows:
            # A real, expected outcome: contracts with no OPRA prints that session (deep OTM,
            # illiquid). Recorded so the exclusion is EXPLAINED rather than perpetually retried.
            empty.append({"symbol": sym, "date": date_et})
            print(f"  [{i}/{len(missing)}] {sym} no bars returned", flush=True)
            continue
        fod.write_cache(sym, rows)
        fetched.append({"symbol": sym, "date": date_et, "bars": len(rows)})
        print(f"  [{i}/{len(missing)}] {sym} cached {len(rows)} bars", flush=True)
        time.sleep(0.15)          # be polite to the data endpoint

    REPORT.write_text(json.dumps({
        "distinct_contracts_in_ledger": len(want), "missing_at_start": len(missing),
        "fetched": fetched, "no_bars_returned": empty, "failed": failed,
        "note": ("no_bars_returned are contracts with no OPRA prints that session -- a real "
                 "data absence, not a fetch bug; they stay excluded and that is correct."),
    }, indent=1), encoding="utf-8")
    print(f"\n[opra-backfill] cached {len(fetched)}, no-bars {len(empty)}, failed {len(failed)}")
    print(f"[opra-backfill] wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
