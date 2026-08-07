"""score_ladder_week_live_2026_08_07.py -- THE WEEK CELL ON LIVE TAPE + REAL OPRA.

Prereg: analysis/recommendations/prereg-score-ladder-v2-2026-08-07.json (c2ec28f3).

The orchestrator-replay week cell (score_ladder_replay_2026_08_07.py) is a weak instrument
for THIS week: the offline reconstruction takes almost no trades 08-03..08-06 (known
entry-layer divergence -- offline OHLC-derived levels vs the live engine's TV/memory level
feed), so its week numbers measure replay divergence more than ladder quality. THIS tool
walks the frozen SCORE-LADDER-V2 admission over the LIVE engine's own per-tick ledger
(automation/state/core-decisions.jsonl -- the scores/blockers the engine actually computed
each minute, live levels included) for 2026-08-03..08-06, pricing every hypothetical entry
and exit on REAL OPRA 5-min bars (backfilled today, backtest/data/options/). No BS
estimation anywhere in this file's P&L.

Lanes per day, per rung {6,7,8,9}: rung-admitted EXTRAS ONLY (the added cohort), qty=3 ATM
(PROBE table), sequential NOT_FLAT, entry = first cached option bar at/after the NEXT tick,
entry price = that bar's OPEN, exits via walk_exit_manager -> exit_manager.plan_exit_actions
ONLY (ribbon_ride registry shape, structure stop at the raw level), time stop 15:40.
The binary side of the week is the arms' REAL broker P&L (already booked); the ladder's
week delta = these extras.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import strategies as fleet_strategies                                     # noqa: E402
import fleet_executor as fx                                                # noqa: E402
import engine_fullhist_replay as efr                                        # noqa: E402
from lib.exit_manager_walk import walk_exit_manager                          # noqa: E402
from lib.option_pricing_real import (                                         # noqa: E402
    bar_at_or_after, load_contract_bars, option_symbol,
)
from crypto.lib.strike_selection import pick_strike                            # noqa: E402
from score_ladder_replay_2026_08_07 import side_admission                       # noqa: E402
from score_ladder_today_est_2026_08_07 import tick_admission                     # noqa: E402

LEDGER = ROOT / "automation" / "state" / "core-decisions.jsonl"
NEW_SPY = REPO / "data" / "spy_5m_2026-05-19_2026-08-06.csv"
OUT_JSON = ROOT / "analysis" / "deep-research" / "SCORE-LADDER-WEEK-LIVE-2026-08-07.json"

WEEK = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]
RUNGS = (6, 7, 8, 9)
REF_EQUITY = 2000.0
QTY = 3
TIME_STOP = dt.time(15, 40)
ENTRY_FLOOR = 0.30


def log(m):
    print(f"[week-live] {m}", flush=True)


def load_day_ticks(day: str) -> list[dict]:
    rows, seen = [], set()
    prefix = f'{{"ts_et": "{day}'
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            if not line.startswith(prefix):
                continue
            r = json.loads(line)
            if r.get("account") != "safe":
                continue
            key = r.get("core_tick_id") or r.get("ts_et")
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
    rows.sort(key=lambda r: r["ts_et"])
    return rows


def walk_day(day: str, ticks: list[dict], rung: int, spy_rth: pd.DataFrame,
             ribbon_lookup: pd.DataFrame, exit_shape: dict) -> dict:
    trades, skipped = [], []
    flat_until: Optional[dt.datetime] = None
    d = dt.date.fromisoformat(day)
    day_spy = spy_rth.loc[spy_rth["timestamp_et"].dt.date == d].reset_index(drop=True)
    for i, r in enumerate(ticks):
        ts = dt.datetime.fromisoformat(r["ts_et"])
        if ts.time() < dt.time(9, 35) or ts.time() >= dt.time(15, 0):
            continue
        if flat_until is not None and ts <= flat_until:
            continue
        adm = tick_admission(r)
        if adm is None or adm["adjusted"] < rung:
            continue
        if i + 1 >= len(ticks):
            continue
        nxt = ticks[i + 1]
        nts = dt.datetime.fromisoformat(nxt["ts_et"])
        spot = float(nxt["spy"])
        strike = pick_strike(spot, REF_EQUITY, adm["side"], fx.PROBE_STRIKE_TIERS)
        symbol = option_symbol(d, int(strike), adm["side"])
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            skipped.append({"ts": r["ts_et"], "reason": "no_opra_cache", "symbol": symbol})
            continue
        ob = bar_at_or_after(opt_df, pd.Timestamp(nts).tz_localize("America/New_York"))
        if ob is None:
            skipped.append({"ts": r["ts_et"], "reason": "no_bar_at_or_after", "symbol": symbol})
            continue
        entry_premium = float(ob.open)
        entry_time = efr.naive_dt(ob.timestamp_et)
        if entry_premium < ENTRY_FLOOR:
            skipped.append({"ts": r["ts_et"], "reason": f"min_premium_floor {entry_premium}"})
            continue
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        res = walk_exit_manager(
            symbol=symbol, side=adm["side"], entry_time_et=entry_time,
            entry_premium=entry_premium, qty=QTY, exit_shape=exit_shape,
            structure_stop_enabled=True, trigger_level=adm["level"],
            strategy="ribbon_ride", time_stop_et=TIME_STOP,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        exit_ts = res.exit_time_et if res.exit_time_et is not None else entry_time
        flat_until = exit_ts
        is_call = adm["side"] == "C"
        trades.append({
            "date": day, "trigger_ts": r["ts_et"], "entry_ts": entry_time.isoformat(),
            "side": adm["side"], "symbol": symbol, "qty": QTY,
            "entry_premium_realOPRA": round(entry_premium, 4),
            "score": int(r["bull_score"] if is_call else r["bear_score"]),
            "blockers": list((r["bull_blockers"] if is_call else r["bear_blockers"]) or []),
            "adjusted": adm["adjusted"], "level": adm["level"],
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
            "exit_ts": exit_ts.isoformat() if exit_ts else None,
            "hold_minutes": res.hold_minutes,
        })
    return {"trades": trades, "skipped": skipped,
            "total": round(sum(t["dollar_pnl"] for t in trades), 2)}


def main() -> int:
    spy_df = pd.read_csv(NEW_SPY)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    spy_rth = spy_df[(spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
                      & (spy_df["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    out = {"_doc": __doc__, "generated_at": dt.datetime.now().isoformat(),
           "prereg": "prereg-score-ladder-v2-2026-08-07.json (c2ec28f3)", "days": {}}
    week_totals = {str(g): 0.0 for g in RUNGS}
    for day in WEEK:
        ticks = load_day_ticks(day)
        n_hold = sum(1 for r in ticks if r.get("verdict") == "HOLD")
        day_out = {"n_ticks": len(ticks), "n_hold": n_hold, "rungs": {}}
        for rung in RUNGS:
            lane = walk_day(day, ticks, rung, spy_rth, ribbon_lookup, exit_shape)
            day_out["rungs"][str(rung)] = lane
            week_totals[str(rung)] += lane["total"]
            log(f"{day} rung {rung}: extras {len(lane['trades'])} -> ${lane['total']:+.2f} "
                f"(skipped {len(lane['skipped'])})")
        out["days"][day] = day_out
    out["week_extras_totals_by_rung"] = {k: round(v, 2) for k, v in week_totals.items()}
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    log(f"week extras totals: {out['week_extras_totals_by_rung']}")
    log(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
