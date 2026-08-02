#!/usr/bin/env python
"""capital_efficiency_2026_08_03.py -- THE HONEST CAPITAL CURVE.

Motivating question (CLAUDE.md's live headline): the current-live core-Safe engine's
full-history replay is $4,808.75 / 191 trades / ~391 days = $25.18/trade, $12.43/calendar-day
-- an 8-16x gap under J's $100-200/day FOCUS-DOCTRINE target. Twelve pre-registered SELECTION
attempts this weekend all nulled. Nobody has checked whether the GAP is closable by SIZE
(capital deployed) rather than SELECTION (which trades are picked) -- that is this script's
whole job. MEASUREMENT + ARITHMETIC ONLY. Zero edits to any trading-path file; this is a
read-only instrument over already-validated artifacts + two already-tested reusable modules
(risk_gate.py, bold_fullhist_replay.py), never reimplementing their logic.

FINDING #0 (surfaces before anything else can be trusted -- discovered THIS session, not
previously disclosed): `engine_fullhist_replay.py` (the tool behind the $4,808.75 headline)
grades every trade at `orchestrator.run_backtest`'s own INTERNAL "quality-tiered sizing" qty
(orchestrator.py:1194-1226 -- a vestigial v13 concept: SUPER=15, ELITE=10, LEVEL=22,
TRENDLINE_LEG2=20, TRENDLINE/BASE=3, then capped down only if unaffordable at a STATIC
$1,746.75 equity), NOT the REAL live formula (`heartbeat_core.py:1964`: qty is ALWAYS
`params['min_contracts']` (3), clamped DOWN by `risk_gate.max_affordable_qty`, NEVER
auto-scaled up -- confirmed byte-exact against real fills by bold_fullhist_replay.py's own
7/7-anchor validation for Bold, and independently reconstructed here for Safe by direct
inspection of orchestrator.py + heartbeat_core.py). 61 of the 191 replayed trades (32%) used
qty in {4,5,6,7,10,13}, never 3. Because P&L is exactly linear in qty (orchestrator.py's own
comment at line 1919: "option P&L is linear in qty"; independently asserted in
bold_fullhist_replay.py's module docstring finding #1), every dollar figure in this script
is rescaled to what the REAL live min_contracts formula would have produced, via pure
arithmetic (`rescale_pnl_linear`) -- no re-simulation, no re-fetch. This is the SAME class of
correction bold_fullhist_replay.py already applied for Bold on 2026-08-01; nobody had applied
it to Safe's own headline number until this script. The correction LOWERS the honest baseline
below the published $4,808.75 -- see `qty_correction` in the output JSON.

LIQUIDITY DATA GAP (verified, not assumed -- task explicitly forbids hand-waving "SPY is
liquid"): this repo has NEVER cached real NBBO SIZE (bid_size/ask_size) anywhere, historical
or live. `backtest/data/options/*.csv` (the OPRA cache, `lib.option_pricing_real`) is OHLCV
TRADE bars only (open/high/low/close/volume/vwap/trade_count) -- confirmed by reading its
schema and every fetch script (`fetch_option_data.py` calls Alpaca's bars endpoint, never a
quotes/NBBO endpoint). The one "nbbo" field that exists anywhere (`core-decisions.jsonl`
since 2026-07-20) is a RECONSTRUCTED bid/ask/mid/spread with NO size field, algebraically
inverted from mid+entry_px+a fixed cross-buffer assumption (`test_nbbo_capture_2026_07_20.py`)
-- not a captured market observation. So "measure the real NBBO size" is not literally
answerable from anything cached in this repo. The best available, fully-disclosed proxy used
here is 5-minute TRADE VOLUME (`volume` field) in each trade's own entry bar -- a trade-FLOW
proxy, not a displayed-DEPTH proxy. It is directionally informative (qty as a tiny fraction of
one bar's own print volume is real evidence the book was not thin) but is NOT proof of
resting size at the instant of order placement; this gap is reported as a finding, not
silently patched over with a "SPY is liquid" assertion.

Run:
    backtest/.venv/Scripts/python.exe backtest/tools/capital_efficiency_2026_08_03.py
    backtest/.venv/Scripts/python.exe backtest/tools/capital_efficiency_2026_08_03.py --skip-bold
        (skips the ~100s Bold full-history re-walk; Safe-side analysis + liquidity + frequency
        still run in full. Useful for a fast iterate loop while writing the report.)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
CRYPTO_LIB = REPO / "crypto" / "lib"
SCRIPTS = REPO / "setup" / "scripts"
for _p in (BACKTEST / "tools", BACKTEST, SCRIPTS, FLEET_DIR, CRYPTO_LIB, REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib import risk_gate as rg  # noqa: E402
from lib.option_pricing_real import load_contract_bars, bar_containing  # noqa: E402
import strike_selection as ss  # noqa: E402  -- crypto/lib/strike_selection.py
import regime_participation_study as rps  # noqa: E402  -- recent_n_trading_days reuse

SAFE_REPLAY_JSON = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
TRADES_CSV = REPO / "journal" / "trades.csv"
SAFE_PARAMS_PATH = REPO / "automation" / "state" / "params.json"
AGG_PARAMS_PATH = REPO / "automation" / "state" / "aggressive" / "params.json"
OUT_JSON = REPO / "analysis" / "deep-research" / "CAPITAL-EFFICIENCY-2026-08-03.json"

EQUITY_GRID = (2000.0, 5000.0, 10000.0, 25000.0, 50000.0)
HYPOTHETICAL_QTYS = (3, 10, 30, 100)
DAILY_TARGETS = (100.0, 150.0, 200.0)
RECENT_N_DAYS = 25
LIQUIDITY_THRESHOLDS = (0.05, 0.10, 0.25, 0.50)


# =============================================================================================
# PURE FUNCTIONS (unit-tested: backtest/tests/test_capital_efficiency_2026_08_03.py)
# =============================================================================================

def pct_return_on_capital(dollar_pnl: float, entry_premium: Optional[float],
                          qty: Optional[float]) -> Optional[float]:
    """P&L as a fraction of capital actually deployed (entry_premium * qty * 100). This is
    QTY-INVARIANT by construction whenever P&L scales linearly with qty (true here -- see
    module docstring): whatever qty a given trade historically used, this ratio is the same
    number the real min_contracts=3 fill would have produced. None on a non-positive/missing
    premium or qty (never divide by zero, never fabricate a return)."""
    if entry_premium is None or qty is None or entry_premium <= 0 or qty <= 0:
        return None
    capital = entry_premium * qty * 100.0
    return dollar_pnl / capital


def rescale_pnl_linear(dollar_pnl: float, qty_from: Optional[float], qty_to: float) -> float:
    """Rescale a resolved trade's dollar P&L to a different qty via the established
    linear-in-qty P&L property (see module docstring). Pure arithmetic, zero re-simulation.
    qty_from<=0/None -> 0.0 (nothing real to scale from)."""
    if qty_from is None or qty_from <= 0:
        return 0.0
    return dollar_pnl * (qty_to / qty_from)


def percentile(sorted_values: Sequence[float], p: float) -> Optional[float]:
    """Linear-interpolation percentile (p in [0,100]) of an ALREADY-SORTED ascending sequence.
    None on empty input. p is clamped to [0,100] defensively."""
    if not sorted_values:
        return None
    p = min(100.0, max(0.0, p))
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    rank = (p / 100.0) * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def distribution_stats(values: Sequence[Optional[float]]) -> dict:
    """n/mean/median/p10/p25/p75/p90/min/max of a numeric sequence. None-safe (Nones are
    dropped, never coerced to 0). An all-empty input returns n=0 and every stat None -- never
    raises, never fabricates a statistic from zero data."""
    vals = sorted(v for v in values if v is not None)
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "p10": None, "p25": None,
                "p75": None, "p90": None, "min": None, "max": None}
    return {
        "n": n,
        "mean": round(sum(vals) / n, 6),
        "median": round(percentile(vals, 50), 6),
        "p10": round(percentile(vals, 10), 6),
        "p25": round(percentile(vals, 25), 6),
        "p75": round(percentile(vals, 75), 6),
        "p90": round(percentile(vals, 90), 6),
        "min": round(vals[0], 6),
        "max": round(vals[-1], 6),
    }


def split_by_outcome(trades: Sequence[Mapping], pnl_key: str = "dollar_pnl") -> tuple[list, list, list]:
    """(winners, losers, flat) -- three-way, never forces a flat (==0) trade into either
    bucket (a flat trade is neither a win nor a loss)."""
    winners = [t for t in trades if t.get(pnl_key, 0) > 0]
    losers = [t for t in trades if t.get(pnl_key, 0) < 0]
    flat = [t for t in trades if t.get(pnl_key, 0) == 0]
    return winners, losers, flat


def qty_fraction_of_bar_volume(qty: float, bar_volume: Optional[int]) -> Optional[float]:
    """Our qty as a fraction of the contract's OWN total traded volume in its entry 5-min bar
    -- a TRADE-FLOW liquidity proxy (see module docstring's LIQUIDITY DATA GAP). None when
    bar_volume is None/0 (can't assess -- never silently treated as infinite liquidity)."""
    if bar_volume is None or bar_volume <= 0 or qty is None:
        return None
    return qty / bar_volume


def liquidity_knee_table(ratios: Sequence[float], thresholds: Sequence[float] = LIQUIDITY_THRESHOLDS) -> dict:
    """For each threshold, % of ASSESSABLE trades (ratios already excludes Nones) whose
    qty/bar_volume ratio EXCEEDS it. The 'knee' is the smallest threshold where a material
    share of trades would represent a large bite of their own bar's print volume."""
    n = len(ratios)
    if n == 0:
        return {"n_assessable": 0, "by_threshold": {}}
    return {
        "n_assessable": n,
        "by_threshold": {
            f"gt_{int(round(t * 100))}pct": round(100.0 * sum(1 for r in ratios if r > t) / n, 1)
            for t in thresholds
        },
    }


def order_clears_gate(*, equity: float, entry_premium: float, min_contracts: int,
                       params: Mapping, risk_gate_module=rg) -> bool:
    """Thin, testable wrapper: can the account's SMALLEST legal order (min_contracts) be
    placed at all, at this equity/premium? Delegates to risk_gate.order_affordable -- the
    SAME cap math (RISK_CAP + MAX_PREMIUM_TIER + MIN_CONTRACTS) the live engine's
    risk_gate.check_order enforces. Never re-derives the cap arithmetic locally (C14)."""
    return risk_gate_module.order_affordable(
        equity=equity, premium=entry_premium, qty=min_contracts, params=params)


def capital_curve_row(trades: Sequence[Mapping], *, equity: float, min_contracts: int,
                       params: Mapping, risk_gate_module=rg,
                       premium_key: str = "entry_premium", qty_key: str = "qty",
                       pnl_key: str = "dollar_pnl", date_key: str = "date") -> dict:
    """ONE equity level's honest capital-curve row for a trade population, using the REAL
    live sizing formula (qty = min_contracts, clamped by risk_gate; NEVER auto-scaled up
    with equity) -- NOT the population's own historical qty. Every trade that clears
    order_affordable at min_contracts is rescaled (rescale_pnl_linear) to min_contracts and
    included; every trade that cannot is EXCLUDED (blocked/deadlocked), never silently
    downsized to some smaller quantity (mirrors risk_gate's own fail-closed convention)."""
    included_pnls: list[float] = []
    included_dates: set = set()
    n_blocked = 0
    n_priced = 0
    for t in trades:
        premium = t.get(premium_key)
        if premium is None or premium <= 0:
            continue
        n_priced += 1
        if order_clears_gate(equity=equity, entry_premium=premium, min_contracts=min_contracts,
                             params=params, risk_gate_module=risk_gate_module):
            pnl = rescale_pnl_linear(t[pnl_key], t.get(qty_key), min_contracts)
            included_pnls.append(pnl)
            if t.get(date_key):
                included_dates.add(t[date_key])
        else:
            n_blocked += 1
    total_pnl = round(sum(included_pnls), 2)
    n_included = len(included_pnls)
    return {
        "equity": equity,
        "min_contracts": min_contracts,
        "n_total_priced_candidates": n_priced,
        "n_included": n_included,
        "n_blocked_deadlock": n_blocked,
        "pct_blocked": round(100.0 * n_blocked / n_priced, 1) if n_priced else None,
        "total_pnl": total_pnl,
        "avg_pnl_per_trade": round(total_pnl / n_included, 2) if n_included else None,
        "n_distinct_days_included": len(included_dates),
    }


def trades_per_day_for_target(target_daily_dollars: float,
                              avg_dollars_per_trade: Optional[float]) -> Optional[float]:
    """Trades/day required to reach a $/day target, given an average $/trade. None when the
    average is None/<=0 (a non-positive edge can never be sized into a positive target by
    adding volume -- more trades at a losing/zero average makes it worse, not better)."""
    if avg_dollars_per_trade is None or avg_dollars_per_trade <= 0:
        return None
    return round(target_daily_dollars / avg_dollars_per_trade, 3)


def recent_n_trades(trades: Sequence[Mapping], n: int, date_key: str = "date",
                    rps_module=rps) -> list:
    """Trades whose date is among the population's OWN newest n distinct dates. Delegates
    the date-window selection to regime_participation_study.recent_n_trading_days (already
    tested, already the standing convention for 'recent N' in this repo) rather than
    reimplementing it."""
    dates = [t[date_key] for t in trades if t.get(date_key)]
    recent_dates = set(rps_module.recent_n_trading_days(dates, n))
    return [t for t in trades if t.get(date_key) in recent_dates]


# =============================================================================================
# I/O (all fail-open on a missing file -- an empty/absent artifact yields an empty population,
# disclosed via n=0 downstream, never a crash)
# =============================================================================================

def load_safe_population() -> tuple[list[dict], dict]:
    if not SAFE_REPLAY_JSON.exists():
        return [], {}
    data = json.loads(SAFE_REPLAY_JSON.read_text(encoding="utf-8"))
    return data.get("trades", []), data


def load_safe_params() -> dict:
    return json.loads(SAFE_PARAMS_PATH.read_text(encoding="utf-8"))


def load_agg_params() -> dict:
    return json.loads(AGG_PARAMS_PATH.read_text(encoding="utf-8"))


def load_real_fills_safe() -> list[dict]:
    """Real Safe (core account_id=='safe') fills from journal/trades.csv, reduced to the
    same {entry_premium, qty, dollar_pnl, date} shape the simulated population uses, so the
    same pure functions apply to both. Rows with an unreadable/non-positive premium or qty
    are excluded, counted, never coerced."""
    rows: list[dict] = []
    if not TRADES_CSV.exists():
        return rows
    with TRADES_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("account_id") != "safe":
                continue
            try:
                premium_paid = float(r.get("premium_paid") or 0)
                qty = float(r.get("qty") or 0)
                dollar_pnl = float(r.get("dollar_pnl") or 0)
            except (TypeError, ValueError):
                continue
            if premium_paid <= 0 or qty <= 0:
                continue
            rows.append({
                "date": r.get("date"), "qty": qty, "dollar_pnl": dollar_pnl,
                "entry_premium": round(premium_paid / (qty * 100.0), 4),
            })
    return rows


def load_bar_volume_for_trade(trade: dict) -> Optional[int]:
    """5-min OPRA bar volume at the trade's own entry_time_et, from the ALREADY-CACHED
    backtest/data/options/{symbol}.csv -- zero network fetch (the 191-trade population is
    fully cached per engine-fullhist-replay-2026-07-23.json's own data_quality section:
    'Excluded, no OPRA cache: 16' were already dropped upstream of this population). None
    when no bar covers the entry instant (never fabricated)."""
    symbol = trade.get("symbol")
    entry_ts = trade.get("entry_time_et")
    if not symbol or not entry_ts:
        return None
    df = load_contract_bars(symbol)
    if df is None or df.empty:
        return None
    when = dt.datetime.fromisoformat(entry_ts)
    bar = bar_containing(df, when)
    return bar.volume if bar is not None else None


def run_bold_atm_replay() -> dict:
    """ONE re-run of Bold's ALREADY-VALIDATED replay_population (bold_fullhist_replay.py,
    walk_exit_manager-based, byte-exact against 7/7 real bold-2 fills per that module's own
    ANCHOR_FILLS check) at CURRENT LIVE block_elite_bull=True (automation/state/aggressive/
    params.json, verified true this session), min_contracts=5, qty_mode='fixed'. Reused
    verbatim -- this session did not write or modify that pipeline. ~100s one-time cost
    (entry ~100s run_backtest walk + ~a few seconds exit re-derivation, matching that
    module's own logged runtime)."""
    import bold_fullhist_replay as bfr  # noqa: PLC0415 -- imported lazily (heavy, ~100s)
    spy_df, vix_df = bfr._load_spy_vix()
    ribbon_lookup = bfr.efr.build_ribbon_lookup(spy_df)
    result = bfr.replay_population(spy_df, vix_df, ribbon_lookup, block_elite_bull=True,
                                   min_contracts=bfr.BOLD_MIN_CONTRACTS, qty_mode="fixed")
    return result


# =============================================================================================
# ORCHESTRATION
# =============================================================================================

def qty_correction_finding(trades: list[dict], safe_params: dict) -> dict:
    """FINDING #0 (module docstring). Compares three totals over the SAME 191 trades:
    (a) the published headline (raw historical qty, up to 13, from a vestigial v13 sizing
        path never wired to live);
    (b) qty rescaled to min_contracts=3 (removes the OVER-sizing, still ignores affordability);
    (c) (b) further filtered through order_affordable at the population's own baseline
        equity (initial_equity=1746.75, the SAFE_BASE_LIVE value engine_fullhist_replay.py
        used) -- the fully live-faithful number."""
    raw_total = round(sum(t["dollar_pnl"] for t in trades), 2)
    min_contracts = int(safe_params["min_contracts"])
    n_qty_above_floor = sum(1 for t in trades if t["qty"] > min_contracts)
    rescaled_only = round(sum(rescale_pnl_linear(t["dollar_pnl"], t["qty"], min_contracts)
                              for t in trades), 2)
    baseline_equity = 1746.75  # engine_fullhist_replay.py's own SAFE_BASE_LIVE.initial_equity
    live_faithful_row = capital_curve_row(trades, equity=baseline_equity,
                                          min_contracts=min_contracts, params=safe_params)
    return {
        "n_trades": len(trades),
        "n_trades_qty_above_min_contracts_floor": n_qty_above_floor,
        "published_headline_total_pnl": raw_total,
        "qty_rescaled_to_min_contracts_total_pnl": rescaled_only,
        "pct_of_headline_after_qty_rescale": round(100.0 * rescaled_only / raw_total, 1) if raw_total else None,
        "fully_live_faithful_total_pnl_at_baseline_equity": live_faithful_row["total_pnl"],
        "fully_live_faithful_n_included": live_faithful_row["n_included"],
        "fully_live_faithful_n_blocked_deadlock": live_faithful_row["n_blocked_deadlock"],
        "pct_of_headline_fully_live_faithful": (
            round(100.0 * live_faithful_row["total_pnl"] / raw_total, 1) if raw_total else None),
        "baseline_equity_used": baseline_equity,
        "mechanism": ("orchestrator.py:1194-1226 assigns a vestigial v13 'quality-tiered' "
                     "starting qty (SUPER=15/ELITE=10/LEVEL=22/TRENDLINE_LEG2=20/BASE=3) per "
                     "trade, then scales DOWN only if unaffordable at a static equity "
                     "(orchestrator.py:1917-1932) -- never up-CLAMPED to match the real live "
                     "formula (heartbeat_core.py:1964: qty is unconditionally "
                     "params['min_contracts'], never scaled by tier)."),
    }


def pct_return_section(trades: list[dict]) -> dict:
    all_pct = [pct_return_on_capital(t["dollar_pnl"], t["entry_premium"], t["qty"]) for t in trades]
    winners, losers, flat = split_by_outcome(trades)
    w_pct = [pct_return_on_capital(t["dollar_pnl"], t["entry_premium"], t["qty"]) for t in winners]
    l_pct = [pct_return_on_capital(t["dollar_pnl"], t["entry_premium"], t["qty"]) for t in losers]
    return {
        "note": ("% return is QTY-INVARIANT under the linear-P&L-in-qty property (module "
                "docstring) -- this section is UNAFFECTED by the qty_correction finding and "
                "uses the population's raw historical rows directly."),
        "all": distribution_stats(all_pct),
        "winners": distribution_stats(w_pct),
        "losers": distribution_stats(l_pct),
        "n_winners": len(winners), "n_losers": len(losers), "n_flat": len(flat),
        "win_rate": round(len(winners) / len(trades), 4) if trades else None,
    }


def liquidity_section(trades: list[dict], safe_params: dict) -> dict:
    min_contracts = int(safe_params["min_contracts"])
    volumes = [(t, load_bar_volume_for_trade(t)) for t in trades]
    n_no_bar = sum(1 for _, v in volumes if v is None)
    by_qty: dict[str, dict] = {}
    for q in HYPOTHETICAL_QTYS:
        ratios = [qty_fraction_of_bar_volume(q, v) for _, v in volumes]
        ratios = [r for r in ratios if r is not None]
        by_qty[str(q)] = {
            "hypothetical_qty": q,
            "ratio_distribution": distribution_stats(ratios),
            "knee": liquidity_knee_table(ratios),
        }
    return {
        "data_gap_disclosure": (
            "NBBO SIZE (bid_size/ask_size) is not cached anywhere in this repo, historical or "
            "live -- see module docstring's LIQUIDITY DATA GAP section. This section uses "
            "5-min TRADE VOLUME in each trade's own entry bar as a trade-flow proxy, NOT a "
            "displayed-depth proxy."),
        "n_trades": len(trades),
        "n_no_bar_data": n_no_bar,
        "n_assessable": len(trades) - n_no_bar,
        "min_contracts_today": min_contracts,
        "by_hypothetical_qty": by_qty,
    }


def safe_capital_curve_section(trades: list[dict], safe_params: dict) -> dict:
    min_contracts = int(safe_params["min_contracts"])
    representative_premium = distribution_stats([t["entry_premium"] for t in trades])["median"]
    rows = []
    for equity in EQUITY_GRID:
        row = capital_curve_row(trades, equity=equity, min_contracts=min_contracts,
                                params=safe_params)
        tier = ss.pick_tier(equity, ss.V15_SAFE_TIERS)
        explain = rg.explain_block(equity=equity, premium=representative_premium,
                                   params=safe_params, proposed_qty=min_contracts)
        row["strike_tier_at_this_equity"] = tier.label
        row["strike_tier_matches_population"] = (tier.strike_offset == 0)  # population is ATM
        row["binding_constraint"] = explain
        row["n_trading_days_in_population"] = len({t["date"] for t in trades})
        row["dollars_per_trading_day"] = (
            round(row["total_pnl"] / row["n_trading_days_in_population"], 2)
            if row["n_trading_days_in_population"] else None)
        rows.append(row)
    return {
        "account": "safe (Gamma-Safe-2 shape: per_trade_risk_cap_pct=0.30, min_contracts=3, "
                   "V15_SAFE_TIERS strike ladder)",
        "representative_premium_used_for_binding_constraint": representative_premium,
        "caveat": ("Premium/strike is held FIXED at the population's real ATM prices for "
                  "every row. V15_SAFE_TIERS stays ATM through equity<$10,000 (both the "
                  "$2,000 and $5,000 rows are genuinely ATM, no caveat) but flips to Slight-"
                  "ITM at $10,000 and ITM-2 at $25,000+ -- those two rows' real premiums "
                  "would differ from what is used here (flagged per-row via "
                  "strike_tier_matches_population=False), not re-priced (would require a "
                  "fresh option-chain re-fetch + re-walk, out of this measurement-only lane)."),
        "rows": rows,
    }


def bold_capital_curve_section(bold_trades: list[dict], agg_params: dict) -> dict:
    import bold_fullhist_replay as bfr  # noqa: PLC0415
    min_contracts = bfr.BOLD_MIN_CONTRACTS
    representative_premium = distribution_stats([t["entry_premium"] for t in bold_trades])["median"]
    rows = []
    for equity in EQUITY_GRID:
        included_pnls = []
        included_dates: set = set()
        n_blocked = 0
        n_priced = 0
        for t in bold_trades:
            premium = t.get("entry_premium")
            if premium is None or premium <= 0:
                continue
            n_priced += 1
            qty = bfr.resolve_bold_qty(premium, equity=equity)
            if qty is None:
                n_blocked += 1
                continue
            included_pnls.append(rescale_pnl_linear(t["dollar_pnl"], t.get("qty"), qty))
            if t.get("date"):
                included_dates.add(t["date"])
        total_pnl = round(sum(included_pnls), 2)
        n_included = len(included_pnls)
        tier = ss.pick_tier(equity, ss.V15_BOLD_CORE_TIERS)
        n_days = len({t["date"] for t in bold_trades})
        rows.append({
            "equity": equity, "min_contracts": min_contracts,
            "n_total_priced_candidates": n_priced, "n_included": n_included,
            "n_blocked_deadlock": n_blocked,
            "pct_blocked": round(100.0 * n_blocked / n_priced, 1) if n_priced else None,
            "total_pnl": total_pnl,
            "avg_pnl_per_trade": round(total_pnl / n_included, 2) if n_included else None,
            "n_distinct_days_included": len(included_dates),
            "strike_tier_at_this_equity": tier.label,
            "strike_tier_matches_population": (tier.strike_offset == 0),  # population is ATM
            "n_trading_days_in_population": n_days,
            "dollars_per_trading_day": round(total_pnl / n_days, 2) if n_days else None,
        })
    return {
        "account": "bold (Gamma-Bold-2 shape: per_trade_risk_cap_pct=0.50, min_contracts=5, "
                   "V15_BOLD_CORE_TIERS strike ladder, NO v15_max_premium_pct_of_account tier)",
        "population_source": ("fresh replay_population() re-run this session, block_elite_"
                              "bull=True (current live), min_contracts=5, ATM strike (Bold's "
                              "real live equity $1,197.52 < $2,000 tier boundary)"),
        "representative_premium_used": representative_premium,
        "caveat": ("V15_BOLD_CORE_TIERS leaves ATM ONLY below $2,000 -- EVERY row in this "
                  "table ($2,000 through $50,000) actually falls in a DIFFERENT strike tier "
                  "(OTM-2/OTM-1/ITM-2) than the ATM population being resized here. This table "
                  "is therefore a SIZING-ONLY counterfactual ('if Bold's real min_contracts/ "
                  "risk-cap formula were applied to today's ATM premiums at higher equity'), "
                  "NOT a strike-tier-aware forecast -- flagged per-row via "
                  "strike_tier_matches_population=False on every single row."),
        "rows": rows,
    }


def frequency_section(safe_curve_rows: list[dict]) -> dict:
    out = {}
    for row in safe_curve_rows:
        equity = row["equity"]
        avg = row["avg_pnl_per_trade"]
        n_days = row["n_trading_days_in_population"]
        needed = {f"${int(t)}/day": trades_per_day_for_target(t, avg) for t in DAILY_TARGETS}
        out[str(equity)] = {
            "avg_pnl_per_trade": avg,
            "trades_per_day_needed": needed,
            "actual_trades_per_trading_day_in_population": (
                round(row["n_included"] / n_days, 3) if n_days else None),
        }
    return {
        "rows": out,
        "regime_participation_cross_reference": (
            "analysis/deep-research/REGIME-PARTICIPATION-2026-08-02.md: of 389 full-"
            "population days, only 36.5% see an entry at all; 42.4% are GATE_BLOCKED (a "
            "named filter fired on a real trigger), 20.6% are CORRECTLY_FLAT (a trigger fired "
            "but never reached the score>=8 bar), and only 0.5% (2 days) are genuine "
            "NO_VOCABULARY (zero triggers all session). Raising trades/day therefore competes "
            "directly with SELECTION quality (relaxing a gate or a score threshold), which "
            "this weekend's 12 pre-registered attempts already tried and nulled -- frequency "
            "is not a free lever."),
    }


def recency_section(trades: list[dict], safe_params: dict) -> dict:
    recent = recent_n_trades(trades, RECENT_N_DAYS)
    recent_dates = sorted({t["date"] for t in recent})
    all_pct_recent = [pct_return_on_capital(t["dollar_pnl"], t["entry_premium"], t["qty"])
                      for t in recent]
    min_contracts = int(safe_params["min_contracts"])
    baseline_equity = 1746.75
    curve_row_recent = capital_curve_row(recent, equity=baseline_equity,
                                         min_contracts=min_contracts, params=safe_params)
    curve_row_full = capital_curve_row(trades, equity=baseline_equity,
                                       min_contracts=min_contracts, params=safe_params)
    return {
        "window": {"n_trades": len(recent), "n_distinct_dates": len(recent_dates),
                  "start": recent_dates[0] if recent_dates else None,
                  "end": recent_dates[-1] if recent_dates else None},
        "pct_return_distribution_recent": distribution_stats(all_pct_recent),
        "pct_return_distribution_full_history": distribution_stats(
            [pct_return_on_capital(t["dollar_pnl"], t["entry_premium"], t["qty"]) for t in trades]),
        "live_faithful_capital_curve_recent_at_baseline_equity": curve_row_recent,
        "live_faithful_capital_curve_full_history_at_baseline_equity": curve_row_full,
        "dollars_per_trading_day_recent": (
            round(curve_row_recent["total_pnl"] / curve_row_recent["n_distinct_days_included"], 2)
            if curve_row_recent["n_distinct_days_included"] else None),
        "dollars_per_trading_day_full_history": (
            round(curve_row_full["total_pnl"] / curve_row_full["n_distinct_days_included"], 2)
            if curve_row_full["n_distinct_days_included"] else None),
    }


def real_fills_cross_check(real_fills: list[dict], sim_trades: list[dict]) -> dict:
    real_pct = [pct_return_on_capital(t["dollar_pnl"], t["entry_premium"], t["qty"]) for t in real_fills]
    sim_pct = [pct_return_on_capital(t["dollar_pnl"], t["entry_premium"], t["qty"]) for t in sim_trades]
    return {
        "disclosure": ("journal/trades.csv account_id=='safe' -- REAL broker fills, core "
                      "account only. Small-n (real trading only began recently vs the "
                      "18-month simulated window) -- reported as a directional cross-check, "
                      "not a replacement for the simulated population."),
        "n_real_fills": len(real_fills),
        "real_fills_pct_return_distribution": distribution_stats(real_pct),
        "simulated_population_pct_return_distribution": distribution_stats(sim_pct),
        "real_fills_total_pnl": round(sum(t["dollar_pnl"] for t in real_fills), 2) if real_fills else None,
        "real_fills_date_range": (
            {"start": min(t["date"] for t in real_fills), "end": max(t["date"] for t in real_fills)}
            if real_fills else None),
    }


# =============================================================================================
# main
# =============================================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-bold", action="store_true",
                    help="skip the ~100s Bold full-history re-walk")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    print("[capital-efficiency] loading Safe 191-trade validated population...")
    safe_trades, safe_raw = load_safe_population()
    safe_params = load_safe_params()
    agg_params = load_agg_params()

    print(f"[capital-efficiency] n_safe_trades={len(safe_trades)}")
    print("[capital-efficiency] computing qty-correction finding (#0)...")
    qty_corr = qty_correction_finding(safe_trades, safe_params)
    print(json.dumps(qty_corr, indent=2))

    print("[capital-efficiency] computing pct-return distribution (task item 1)...")
    pct_section = pct_return_section(safe_trades)

    print("[capital-efficiency] computing liquidity proxy from cached OPRA bar volume "
          "(task item 2)...")
    liq_section = liquidity_section(safe_trades, safe_params)

    print("[capital-efficiency] computing Safe capital curve across equity grid "
          "(task item 3)...")
    safe_curve = safe_capital_curve_section(safe_trades, safe_params)

    bold_curve = None
    bold_trades: list[dict] = []
    if not args.skip_bold:
        print("[capital-efficiency] re-running Bold's validated ATM full-history replay "
              "(~100s, block_elite_bull=True, min_contracts=5)...")
        bold_result = run_bold_atm_replay()
        bold_trades = bold_result["rows"]
        print(f"[capital-efficiency] n_bold_trades={len(bold_trades)}")
        print("[capital-efficiency] computing Bold capital curve across equity grid...")
        bold_curve = bold_capital_curve_section(bold_trades, agg_params)
    else:
        print("[capital-efficiency] --skip-bold set: Bold capital curve omitted this run.")

    print("[capital-efficiency] computing frequency arithmetic (task item 4)...")
    freq_section = frequency_section(safe_curve["rows"])

    print("[capital-efficiency] computing recency check (task item 5)...")
    recency = recency_section(safe_trades, safe_params)

    print("[capital-efficiency] computing real-fills cross-check (task item 6)...")
    real_fills = load_real_fills_safe()
    real_check = real_fills_cross_check(real_fills, safe_trades)

    payload = {
        "_doc": ("Capital-efficiency / honest-capital-curve instrument. MEASUREMENT + "
                "ARITHMETIC ONLY -- zero trading-path edits. See module docstring for the "
                "qty-correction (#0) and liquidity-data-gap findings."),
        "generated_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).isoformat(),
        "source_safe_replay": str(SAFE_REPLAY_JSON.relative_to(REPO)),
        "source_safe_replay_window": safe_raw.get("window"),
        "qty_correction_finding": qty_corr,
        "pct_return_distribution": pct_section,
        "liquidity": liq_section,
        "capital_curve": {"safe": safe_curve, "bold": bold_curve},
        "frequency": freq_section,
        "recency_check_recent_25_trading_days": recency,
        "real_fills_cross_check": real_check,
        "bold_population_n": len(bold_trades),
    }

    out_path = Path(args.out) if args.out else OUT_JSON
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    try:
        shown = out_path.relative_to(REPO)
    except ValueError:
        shown = out_path
    print(f"\n[capital-efficiency] wrote {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
