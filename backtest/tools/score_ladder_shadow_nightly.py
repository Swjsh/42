"""score_ladder_shadow_nightly.py -- $0 nightly SCORE-LADDER-V2 shadow ledger.

Prereg: analysis/recommendations/prereg-score-ladder-v2-2026-08-07.json (c2ec28f3).
Verdict that created this: PREREG-ONLY (2026-08-07) -- the demerit ladder does NOT arm on
current evidence; THIS ledger is its forward clock. Runs after ~16:35 ET (same-day OPRA
unlocks ~16:21): fetches the day's missing ATM+/-3 contracts through the established
expand_opra_cache path, walks the frozen admission over the live engine's own tick ledger
(core-decisions.jsonl) per rung {6,7,8,9} on REAL OPRA via walk_exit_manager, and appends
one row per rung to analysis/arm-ladder/ladder-v2-shadow-ledger.jsonl.

Forward arm bar (frozen here, before any forward data): consider arming BULL-ONLY rung 8 on
risky-1 only after >=10 ledger sessions with (a) rung-8 extras net > 0, (b) no session
worse than -$500 at qty3, (c) chop/fade sessions (negative-extras days) not worse than
-$300/session on average. Bear-side arming is OFF the table on current evidence
(population extras -$6.3K; echoes the 2026-07-27 disarmed lane).

Usage: backtest/.venv/Scripts/python.exe backtest/tools/score_ladder_shadow_nightly.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import strategies as fleet_strategies                                  # noqa: E402
import engine_fullhist_replay as efr                                     # noqa: E402
from expand_opra_cache import (                                           # noqa: E402
    already_cached, fetch_contract_bars, option_symbol as occ_symbol,
    write_cache, write_empty_sentinel,
)
from _alpaca_creds import resolve_alpaca_creds                             # noqa: E402
from score_ladder_week_live_2026_08_07 import load_day_ticks, walk_day      # noqa: E402

LEDGER_OUT = ROOT / "analysis" / "arm-ladder" / "ladder-v2-shadow-ledger.jsonl"
RUNGS = (6, 7, 8, 9)


def latest_spy_cache() -> Path:
    cands = sorted((REPO / "data").glob("spy_5m_2026-*_*.csv"))
    return cands[-1]


def ensure_day_opra(day: dt.date, ticks: list[dict]) -> int:
    """Fetch ATM+/-3-around-day-range contracts missing from the cache. Returns n fetched."""
    if not ticks:
        return 0
    spots = [float(r["spy"]) for r in ticks if r.get("spy")]
    lo, hi = math.floor(min(spots)) - 3, math.ceil(max(spots)) + 3
    todo = []
    for strike in range(lo, hi + 1):
        for side in ("C", "P"):
            sym = occ_symbol(day, strike, side)
            if not already_cached(sym):
                todo.append(sym)
    if not todo:
        return 0
    key, secret = resolve_alpaca_creds()[:2]
    n = 0
    for sym in todo:
        try:
            rows = fetch_contract_bars(sym, day, key, secret)
            if rows:
                write_cache(sym, rows)
            else:
                write_empty_sentinel(sym)
            n += 1
        except Exception as e:  # noqa: BLE001
            print(f"[shadow] fetch err {sym}: {e}", flush=True)
        time.sleep(0.25)
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()
    day_s = args.date
    day = dt.date.fromisoformat(day_s)

    ticks = load_day_ticks(day_s)
    if not ticks:
        print(f"[shadow] no ticks for {day_s} -- nothing to tally (weekend/holiday?)")
        return 0
    n_fetched = ensure_day_opra(day, ticks)

    spy_path = latest_spy_cache()
    spy_df = pd.read_csv(spy_path)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    spy_rth = spy_df[(spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
                      & (spy_df["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    LEDGER_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_OUT, "a", encoding="utf-8") as f:
        for rung in RUNGS:
            lane = walk_day(day_s, ticks, rung, spy_rth, ribbon_lookup, exit_shape)
            bull = [t for t in lane["trades"] if t["side"] == "C"]
            bear = [t for t in lane["trades"] if t["side"] == "P"]
            row = {
                "date": day_s, "rung": rung, "tallied_at": dt.datetime.now().isoformat(),
                "n_extras": len(lane["trades"]), "extras_pnl": lane["total"],
                "bull_n": len(bull), "bull_pnl": round(sum(t["dollar_pnl"] for t in bull), 2),
                "bear_n": len(bear), "bear_pnl": round(sum(t["dollar_pnl"] for t in bear), 2),
                "n_skipped": len(lane["skipped"]), "n_opra_fetched": n_fetched,
                "spy_cache": spy_path.name,
                "trades": [{k: t[k] for k in ("trigger_ts", "side", "symbol", "adjusted",
                                                 "blockers", "entry_premium_realOPRA",
                                                 "dollar_pnl", "exit_reason")}
                            for t in lane["trades"]],
            }
            f.write(json.dumps(row, default=str) + "\n")
            print(f"[shadow] {day_s} rung {rung}: extras {row['n_extras']} "
                  f"${row['extras_pnl']:+.2f} (bull {row['bull_n']}/${row['bull_pnl']:+.2f} "
                  f"bear {row['bear_n']}/${row['bear_pnl']:+.2f})", flush=True)
    print(f"[shadow] appended 4 rows to {LEDGER_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
