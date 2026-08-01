"""bull_gate_f5class_requal_2026_08_01.py -- WEEKEND-TWELVE Next-Twelve #2: block_elite_bull
re-qualification on the f5=require (ribbon BULL-stacked) subclass.

FROZEN PRE-REG: analysis/recommendations/bull-gate-f5class-requal-prereg-2026-08-01.json,
committed beaa7ba8 (et_clock 2026-08-01 14:14:45 Saturday EDT) BEFORE this file existed.
Every convention below (gates, n floor, cell definitions, scope lock) is read FROM that
file, not re-derived here -- this docstring restates it for a reader who opens this file
first, but the prereg is the source of truth on any conflict.

WHY THIS EXISTS: shelf_hold_reclaim_study.py (WS5, 2026-08-01) found F5 (ribbon BULL-stacked
at entry) is the strongest post-hoc separator on its OWN independent shelf/geometry detector
-- C_cross|f5=require|CONTROL: n=168, +$5,447 total, +$32.4/tr, positive in every window
including held-out (+$1,254). WS5's own conclusion: "the money lane is re-qualifying
block_elite_bull under its own written condition, not wiring a new admission geometry." This
script tests that claim DIRECTLY on the PRODUCTION block_elite_bull refused cohort (gates.py
tier=='ELITE' + 'level_reclaim' in triggers + Safe VIX band [0,25)) -- a different, though
structurally related, population from WS5's own geometry detector.

FILENAME COLLISION (disclosed in the prereg's filename_collision_disclosure block): the
synthesis (WEEKEND-TWELVE-2026-08-01.md line 88) suggested 'bull_gate_atm_ssb_requalification.py'
as this study's harness. That file already exists -- a different, already-shipped 2026-07-22
study (window 2026-05-21..2026-07-17, no F5 classification, its own frozen prereg). This repo's
standing convention is one uniquely-dated script per study (every 2026-08-01 lane did this);
overwriting a prior lane's runner would corrupt ITS reproducibility trail. This file is the
non-colliding replacement; the elite-bull requal LINEAGE's mining/replay machinery is reused
(imported: added_bull_cohort-style diff, walk_exit_manager wiring, N_FLOOR=20, drop-best,
elite_bull_postfix_requal's already-mined post-fix cohort) -- not the stale filename.

METHOD (two cells, DIFFERENT mining methods, per the prereg's honest disclosure):

  Cell A (full-391 population, 2025-01-02..2026-07-31): Method A, backtest simulation.
    run_backtest(use_real_fills=True) twice -- BASE (block_elite_bull=True, production) and
    UNBLOCK_ELITE (block_elite_bull=False) -- current ATM strike + current Safe gate stack
    (elite_bear_level_reject_gate_ab.SAFE_BASE, the field-reconciled config
    engine_fullhist_replay.py itself uses) held fixed across the window. Added cohort =
    trades in UNBLOCK_ELITE not in BASE, side=='C'. DISCLOSED: run_backtest's ELITE/
    level_reclaim trigger sources levels from lib.levels._detect_from_history (backtest-
    native, retro-computed from price history, cached per LevelSet) -- NOT the live
    refresh_levels_intraday.py/key-levels.json pipeline that had the IEX/SIP bug fixed
    2026-07-27. Cell A therefore tests STRUCTURAL GENERALIZATION across history, not
    literally "under the corrected feed" -- that is Cell B.

  Cell B (post-fix era, 2026-07-28..2026-07-31): Method B, reclassify already-mined trades.
    Reuses analysis/recommendations/elite-bull-requal-2026-07-31.json's ALREADY-COMMITTED
    decision-log-mined cohort (safe_per_event_qty3/qty10, n=10 events, mined from
    automation/state/core-decisions.jsonl action==SKIP_ELITE_BULL_LEVEL_RECLAIM, full E1/E2/
    E3/F1 exclusion ladder already applied, already replayed through walk_exit_manager at the
    live RIBBON_RIDE CONTROL shape). f5 is computed POST-HOC on each trade's logged
    entry_ts_et -- no re-mining, no re-walk, only a new classification label. This IS a
    genuine "under the corrected feed" population (real engine refusals logged live during
    the levels-compiler-v2 era).

FRAME DISCIPLINE (C6, DST look-ahead -- lib/et_frame.py): Cell A's window crosses two winters
(~129/391 days EST). SPY/VIX are pre-parsed et-v2 (parse_timestamp_et(frame='et-v2')) BEFORE
being handed to run_backtest -- already-parsed datetime input passes through orchestrator's
own internal pd.to_datetime() calls as a no-op (et_frame.py's own documented guarantee), so
et-v2 correctness propagates through RTH slicing, level detection, and ribbon computation.
_align_vix_to_spy's internal pd.to_datetime(..., utc=True) mis-tags naive et-v2 wall time as
UTC, but ONLY as a same-row alignment key on BOTH sides consistently (index discarded right
after) -- harmless. HOWEVER: run_backtest's own use_real_fills entry-premium/dollar_pnl and
lib.option_pricing_real.load_contract_bars both do PLAIN pd.to_datetime() (no utc=True, no
frame) on OPRA bars -- wall-v1, mislabeled for winter dates. This script therefore NEVER
trusts run_backtest's own entry_premium/dollar_pnl (discarded, same doctrine as
engine_fullhist_replay.py/bull_gate_atm_ssb_requalification.py): entry premium AND the exit
walk both use an independently-built et-v2-parsed option loader (mirrors
shelf_hold_reclaim_study.load_opt_et2 exactly). DISCLOSED residual risk: run_backtest's own
use_real_fills ADMISSION gate (whether a trade enters the cohort AT ALL) may consult
wall-v1-parsed option data internally for winter dates -- could rarely admit/exclude a winter
trade at the margin differently than a fully et-v2-native pipeline. Not expected to be
material (DST-window trades are ~1/3 of the population; this affects admission only, never
the P&L math of admitted trades, which is always independently et-v2-derived here).

Rail-4 CLEAR: analysis only. Does not edit params.json/aggressive/params.json. No live network
reads (real OPRA cache only; missing contracts dropped and counted, never imputed -- C7).

Run: backtest/.venv/Scripts/python.exe backtest/tools/bull_gate_f5class_requal_2026_08_01.py
     [--smoke]   last 10 sessions of Cell A only (mechanism check), writes to a .smoke.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]              # backtest/
ROOT = REPO.parent                                        # repo root
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(ROOT / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import elite_bear_level_reject_gate_ab as eb  # noqa: E402  -- SAFE_BASE, field-reconciled prod config
import strategies as fleet_strategies  # noqa: E402  -- automation/state/fleet/strategies.py
from lib.et_frame import parse_timestamp_et  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.orchestrator import run_backtest, BacktestResult  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

DATA = REPO / "data"
OLD_SPY = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
NEW_SPY = DATA / "spy_5m_2026-05-19_2026-07-31.csv"
OLD_VIX = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
NEW_VIX = DATA / "vix_5m_2026-05-19_2026-07-31.csv"
OPT_DIR = DATA / "options"

FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 31)
EXPECTED_DAYS = 391
HALF_DAYS = {dt.date(2025, 7, 3), dt.date(2025, 11, 28), dt.date(2025, 12, 24)}

POSTFIX_START = dt.date(2026, 7, 28)
POSTFIX_END = dt.date(2026, 7, 31)

TIME_STOP_ET = dt.time(15, 40)     # live Safe params.json time_stop_et
ENTRY_PREMIUM_FLOOR = 0.30         # params.json min_entry_premium
N_FLOOR = 20                        # OP-16's own evidence_n bar (prereg gates.n_floor)
STRIKE_OFFSET_ATM = 0

PREREG = ROOT / "analysis" / "recommendations" / "bull-gate-f5class-requal-prereg-2026-08-01.json"
POSTFIX_SOURCE = ROOT / "analysis" / "recommendations" / "elite-bull-requal-2026-07-31.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "bull-gate-f5class-requal-2026-08-01.json"
SMOKE_JSON = ROOT / "analysis" / "recommendations" / "bull-gate-f5class-requal-2026-08-01.smoke.json"

# Single delta from eb.SAFE_BASE: refresh initial_equity to the most current live-verified
# figure (CLAUDE.md Account context, 2026-07-11) -- SAME pattern engine_fullhist_replay.py
# uses (SAFE_BASE_LIVE = dict(eb.SAFE_BASE, initial_equity=1746.75)).
SAFE_BASE_LIVE = dict(eb.SAFE_BASE, initial_equity=1746.75)


def log(msg: str) -> None:
    print(f"[f5class-requal] {msg}", flush=True)


def _prod_cfg(*, block_elite_bull: bool) -> dict:
    """Current production Safe gate stack, ONE key toggled. block_bull_1100_1200 (a
    DIFFERENT gate) stays at its production value (True) -- out of scope per the prereg's
    scope_lock (conflating two gates in one BH-FDR family would blur both)."""
    return dict(SAFE_BASE_LIVE, block_elite_bull=block_elite_bull)


# ================================================================== et-v2 data (C6 discipline)
def _load_csv_et2(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp_et"] = parse_timestamp_et(df["timestamp_et"], frame="et-v2")
    return df


def load_merged(old_path: Path, new_path: Path, tail_after: dt.date = dt.date(2026, 7, 22)) -> pd.DataFrame:
    """OLD file + strictly-after-`tail_after` tail of NEW file, et-v2 parsed (shelf_hold_
    reclaim_study.load_merged convention, byte-identical population lineage)."""
    old = _load_csv_et2(old_path)
    new = _load_csv_et2(new_path)
    tail = new[new["timestamp_et"].dt.date > tail_after]
    out = (pd.concat([old, tail], ignore_index=True)
             .sort_values("timestamp_et").reset_index(drop=True))
    return out.drop_duplicates(subset="timestamp_et").reset_index(drop=True)


def build_rth(spy_df: pd.DataFrame) -> pd.DataFrame:
    mask = ((spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
            & (spy_df["timestamp_et"].dt.time < dt.time(16, 0)))
    return spy_df.loc[mask].reset_index(drop=True)


_OPT_CACHE: dict[str, Optional[pd.DataFrame]] = {}


def option_symbol(day: dt.date, strike: int, side: str = "C") -> str:
    return f"SPY{day.strftime('%y%m%d')}{side}{strike * 1000:08d}"


def load_opt_et2(symbol: str) -> Optional[pd.DataFrame]:
    """et-v2-parsed cached OPRA contract bars (mirrors shelf_hold_reclaim_study.load_opt_et2
    exactly). NEVER lib.option_pricing_real.load_contract_bars, which does plain (wall-v1)
    pd.to_datetime with no frame handling -- would misalign entry/exit timestamps against
    this script's et-v2 SPY frame on winter dates."""
    if symbol in _OPT_CACHE:
        return _OPT_CACHE[symbol]
    path = OPT_DIR / f"{symbol}.csv"
    if not path.exists():
        _OPT_CACHE[symbol] = None
        return None
    df = pd.read_csv(path)
    df["timestamp_et"] = parse_timestamp_et(df["timestamp_et"], frame="et-v2")
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    _OPT_CACHE[symbol] = df
    return df


