"""hard_day_strike_axis_2026_08_04.py -- LENS 4 THE HARD-DAY TEST.

THE QUESTION: 2026-08-04's biggest single config contributor was ATM-TIER-EXTENSION-2K-10K
(V15_BOLD_CORE_TIERS $2K-$10K row OTM-2 -> ATM). At a FIXED contract count an ATM 0DTE call
costs ~2.2x an OTM-2 one, so the extension is functionally a ~2.2x NOTIONAL increase wearing a
strike-selection costume. On a trend day that pays. The honest risk is the mirror: does the
current stack LOSE MORE on a hostile day than the old one did?

WHY THIS IS A SEPARATE, SIMPLER TOOL THAN repeatability_decompose_2026_08_04.py
--------------------------------------------------------------------------------
That module reconstructs ADMISSION (which entries an arm would have taken) from the live
decision ledgers. On 2026-08-04 it reproduces the broker day to the cent. On the pre-2026-08-03
hard days it does NOT: those ledgers ran a ~3-minute tick cadence, and some core fills have no
matching core-decisions ENTER row at all (2026-07-22: safe-2 took a real -$108 round trip while
core-decisions logged zero ENTER verdicts that session -- an extra_exec/second-path fill, the
exact L244 blind spot). Its parity gate FAILS on all three hard days (hybrid_err $117 / $108 /
$54), so nothing it says about them is quotable. Rather than paper over that, this tool asks a
narrower question it can answer EXACTLY:

  Hold the trade fixed -- same arm, same entry timestamp, same qty, same exit contract --
  and change ONLY the strike. Lane A is the REAL broker round trip (no simulation whatsoever).
  Lane B re-prices the identical trade at OTM-2 on real 1-minute OPRA through the REAL
  exit_manager core. n is exactly the real trade count; there is no admission model to be
  wrong about.

WHAT THIS DELIBERATELY DOES NOT CLAIM
--------------------------------------
  * NOT a full "yesterday's config" replay of those days. Only the strike axis moves.
  * Qty is held at the LIVE value. On the hard days the arms were ~$1.7K equity (where BOTH
    tier tables already said ATM); the OTM-2 lane is therefore the counterfactual "had these
    same trades been taken from the $2K-$10K bracket the arms occupy TODAY". Equity-driven
    re-sizing is NOT modelled -- stated, not hidden.
  * A trade whose OTM-2 contract has no cached OPRA bar, or prices under the $0.30
    min_entry_premium floor, is reported in its own bucket (floor-blocked trades are counted
    as $0 -- the live engine would not have taken them at all -- and the count is disclosed).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(BACKTEST / "tools"),
           str(REPO / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import repeatability_decompose_2026_08_04 as rd  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.et_frame import FRAME_ET_V2  # noqa: E402
from fills_fifo import mine_real_arm_fills  # noqa: E402
import strategies as fleet_strategies  # noqa: E402


def shape_for_roundtrip(arm: str, date_et: str, entry_ts: dt.datetime,
                        symbol: str) -> tuple[dict, bool, Optional[float], str]:
    """(exit_shape, structure_stop_enabled, trigger_level, source) for one real round trip.

    Preferred source is the arm's OWN ledger placement payload for that entry -- the exact
    shape fleet_executor._exit_shape_dict resolved live, per-arm exit_patch included. Falls
    back to the RIBBON_RIDE registry shape (what heartbeat_core registers for a core-arm
    ribbon entry) when no placement row exists, and says which it used."""
    if arm in rd.FLEET_ARMS:
        rows = rd._jsonl(REPO / "automation" / "state" / "fleet" / arm / "decisions.jsonl", date_et)
        best, best_gap = None, None
        for r in rows:
            pl = r.get("placement") or {}
            if pl.get("symbol") != symbol:
                continue
            gap = abs((rd._naive_et(r["ts_et"]) - entry_ts).total_seconds())
            if gap <= 300 and (best_gap is None or gap < best_gap):
                best, best_gap = r, gap
        if best is not None:
            pl = best["placement"]
            return (rd._exit_shape_from_placement(pl),
                    str(pl.get("stop_mode", "")).lower() == "structure",
                    pl.get("trigger_level"), "arm_ledger_placement")
    params_path = (REPO / "automation" / "state" / "params.json" if arm in ("safe-2", "safe-3")
                   else REPO / "automation" / "state" / "aggressive" / "params.json")
    params = json.loads(params_path.read_text(encoding="utf-8"))
    return (fleet_strategies.RIBBON_RIDE.exit.to_dict(),
            bool(params.get("structure_stop_enabled", False)), None, "ribbon_ride_registry")


def run_day(date_et: str) -> dict:
    spy_5m, ribbon_lookup = rd.load_spy(date_et)
    cache = rd.OptCache(date_et, ribbon_lookup, spy_5m)
    rows, floor_blocked, no_bars = [], 0, 0
    for arm in rd.ALL_ARMS:
        for rt in mine_real_arm_fills(arm):
            if rt["date"] != date_et:
                continue
            entry_ts = rd._naive_et(rt["entry_ts_et"])
            side = rt["side"]
            atm_strike = int(rt["symbol"][-8:-3])
            cf_strike = rd.otm2_strike(atm_strike, side)
            cf_symbol = rd.occ_symbol(date_et, cf_strike, side)
            real_pnl = float(rt["real_pnl"])
            shape, struct, trig, shape_src = shape_for_roundtrip(arm, date_et, entry_ts, rt["symbol"])

            opt = cache.bars(cf_symbol)
            atm_close = cache.close_at(rt["symbol"], entry_ts)
            cf_close = cache.close_at(cf_symbol, entry_ts) if opt is not None else None
            if opt is None or opt.empty or cf_close is None or not atm_close:
                no_bars += 1
                rows.append({"arm": arm, "entry": rt["entry_ts_et"], "symbol": rt["symbol"],
                             "cf_symbol": cf_symbol, "atm_pnl": real_pnl, "otm2_pnl": None,
                             "note": "no_opra_for_counterfactual"})
                continue
            ratio = rd.exec_cost_ratio(float(rt["entry_premium"]), atm_close) or 1.0
            cf_premium = round(cf_close * ratio, 2)
            if cf_premium < rd.MIN_ENTRY_PREMIUM:
                floor_blocked += 1
                rows.append({"arm": arm, "entry": rt["entry_ts_et"], "symbol": rt["symbol"],
                             "cf_symbol": cf_symbol, "cf_premium": cf_premium,
                             "atm_pnl": real_pnl, "otm2_pnl": 0.0,
                             "note": "otm2_below_min_entry_premium_floor_not_taken"})
                continue
            res = walk_exit_manager(
                symbol=cf_symbol, side=side, entry_time_et=entry_ts, entry_premium=cf_premium,
                qty=int(rt["qty"]), exit_shape=shape, structure_stop_enabled=struct,
                trigger_level=trig, strategy="", time_stop_et=rd.DEFAULT_TIME_STOP,
                opt_df=opt, ribbon_tick_df=cache.ribbon(cf_symbol), five_min_spy_df=cache.spy_5m,
                opt_df_resolution="1min", frame=FRAME_ET_V2)
            pnl = sum((lg.fill_price - cf_premium) * lg.qty * 100 for lg in res.legs)
            done = sum(lg.qty for lg in res.legs)
            if done < int(rt["qty"]):
                pnl += (float(opt.iloc[-1]["close"]) - cf_premium) * (int(rt["qty"]) - done) * 100
            rows.append({"arm": arm, "entry": rt["entry_ts_et"], "symbol": rt["symbol"],
                         "cf_symbol": cf_symbol, "qty": int(rt["qty"]),
                         "atm_premium": float(rt["entry_premium"]), "cf_premium": cf_premium,
                         "atm_pnl": real_pnl, "otm2_pnl": round(pnl, 2),
                         "otm2_exit_reason": res.exit_reason, "shape_source": shape_src})
    priced = [r for r in rows if r.get("otm2_pnl") is not None]
    atm_tot = round(sum(r["atm_pnl"] for r in priced), 2)
    otm_tot = round(sum(r["otm2_pnl"] for r in priced), 2)
    arch = _archetype(date_et)
    return {"date_et": date_et, "archetype": arch, "n_roundtrips": len(rows),
            "n_priced": len(priced), "n_no_opra_excluded": no_bars,
            "n_otm2_floor_blocked": floor_blocked,
            "atm_total_REAL": atm_tot, "otm2_total_SIM": otm_tot,
            "atm_minus_otm2": round(atm_tot - otm_tot, 2),
            "premium_ratio_median": _median([r["atm_premium"] / r["cf_premium"]
                                             for r in priced
                                             if r.get("cf_premium") and r.get("atm_premium")]),
            "rows": rows}


def _median(xs):
    xs = sorted(x for x in xs if x)
    if not xs:
        return None
    n = len(xs)
    return round(xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2, 3)


def _archetype(date_et: str) -> Optional[str]:
    from lib.regime_slice import archetype_of
    return archetype_of(date_et)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dates", nargs="+", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = {"lane_A": "REAL broker round trips at the strike actually traded (ATM) -- no sim",
           "lane_B": "same trades re-struck OTM-2, real 1-min OPRA through the real exit core (SIM)",
           "days": {}}
    print(f"{'date':<12}{'archetype':<12}{'n':>4}{'ATM(real)':>12}{'OTM2(sim)':>12}"
          f"{'ATM-OTM2':>11}{'prem x':>8}{'floorblk':>9}")
    for d in args.dates:
        r = run_day(d)
        out["days"][d] = r
        print(f"{d:<12}{str(r['archetype']):<12}{r['n_priced']:>4}{r['atm_total_REAL']:>12,.2f}"
              f"{r['otm2_total_SIM']:>12,.2f}{r['atm_minus_otm2']:>11,.2f}"
              f"{(r['premium_ratio_median'] or 0):>8.2f}{r['n_otm2_floor_blocked']:>9}")
    tot_a = round(sum(v["atm_total_REAL"] for v in out["days"].values()), 2)
    tot_b = round(sum(v["otm2_total_SIM"] for v in out["days"].values()), 2)
    out["totals"] = {"atm_REAL": tot_a, "otm2_SIM": tot_b, "atm_minus_otm2": round(tot_a - tot_b, 2)}
    print(f"{'TOTAL':<24}{'':>4}{tot_a:>12,.2f}{tot_b:>12,.2f}{tot_a - tot_b:>11,.2f}")
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
