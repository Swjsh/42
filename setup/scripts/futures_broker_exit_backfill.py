"""futures_broker_exit_backfill.py -- one-off backfill for FUTURES-BROKER-LANE-NEVER-LOGS-EXITS.

Walks the trader-broker lane's OWN `ENTER` rows in `automation/state/futures/trader-broker/
decisions.jsonl` (order_ids the lane itself placed -- never another lane's fills on the
same shared sandbox account) in chronological order, and for each one:
  1. writes an `open-entry.json` context (the reconciler's normal ENTER-time write, done
     here after the fact because the writer bug meant it was never written live),
  2. calls `futures_broker_reconciler.reconcile_broker_exits` against the SANDBOX's own
     real order/fill history (read-only) to find and journal the real closing fill(s),
     labeled `backfilled_2026_09_03` (never `reconciled_2026_09_03`, which is reserved for
     the live per-tick path so a reader can always tell which wrote a row).

Idempotent: `reconcile_broker_exits` skips any fill_id already recorded in
`journaled-fills.json`, so re-running this script is a no-op after the first successful run.

READ-ONLY against the broker (get_recent_fills only). WRITES only journal/futures/trades.csv
and this lane's own trader-broker/ state files. Never places, cancels, or replaces an order.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

DECISIONS = REPO / "automation" / "state" / "futures" / "trader-broker" / "decisions.jsonl"


def _load_entries() -> list[dict]:
    rows = []
    if not DECISIONS.exists():
        return rows
    with DECISIONS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("action") == "ENTER" and r.get("order_ids") and r.get("entry"):
                rows.append(r)
    rows.sort(key=lambda r: r.get("ts_et", ""))
    return rows


def main(argv=None) -> int:
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be journaled, write nothing")
    args = ap.parse_args(argv)

    from futures.futures_broker_reconciler import (  # noqa: PLC0415
        record_open_entry, reconcile_broker_exits, open_entry_path,
    )
    from futures.futures_trader_core import _load_broker_env, lane_paths  # noqa: PLC0415
    from futures.tastytrade_paper import TastytradeBroker  # noqa: PLC0415
    from futures.instruments import get as get_instrument  # noqa: PLC0415

    entries = _load_entries()
    if not entries:
        print("[backfill] no ENTER rows with order_ids found -- nothing to do")
        return 0
    print(f"[backfill] {len(entries)} ENTER row(s) to reconcile")

    _load_broker_env()
    broker = TastytradeBroker(watch_only=False)  # read-only calls only -- see module docstring
    if not broker.connect():
        print(f"[backfill] ABORT: could not connect to sandbox: {broker.last_failure_detail}")
        return 1

    paths = lane_paths(backend="tastytrade")
    total_journaled = 0
    for idx, row in enumerate(entries):
        instrument = row.get("instrument", "MES")
        inst = get_instrument(instrument)
        entry_ts = row["ts_et"]
        try:
            now_et = dt.datetime.fromisoformat(entry_ts)
        except ValueError:
            print(f"[backfill] SKIP unparseable ts_et {entry_ts!r}")
            continue

        # Bound this entry's fill search to STRICTLY BEFORE the next ENTER (if any) --
        # otherwise a fill that actually closed a LATER entry (same symbol, same closing
        # side) gets swept into this earlier entry's window and wrongly marked "already
        # journaled", starving the later entry of its own real close. The last entry in the
        # walk has no next one, so it searches all the way to real "now".
        next_row = entries[idx + 1] if idx + 1 < len(entries) else None
        until_et = None
        if next_row is not None:
            try:
                until_et = dt.datetime.fromisoformat(next_row["ts_et"])
            except ValueError:
                until_et = None

        print(f"[backfill] {entry_ts} ENTER {row['entry'].get('setup')} "
             f"order_ids={row['order_ids']} (until={until_et or 'now'})")
        if args.dry_run:
            continue

        record_open_entry(paths, symbol=inst.symbol, entry=row["entry"],
                          order_ids=row["order_ids"], now_et=now_et)
        exits = reconcile_broker_exits(
            broker, inst, paths, dt.datetime.now(), point_value=inst.point_value,
            backend_name="TastytradeBroker", label="backfilled_2026_09_03",
            until_et=until_et)
        if exits:
            total_journaled += len(exits)
            for e in exits:
                print(f"    -> journaled qty={e['qty']} pnl={e['pnl']} "
                     f"fill_id={e['fill']['fill_id']} @ {e['fill']['filled_at']}")
        else:
            print("    -> no NEW closing fill found (already journaled, or still open)")

    # Leave no dangling open-entry.json from this backfill run pointing at the OLDEST
    # entry if the newest one is genuinely still open at the broker -- re-point it at
    # whichever entry (if any) reconcile_broker_exits did not fully close.
    still_open = open_entry_path(paths)
    if still_open.exists():
        data = json.loads(still_open.read_text(encoding="utf-8"))
        print(f"[backfill] NOTE: entry at {data.get('entry_time_et')} still shows "
             f"{float(data.get('entry', {}).get('qty', 0)) - float(data.get('closed_qty', 0))} "
             f"contract(s) unaccounted for -- broker may still be flat (a stray fill this "
             f"reconciler could not attribute) or genuinely open; verify with a read-only "
             f"is_flat()/get_positions() check before trusting this file.")

    print(f"[backfill] DONE -- {total_journaled} exit row(s) journaled this run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
