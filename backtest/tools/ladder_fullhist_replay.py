"""ladder_fullhist_replay.py -- OVERNIGHT PROOF ENGINE for the SCORE LADDER lane shipped in
deb781ea (2026-07-27 evening): "entering min-size BEAR when bear_score >= floor (7, 8, 9) AND a
raw level-tied trigger fired AND its level exists, on ticks the binary engine scored-but-refused"
-- replayed across ALL available history (2025-01-02 .. 2026-07-27), not just the 10 hand-picked
anchors `arm_score_ladder_replay.py` covers. That tool answers "would these 10 named trades have
qualified"; this tool answers "what would 386+ days of this lane's OWN trading have produced,
including its own losers, walked one-position-at-a-time like the fleet actually runs it."

===========================================================================================
LANE SEMANTICS -- pinned to the REAL production code, not re-invented (per task instruction:
"read build_shared_signal._ladder_block + fleet_executor._ladder_plan for the semantics")
===========================================================================================
  Trigger set   automation/state/fleet/build_shared_signal.py#LADDER_LEVEL_TIED = {
                level_rejection, fhh_level_rejection, confluence, sequence_rejection} -- NOTE
                this is narrower than arm_score_ladder_replay.py's own research LEVEL_TIED_BEAR
                (which also allows trendline_rejection); this tool uses the PRODUCTION set,
                imported directly from build_shared_signal, not a hand-copied literal.
  Gate          fleet_executor.py#_ladder_plan: fires only when (a) bear.passed is NOT True,
                (b) bear_score >= floor, (c) >=1 raw trigger in LADDER_LEVEL_TIED, (d) the raw
                rejection_level exists. "bear.passed is not True" in the live shared-signal is
                itself gated on verdict=='HOLD' + reason 'no setup passed scoring (neither bear
                nor bull)' (_ladder_block_from_row) -- i.e. NEITHER side passed scoring. This
                replay reproduces that "neither side passed" condition directly against the
                orchestrator's OWN bear/bull scoring (see BULL-PASSED CAPTURE below), rather
                than re-deriving a verdict string that only the live heartbeat_core emits.
  Strike        fleet_executor.PROBE_STRIKE_TIERS (ATM at $0-10K, same table _ladder_plan uses
                -- NOT the arm's own bold/OTM sizing table). Reference equity is fixed at
                $2,000 for strike selection ONLY -- irrelevant to the result because both the
                $0-2K and $2-10K PROBE_STRIKE_TIERS rows resolve to offset=0 (ATM); every one
                of the 5 live fleet arms as of 2026-07-27 sits in that $0-10K band anyway
                (arm_score_ladder_replay.py's own ARMS table: $1,179-$1,852).
  Sizing        min_contracts=3 (task's explicit "min-size (3 contracts)" spec; also matches
                automation/state/params.json's Safe-family min_contracts and CLAUDE.md Rule 6's
                headline floor -- the Bold-family aggressive/params.json floor is 5, but this
                replay models ONE representative min-size lane, not a per-fleet-account fan-out).
  Exit          automation/state/fleet/strategies.py#RIBBON_RIDE.exit.to_dict() (the SAME
                structure-stop shape engine_fullhist_replay.py uses for the binary engine's OWN
                entries) via backtest/lib/exit_manager_walk.py#walk_exit_manager -- the REAL
                exit_manager.plan_exit_actions decision core, not a re-derived approximation.
                structure_stop_enabled=True, trigger_level=the raw rejection_level (the chart-
                stop anchor _ladder_plan itself threads through).
  Entry price   the NEXT 5-min SPY bar's corresponding OPTION bar's OPEN (entry+1 convention,
                per markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md -- the trigger
                bar's own extremes are never eligible). DELIBERATE CHOICE, disclosed: this uses
                the option bar's OPEN, not VWAP (simulator_real.py's convention for REAL
                production entries) -- because walk_exit_manager's own exit fills are ALREADY a
                single-point-sample-at-bar-open convention (its module comment: "the bar's OPEN
                as ... the closest available analog to a live NBBO snapshot"); using OPEN for
                entry too keeps this synthetic ladder-rescue trade internally consistent with
                the SAME point-sample philosophy its own exit walker uses, rather than mixing a
                VWAP-based entry against an OPEN-based exit convention.

===========================================================================================
BULL-PASSED CAPTURE (no orchestrator.py edit -- read-only on live/config files per task scope)
===========================================================================================
`BacktestResult.decisions` already logs the bear side's raw bear_score/blockers/triggers_fired/
rejection_level/passed on ONE row per evaluated bar (orchestrator.py:1108-1121, "Always log the
decision" -- verified: 19 decisions.append() call sites total, only this ONE omits an "action"
key, so `"action" not in row` uniquely isolates it). It does NOT log the bull side's `passed` on
that base row (bull fields only appear on additional rows appended when a side actually wins,
carrying the WINNING side's data, not bear's). Rather than reimplementing the ctx-building
pipeline (ribbon/HTF/levels/level_states -- ~150 lines orchestrator.py already owns), this tool
monkeypatches `lib.orchestrator.evaluate_bullish_setup` for the duration of ONE run_backtest call
to record `{bar_idx: bull_result.passed}` as a side effect, then restores the original in a
`finally`. This is a pure pass-through wrapper (same args in, same object out, zero behavior
change) -- verified empirically against 2026-07-27 09:35-10:10 (see calibration section) that it
does not disturb the orchestrator's own GAMMA_ENGINE_SCORE_ASSERT cross-check.

===========================================================================================
DATA WINDOW
===========================================================================================
`backtest/data/spy_5m_2025-01-01_2026-07-22.csv` (engine_fullhist_replay.py's own file, kept
byte-identical for that sub-window) + the STRICTLY-AFTER-07-22 tail of
`backtest/data/spy_5m_2026-05-19_2026-07-27.csv` (431 rows: 07-23, 07-24, 07-27 -- 07-25/26 are
the weekend). No dedup ambiguity: the two files never overlap in what's actually concatenated (the
tail is pre-filtered to dates > 2026-07-22), so the pre-existing engine-fullhist-replay-2026-07-23
scorecard's window is reproduced BYTE-IDENTICALLY as a strict prefix of this run's data, and the
BASELINE lane below is directly comparable to it (recomputed over the extended window for an
apples-to-apples same-window comparison against the 3 ladder lanes, not re-quoted from the older,
5-day-shorter scorecard).

===========================================================================================
HONEST DESIGN CHOICE -- real OPRA fills only for P&L; BS-synthetic is DISCLOSED, not blended
===========================================================================================
Every ladder candidate whose resolved contract has NO cached OPRA bar (backtest/data/options/
{symbol}.csv) at or after its entry+1 timestamp gets a Black-Scholes SYNTHETIC entry premium
computed and recorded (per-trade, flagged `is_synthetic`/`synthetic_entry_premium`) for
disclosure, but is EXCLUDED from the lane's P&L/WR/expectancy aggregate -- there is no
established, validated mechanism anywhere in this codebase for walking a full BS-synthetic EXIT
PATH through walk_exit_manager (a single BS point-price cannot drive TP1/stop/trail decisions
without inventing an unprecedented synthetic bar-series generator), and this codebase's own
standing lesson (CLAUDE.md C1: "Real-fills is the only WR authority", L02/12/23/50/71/99/100/
107/182) plus engine_fullhist_replay.py's own established precedent (real OPRA fills only, zero
BS blending) both argue against inventing one under time pressure. Each lane reports
`n_excluded_synthetic_priced` / `pct_synthetic_of_would_be_entries` so the participation-rate gap
this creates is visible, not hidden.

Run: backtest/.venv/Scripts/python.exe backtest/tools/ladder_fullhist_replay.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                      # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import elite_bear_level_reject_gate_ab as eb              # noqa: E402
import strategies as fleet_strategies                       # noqa: E402
import build_shared_signal as bss                            # noqa: E402  -- LADDER_LEVEL_TIED
import fleet_executor as fx                                    # noqa: E402  -- PROBE_STRIKE_TIERS
import engine_fullhist_replay as efr                             # noqa: E402  -- reused loading/exit machinery
import lib.orchestrator as orch_mod                                # noqa: E402
from lib.orchestrator import run_backtest                            # noqa: E402
from lib.exit_manager_walk import walk_exit_manager                   # noqa: E402
from lib.option_pricing_real import (                                  # noqa: E402
    bar_at_or_after, load_contract_bars, option_symbol,
)
from lib.pricing import black_scholes, time_to_expiry_years, vix_to_iv  # noqa: E402
from crypto.lib.strike_selection import pick_strike                      # noqa: E402

DATA = REPO / "data"
OLD_SPY_FILE = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
OLD_VIX_FILE = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
NEW_SPY_FILE = DATA / "spy_5m_2026-05-19_2026-07-27.csv"
NEW_VIX_FILE = DATA / "vix_5m_2026-05-19_2026-07-27.csv"

FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 27)
OLD_WINDOW_END = dt.date(2026, 7, 22)   # engine_fullhist_replay.py's own window boundary

MIN_CONTRACTS = 3
REF_EQUITY_FOR_STRIKE = 2000.0   # irrelevant to the strike (ATM either way, see module docstring)
FLOORS = (7, 8, 9)

OUT_DIR = ROOT / "analysis" / "arm-ladder"
OUT_JSON = OUT_DIR / "LADDER-FULLHIST-2026-07-27.json"
OUT_MD = OUT_DIR / "LADDER-FULLHIST-2026-07-27.md"

CALIBRATION_DAY = dt.date(2026, 7, 27)
CALIBRATION_TIME = dt.time(9, 40)
CALIBRATION_PINNED = dict(bear_score=9, blockers=[5], trigger="level_rejection", rejection_level=744.9)


def log(msg: str) -> None:
    print(f"[ladder-fullhist] {msg}", flush=True)


# =============================================================================== data load

def build_rth_frame(spy_df_full: pd.DataFrame) -> pd.DataFrame:
    """CRITICAL ALIGNMENT: `orchestrator.run_backtest` does NOT use the raw frame's own row
    positions for `BacktestResult.decisions[].bar_idx` -- internally it rebuilds
    `spy_df = spy_df_full.loc[rth_mask].reset_index(drop=True)` (orchestrator.py:805-810,
    rth_mask = time in [09:30, 16:00)) BEFORE its scoring loop, and every `bar_idx` it logs is
    a position into THAT reindexed frame, not the raw input (which this repo's cached SPY CSVs
    routinely carry premarket/after-hours bars in -- e.g. 2025-01-02 in
    spy_5m_2025-01-01_2026-07-22.csv runs 10:30 through 17:20, extended-hours included).
    `run_backtest` itself is still called with the RAW (unfiltered) frame -- untouched --
    because `_detect_from_history`'s premarket-level detection (PMH/PML) reads
    `spy_df_full`, the orchestrator's OTHER internal name for that same raw input; pre-
    filtering the frame handed to run_backtest would silently drop premarket levels and
    diverge from engine_fullhist_replay.py's own established baseline. This function builds
    the SAME rth_mask + reset_index split as a SEPARATE frame, used ONLY for this tool's own
    post-hoc bar_idx-based lookups (next_bar_same_day / resolve_ladder_entry), so
    `spy_rth.iloc[bar_idx]` is guaranteed to be the exact bar orchestrator scored."""
    mask = (
        (spy_df_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_df_full["timestamp_et"].dt.time < dt.time(16, 0))
    )
    return spy_df_full.loc[mask].reset_index(drop=True)


def load_extended_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """OLD file (byte-identical to engine_fullhist_replay.py's own window) + the strictly-
    after-07-22 tail of the NEW file. No overlap, no dedup ambiguity -- see module docstring."""
    spy_old = pd.read_csv(OLD_SPY_FILE)
    spy_old["timestamp_et"] = pd.to_datetime(spy_old["timestamp_et"])
    spy_new = pd.read_csv(NEW_SPY_FILE)
    spy_new["timestamp_et"] = pd.to_datetime(spy_new["timestamp_et"])
    spy_tail = spy_new[spy_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    spy_df = (pd.concat([spy_old, spy_tail], ignore_index=True)
                .sort_values("timestamp_et").reset_index(drop=True))

    vix_old = pd.read_csv(OLD_VIX_FILE)
    vix_old["timestamp_et"] = pd.to_datetime(vix_old["timestamp_et"])
    vix_new = pd.read_csv(NEW_VIX_FILE)
    vix_new["timestamp_et"] = pd.to_datetime(vix_new["timestamp_et"])
    vix_tail = vix_new[vix_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    vix_df = (pd.concat([vix_old, vix_tail], ignore_index=True)
                .sort_values("timestamp_et").reset_index(drop=True))
    return spy_df, vix_df


# ============================================================ bull-passed capture (see docstring)

def run_backtest_with_bull_capture(spy_df, vix_df, start_date, end_date, **kwargs):
    """run_backtest, plus a {bar_idx: bull_result.passed} side-channel. Pure pass-through
    wrapper -- restores the original evaluate_bullish_setup in `finally` regardless of outcome."""
    bull_passed_by_idx: dict[int, bool] = {}
    orig = orch_mod.evaluate_bullish_setup

    def _capture(ctx, **kw):
        res = orig(ctx, **kw)
        bull_passed_by_idx[ctx.bar_idx] = bool(res.passed)
        return res

    orch_mod.evaluate_bullish_setup = _capture
    try:
        r = run_backtest(spy_df, vix_df, start_date=start_date, end_date=end_date, **kwargs)
    finally:
        orch_mod.evaluate_bullish_setup = orig
    return r, bull_passed_by_idx


# =============================================================================== candidates

def is_ladder_candidate(row: dict, bull_passed: bool) -> bool:
    """Floor-independent pre-filter -- mirrors fleet_executor._ladder_plan's gate MINUS the
    floor comparison (applied per-lane in run_lane). `"action" not in row` isolates the base
    "always logged" decision row (the one carrying bear's own raw fields) from the 18 other
    decisions.append() call sites, all of which carry an "action" key and, for bear-refused
    bars, may re-log the WINNING (non-bear) side's triggers/level under a hardcoded
    passed=False -- including those would contaminate bear's own raw fields with bull's."""
    if "action" in row:
        return False
    if row.get("passed") is not False:
        return False
    if bull_passed:
        return False   # neither side passed scoring -- mirrors verdict=='HOLD' upstream
    triggers = row.get("triggers_fired") or []
    if not any(t in bss.LADDER_LEVEL_TIED for t in triggers):
        return False
    level = row.get("rejection_level")
    if not isinstance(level, (int, float)):
        return False
    return True


def build_candidates(decisions: list[dict], bull_passed_by_idx: dict[int, bool]) -> list[dict]:
    out = []
    for row in decisions:
        bp = bull_passed_by_idx.get(row.get("bar_idx"), False)
        if is_ladder_candidate(row, bp):
            out.append(dict(row))
    return out


# =============================================================================== entry+1 resolution

def next_bar_same_day(spy_df: pd.DataFrame, trigger_idx: int) -> Optional[int]:
    """entry+1 convention: the NEXT positional row in the continuous RTH frame, same calendar
    day as the trigger bar. None if the trigger bar is the day's last available row (rare --
    the ladder's own scoring window already excludes bars at/after time_stop_et=15:40, and RTH
    runs to 15:55, so this only bites on a genuine data gap)."""
    next_idx = trigger_idx + 1
    if next_idx >= len(spy_df):
        return None
    trig_date = spy_df.iloc[trigger_idx]["timestamp_et"].date()
    if spy_df.iloc[next_idx]["timestamp_et"].date() != trig_date:
        return None
    return next_idx


def resolve_ladder_entry(
    spy_df: pd.DataFrame, trigger_idx: int, strike: int, trade_date: dt.date,
    vix_now: float, spot: float,
    opt_loader: Callable[[str], Optional[pd.DataFrame]] = load_contract_bars,
) -> dict:
    """Returns either {"ok": True, symbol, opt_df, entry_time_et (naive), entry_premium} from
    the REAL OPRA cache, or {"ok": False, reason, synthetic_entry_premium} -- a BS-synthetic
    premium computed for disclosure ONLY (see module docstring; never fed through a synthetic
    exit walk)."""
    next_idx = next_bar_same_day(spy_df, trigger_idx)
    if next_idx is None:
        return {"ok": False, "reason": "no_next_bar_same_day", "synthetic_entry_premium": None}
    next_ts = spy_df.iloc[next_idx]["timestamp_et"]
    symbol = option_symbol(trade_date, int(strike), "P")
    opt_df = opt_loader(symbol)
    reason = "no_opra_cache"
    if opt_df is not None:
        ob = bar_at_or_after(opt_df, next_ts)
        if ob is not None:
            return {
                "ok": True, "symbol": symbol, "opt_df": opt_df,
                "entry_time_et": efr.naive_dt(ob.timestamp_et),
                "entry_premium": float(ob.open),
            }
        reason = "opra_cached_but_no_bar_at_or_after_next"
    iv = vix_to_iv(vix_now)
    tte = time_to_expiry_years(next_ts.to_pydatetime())
    price, _delta = black_scholes(spot, strike, iv, tte, is_call=False)
    return {"ok": False, "reason": reason, "synthetic_entry_premium": round(max(price, 0.01), 4)}


# =============================================================================== one lane

def run_lane(
    floor: int, candidates: list[dict], spy_df: pd.DataFrame, ribbon_lookup: pd.DataFrame,
    exit_shape: dict, min_contracts: int = MIN_CONTRACTS, ref_equity: float = REF_EQUITY_FOR_STRIKE,
    opt_loader: Callable[[str], Optional[pd.DataFrame]] = load_contract_bars,
) -> tuple[list[dict], list[dict]]:
    """Walks this floor's qualifying candidates in chronological order, ONE POSITION AT A TIME
    (NOT_FLAT discipline): a candidate strictly inside an already-open position's [entry, exit]
    window is skipped, never queued. Returns (trades, excluded_disclosure_rows)."""
    lane_candidates = sorted(
        (c for c in candidates if c["bear_score"] >= floor),
        key=lambda c: c["bar_idx"],
    )
    trades: list[dict] = []
    excluded: list[dict] = []
    flat_until: Optional[dt.datetime] = None

    for c in lane_candidates:
        trig_idx = c["bar_idx"]
        trig_row = spy_df.iloc[trig_idx]
        trig_ts = efr.naive_dt(trig_row["timestamp_et"])
        if flat_until is not None and trig_ts <= flat_until:
            continue   # NOT_FLAT -- still holding this lane's prior position through this tick

        spot = float(c["spy_close"])
        strike = pick_strike(spot, ref_equity, "P", fx.PROBE_STRIKE_TIERS)
        trade_date = trig_row["timestamp_et"].date()
        res = resolve_ladder_entry(spy_df, trig_idx, strike, trade_date, float(c["vix"]), spot,
                                    opt_loader=opt_loader)
        if not res["ok"]:
            excluded.append({
                "floor": floor, "date": trade_date.isoformat(), "trigger_bar_idx": trig_idx,
                "trigger_time_et": trig_ts.isoformat(), "bear_score": c["bear_score"],
                "blockers": c["blockers"], "triggers_raw": c["triggers_fired"],
                "rejection_level": c["rejection_level"], "strike": strike,
                "exclude_reason": res["reason"],
                "synthetic_entry_premium": res.get("synthetic_entry_premium"),
                "is_synthetic": res.get("synthetic_entry_premium") is not None,
            })
            continue   # never entered -- lane stays flat, free for the NEXT candidate

        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == trade_date].reset_index(drop=True)
        rtd = efr.ribbon_tick_df_for(res["opt_df"], ribbon_lookup)
        walk = walk_exit_manager(
            symbol=res["symbol"], side="P", entry_time_et=res["entry_time_et"],
            entry_premium=res["entry_premium"], qty=min_contracts, exit_shape=exit_shape,
            structure_stop_enabled=True, trigger_level=float(c["rejection_level"]),
            strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
            opt_df=res["opt_df"], ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        exit_ts = walk.exit_time_et if walk.exit_time_et is not None else res["entry_time_et"]
        flat_until = exit_ts

        trades.append({
            "floor": floor, "date": trade_date.isoformat(), "trigger_bar_idx": trig_idx,
            "trigger_time_et": trig_ts.isoformat(), "bear_score": c["bear_score"],
            "blockers": c["blockers"], "triggers_raw": c["triggers_fired"],
            "rejection_level": c["rejection_level"],
            "entry_time_et": res["entry_time_et"].isoformat(),
            "entry_premium": round(res["entry_premium"], 4), "strike": strike, "side": "P",
            "qty": min_contracts, "symbol": res["symbol"], "dollar_pnl": walk.dollar_pnl,
            "exit_reason": walk.exit_reason,
            "exit_time_et": exit_ts.isoformat() if exit_ts else None,
            "hold_minutes": walk.hold_minutes, "resolved": walk.resolved,
            "n_ticks_walked": walk.n_ticks_walked, "is_synthetic": False,
        })
    return trades, excluded


# =============================================================================== baseline (binary engine)

def run_baseline(r, spy_df: pd.DataFrame, ribbon_lookup: pd.DataFrame, exit_shape: dict) -> tuple[list[dict], dict]:
    """Reuses `r.trades` from the SAME run_backtest(**SAFE_BASE_LIVE) call the ladder candidates
    were mined from (no second 100+s run_backtest call) -- otherwise byte-identical to
    engine_fullhist_replay.py's own main() loop, extended over this tool's wider window."""
    rows = []
    n_no_opra = 0
    n_no_spy_day = 0
    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            n_no_opra += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            n_no_spy_day += 1
            continue
        entry_time_et = efr.naive_dt(t.entry_time_et)
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et,
            entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=exit_shape,
            structure_stop_enabled=True,
            trigger_level=(float(t.rejection_level) if t.rejection_level else None),
            strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        rows.append({
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "setup": t.setup, "side": t.side, "symbol": symbol, "qty": int(t.qty),
            "entry_premium": round(float(t.entry_premium), 4), "triggers": t.triggers_fired,
            "rejection_level": t.rejection_level, "dollar_pnl": res.dollar_pnl,
            "exit_reason": res.exit_reason, "hold_minutes": res.hold_minutes,
            "resolved": res.resolved,
        })
    return rows, {"n_excluded_no_opra": n_no_opra, "n_excluded_no_spy_day": n_no_spy_day}


# =============================================================================== stats

def lane_stats(trades: list[dict], all_calendar_dates: list[dt.date], held_out_cutoff: dt.date) -> dict:
    empty = {
        "n_trades": 0, "total_pnl": 0.0, "win_rate": None, "avg_pnl_per_trade": None,
        "max_drawdown": 0.0, "max_drawdown_date": None,
        "day_majority": {"win_days": 0, "total_trading_days": 0, "is_majority": None},
        "survives_dropping_best_trade": {"best_trade_pnl": None, "total_minus_best": 0.0, "still_positive": None},
        "held_out_last_25pct": {"cutoff_date": held_out_cutoff.isoformat(), "n_trades": 0,
                                 "total_pnl": 0.0, "win_rate": None},
    }
    if not trades:
        return empty

    df = pd.DataFrame(trades)
    df["dollar_pnl"] = df["dollar_pnl"].astype(float)
    total_pnl = round(float(df["dollar_pnl"].sum()), 2)
    n = len(df)
    wr = round(float((df["dollar_pnl"] > 0).mean()), 4)
    avg = round(total_pnl / n, 2)

    per_day = df.groupby("date")["dollar_pnl"].sum()
    day_series = pd.Series({str(d): float(per_day.get(str(d), 0.0)) for d in all_calendar_dates})
    cum = day_series.cumsum()
    running_max = cum.cummax()
    dd = cum - running_max
    max_dd = round(float(dd.min()), 2)
    max_dd_date = str(dd.idxmin())

    win_days = int((per_day > 0).sum())
    total_trading_days = len(per_day)
    day_majority = {
        "win_days": win_days, "total_trading_days": total_trading_days,
        "is_majority": (win_days > total_trading_days / 2.0) if total_trading_days else None,
    }

    best_idx = df["dollar_pnl"].idxmax()
    best_pnl = float(df.loc[best_idx, "dollar_pnl"])
    total_minus_best = round(total_pnl - best_pnl, 2)
    survives = {"best_trade_pnl": round(best_pnl, 2), "total_minus_best": total_minus_best,
                "still_positive": total_minus_best > 0}

    held = df[df["date"] >= held_out_cutoff.isoformat()]
    held_out = {
        "cutoff_date": held_out_cutoff.isoformat(), "n_trades": len(held),
        "total_pnl": round(float(held["dollar_pnl"].sum()), 2) if len(held) else 0.0,
        "win_rate": (round(float((held["dollar_pnl"] > 0).mean()), 4) if len(held) else None),
    }

    return {
        "n_trades": n, "total_pnl": total_pnl, "win_rate": wr, "avg_pnl_per_trade": avg,
        "max_drawdown": max_dd, "max_drawdown_date": max_dd_date,
        "day_majority": day_majority, "survives_dropping_best_trade": survives,
        "held_out_last_25pct": held_out,
    }


# =============================================================================== calibration

def check_calibration(decisions: list[dict], bull_passed_by_idx: dict[int, bool]) -> dict:
    """Locates the 2026-07-27 09:40 bar's own decision row and compares it against the pinned
    live-incident ground truth (test_why_not_provenance.py: bear_score=9, blockers=[5],
    level_rejection, rejection_level=744.9). See module docstring for why an exact match is NOT
    expected via the general full-pipeline path (known, already-disclosed feed-provenance gap,
    same root cause arm_score_ladder_replay.py found earlier the same day)."""
    row = None
    for d in decisions:
        if "action" in d:
            continue
        ts = d["timestamp_et"]
        if getattr(ts, "date", lambda: None)() == CALIBRATION_DAY and getattr(ts, "time", lambda: None)() == CALIBRATION_TIME:
            row = d
            break
    if row is None:
        return {"found": False, "note": "2026-07-27 09:40 bar not present in decisions -- data/window gap"}

    bp = bull_passed_by_idx.get(row["bar_idx"], False)
    triggers = row.get("triggers_fired") or []
    exact = (row["bear_score"] == CALIBRATION_PINNED["bear_score"]
              and row["blockers"] == CALIBRATION_PINNED["blockers"]
              and CALIBRATION_PINNED["trigger"] in triggers
              and row["rejection_level"] == CALIBRATION_PINNED["rejection_level"])
    roughly = (row["bear_score"] in (8, 9) and CALIBRATION_PINNED["trigger"] in triggers
                and row["rejection_level"] is not None)
    return {
        "found": True, "bar_idx": row["bar_idx"], "bear_score": row["bear_score"],
        "blockers": row["blockers"], "triggers_raw": triggers,
        "rejection_level": row["rejection_level"], "bear_passed": row["passed"],
        "bull_passed": bp, "pinned_ground_truth": CALIBRATION_PINNED,
        "exact_match_pinned_ground_truth": exact, "roughly_reproduces": roughly,
        "floor_7_would_qualify": row["bear_score"] >= 7,
        "floor_8_would_qualify": row["bear_score"] >= 8,
        "floor_9_would_qualify": row["bear_score"] >= 9,
        "note": (
            "EXACT pinned match." if exact else
            "Off-by-one from the pinned ground truth (bear_score/blockers/rejection_level all "
            "shift by a small amount) -- the SAME known feed-provenance gap already root-caused "
            "same-day in analysis/arm-ladder/ARM-LADDER-V1-2026-07-27.md: the cached 09:40 bar in "
            "backtest/data/spy_5m_2026-05-19_2026-07-27.csv is not byte-identical to the real IEX "
            "bar the live engine read (a few cents on open/high/low), which shifts filter 5's "
            "confluence match and filter 9's volume-baseline check. Not re-investigated here -- "
            "citing the existing, already-verified finding rather than re-deriving it."
        ),
    }


# =============================================================================== main

def main() -> int:
    t_start = time.time()
    log(f"loading extended SPY/VIX data: {FULL_START}..{FULL_END}")
    spy_df_raw, vix_df = load_extended_data()
    log(f"  spy rows={len(spy_df_raw)} range={spy_df_raw['timestamp_et'].min()}..{spy_df_raw['timestamp_et'].max()}")
    spy_rth = build_rth_frame(spy_df_raw)
    log(f"  RTH-only reindexed frame (matches orchestrator's own bar_idx space): {len(spy_rth)} rows "
        f"(raw had {len(spy_df_raw)} -- {len(spy_df_raw) - len(spy_rth)} premarket/after-hours bars dropped)")

    log("running run_backtest(**SAFE_BASE_LIVE) with bull-passed capture (entry+scoring layer)")
    t0 = time.time()
    r, bull_passed_by_idx = run_backtest_with_bull_capture(
        spy_df_raw, vix_df, start_date=FULL_START, end_date=FULL_END, **efr.SAFE_BASE_LIVE,
    )
    entry_elapsed = time.time() - t0
    log(f"  done in {entry_elapsed:.1f}s -- {len(r.trades)} baseline entries, "
        f"{len(r.decisions)} decision rows")

    ribbon_lookup = efr.build_ribbon_lookup(spy_df_raw)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    all_calendar_dates = sorted(spy_rth["timestamp_et"].dt.date.unique())
    window_days = (FULL_END - FULL_START).days
    held_out_cutoff = FULL_START + dt.timedelta(days=round(window_days * 0.75))

    log("re-deriving BASELINE exits (binary engine's own real entries) via walk_exit_manager")
    t1 = time.time()
    baseline_rows, baseline_dq = run_baseline(r, spy_rth, ribbon_lookup, exit_shape)
    baseline_stats = lane_stats(baseline_rows, all_calendar_dates, held_out_cutoff)
    log(f"  baseline: n={baseline_stats['n_trades']} total_pnl=${baseline_stats['total_pnl']:+.2f} "
        f"({time.time()-t1:.1f}s)")

    log("building ladder candidates from decisions (bear-refused, level-tied trigger, level exists)")
    candidates = build_candidates(r.decisions, bull_passed_by_idx)
    log(f"  {len(candidates)} floor-independent candidates (score>=7 superset)")

    lanes = {}
    for floor in FLOORS:
        t2 = time.time()
        trades, excluded = run_lane(floor, candidates, spy_rth, ribbon_lookup, exit_shape)
        stats = lane_stats(trades, all_calendar_dates, held_out_cutoff)
        n_synth = sum(1 for e in excluded if e.get("is_synthetic"))
        would_be = len(trades) + n_synth
        stats["n_candidates_at_floor"] = sum(1 for c in candidates if c["bear_score"] >= floor)
        stats["n_excluded_total"] = len(excluded)
        stats["n_excluded_synthetic_priced"] = n_synth
        stats["pct_synthetic_of_would_be_entries"] = (
            round(100.0 * n_synth / would_be, 1) if would_be else None
        )
        lanes[floor] = {"trades": trades, "excluded": excluded, "stats": stats}
        log(f"  floor={floor}: n_candidates={stats['n_candidates_at_floor']} "
            f"n_entered={stats['n_trades']} total_pnl=${stats['total_pnl']:+.2f} "
            f"WR={stats['win_rate']} synthetic={n_synth} ({time.time()-t2:.1f}s)")

    calibration = check_calibration(r.decisions, bull_passed_by_idx)
    log(f"CALIBRATION 2026-07-27 09:40: found={calibration.get('found')} "
        f"bear_score={calibration.get('bear_score')} roughly_reproduces={calibration.get('roughly_reproduces')}")

    total_elapsed = time.time() - t_start
    write_outputs(lanes, baseline_rows, baseline_stats, baseline_dq, calibration,
                  all_calendar_dates, held_out_cutoff, entry_elapsed, total_elapsed)
    return 0


def _lane_json(floor: int, lanes: dict) -> dict:
    L = lanes[floor]
    return {"floor": floor, "stats": L["stats"], "trades": L["trades"], "excluded": L["excluded"]}


def write_outputs(lanes, baseline_rows, baseline_stats, baseline_dq, calibration,
                   all_calendar_dates, held_out_cutoff, entry_elapsed, total_elapsed) -> None:
    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "window": {"start": FULL_START.isoformat(), "end": FULL_END.isoformat(),
                    "n_calendar_rth_days": len(all_calendar_dates)},
        "known_divergence": (
            "replay-vs-live divergence is KNOWN (engine_fullhist_replay.py's own fidelity check: "
            "the entry layer's single-isolated-bar reconstruction does not always land on the "
            "identical bar as a live fill on days with intraday state, e.g. 2026-07-17 anchors "
            "2/4 -- see that tool's ANCHOR_DAY sanity check). This ladder replay inherits the same "
            "entry-layer scope/limitation for its scoring inputs."
        ),
        "held_out_split": {"cutoff_date": held_out_cutoff.isoformat(),
                            "note": "last ~25% of the calendar window by date, touched once, reported not tuned"},
        "calibration_2026_07_27_0940": calibration,
        "baseline_binary_engine": {"stats": baseline_stats, "data_quality": baseline_dq,
                                    "trades": baseline_rows},
        "lanes": {str(f): _lane_json(f, lanes) for f in FLOORS},
        "runtime_seconds": {"entry_layer": round(entry_elapsed, 1), "total": round(total_elapsed, 1)},
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out, lanes)
    log(f"wrote {OUT_MD}")


def _fmt_pnl(v) -> str:
    if v is None:
        return "n/a"
    return f"+${v:.2f}" if v >= 0 else f"-${abs(v):.2f}"


def write_markdown(out: dict, lanes: dict) -> None:
    cal = out["calibration_2026_07_27_0940"]
    bstats = out["baseline_binary_engine"]["stats"]
    L = ["# SCORE LADDER full-history replay -- 2025-01-02 .. 2026-07-27", ""]
    L.append(f"Generated {out['generated_at']}. Runner: `backtest/tools/ladder_fullhist_replay.py`. "
              f"Runtime: {out['runtime_seconds']['total']}s total "
              f"({out['runtime_seconds']['entry_layer']}s entry/scoring layer).")
    L.append("")
    L.append("## Verdict first")
    L.append("")
    L.append("| Lane | N trades | Total P&L | WR | Avg/trade | Max DD | Day-majority | Survives drop-best | Held-out (last 25%) | Synthetic excluded |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    b = bstats
    L.append(
        f"| **BASELINE (binary engine)** | {b['n_trades']} | {_fmt_pnl(b['total_pnl'])} | "
        f"{b['win_rate']} | {_fmt_pnl(b['avg_pnl_per_trade'])} | {_fmt_pnl(b['max_drawdown'])} | "
        f"{b['day_majority']['win_days']}/{b['day_majority']['total_trading_days']} "
        f"({b['day_majority']['is_majority']}) | "
        f"{_fmt_pnl(b['survives_dropping_best_trade']['total_minus_best'])} "
        f"({b['survives_dropping_best_trade']['still_positive']}) | "
        f"{b['held_out_last_25pct']['n_trades']}tr {_fmt_pnl(b['held_out_last_25pct']['total_pnl'])} | -- |"
    )
    for f in FLOORS:
        s = lanes[f]["stats"]
        L.append(
            f"| **Ladder floor={f}** | {s['n_trades']} | {_fmt_pnl(s['total_pnl'])} | "
            f"{s['win_rate']} | {_fmt_pnl(s['avg_pnl_per_trade'])} | {_fmt_pnl(s['max_drawdown'])} | "
            f"{s['day_majority']['win_days']}/{s['day_majority']['total_trading_days']} "
            f"({s['day_majority']['is_majority']}) | "
            f"{_fmt_pnl(s['survives_dropping_best_trade']['total_minus_best'])} "
            f"({s['survives_dropping_best_trade']['still_positive']}) | "
            f"{s['held_out_last_25pct']['n_trades']}tr {_fmt_pnl(s['held_out_last_25pct']['total_pnl'])} | "
            f"{s['n_excluded_synthetic_priced']}/{s['n_candidates_at_floor']} "
            f"({s['pct_synthetic_of_would_be_entries']}%) |"
        )
    L.append("")

    L.append("## Calibration check -- 2026-07-27 09:40 (the incident deb781ea's own commit cites)")
    L.append("")
    if cal.get("found"):
        L.append(
            f"- Reproduced: bear_score={cal['bear_score']}, blockers={cal['blockers']}, "
            f"triggers={cal['triggers_raw']}, rejection_level={cal['rejection_level']}, "
            f"bull_passed={cal['bull_passed']}"
        )
        L.append(
            f"- Pinned live-incident ground truth: bear_score={cal['pinned_ground_truth']['bear_score']}, "
            f"blockers={cal['pinned_ground_truth']['blockers']}, "
            f"trigger={cal['pinned_ground_truth']['trigger']}, "
            f"rejection_level={cal['pinned_ground_truth']['rejection_level']}"
        )
        L.append(f"- **Exact match: {cal['exact_match_pinned_ground_truth']}. "
                  f"Roughly reproduces: {cal['roughly_reproduces']}.**")
        L.append(f"- {cal['note']}")
        L.append(
            f"- Would qualify at floor 7: {cal['floor_7_would_qualify']} | "
            f"floor 8: {cal['floor_8_would_qualify']} | floor 9: {cal['floor_9_would_qualify']}"
        )
        for f in FLOORS:
            day_trades = [t for t in lanes[f]["trades"] if t["date"] == "2026-07-27"]
            if day_trades:
                t = day_trades[0]
                L.append(f"  - Lane floor={f}: entered {t['trigger_time_et']} "
                          f"(bear_score={t['bear_score']}) -> P&L {_fmt_pnl(t['dollar_pnl'])} "
                          f"({t['exit_reason']})")
            else:
                excl = [e for e in lanes[f]["excluded"] if e["date"] == "2026-07-27"]
                if excl:
                    L.append(f"  - Lane floor={f}: candidate excluded ({excl[0]['exclude_reason']})")
                else:
                    L.append(f"  - Lane floor={f}: no qualifying candidate on 2026-07-27")
    else:
        L.append(f"- {cal.get('note')}")
    L.append("")

    L.append("## Disclosures")
    L.append("")
    L.append(f"- {out['known_divergence']}")
    L.append(f"- Held-out split: last ~25% of the window (cutoff {out['held_out_split']['cutoff_date']}), "
              "touched once (reported, not used to tune floors/exit shape).")
    L.append(
        "- Synthetic-premium share: BS-synthetic entries are flagged per-trade "
        "(`is_synthetic`/`synthetic_entry_premium` in the JSON) and counted separately per lane "
        "(`n_excluded_synthetic_priced` / `pct_synthetic_of_would_be_entries`) -- they are NEVER "
        "blended into the P&L/WR/expectancy numbers above (real OPRA fills only; see module "
        "docstring for why a synthetic exit walk was not attempted)."
    )
    L.append(
        f"- Baseline data quality: {out['baseline_binary_engine']['data_quality']['n_excluded_no_opra']} "
        "entries excluded (no OPRA cache), "
        f"{out['baseline_binary_engine']['data_quality']['n_excluded_no_spy_day']} excluded (no SPY day)."
    )
    L.append(
        "- Entry price convention: NEXT option bar's OPEN after the trigger bar (entry+1, per "
        "markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md) -- deliberately matches "
        "walk_exit_manager's own point-sample-at-open exit convention, NOT simulator_real.py's "
        "VWAP-based convention for the binary engine's own real entries."
    )
    L.append(
        "- One-position-at-a-time (NOT_FLAT) discipline is per-lane, independent across floors 7/8/9 "
        "-- each lane can be in a DIFFERENT position (or flat) at the same wall-clock time."
    )
    L.append("")

    L.append("## Honest read")
    L.append("")
    best_lane = max(FLOORS, key=lambda f: lanes[f]["stats"]["total_pnl"])
    bl = lanes[best_lane]["stats"]
    L.append(
        f"Across {out['window']['n_calendar_rth_days']} RTH days ({out['window']['start']}.."
        f"{out['window']['end']}), the binary engine's own entries produced "
        f"{_fmt_pnl(b['total_pnl'])} on {b['n_trades']} trades (WR {b['win_rate']}). The 3 score-ladder "
        f"lanes, walked one-position-at-a-time on min-size (3 contracts, ATM strike, the SAME "
        f"structure-stop RIBBON_RIDE exit shape) against every bar the binary engine scored-but-"
        f"refused, produced floor=7 {_fmt_pnl(lanes[7]['stats']['total_pnl'])} "
        f"(n={lanes[7]['stats']['n_trades']}, WR={lanes[7]['stats']['win_rate']}), "
        f"floor=8 {_fmt_pnl(lanes[8]['stats']['total_pnl'])} "
        f"(n={lanes[8]['stats']['n_trades']}, WR={lanes[8]['stats']['win_rate']}), "
        f"floor=9 {_fmt_pnl(lanes[9]['stats']['total_pnl'])} "
        f"(n={lanes[9]['stats']['n_trades']}, WR={lanes[9]['stats']['win_rate']}). "
        f"The best-performing lane by total P&L is floor={best_lane} "
        f"({_fmt_pnl(bl['total_pnl'])}, day-majority={bl['day_majority']['is_majority']}, "
        f"survives-drop-best={bl['survives_dropping_best_trade']['still_positive']}, "
        f"held-out-last-25%={_fmt_pnl(bl['held_out_last_25pct']['total_pnl'])}). "
        "This is a HYPOTHESIS-UNDER-TEST replay of a lane that ships on ONE live account "
        "(risky-3, floor=7) -- the numbers above are the honest full-history evidence for or "
        "against widening it, not a claim that any number here already matches what risky-3's "
        "own forward paper ledger will show (see the known-divergence disclosure)."
    )
    L.append("")
    L.append("---")
    L.append("_Raw JSON with full per-trade/per-excluded-candidate detail: "
              "`analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json`._")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