# ================================================================== cohort mining (Method A)
def _et_naive(ts) -> dt.datetime:
    p = pd.Timestamp(ts)
    if p.tzinfo is not None:
        p = p.tz_localize(None)
    return p.to_pydatetime()


def _trade_key(t) -> tuple:
    return (_et_naive(t.entry_time_et), t.side, round(float(t.strike), 2))


def added_bull_cohort(base: BacktestResult, unblock: BacktestResult) -> list:
    """Trades present in `unblock` (block_elite_bull=False) but not `base` (block_elite_bull=
    True), side=='C' only -- exactly what block_elite_bull alone refuses, net of every other
    gate (both runs share the identical production value for every other gate). Ported
    verbatim from bull_gate_atm_ssb_requalification.py (2026-07-22)."""
    base_keys = {_trade_key(t) for t in base.trades}
    return [t for t in unblock.trades if t.side == "C" and _trade_key(t) not in base_keys]


# ================================================================== f5 classification
def build_ribbon_lookup(spy_rth_et2: pd.DataFrame) -> pd.DataFrame:
    """Continuous ribbon 'stack' series over the full et-v2 RTH close series, keyed by
    timestamp_et for backward as-of lookup. Identical method to shelf_hold_reclaim_study.py's
    f5_bull (stack_arr[g] == 'BULL', same compute_ribbon call, same warmup/continuity)."""
    ribbon_df = compute_ribbon(spy_rth_et2["close"].reset_index(drop=True))
    lookup = spy_rth_et2[["timestamp_et"]].copy().reset_index(drop=True)
    lookup["stack"] = ribbon_df["stack"].values
    return lookup.sort_values("timestamp_et").reset_index(drop=True)


