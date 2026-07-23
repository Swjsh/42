"""bull_gate_atm_ssb_requalification.py -- the OWED OP-16 re-eval, executed at ATM strike.

Mission (2026-07-22, J-directed MIRROR-PARITY AUDIT + BULL REQUALIFICATION): CLAUDE.md OP-16
says the bull side "stays enabled pending honest re-eval at n>=20 under SS-B + corrected strike
tier" -- that re-eval had never been run AT ATM. The existing block-elite-bull-ssb-revalidation
(2026-07-10) already applied the SS-B exit shape but still used OTM-2 strikes (STRIKE_OFFSET_
BULL=-2, explicitly pinned in its own pre-registration). This script corrects that ONE variable
and extends the added-cohort method to the OTHER live bull gate in GATE_ORDER (block_bull_1100_
1200), which has never had a dedicated requalification at any exit shape.

Executes the frozen pre-registration at
analysis/recommendations/bull-requalification-prereg-2026-07-22.json (read for cohort
definitions/pass-bar; no re-picks after seeing results).

METHOD
------
1. Detect signals via run_backtest(use_real_fills=True), strike_offset=0 (ATM), current
   production gate stack, isolating ONE gate at a time (the other held at its production value):
     BASE            = block_elite_bull=True,  block_bull_1100_1200=True   (both prod)
     UNBLOCK_ELITE    = block_elite_bull=False, block_bull_1100_1200=True
     UNBLOCK_1100     = block_elite_bull=True,  block_bull_1100_1200=False
   Added cohort per gate = trades in the UNBLOCK run not in BASE, side=='C'.
2. Re-walk EVERY added trade's EXIT through the REAL production exit_manager decision core
   (backtest/lib/exit_manager_walk.py#walk_exit_manager) using automation/state/fleet/
   strategies.py's live RIBBON_RIDE.exit.to_dict() shape (the shipped SS-B cell) with
   structure_stop_enabled=True -- NOT simulate_trade_real, which exit_manager_walk.py's own
   docstring documents as KNOWN-DIVERGENT from the live exit manager. Only entry_time_et/
   entry_premium/strike/rejection_level are taken from the run_backtest detection pass; every
   dollar of P&L reported here comes from the walk, not from run_backtest's own (OLD-exit)
   simulate_trade_real total.
3. 100% LOCAL CACHE. No broker/Alpaca imports anywhere in this script's import graph (verified:
   fleet_broker / exit_shape_parity_study / structure_stop_study are NOT imported). A signal
   whose option contract is not cached locally is DROPPED and counted in n_missing_bars, never
   imputed (C7 discipline).

Rail-4 CLEAR: analysis only. Touches NO trading-path file. No commits/pushes. No live network
reads (verified via import graph, not just behavior).

Run: backtest/.venv/Scripts/python.exe backtest/tools/bull_gate_atm_ssb_requalification.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import pandas as pd  # noqa: E402

from lib.orchestrator import run_backtest, BacktestResult  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
import strategies as strat_mod  # noqa: E402  (automation/state/fleet/strategies.py)

PREREG = REPO / "analysis" / "recommendations" / "bull-requalification-prereg-2026-07-22.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "bull-requalification-2026-07-22.json"

SPY_CSV = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-17.csv"
VIX_CSV = REPO / "backtest" / "data" / "vix_5m_2026-05-19_2026-07-17.csv"

START = dt.date(2026, 5, 21)
END = dt.date(2026, 7, 17)

TIME_STOP_ET = dt.time(15, 50)   # exit_manager.TIME_STOP_ET (live constant)
STRIKE_OFFSET_ATM = 0
N_FLOOR = 20                      # OP-16's own evidence_n bar, cited verbatim by the task brief


def _prod_cfg(*, block_elite_bull: bool, block_bull_1100_1200: bool) -> dict:
    """Current PRODUCTION Safe gate stack, strike forced to ATM (0). Every value below is
    read live from this repo's own docstrings/params.json (not re-derived) -- see the
    pre-registration's 'other_gates_held_at_production' block for the source of each."""
    return dict(
        use_real_fills=True,
        no_trade_before=dt.time(9, 35),
        enable_bullish=True,
        block_elite_bull=block_elite_bull,
        block_elite_bull_vix_low=0.0,
        block_elite_bull_vix_high=25.0,
        block_bull_1100_1200=block_bull_1100_1200,
        block_level_rejection=True,
        vix_bear_hard_cap=23.0,
        min_triggers_bull=2,
        strike_offset=STRIKE_OFFSET_ATM,
        per_trade_risk_cap_pct=0.30,
        initial_equity=1746.75,
    )


def _et_naive(ts) -> dt.datetime:
    p = pd.Timestamp(ts)
    if p.tzinfo is not None:
        p = p.tz_localize(None)
    return p.to_pydatetime()


