#!/usr/bin/env python
"""sizing_scaling_decision_2026_08_03.py -- DECISION PACKAGE measurement harness for
equity-scaled position sizing (wiring `position_sizing_tiers` into core, the CAPITAL-
EFFICIENCY-2026-08-03.md headline lever). MEASUREMENT ONLY -- zero edits to any trading-path
file (heartbeat_core.py, params.json/aggressive/params.json, exit_manager.py,
exit_actuator.py, option_pricing_real.py, exit_manager_walk.py are all imported/read, never
modified this session).

Answers, pre-registered before running: does replaying the population at EQUITY-SCALED qty
(fleet's own `position_sizing_tiers`, already present in BOTH base params files but never
read by core) beat today's flat `min_contracts` sizing -- and does it do so WITHOUT tripping
the daily kill switch (CLAUDE.md Rule 5) more often? See analysis/deep-research/
SIZING-SCALING-DECISION-2026-08-03.md for the narrative/verdict.

METHODOLOGY (stated once, applies to every number below):
  - Real OPRA option bars only (backtest/data/options/*.csv, via
    lib.option_pricing_real.load_contract_bars) -- no synthetic pricing.
  - Entry metadata (date/time/side/symbol/entry_premium/triggers/trigger_level) is REUSED
    from the two already-validated populations (Safe: analysis/recommendations/
    engine-fullhist-replay-2026-07-23.json, 191 trades; Bold: a fresh
    bold_fullhist_replay.bold_base_live(block_elite_bull=True) entry-layer run, 156-ish
    trades) -- entry detection itself is NOT re-derived here (out of scope, and re-deriving
    it would risk a different signal set than the already-validated population).
  - EVERY dollar figure below comes from a FRESH real bar-by-bar exit re-derivation
    (lib.exit_manager_walk.walk_exit_manager, driving the REAL automation/state/fleet/
    exit_manager.py#plan_exit_actions decision core) at EACH candidate qty this study needs
    -- NOT a linear rescale of an already-computed number. This is possible (and cheap: no
    re-fetch, cached OPRA bars) because exit TRIGGER PRICES are pure percentages of entry
    premium, independent of qty; only the dollar magnitude and the TP1/runner leg SPLIT
    (integer-rounded) depend on qty, and walk_exit_manager computes both exactly.
  - VERIFIED LIVE VALUE CORRECTION (read from setup/scripts/heartbeat_core.py:2176-2182 +
    automation/state/fleet/strategies.py#RIBBON_RIDE.exit, this session): core's LIVE
    ribbon_ride exit registration does NOT read the account's own params.json top-level
    `tp1_qty_fraction` -- it unconditionally uses `strategies.by_name("ribbon_ride").exit.
    to_dict()`, which hardcodes tp1_qty_fraction=0.667 for BOTH accounts. CLAUDE.md's
    documented "tp1_qty_fraction 0.8 Safe / 0.667 Bold" (and this task's own framing) is
    TRUE OF THE PARAMS FILE but NOT TRUE OF THE LIVE RIBBON_RIDE EXIT PATH -- Safe's 0.8 is
    read only for specific TRADE-TO-LEARN extra setups (vwap_continuation etc.) that lack
    their own isolated "tq" override, a narrower scope than the ribbon_ride core path this
    study's whole population is drawn from. This script uses the VERIFIED live value (0.667,
    both accounts) throughout -- see the report's mechanism section for the full citation.
  - Sequential ONE-POSITION admission: inherited from the source populations (both built by
    a single-position orchestrator walk) -- unaffected by qty (exit TIMING is qty-invariant).
  - Daily kill switch (Rule 5): simulated explicitly, chronologically, per calendar date --
    NOT in the source populations (which don't model account-level state). Once a day's
    cumulative included P&L breaches -kill_pct*start_of_day_equity, every SUBSEQUENT same-day
    trade (by entry_time_et order) is EXCLUDED from that day's total (it would never have
    fired live) and counted separately. start_of_day_equity = the grid equity level (this is
    a STATIC scaling exercise, not a compounding account-curve simulation -- same convention
    CAPITAL-EFFICIENCY-2026-08-03.md's own capital curve used, disclosed there and here).
  - Fleet's ACTUAL behavior is DENY-not-shrink on a Rule-6 breach (risk_gate.check_order
    returns Deny outright when the fleet-tiered qty's notional exceeds the cap; it does NOT
    downsize to whatever fits, unlike core's existing min_contracts clamp). This script
    models the scaled arm the SAME way (order_affordable at the tiered qty; excluded, not
    shrunk, on failure) -- see the mechanism section for why a core-native wiring could do
    strictly better (shrink instead of deny) and why this measurement is therefore a LOWER
    BOUND on the scaled arm's true potential, not an upper bound.

Run:
    backtest/.venv/Scripts/python.exe backtest/tools/sizing_scaling_decision_2026_08_03.py
    (~2-5 min: Bold's entry layer, run once, is the only slow step; every qty re-walk after
    that reuses cached OPRA bars + a cached ribbon join per symbol.)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
TOOLS = BACKTEST / "tools"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (TOOLS, BACKTEST, FLEET_DIR, REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

from lib import risk_gate as rg  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402
import strategies as fleet_strategies  # noqa: E402 -- automation/state/fleet/strategies.py
import exit_manager as em  # noqa: E402       -- automation/state/fleet/exit_manager.py
import fleet_executor as fx  # noqa: E402      -- automation/state/fleet/fleet_executor.py
import engine_fullhist_replay as efr  # noqa: E402  -- ribbon lookup + naive_dt primitives
import bold_fullhist_replay as bfr  # noqa: E402    -- Bold entry-layer config
import elite_bear_level_reject_gate_ab as eb  # noqa: E402  -- entry_date
import regime_participation_study as rps  # noqa: E402      -- recent_n_trading_days

SAFE_PARAMS_PATH = REPO / "automation" / "state" / "params.json"
BOLD_PARAMS_PATH = REPO / "automation" / "state" / "aggressive" / "params.json"
SAFE_POP_JSON = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
OUT_JSON = REPO / "analysis" / "deep-research" / "SIZING-SCALING-DECISION-2026-08-03.json"

EQUITY_GRID = (2000.0, 5000.0, 10000.0, 25000.0)
RECENT_N_DAYS = 25
TIME_STOP_ET = dt.time(15, 40)
# VERIFIED live value for BOTH accounts' core ribbon_ride path -- see module docstring.
RIBBON_TP1_QTY_FRACTION = 0.667

# Real-verified current balances (task-supplied range + live-verified points on record:
# CLAUDE.md 2026-07-11 Safe $1,746.75; fill-funnel-2026-07-29/30.json Safe $1,160.42;
# bold_fullhist_replay.py 2026-08-01 Bold $1,197.52). $2,122 (task-supplied upper end) is
# reported as given -- not independently re-verified live this session (no live MCP call
# made; this is an offline analysis lane) -- but ALL of these figures share the property
# that matters here: every one is below the $2,000 tier boundary (see report §5).
REAL_BALANCES_SAFE = (1160.42, 1746.75, 2122.0)
REAL_BALANCE_BOLD = 1197.52


def log(msg: str) -> None:
    print(f"[sizing-scaling] {msg}", flush=True)


# =============================================================================================
# PURE FUNCTIONS (guarded: backtest/tests/test_sizing_scaling_decision_2026_08_03.py)
# =============================================================================================

def reached_tp1(exit_reason: str) -> bool:
    """True iff the position's TERMINAL exit_reason implies TP1 already partially filled
    before this exit closed the runner remainder. Determined from exit_manager.
    plan_exit_actions' own reason vocabulary (automation/state/fleet/exit_manager.py): every
    POST-TP1 terminal reason contains "runner_stop", "runner_target", or a literal
    "(runner)" suffix; no PRE-TP1 reason ever does (verified by reading every `reason=`
    call site in plan_exit_actions, 2026-08-02). A trade that never fires TP1 exits its FULL
    qty in one leg -- for those trades a qty change never touches a leg-split at all."""
    if not exit_reason:
        return False
    r = exit_reason.lower()
    return ("runner_stop" in r) or ("runner_target" in r) or ("(runner)" in r)


def leg_split_row(qty: int, tp1_qty_fraction: float) -> dict:
    """ONE qty value's real leg split, via the REAL production ExitState.from_entry (zero
    reimplementation of the int()-floor rounding rule). Returns realized vs nominal TP1
    fraction and a zero-qty-leg flag (the task's explicit 'no zero-qty leg' ask)."""
    shape = {"tp1_qty_fraction": tp1_qty_fraction, "premium_stop_pct": -0.20,
             "tp1_premium_pct": 1.0, "profit_lock_mode": "fixed"}
    st = em.ExitState.from_entry(symbol="TEST", side="P", entry_premium=1.0, qty=qty,
                                  exit_shape=shape, strategy="ribbon_ride")
    realized = (st.tp1_qty / qty) if qty else None
    return {
        "qty": qty, "tp1_qty": st.tp1_qty, "runner_qty": st.runner_qty,
        "nominal_tp1_fraction": tp1_qty_fraction,
        "realized_tp1_fraction": round(realized, 4) if realized is not None else None,
        "delta_vs_nominal_pct_pts": (round((realized - tp1_qty_fraction) * 100, 2)
                                     if realized is not None else None),
        "zero_qty_leg": bool(st.tp1_qty == 0 or st.runner_qty == 0),
    }


def daily_kill_switch_walk(day_trades_sorted: Sequence[Mapping], *, sod_equity: float,
                           kill_pct: float, pnl_key: str = "pnl") -> dict:
    """ONE calendar day's chronological walk under CLAUDE.md Rule 5. `day_trades_sorted`
    MUST already be sorted by entry time (this function does not re-sort -- a caller bug
    is visible, not silently masked). Once cumulative included P&L breaches
    -kill_pct*sod_equity, every SUBSEQUENT trade this day is EXCLUDED (would never have
    fired live under the kill switch) -- the trade THAT TRIPPED the switch is itself still
    included (it already fired before the breach was known)."""
    included: list = []
    excluded: list = []
    cum = 0.0
    tripped = False
    trip_after_index: Optional[int] = None
    floor = -abs(kill_pct) * sod_equity
    for i, t in enumerate(day_trades_sorted):
        if tripped:
            excluded.append(t)
            continue
        included.append(t)
        cum += t[pnl_key]
        if cum <= floor and trip_after_index is None:
            tripped = True
            trip_after_index = i
    return {"included": included, "excluded": excluded, "day_pnl": round(cum, 2),
            "kill_tripped": tripped, "trip_after_index": trip_after_index,
            "n_included": len(included), "n_excluded": len(excluded)}


def equity_curve_stats(day_pnl_by_date: Mapping[str, float]) -> dict:
    """Max drawdown (peak-to-trough on the CUMULATIVE day_pnl curve, chronological) + worst
    single day, off a {date: day_pnl} map. Empty input -> zeroed/None, never raises."""
    dates = sorted(day_pnl_by_date.keys())
    if not dates:
        return {"max_drawdown_dollars": 0.0, "worst_single_day_date": None,
                "worst_single_day_pnl": None, "n_days": 0, "final_cumulative_pnl": 0.0}
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    worst_date, worst_pnl = None, None
    for d in dates:
        pnl = day_pnl_by_date[d]
        if worst_pnl is None or pnl < worst_pnl:
            worst_date, worst_pnl = d, pnl
        cum += pnl
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return {"max_drawdown_dollars": round(max_dd, 2), "worst_single_day_date": worst_date,
            "worst_single_day_pnl": round(worst_pnl, 2) if worst_pnl is not None else None,
            "n_days": len(dates), "final_cumulative_pnl": round(cum, 2)}


def classify_elite(triggers: Sequence[str]) -> bool:
    """Fleet's OWN ELITE definition (fleet_executor._is_elite), reused verbatim -- a trade
    is ELITE iff its trigger set includes 'confluence' OR any 'sequence_*' trigger name."""
    trig_lower = [str(t).lower() for t in (triggers or [])]
    block = {"confluence": "confluence" in trig_lower, "triggers_fired": list(triggers or [])}
    return fx._is_elite(block)


# =============================================================================================
# I/O + entry-layer construction (real OPRA, real orchestrator entries -- reused, not re-derived)
# =============================================================================================

def load_safe_raw_trades() -> list[dict]:
    data = json.loads(SAFE_POP_JSON.read_text(encoding="utf-8"))
    return data["trades"]


def build_safe_context():
    spy_df = pd.read_csv(efr.SPY_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    return spy_df, ribbon_lookup


def build_bold_context(block_elite_bull: bool = True):
    """ONE run_backtest entry-layer pass (the only slow step, ~70-100s) -- exits are
    re-derived fresh per qty afterward, cheaply, off cached OPRA bars."""
    spy_df, vix_df = bfr._load_spy_vix()
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    base = bfr.bold_base_live(block_elite_bull)
    t0 = time.time()
    r = run_backtest(spy_df, vix_df, start_date=bfr.FULL_START, end_date=bfr.FULL_END, **base)
    log(f"  Bold entry layer: {len(r.trades)} raw entries in {time.time()-t0:.1f}s")
    return spy_df, ribbon_lookup, r.trades


_OPT_CACHE: dict[str, Any] = {}
_RIBBON_TICK_CACHE: dict[str, Any] = {}


def _opt_and_ribbon(symbol: str, ribbon_lookup):
    if symbol not in _OPT_CACHE:
        _OPT_CACHE[symbol] = load_contract_bars(symbol)
    opt_df = _OPT_CACHE[symbol]
    if opt_df is None:
        return None, None
    if symbol not in _RIBBON_TICK_CACHE:
        _RIBBON_TICK_CACHE[symbol] = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
    return opt_df, _RIBBON_TICK_CACHE[symbol]


def _rewalk(symbol: str, side: str, entry_time_et, entry_premium: float, qty: int,
           trigger_level: Optional[float], day_spy: pd.DataFrame,
           ribbon_lookup) -> Optional[dict]:
    opt_df, rtd = _opt_and_ribbon(symbol, ribbon_lookup)
    if opt_df is None or day_spy.empty:
        return None
    shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    res = walk_exit_manager(
        symbol=symbol, side=side, entry_time_et=entry_time_et, entry_premium=entry_premium,
        qty=qty, exit_shape=shape, structure_stop_enabled=True, trigger_level=trigger_level,
        strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
        opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
    )
    return {"dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
            "resolved": res.resolved,
            "legs": [{"kind": lg.kind, "qty": lg.qty, "stage": lg.stage,
                      "leg_pnl": lg.leg_pnl} for lg in res.legs]}


def build_unified_records(account: str, raw_trades, qty_values: Sequence[int],
                          spy_df: pd.DataFrame, ribbon_lookup) -> tuple[list[dict], dict]:
    """One unified record per admitted trade, carrying a FULL re-walked dollar_pnl for
    EVERY qty in qty_values (real walk_exit_manager, real OPRA, cached per symbol).
    Returns (records, exclusion_counters)."""
    records: list[dict] = []
    n_no_opra = 0
    n_no_spy_day = 0
    n_unresolved = 0
    n_exit_reason_qty_variant = 0  # sanity counter -- SHOULD stay 0, see main()'s assertion
    spy_by_date = {d: g.reset_index(drop=True) for d, g in
                  spy_df.groupby(spy_df["timestamp_et"].dt.date)}

    for t in raw_trades:
        if account == "safe":
            date_s = t["date"]
            edate = dt.date.fromisoformat(date_s)
            entry_time_et = efr.naive_dt(pd.Timestamp(t["entry_time_et"]))
            side = t["side"]
            symbol = t["symbol"]
            entry_premium = float(t["entry_premium"])
            triggers = list(t.get("triggers") or [])
            trigger_level = t.get("trigger_level")
        else:
            edate = eb.entry_date(t)
            date_s = edate.isoformat()
            entry_time_et = efr.naive_dt(t.entry_time_et)
            side = t.side
            symbol = option_symbol(edate, int(t.strike), t.side)
            entry_premium = float(t.entry_premium)
            triggers = list(t.triggers_fired or [])
            trigger_level = float(t.rejection_level) if t.rejection_level else None

        day_spy = spy_by_date.get(edate)
        if day_spy is None or day_spy.empty:
            n_no_spy_day += 1
            continue

        elite = classify_elite(triggers)
        pnl_by_qty: dict[int, float] = {}
        exit_reason_by_qty: dict[int, str] = {}
        legs_by_qty: dict[int, list] = {}
        any_unresolved = False
        for q in qty_values:
            res = _rewalk(symbol, side, entry_time_et, entry_premium, q, trigger_level,
                         day_spy, ribbon_lookup)
            if res is None:
                continue
            if not res["resolved"]:
                any_unresolved = True
            pnl_by_qty[q] = round(res["dollar_pnl"], 2)
            exit_reason_by_qty[q] = res["exit_reason"]
            legs_by_qty[q] = res["legs"]

        if not pnl_by_qty:
            n_no_opra += 1
            continue
        if any_unresolved:
            n_unresolved += 1
            continue

        # SANITY CHECK (not a filter): exit_reason must be IDENTICAL across every qty --
        # exit trigger PRICES are pure percentages of entry premium, independent of qty
        # (see module docstring). A mismatch would mean a hidden qty-dependent branch
        # exists somewhere in the walk -- counted + disclosed, never silently ignored.
        distinct_reasons = set(exit_reason_by_qty.values())
        if len(distinct_reasons) > 1:
            n_exit_reason_qty_variant += 1

        records.append({
            "account": account, "date": date_s, "entry_time_et": entry_time_et.isoformat(),
            "side": side, "symbol": symbol, "entry_premium": entry_premium,
            "triggers": triggers, "elite": elite,
            "pnl_by_qty": pnl_by_qty, "exit_reason_by_qty": exit_reason_by_qty,
            "legs_by_qty": legs_by_qty,
        })

    counters = {"n_raw": len(raw_trades), "n_admitted": len(records),
               "n_excluded_no_opra": n_no_opra, "n_excluded_no_spy_day": n_no_spy_day,
               "n_excluded_unresolved": n_unresolved,
               "n_exit_reason_qty_variant_MUST_BE_ZERO": n_exit_reason_qty_variant}
    return records, counters


# =============================================================================================
# CAPITAL CURVE (per account x equity x arm)
# =============================================================================================

def capital_curve(records: Sequence[Mapping], *, account: str, equity: float, arm: str,
                  params: Mapping, tiers: Optional[list], min_contracts: int,
                  kill_pct: float) -> dict:
    """arm='baseline' -> qty=min_contracts for every trade (today's real formula).
    arm='scaled' -> qty=fleet_executor._qty_for(tiers, equity, elite) per trade (fleet's
    OWN mechanism, reused verbatim). Both arms are admitted via the SAME
    risk_gate.order_affordable check (deny-not-shrink, matching fleet's real finalize()
    behavior) and both undergo the SAME chronological daily kill-switch walk -- the only
    difference between the two arms is which qty is looked up."""
    by_date: dict[str, list] = {}
    n_no_tier = 0
    n_denied = 0
    n_priced = 0
    for rec in records:
        if arm == "baseline":
            qty = min_contracts
        else:
            qty = fx._qty_for(tiers, equity, rec["elite"])
            if qty is None:
                n_no_tier += 1
                continue
        pnl = rec["pnl_by_qty"].get(qty)
        if pnl is None:
            continue  # qty not in the pre-walked set -- a caller/config bug, never silent
        n_priced += 1
        if not rg.order_affordable(equity=equity, premium=rec["entry_premium"], qty=qty,
                                   params=params):
            n_denied += 1
            continue
        by_date.setdefault(rec["date"], []).append({**rec, "qty_used": qty, "pnl": pnl})

    day_pnl: dict[str, float] = {}
    n_excluded_ks = 0
    n_days_breached = 0
    n_included = 0
    winners = losers = flat = 0
    for date, day_trades in by_date.items():
        day_sorted = sorted(day_trades, key=lambda r: r["entry_time_et"])
        walk = daily_kill_switch_walk(day_sorted, sod_equity=equity, kill_pct=kill_pct,
                                      pnl_key="pnl")
        day_pnl[date] = walk["day_pnl"]
        n_excluded_ks += walk["n_excluded"]
        if walk["kill_tripped"]:
            n_days_breached += 1
        n_included += walk["n_included"]
        for r in walk["included"]:
            if r["pnl"] > 0:
                winners += 1
            elif r["pnl"] < 0:
                losers += 1
            else:
                flat += 1

    stats = equity_curve_stats(day_pnl)
    total = stats["final_cumulative_pnl"]
    n_days = stats["n_days"]
    decided = winners + losers
    return {
        "account": account, "equity": equity, "arm": arm,
        "n_candidate_trades": len(records), "n_no_tier_coverage": n_no_tier,
        "n_priced": n_priced, "n_denied_risk_cap": n_denied,
        "n_included_trades": n_included, "n_excluded_by_kill_switch": n_excluded_ks,
        "n_days_with_a_trade": n_days, "n_days_kill_switch_breached": n_days_breached,
        "total_pnl": total,
        "dollars_per_trade": round(total / n_included, 2) if n_included else None,
        "dollars_per_day": round(total / n_days, 2) if n_days else None,
        "win_rate": round(winners / decided, 4) if decided else None,
        "n_winners": winners, "n_losers": losers, "n_flat": flat,
        "max_drawdown_dollars": stats["max_drawdown_dollars"],
        "max_drawdown_pct_of_grid_equity": (round(100 * stats["max_drawdown_dollars"] / equity, 2)
                                            if equity else None),
        "worst_single_day_date": stats["worst_single_day_date"],
        "worst_single_day_pnl": stats["worst_single_day_pnl"],
    }


def qty_values_needed(tiers: list, min_contracts: int, equity_grid: Sequence[float]) -> list[int]:
    vals = {min_contracts}
    for e in equity_grid:
        for elite in (False, True):
            q = fx._qty_for(tiers, e, elite)
            if q is not None:
                vals.add(int(q))
    return sorted(vals)


# =============================================================================================
# ORCHESTRATION
# =============================================================================================

def main() -> int:
    t_start = time.time()
    safe_params = json.loads(SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
    bold_params = json.loads(BOLD_PARAMS_PATH.read_text(encoding="utf-8"))
    safe_tiers = safe_params["position_sizing_tiers"]
    bold_tiers = bold_params["position_sizing_tiers"]
    safe_min = int(safe_params["min_contracts"])
    bold_min = int(bold_params["min_contracts"])
    safe_kill_pct = float(safe_params["daily_loss_kill_switch_pct"])
    bold_kill_pct = float(bold_params["daily_loss_kill_switch_pct"])

    safe_qtys = qty_values_needed(safe_tiers, safe_min, EQUITY_GRID)
    bold_qtys = qty_values_needed(bold_tiers, bold_min, EQUITY_GRID)
    log(f"Safe qty values needed: {safe_qtys}")
    log(f"Bold qty values needed: {bold_qtys}")

    # ---- leg-split table (task item 4) -- pure, instant, real ExitState.from_entry ----
    leg_split = {
        "safe": [leg_split_row(q, RIBBON_TP1_QTY_FRACTION) for q in safe_qtys],
        "bold": [leg_split_row(q, RIBBON_TP1_QTY_FRACTION) for q in bold_qtys],
        "tp1_qty_fraction_used": RIBBON_TP1_QTY_FRACTION,
        "note": ("Both accounts' core ribbon_ride path uses the SAME verified live value "
                "(0.667) -- see module docstring. This table is account-agnostic; the two "
                "qty lists differ only because the two accounts' position_sizing_tiers "
                "produce different candidate quantities."),
    }

    # ---- entry layers ----
    log("loading Safe 191-trade validated population (entries reused, exits re-derived)...")
    safe_raw = load_safe_raw_trades()
    safe_spy, safe_ribbon = build_safe_context()
    log(f"building Safe unified records across {len(safe_qtys)} qty values "
        f"({len(safe_raw)} raw trades x {len(safe_qtys)} qty = "
        f"{len(safe_raw)*len(safe_qtys)} walk_exit_manager calls)...")
    t0 = time.time()
    safe_records, safe_counters = build_unified_records("safe", safe_raw, safe_qtys,
                                                         safe_spy, safe_ribbon)
    log(f"  done in {time.time()-t0:.1f}s -- {safe_counters}")

    log("running Bold entry layer (block_elite_bull=True, current live) + unified records...")
    bold_spy, bold_ribbon, bold_raw = build_bold_context(block_elite_bull=True)
    t0 = time.time()
    bold_records, bold_counters = build_unified_records("bold", bold_raw, bold_qtys,
                                                         bold_spy, bold_ribbon)
    log(f"  done in {time.time()-t0:.1f}s -- {bold_counters}")

    if safe_counters["n_exit_reason_qty_variant_MUST_BE_ZERO"] or \
       bold_counters["n_exit_reason_qty_variant_MUST_BE_ZERO"]:
        log("*** WARNING: exit_reason varied by qty for at least one trade -- the "
            "qty-invariant-timing assumption this whole study leans on does NOT hold "
            "universally. See per-record exit_reason_by_qty in the output JSON.")

    # ---- capital curves: baseline vs scaled, per account, per equity level ----
    def account_curves(records, account, params, tiers, min_contracts, kill_pct,
                       equity_grid):
        rows = []
        for equity in equity_grid:
            for arm in ("baseline", "scaled"):
                rows.append(capital_curve(records, account=account, equity=equity, arm=arm,
                                          params=params, tiers=tiers,
                                          min_contracts=min_contracts, kill_pct=kill_pct))
        return rows

    log("computing full-history capital curves (baseline vs scaled)...")
    safe_curves = account_curves(safe_records, "safe", safe_params, safe_tiers, safe_min,
                                 safe_kill_pct, EQUITY_GRID)
    bold_curves = account_curves(bold_records, "bold", bold_params, bold_tiers, bold_min,
                                 bold_kill_pct, EQUITY_GRID)

    # ---- recency: newest 25 trading days, same equity grid ----
    log("computing recency-25-trading-day slice...")
    safe_dates = sorted({r["date"] for r in safe_records})
    bold_dates = sorted({r["date"] for r in bold_records})
    safe_recent_dates = set(rps.recent_n_trading_days(safe_dates, RECENT_N_DAYS))
    bold_recent_dates = set(rps.recent_n_trading_days(bold_dates, RECENT_N_DAYS))
    safe_recent_records = [r for r in safe_records if r["date"] in safe_recent_dates]
    bold_recent_records = [r for r in bold_records if r["date"] in bold_recent_dates]
    safe_recent_curves = account_curves(safe_recent_records, "safe", safe_params, safe_tiers,
                                        safe_min, safe_kill_pct, EQUITY_GRID)
    bold_recent_curves = account_curves(bold_recent_records, "bold", bold_params, bold_tiers,
                                        bold_min, bold_kill_pct, EQUITY_GRID)

    # ---- honest alternative at TODAY's real balances (task item 5) ----
    log("pricing the honest alternative at today's real balances...")
    real_balance_rows = []
    for e in REAL_BALANCES_SAFE:
        for arm in ("baseline", "scaled"):
            real_balance_rows.append(capital_curve(safe_records, account="safe", equity=e,
                                                    arm=arm, params=safe_params,
                                                    tiers=safe_tiers, min_contracts=safe_min,
                                                    kill_pct=safe_kill_pct))
    for arm in ("baseline", "scaled"):
        real_balance_rows.append(capital_curve(bold_records, account="bold",
                                                equity=REAL_BALANCE_BOLD, arm=arm,
                                                params=bold_params, tiers=bold_tiers,
                                                min_contracts=bold_min,
                                                kill_pct=bold_kill_pct))
    # tier-table equity threshold where scaling starts to matter (pure lookup, no sim needed)
    tier_thresholds = {
        "safe": sorted({t["equity_min"] for t in safe_tiers if t["equity_min"] > 0}),
        "bold": sorted({t["equity_min"] for t in bold_tiers if t["equity_min"] > 0}),
    }

    payload = {
        "_doc": ("Sizing-scaling decision package measurement. MEASUREMENT ONLY -- zero "
                "trading-path edits. See module docstring for full methodology + the "
                "verified tp1_qty_fraction correction."),
        "generated_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).isoformat(),
        "equity_grid": list(EQUITY_GRID),
        "qty_values": {"safe": safe_qtys, "bold": bold_qtys},
        "position_sizing_tiers": {"safe": safe_tiers, "bold": bold_tiers},
        "min_contracts": {"safe": safe_min, "bold": bold_min},
        "daily_loss_kill_switch_pct": {"safe": safe_kill_pct, "bold": bold_kill_pct},
        "tier_thresholds_where_scaling_starts": tier_thresholds,
        "record_build_counters": {"safe": safe_counters, "bold": bold_counters},
        "leg_split_table": leg_split,
        "capital_curves_full_history": {"safe": safe_curves, "bold": bold_curves},
        "capital_curves_recent_25_trading_days": {
            "safe": safe_recent_curves, "bold": bold_recent_curves,
            "window": {"safe": {"start": min(safe_recent_dates) if safe_recent_dates else None,
                                "end": max(safe_recent_dates) if safe_recent_dates else None,
                                "n_trading_days": len(safe_recent_dates)},
                      "bold": {"start": min(bold_recent_dates) if bold_recent_dates else None,
                               "end": max(bold_recent_dates) if bold_recent_dates else None,
                               "n_trading_days": len(bold_recent_dates)}},
        },
        "honest_alternative_at_real_balances": {
            "safe_balances_tried": list(REAL_BALANCES_SAFE),
            "bold_balance_tried": REAL_BALANCE_BOLD,
            "rows": real_balance_rows,
        },
        "runtime_seconds": round(time.time() - t_start, 1),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON.relative_to(REPO)}")
    log(f"total runtime: {payload['runtime_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