def classify_f5(entry_times: list, ribbon_lookup: pd.DataFrame) -> list[bool]:
    """Backward (no look-ahead) merge_asof of each entry_time_et onto the continuous ribbon
    stack series. True iff stack == 'BULL' at (or immediately before) entry."""
    left = pd.DataFrame({"timestamp_et": pd.to_datetime(entry_times)})
    merged = pd.merge_asof(left.sort_values("timestamp_et"), ribbon_lookup,
                            on="timestamp_et", direction="backward")
    # merge_asof requires sorted input; restore original order via a stable index round-trip
    merged = merged.set_index(left.sort_values("timestamp_et").index).sort_index()
    return (merged["stack"] == "BULL").tolist()


# ================================================================== exit re-walk (Cell A)
RIBBON_RIDE_SHAPE = fleet_strategies.RIBBON_RIDE.exit.to_dict()


def build_day_frames(spy_rth_et2: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per-day RTH SPY slices keyed by ISO date string, built once (day_frames convention
    shared by shelf_hold_reclaim_study.py) -- avoids an O(n_trades x n_total_bars) boolean
    mask per requalify_trade() call."""
    out: dict[str, pd.DataFrame] = {}
    for d, grp in spy_rth_et2.groupby(spy_rth_et2["timestamp_et"].dt.date, sort=True):
        out[d.isoformat()] = grp.reset_index(drop=True)
    return out


def requalify_trade(t, ribbon_lookup: pd.DataFrame, day_frames: dict[str, pd.DataFrame]) -> Optional[dict]:
    """Re-derive entry premium AND re-walk the exit through the REAL exit_manager core at the
    live SS-B/RIBBON_RIDE shape, using an independently et-v2-parsed option DataFrame for
    BOTH (run_backtest's own entry_premium/dollar_pnl is discarded -- see module docstring's
    FRAME DISCIPLINE section). Returns None (dropped, counted in n_missing_bars) if the
    contract isn't cached, has no bar at/after the entry tick, or the trade's day has no RTH
    SPY frame (C7 -- never imputed)."""
    entry_ts = _et_naive(t.entry_time_et)
    date = entry_ts.date()
    day_key = date.isoformat()
    five_min_spy_df = day_frames.get(day_key)
    if five_min_spy_df is None or five_min_spy_df.empty:
        return None
    strike = int(round(t.strike))
    symbol = option_symbol(date, strike, "C")
    opt_df = load_opt_et2(symbol)
    if opt_df is None or opt_df.empty:
        return None
    after = opt_df[opt_df["timestamp_et"] >= pd.Timestamp(entry_ts)]
    if after.empty:
        return None
    fill = after.iloc[0]
    entry_premium = float(fill["open"])
    if entry_premium <= 0 or entry_premium < ENTRY_PREMIUM_FLOOR:
        return None
    fill_ts = pd.Timestamp(fill["timestamp_et"]).to_pydatetime()

    res = walk_exit_manager(
        symbol=symbol, side="C", entry_time_et=fill_ts,
        entry_premium=entry_premium, qty=int(t.qty),
        exit_shape=RIBBON_RIDE_SHAPE, structure_stop_enabled=True,
        trigger_level=float(t.rejection_level) if t.rejection_level is not None else None,
        strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
        opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=five_min_spy_df)
    if res.exit_time_et is None:
        return None   # fill landed on the day's last bar -- unwalkable, dropped not zeroed (C7)

    f5_bull = classify_f5([fill_ts], ribbon_lookup)[0]

    return {
        "date": date.isoformat(), "entry_ts_et": fill_ts.isoformat(),
        "strike": strike, "entry_premium": round(entry_premium, 4), "qty": int(t.qty),
        "triggers_fired": list(t.triggers_fired or []),
        "trigger_level": t.rejection_level,
        "pnl": round(res.dollar_pnl, 2), "exit_reason": res.exit_reason,
        "exit_time_et": res.exit_time_et.isoformat() if res.exit_time_et else None,
        "hold_minutes": res.hold_minutes,
        "f5_bull": bool(f5_bull),
    }


# ================================================================== stats (shared vocabulary,
# ported verbatim from shelf_hold_reclaim_study.py so BOTH lanes' p-values/BH-FDR are computed
# identically and remain directly comparable to WS5's own numbers)
def one_sample_p(pnls: list[float]) -> float:
    n = len(pnls)
    if n < 2:
        return 1.0
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    se = (var / n) ** 0.5
    if se == 0:
        return 1.0
    tstat = mean / se
    return max(0.0, min(1.0, 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(tstat) / (2 ** 0.5))))))


def bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    max_k = -1
    for rank, i in enumerate(order):
        if pvals[i] <= (rank + 1) / m * q:
            max_k = rank
    sig = [False] * m
    for rank, i in enumerate(order):
        sig[i] = rank <= max_k
    return sig


def drop_best(pnls: list[float]) -> tuple[float, bool]:
    """Total minus the single largest-winning TRADE (trade-level, not day-level). Only drops
    an actual WINNER (pnl > 0) -- bull_gate_atm_ssb_requalification.drop_top1's exact
    semantics (its own guard test pins this: an all-losing cohort's drop-best equals its raw
    total, never a 'least-bad-loser-removed' number, since there is no single-trade-luck
    story to strip out of a cohort with zero wins). NOTE: this differs from shelf_hold_
    reclaim_study.lane_stats.drop_best, which drops max(pnls) unconditionally (even when
    negative) -- deliberately NOT followed here; bull_gate_atm_ssb_requalification.py is the
    more directly-cited lineage for this exact gate-family and its convention is the more
    semantically correct one for what this check is trying to measure."""
    if not pnls:
        return 0.0, False
    winners = [p for p in pnls if p > 0]
    if not winners:
        total = sum(pnls)
        return round(total, 2), total > 0
    remainder = sum(pnls) - max(winners)
    return round(remainder, 2), remainder > 0


def day_majority(trades: list[dict]) -> dict:
    by_day: dict[str, float] = {}
    for t in trades:
        by_day[t["date"]] = by_day.get(t["date"], 0.0) + t["pnl"]
    win_days = sum(1 for v in by_day.values() if v > 0)
    days = len(by_day)
    return {"win_days": win_days, "days": days,
            "is_majority": (win_days > days / 2.0) if days else None}


def recent_25_slice(trades: list[dict], recent_start: Optional[str]) -> list[dict]:
    if recent_start is None:
        return list(trades)   # whole cell IS the recent window (Cell B, per prereg g4 text)
    return [t for t in trades if t["date"] >= recent_start]


def cell_stats(trades: list[dict], n_missing: int, recent_start: Optional[str]) -> dict:
    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    total = round(sum(pnls), 2)
    remainder, remainder_pos = drop_best(pnls)
    recent = recent_25_slice(trades, recent_start)
    recent_total = round(sum(t["pnl"] for t in recent), 2)
    by_day: dict[str, float] = {}
    for t in trades:
        by_day[t["date"]] = round(by_day.get(t["date"], 0.0) + t["pnl"], 2)
    top_day_share = (round(max(by_day.values()) / total, 3)
                      if (total and by_day) else None)
    return {
        "n": n, "n_missing_bars": n_missing,
        "win_rate": round(sum(1 for p in pnls if p > 0) / n, 4) if n else 0.0,
        "total_pnl": total,
        "expectancy_per_trade": round(total / n, 2) if n else 0.0,
        "p_value_raw": round(one_sample_p(pnls), 5),
        "day_majority": day_majority(trades),
        "drop_best": {"remainder": remainder, "still_positive": remainder_pos},
        "recent_25": {"start": recent_start, "n": len(recent), "total_pnl": recent_total,
                      "collapsed_whole_cell": recent_start is None},
        "concentration_top_day_share": top_day_share,
        "by_day_pnl": by_day,
        "trades": sorted(trades, key=lambda t: t["entry_ts_et"]),
    }


def grade_cell(stats: dict) -> dict:
    """Verdict tiers per the prereg's verdict_routing.reporting_tiers -- EVIDENCE, not a
    ship/arm action (this study never flips Safe's gate)."""
    n = stats["n"]
    if n < N_FLOOR:
        return {"tier": "UNDERPOWERED", "n": n, "n_floor": N_FLOOR,
                "note": f"n={n} < floor={N_FLOOR}: reported, not verdict-bearing."}
    g1 = stats["total_pnl"] > 0
    g2 = bool(stats["day_majority"]["is_majority"])
    g3 = bool(stats["drop_best"]["still_positive"])
    g4 = stats["recent_25"]["total_pnl"] >= 0
    if not g1:
        tier = "EVIDENCE_AGAINST"
    elif (g2 or g3) and g4:
        tier = "EVIDENCE_FOR_REEVAL"
    else:
        tier = "MIXED"
    return {"tier": tier, "n": n, "n_floor": N_FLOOR,
            "g1_positive_aggregate": g1, "g2_day_majority": g2,
            "g3_drop_best": g3, "g4_recent25_first_class": g4}


# ================================================================== Cell B (post-fix reuse)
def load_postfix_trades(ribbon_lookup: pd.DataFrame) -> dict:
    """Reclassify the ALREADY-MINED, ALREADY-COMMITTED post-fix cohort from
    elite-bull-requal-2026-07-31.json by f5 -- no re-mining, no re-walk (Method B, per the
    prereg). Returns {'qty3': {...}, 'qty10': {...}} each split into require/drop trade lists."""
    src = json.loads(POSTFIX_SOURCE.read_text(encoding="utf-8"))
    out: dict = {}
    for qty_key, cohort_key in (("qty3", "safe_per_event_qty3"), ("qty10", "safe_per_event_qty10")):
        cohort = src["cohorts"][cohort_key]
        entry_times = [pd.Timestamp(t["entry_ts_et"]) for t in cohort["trades"]]
        f5_flags = classify_f5(entry_times, ribbon_lookup)
        require_trades, drop_trades = [], []
        for t, f5 in zip(cohort["trades"], f5_flags):
            row = {
                "date": t["date"], "entry_ts_et": t["entry_ts_et"], "strike": t["strike"],
                "entry_premium": t["entry_premium"], "qty": t["qty"], "pnl": t["pnl"],
                "exit_reason": t["exit_reason"], "f5_bull": bool(f5),
            }
            drop_trades.append(row)
            if f5:
                require_trades.append(row)
        out[qty_key] = {"require": require_trades, "drop": drop_trades,
                        "source": str(POSTFIX_SOURCE.relative_to(ROOT)).replace("\\", "/"),
                        "source_cohort": cohort_key}
    return out


# ================================================================== main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    log(f"prereg loaded: {PREREG.name}")

    control_shape = fleet_strategies.RIBBON_RIDE.exit.to_dict()
    assert control_shape == fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    log(f"CONTROL shape (registry byte-identical): {json.dumps(control_shape)}")

    log("loading SPY/VIX merged frames (et-v2)")
    spy_raw = load_merged(OLD_SPY, NEW_SPY)
    vix_raw = load_merged(OLD_VIX, NEW_VIX)
    spy_rth = build_rth(spy_raw)
    all_days = [d for d in sorted(spy_rth["timestamp_et"].dt.date.unique())
                if FULL_START <= d <= FULL_END and d not in HALF_DAYS]
    log(f"population: {len(all_days)} RTH sessions {all_days[0]}..{all_days[-1]} "
        f"(expected {EXPECTED_DAYS})")
    if len(all_days) != EXPECTED_DAYS:
        log("FATAL: population != the verified 391 -- aborting before any cell is computed")
        return 1
    recent_start = all_days[-25].isoformat()
    log(f"recent-25 start (Cell A): {recent_start}")

    if args.smoke:
        run_start, run_end = all_days[-10], all_days[-1]
        log(f"SMOKE MODE: restricting Cell A run to {run_start}..{run_end}")
    else:
        run_start, run_end = FULL_START, FULL_END

    log("precomputing ribbon lookup (continuous et-v2 RTH close series)")
    ribbon_lookup = build_ribbon_lookup(spy_rth)
    day_frames = build_day_frames(spy_rth)

    log("running BASE (block_elite_bull=True, production)...")
    base = run_backtest(spy_raw, vix_raw, start_date=run_start, end_date=run_end,
                        **_prod_cfg(block_elite_bull=True))
    log("running UNBLOCK_ELITE (block_elite_bull=False)...")
    unblock = run_backtest(spy_raw, vix_raw, start_date=run_start, end_date=run_end,
                           **_prod_cfg(block_elite_bull=False))

    elite_added = added_bull_cohort(base, unblock)
    log(f"base n={len(base.trades)} unblock n={len(unblock.trades)} elite_added={len(elite_added)}")

    replays, n_missing = [], 0
    for t in elite_added:
        r = requalify_trade(t, ribbon_lookup, day_frames)
        if r is None:
            n_missing += 1
        else:
            replays.append(r)
    log(f"cell_A requalified n={len(replays)} n_missing={n_missing}")

    cell_a_require = [r for r in replays if r["f5_bull"]]
    cell_a_drop = replays

    cell_a_require_pf = [r for r in cell_a_require if r["date"] >= POSTFIX_START.isoformat()]

    log("reclassifying Cell B (post-fix, already-mined) by f5...")
    postfix = load_postfix_trades(ribbon_lookup)

    cells = {
        "cell_A_full391_f5_require": cell_stats(cell_a_require, n_missing if not args.smoke else 0, recent_start),
        "cell_A_full391_f5_drop": cell_stats(cell_a_drop, n_missing if not args.smoke else 0, recent_start),
        "cell_B_postfix_f5_require_qty3": cell_stats(postfix["qty3"]["require"], 0, None),
        "cell_B_postfix_f5_drop_qty3": cell_stats(postfix["qty3"]["drop"], 0, None),
        "cell_B_postfix_f5_require_qty10": cell_stats(postfix["qty10"]["require"], 0, None),
        "cell_B_postfix_f5_drop_qty10": cell_stats(postfix["qty10"]["drop"], 0, None),
    }

    # BH-FDR family per the prereg (g5): cell_A{require,drop} + cell_B{require,drop} at qty3
    # (qty3 is PRIMARY sizing per elite-bull-requal-prereg-2026-07-31.json; qty10 reported as
    # a sensitivity cell, excluded from the formal family -- disclosed, matches the prereg text).
    bh_family_keys = ["cell_A_full391_f5_require", "cell_A_full391_f5_drop",
                       "cell_B_postfix_f5_require_qty3", "cell_B_postfix_f5_drop_qty3"]
    pvals = [cells[k]["p_value_raw"] for k in bh_family_keys]
    sig = bh_fdr(pvals, q=0.10)
    for k, s in zip(bh_family_keys, sig):
        cells[k]["bh_fdr_significant_q10"] = bool(s)
    for k in cells:
        cells[k].setdefault("bh_fdr_significant_q10", None)   # qty10 sensitivity cells: N/A

    grades = {k: grade_cell(cells[k]) for k in cells}

    out = {
        "_doc": "bull_gate_f5class_requal_2026_08_01 -- block_elite_bull re-qualification on "
                "the f5=require (ribbon BULL-stacked) subclass. EVIDENCE for Safe's scheduled "
                "forward re-eval trigger ONLY -- does not flip Safe's gate. ANALYSIS ONLY.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "smoke": bool(args.smoke),
        "cell_A_window": [run_start.isoformat(), run_end.isoformat()],
        "cell_A_n_sessions_population": len(all_days),
        "cell_A_recent_25_start": recent_start,
        "cell_B_window": [POSTFIX_START.isoformat(), POSTFIX_END.isoformat()],
        "cell_B_source": str(POSTFIX_SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "strike_offset": STRIKE_OFFSET_ATM,
        "exit_shape_used": control_shape,
        "base_trade_count": len(base.trades),
        "unblock_elite_trade_count": len(unblock.trades),
        "elite_added_raw_n": len(elite_added),
        "cell_A_postfix_overlap_n_require": len(cell_a_require_pf),
        "n_floor": N_FLOOR,
        "bh_fdr_family": bh_family_keys,
        "cells": cells,
        "grades": grades,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    dest = SMOKE_JSON if args.smoke else OUT_JSON
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {dest}")
    for k in cells:
        log(f"  {k}: n={cells[k]['n']} total=${cells[k]['total_pnl']} "
            f"tier={grades[k]['tier']}")
    log(f"runtime {out['runtime_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