def _trade_key(t):
    return (_et_naive(t.entry_time_et), t.side, round(float(t.strike), 2))


def added_bull_cohort(base: BacktestResult, unblock: BacktestResult) -> list:
    base_keys = {_trade_key(t) for t in base.trades}
    return [t for t in unblock.trades if t.side == "C" and _trade_key(t) not in base_keys]


# --------------------------------------------------------------------------------------------
# LOCAL-CACHE-ONLY exit re-walk (no network, no broker import)
# --------------------------------------------------------------------------------------------
def _opt_df_for(date: dt.date, strike: int, side: str) -> Optional[pd.DataFrame]:
    symbol = option_symbol(date, int(round(strike)), side)
    df = load_contract_bars(symbol)
    if df is None or df.empty:
        return None
    return df


_spy_full_cache: Optional[pd.DataFrame] = None


def _spy_full() -> pd.DataFrame:
    global _spy_full_cache
    if _spy_full_cache is None:
        df = pd.read_csv(SPY_CSV)
        ts = pd.to_datetime(df["timestamp_et"])
        if getattr(ts.dt, "tz", None) is not None:
            ts = ts.dt.tz_localize(None)
        df = df.assign(timestamp_et=ts)
        _spy_full_cache = df
    return _spy_full_cache


RIBBON_RIDE_SHAPE = strat_mod.RIBBON_RIDE.exit.to_dict()


def requalify_trade(t) -> Optional[dict]:
    """Re-walk ONE TradeFill's exit through the REAL exit_manager core at the live SS-B shape.
    Returns None (dropped) if the option contract is not cached locally."""
    entry_ts = _et_naive(t.entry_time_et)
    date = entry_ts.date()
    opt_df = _opt_df_for(date, t.strike, t.side)
    if opt_df is None:
        return None
    spy_full = _spy_full()
    five_min = spy_full[spy_full["timestamp_et"].dt.date == date]
    if five_min.empty:
        return None
    res = walk_exit_manager(
        symbol=option_symbol(date, int(round(t.strike)), t.side),
        side=t.side,
        entry_time_et=entry_ts,
        entry_premium=float(t.entry_premium),
        qty=int(t.qty),
        exit_shape=RIBBON_RIDE_SHAPE,
        structure_stop_enabled=True,
        trigger_level=float(t.rejection_level) if t.rejection_level is not None else None,
        strategy="ribbon_ride",
        time_stop_et=TIME_STOP_ET,
        opt_df=opt_df,
        ribbon_tick_df=None,
        five_min_spy_df=five_min,
    )
    structure_fired = any(leg.stage == "structure_stop" for leg in res.legs)
    return {
        "date": date.isoformat(),
        "entry_ts_et": entry_ts.isoformat(),
        "strike": int(round(t.strike)),
        "entry_premium": round(float(t.entry_premium), 4),
        "qty": int(t.qty),
        "triggers_fired": list(t.triggers_fired or []),
        "trigger_level": t.rejection_level,
        "pnl": res.dollar_pnl,
        "exit_reason": res.exit_reason,
        "structure_fired": structure_fired,
        "hold_minutes": res.hold_minutes,
    }


# --------------------------------------------------------------------------------------------
# STATS
# --------------------------------------------------------------------------------------------
def drop_top1(pnls: list[float]) -> tuple[float, bool]:
    if not pnls:
        return 0.0, False
    winners = [p for p in pnls if p > 0]
    if not winners:
        total = sum(pnls)
        return round(total, 2), total > 0
    remainder = sum(pnls) - max(winners)
    return round(remainder, 2), remainder > 0


def half_split_stability(replays: list[dict]) -> dict:
    if not replays:
        return {"first_half_pnl": 0.0, "second_half_pnl": 0.0, "both_negative": False, "n_first": 0, "n_second": 0}
    ordered = sorted(replays, key=lambda r: r["entry_ts_et"])
    mid = len(ordered) // 2
    first, second = ordered[:mid] if mid > 0 else ordered[:1], ordered[mid:] if mid > 0 else ordered[1:]
    first_pnl = round(sum(r["pnl"] for r in first), 2)
    second_pnl = round(sum(r["pnl"] for r in second), 2)
    return {
        "first_half_pnl": first_pnl, "second_half_pnl": second_pnl,
        "n_first": len(first), "n_second": len(second),
        "both_negative": first_pnl < 0 and second_pnl < 0,
    }


def cohort_stats(replays: list[dict], n_missing: int) -> dict:
    pnls = [r["pnl"] for r in replays]
    n = len(pnls)
    total = round(sum(pnls), 2)
    wins = sum(1 for p in pnls if p > 0)
    remainder, remainder_pos = drop_top1(pnls)
    by_day: dict = {}
    for r in replays:
        by_day[r["date"]] = round(by_day.get(r["date"], 0.0) + r["pnl"], 2)
    top3 = sorted(by_day.values(), reverse=True)[:3]
    top3_pct = round(sum(top3) / total * 100.0, 1) if total else None
    n_structure_fired = sum(1 for r in replays if r.get("structure_fired"))
    split = half_split_stability(replays)
    return {
        "n": n, "n_missing_bars": n_missing,
        "win_rate": round(wins / n, 4) if n else 0.0,
        "total_pnl": total,
        "expectancy_per_trade": round(total / n, 2) if n else 0.0,
        "drop_top1_remainder": remainder, "drop_top1_positive": remainder_pos,
        "top3_day_pct_of_net": top3_pct,
        "n_structure_fired": n_structure_fired,
        "half_split": split,
        "by_day_pnl": by_day,
        "trades": sorted(replays, key=lambda r: r["entry_ts_et"]),
    }


def grade(stats: dict) -> dict:
    n = stats["n"]
    if n < N_FLOOR:
        return {"verdict": "RETEST-INSUFFICIENT-N", "n": n, "n_floor": N_FLOOR,
                "note": f"n={n} < floor={N_FLOOR}: no verdict forced either way."}
    cond_total_pos = stats["total_pnl"] > 0
    cond_stable = not stats["half_split"]["both_negative"]
    cond_drop_top1 = stats["drop_top1_positive"]
    all_pass = cond_total_pos and cond_stable and cond_drop_top1
    return {
        "verdict": "RETIRE" if all_pass else "KEEP",
        "n": n, "n_floor": N_FLOOR,
        "condition_total_positive": cond_total_pos,
        "condition_half_split_not_both_negative": cond_stable,
        "condition_drop_top1_positive": cond_drop_top1,
    }


def main() -> int:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    print(f"[bull-requal] prereg loaded: {preg['study']} v{preg['version']}", flush=True)

    spy_df = pd.read_csv(SPY_CSV)
    vix_df = pd.read_csv(VIX_CSV)

    print(f"[bull-requal] running BASE (both gates ON, ATM strike)...", flush=True)
    base = run_backtest(spy_df, vix_df, start_date=START, end_date=END,
                        **_prod_cfg(block_elite_bull=True, block_bull_1100_1200=True))
    print(f"[bull-requal] running UNBLOCK_ELITE (block_elite_bull OFF)...", flush=True)
    unblock_elite = run_backtest(spy_df, vix_df, start_date=START, end_date=END,
                                 **_prod_cfg(block_elite_bull=False, block_bull_1100_1200=True))
    print(f"[bull-requal] running UNBLOCK_1100 (block_bull_1100_1200 OFF)...", flush=True)
    unblock_1100 = run_backtest(spy_df, vix_df, start_date=START, end_date=END,
                                **_prod_cfg(block_elite_bull=True, block_bull_1100_1200=False))

    elite_added = added_bull_cohort(base, unblock_elite)
    b1100_added = added_bull_cohort(base, unblock_1100)
    print(f"[bull-requal] base n={len(base.trades)} elite_added={len(elite_added)} "
          f"b1100_added={len(b1100_added)}", flush=True)

    def _requalify_all(trades):
        replays, missing = [], 0
        for t in trades:
            r = requalify_trade(t)
            if r is None:
                missing += 1
            else:
                replays.append(r)
        return replays, missing

    elite_replays, elite_missing = _requalify_all(elite_added)
    b1100_replays, b1100_missing = _requalify_all(b1100_added)

    elite_stats = cohort_stats(elite_replays, elite_missing)
    b1100_stats = cohort_stats(b1100_replays, b1100_missing)

    elite_grade = grade(elite_stats)
    b1100_grade = grade(b1100_stats)

    out = {
        "_doc": "bull_gate_atm_ssb_requalification -- the OWED OP-16 re-eval at ATM strike + "
                "SS-B/RIBBON_RIDE exit shape. Executed against the frozen "
                "bull-requalification-prereg-2026-07-22.json. ANALYSIS ONLY.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "window": [START.isoformat(), END.isoformat()],
        "strike_offset": STRIKE_OFFSET_ATM,
        "exit_shape_used": RIBBON_RIDE_SHAPE,
        "base_trade_count": len(base.trades),
        "block_elite_bull": {
            "added_cohort_n_raw": len(elite_added),
            "stats": elite_stats,
            "grade": elite_grade,
        },
        "block_bull_1100_1200": {
            "added_cohort_n_raw": len(b1100_added),
            "stats": b1100_stats,
            "grade": b1100_grade,
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[bull-requal] wrote {OUT_JSON}", flush=True)
    print(f"[bull-requal] block_elite_bull: n={elite_stats['n']} total=${elite_stats['total_pnl']} "
          f"verdict={elite_grade['verdict']}", flush=True)
    print(f"[bull-requal] block_bull_1100_1200: n={b1100_stats['n']} total=${b1100_stats['total_pnl']} "
          f"verdict={b1100_grade['verdict']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
