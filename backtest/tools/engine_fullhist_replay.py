"""engine_fullhist_replay.py -- FULL-HISTORY production-parity replay of the CURRENT LIVE
core-Safe engine, ordered by J 2026-07-23 ("every day we have needs a walkthrough on the
engine -- max days of data and testing"). Scorecard: analysis/recommendations/
engine-fullhist-replay-2026-07-23.{json,md}.

TWO-LAYER DESIGN (the SIM-EXIT-SHAPE-PARITY trap, see queue.md + regime_readjudication_
correctexit.py 2026-07-17, applies here exactly and is deliberately routed around):

  ENTRY layer: backtest/lib/orchestrator.py#run_backtest(**SAFE_BASE_LIVE) -- the
    engine_cli-equivalent score+gate+filter cascade (markdown/specs/BACKTEST-AS-HEARTBEAT-
    DESIGN.md). SAFE_BASE_LIVE is elite_bear_level_reject_gate_ab.py's SAFE_BASE (itself a
    hand-built, field-cited translation of automation/state/params.json), re-verified field-
    by-field against TODAY's (2026-07-22) params.json before this run -- zero drift found in
    any of: strike tier (ATM, V15_SAFE_TIERS <$10K), premium catastrophe caps (-50%/-50%),
    tp1 (0.5/0.8), runner (2.5x), chart-stop buffer (0.5), time-stop (15:40 ET), f9_vol_mult
    (0.7), min_triggers (1 bear/2 bull), entry window (09:35-15:00 ET), block_level_rejection,
    block_elite_bull (VIX[0,25)), entry_bar_body_pct_min (0.2), block_bull_1100_1200,
    midday_trendline_gate (off), ribbon momentum/duration gates (both off, L107), vix_bear_
    hard_cap (23.0), per_trade_risk_cap_pct (0.30, Rule 6 Safe), enable_bullish (true, OP-16),
    min_entry_premium (0.3). Only initial_equity is bumped from the study's $1,724.53
    (2026-07-17 live-verified) to $1,746.75 (2026-07-11 CLAUDE.md live-verified figure, the
    most current on record) -- both static (this repo's established full-window-study
    convention; NOT a compounding account curve, disclosed in the scorecard).

  EXIT layer: backtest/lib/exit_manager_walk.py#walk_exit_manager, driving the REAL
    automation/state/fleet/exit_manager.py#plan_exit_actions decision core under the REAL
    automation/state/fleet/strategies.py#RIBBON_RIDE.exit.to_dict() shape -- NOT
    simulate_trade_real's dollar_pnl, which sources exit knobs from params.json's TOP-LEVEL
    keys (profit_lock_mode="fixed", tp1_premium_pct=0.5, runner_max_premium_pct=2.5) and is
    KNOWN-DIVERGENT from the live shape (profit_lock_mode="trailing" chandelier arm+5%/
    trail15%, tp1_premium_pct=1.0, runner_target_pct=99.0, stop_mode="structure"). Every raw
    TradeFill.dollar_pnl from run_backtest is DISCARDED; only entry metadata (time, side,
    strike, qty, entry_premium, trigger_level, triggers_fired) survives into the exit re-
    derivation. This is the SAME pattern regime_readjudication_correctexit.py shipped
    2026-07-17 (16-trade cohort), extended here to the FULL population of ribbon_ride entries
    across the full 18-month OPRA-covered window.

FIDELITY IMPROVEMENT over the 2026-07-17 precedent: that script passed ribbon_tick_df=None
(ribbon_flip_back exits never fire in its replay) because its 16-trade cohort didn't warrant
building the alignment. This script builds ribbon_tick_df PROPERLY: computes the ribbon once
over the FULL continuous RTH close series (identical to what run_backtest computes internally
for scoring -- same warmup, same continuity across days), then for each trade does a backward
(no-lookahead) merge_asof onto that trade's OWN option-contract bar timestamps, so
ribbon_flip_back exits are modeled instead of silently disabled.

SCOPE DISCLOSURE (OP-20): orchestrator.run_backtest only models the RIDE_THE_RIBBON family
(BEARISH_REJECTION_RIDE_THE_RIBBON / BULLISH_RECLAIM_RIDE_THE_RIBBON) -- the two setups in
params.json's setups_allowed. It does NOT model the "extra setups" dispatched via
setup_dispatch.py (bollinger_squeeze, vwap_continuation, vwap_reclaim_failed_break,
vix_regime_dayside, double_bottom_base_quiet, gap_and_go) -- each of those places real Safe-
paper orders live today but has no production-parity FULL-HISTORY batch-replay harness in
this codebase as of this run (exit_manager_replay.py's own scope is single-day/today-only).
This scorecard is therefore the CORE ribbon_ride path's honest full-history number -- it
UNDERSTATES total Safe-account P&L by omitting the extra-setup contribution, and is silent on
Bold/aggressive entirely (Safe-account params + strike tier only, per the task's brief).

Real OPRA fills only: any trade whose contract CSV is not locally cached (backtest/data/
options/{symbol}.csv, populated by tools/fetch_option_data.py) is EXCLUDED and counted, never
synthesized via Black-Scholes -- run_backtest(use_real_fills=True) itself already returns None
(no trade) from simulate_trade_real for any entry whose contract isn't cached (lib/
simulator_real.py:420-422), so the raw TradeFill population is already real-fills-only at
entry; this script's own OPRA lookup for the EXIT re-derivation is a second, independent check
(n_no_opra_for_exit, should be ~0 given the entry already required the same cache).

Run: backtest/.venv/Scripts/python.exe backtest/tools/engine_fullhist_replay.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]           # backtest/
ROOT = REPO.parent                                     # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import elite_bear_level_reject_gate_ab as eb  # noqa: E402 -- SAFE_BASE, classify_tier, entry_date
import strategies as fleet_strategies  # noqa: E402  -- automation/state/fleet/strategies.py
from lib.orchestrator import run_backtest  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

DATA = REPO / "data"
SPY_FILE = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
VIX_FILE = DATA / "vix_5m_2025-01-01_2026-07-22.csv"

FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 22)
TIME_STOP_ET = dt.time(15, 40)   # matches SAFE_BASE's time_stop_minutes_before_close=20

OUT_JSON = ROOT / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.md"

# Single delta from eb.SAFE_BASE: refresh initial_equity to the most current live-verified
# figure (CLAUDE.md, 2026-07-11: $1,746.75; the 2026-07-17 study used $1,724.53). Both static
# across the whole window -- see module docstring.
SAFE_BASE_LIVE = dict(eb.SAFE_BASE, initial_equity=1746.75)

# Sanity anchors (task step 5) -- the replay MUST reproduce these before its number is trusted.
# NOTE (corrected after ground-truth check against journal/trades.csv, account_id=="safe"):
# the task brief's "2026-07-17 core ~= +$342 engine-only" is core_safe($151)+core_bold($191)
# COMBINED (exit-manager-replay-2026-07-17.json per_arm) -- core_safe ALONE (this script's
# scope) is +$151.00 on 4 RIDE_THE_RIBBON entries (11:06 P744 ELITE -37, 11:40 P745 ELITE -102,
# 13:01 P746 TRENDLINE +241, 14:49 P743 TRENDLINE -56; a 5th core_safe fill that day,
# 14:03 bollinger_squeeze +105, is OUT OF SCOPE -- not a ribbon_ride setup). The task brief's
# "2026-07-21/22 ~= zero core entries" is also imprecise for 07-21: ground truth shows exactly
# ONE core_safe RIDE_THE_RIBBON entry that day (14:58 P748 TRENDLINE, dollar_pnl=$0, exit
# ribbon_flip) -- 07-22 genuinely has zero. Anchors below use the CORRECTED ground truth.
ANCHOR_DAY = dt.date(2026, 7, 17)
ANCHOR_DAY_EXPECT_PNL = 151.00
ANCHOR_DAY_EXPECT_ENTRIES = [  # (time_et HH:MM, strike, side, tier, live_dollar_pnl)
    ("11:06", 744, "P", "ELITE", -37.0),
    ("11:40", 745, "P", "ELITE", -102.0),
    ("13:01", 746, "P", "TRENDLINE", 241.0),
    ("14:49", 743, "P", "TRENDLINE", -56.0),
]
ANCHOR_DAY_TOL = 60.0
ANCHOR_QUIET_DAY = dt.date(2026, 7, 21)
ANCHOR_QUIET_DAY_EXPECT_ENTRIES = [("14:58", 748, "P", "TRENDLINE", 0.0)]
ANCHOR_ZERO_DAY = dt.date(2026, 7, 22)


def log(msg: str) -> None:
    print(f"[fullhist-replay] {msg}", flush=True)


def naive_dt(ts) -> dt.datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts


def build_ribbon_lookup(spy_df: pd.DataFrame) -> pd.DataFrame:
    """Continuous RTH-only ribbon (fast/pivot/slow EMA warmup preserved across days,
    byte-identical inputs to what orchestrator.run_backtest computes internally for scoring).
    Returns a 2-col frame (timestamp_et, stack) for backward-merge_asof alignment onto any
    option contract's own bar timestamps."""
    rth_mask = (
        (spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_df["timestamp_et"].dt.time < dt.time(16, 0))
    )
    spy_rth = spy_df.loc[rth_mask].reset_index(drop=True)
    ribbon = compute_ribbon(spy_rth["close"])
    out = spy_rth[["timestamp_et"]].copy()
    out["stack"] = ribbon["stack"].values
    return out.sort_values("timestamp_et").reset_index(drop=True)


def ribbon_tick_df_for(opt_df: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> pd.DataFrame:
    """Backward (no-lookahead) as-of join: each option bar timestamp gets the ribbon stack
    from the most recent closed 5-min SPY bar at or before it. Row-order/count matches
    opt_df exactly, as walk_exit_manager's positional ribbon_stack_at(idx) requires."""
    left = opt_df[["timestamp_et"]].copy()
    left_ts = left["timestamp_et"]
    if getattr(left_ts.dt, "tz", None) is not None:
        left["timestamp_et"] = left_ts.dt.tz_localize(None)
    right = ribbon_lookup.copy()
    right_ts = right["timestamp_et"]
    if getattr(right_ts.dt, "tz", None) is not None:
        right["timestamp_et"] = right_ts.dt.tz_localize(None)
    # opt_df / ribbon_lookup are already chronologically ordered (raw OHLC bar series); do NOT
    # re-sort here -- merge_asof's positional row-order-preservation (left join, one row out per
    # row in) is exactly what walk_exit_manager's positional ribbon_stack_at(idx) requires, and a
    # sort on an already-sorted key is a stable no-op so this is defensive, not a behavior change.
    left = left.sort_values("timestamp_et", kind="stable")
    right = right.sort_values("timestamp_et", kind="stable")
    merged = pd.merge_asof(left, right, on="timestamp_et", direction="backward")
    assert len(merged) == len(opt_df), "merge_asof row count drifted from opt_df -- alignment broken"
    return merged.reset_index(drop=True)[["stack"]]


def main() -> int:
    t_start = time.time()
    log(f"loading merged full-history SPY/VIX data: {SPY_FILE.name} / {VIX_FILE.name}")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    log(f"  spy rows={len(spy_df)} range={spy_df['timestamp_et'].min()} .. {spy_df['timestamp_et'].max()}")

    log("computing continuous RTH ribbon lookup (for exit-layer ribbon_flip_back fidelity)")
    ribbon_lookup = build_ribbon_lookup(spy_df)

    log("running run_backtest(**SAFE_BASE_LIVE) -- engine_cli-equivalent entry/gate/filter cascade")
    t0 = time.time()
    r = run_backtest(spy_df, vix_df, start_date=FULL_START, end_date=FULL_END, **SAFE_BASE_LIVE)
    entry_elapsed = time.time() - t0
    log(f"  run_backtest done in {entry_elapsed:.1f}s -- {len(r.trades)} raw entries "
        f"(dollar_pnl DISCARDED -- WRONG exit shape)")

    correct_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    log(f"CORRECT exit shape (strategies.py#RIBBON_RIDE.exit.to_dict()): {correct_shape}")

    rows = []
    n_no_opra = 0
    n_no_spy_day = 0
    t1 = time.time()
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

        entry_time_et = naive_dt(t.entry_time_et)
        entry_premium = float(t.entry_premium)
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        qty = int(t.qty)
        tier = eb.classify_tier(t.triggers_fired)
        rtd = ribbon_tick_df_for(opt_df, ribbon_lookup)

        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et, entry_premium=entry_premium,
            qty=qty, exit_shape=correct_shape, structure_stop_enabled=True,
            trigger_level=trigger_level, strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        rows.append({
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "setup": t.setup, "side": t.side, "tier": tier, "symbol": symbol,
            "qty": qty, "entry_premium": round(entry_premium, 4), "triggers": t.triggers_fired,
            "trigger_level": trigger_level,
            "wrong_exit_pnl_discarded": round(float(t.dollar_pnl), 2),
            "dollar_pnl": res.dollar_pnl,
            "exit_reason": res.exit_reason,
            "resolved_stop_mode": res.stop_mode,
            "hold_minutes": res.hold_minutes,
            "n_ticks_walked": res.n_ticks_walked,
            "resolved": res.resolved,
        })

    exit_elapsed = time.time() - t1
    log(f"exit re-derivation done in {exit_elapsed:.1f}s -- n_replayed={len(rows)} "
        f"n_no_opra_excluded={n_no_opra} n_no_spy_day_excluded={n_no_spy_day}")

    if not rows:
        log("FATAL: zero trades replayed -- aborting")
        return 1

    total_elapsed = time.time() - t_start
    write_scorecard(rows, r, n_no_opra, n_no_spy_day, spy_df, entry_elapsed, exit_elapsed, total_elapsed)
    return 0


def write_scorecard(rows, r, n_no_opra, n_no_spy_day, spy_df, entry_elapsed, exit_elapsed, total_elapsed) -> None:
    df = pd.DataFrame(rows)
    df["dollar_pnl"] = df["dollar_pnl"].astype(float)

    total_pnl = round(df["dollar_pnl"].sum(), 2)
    n_trades = len(df)
    wins = df[df["dollar_pnl"] > 0]
    losses = df[df["dollar_pnl"] <= 0]
    win_rate = round(len(wins) / n_trades, 4) if n_trades else None
    gross_win = wins["dollar_pnl"].sum()
    gross_loss = -losses["dollar_pnl"].sum()
    profit_factor = round(gross_win / gross_loss, 3) if gross_loss > 0 else None
    avg_trade = round(total_pnl / n_trades, 2) if n_trades else None

    # --- calendar-day P&L series across the FULL RTH day set (0 on no-trade days) ---
    all_dates = sorted(spy_df["timestamp_et"].dt.date.unique())
    per_day = df.groupby("date")["dollar_pnl"].sum()
    day_series = pd.Series({str(d): float(per_day.get(str(d), 0.0)) for d in all_dates})
    n_calendar_days = len(all_dates)
    n_trading_days = int((day_series != 0.0).sum())
    dollar_per_calendar_day_avg = round(total_pnl / n_calendar_days, 2)
    dollar_per_calendar_day_median = round(day_series.median(), 2)
    trading_day_pnls = day_series[day_series != 0.0]
    dollar_per_trading_day_avg = round(trading_day_pnls.mean(), 2) if n_trading_days else None
    dollar_per_trading_day_median = round(trading_day_pnls.median(), 2) if n_trading_days else None
    pct_days_traded = round(100.0 * n_trading_days / n_calendar_days, 1)

    # --- equity curve + drawdown ---
    cum = day_series.cumsum()
    running_max = cum.cummax()
    drawdown = cum - running_max
    max_drawdown = round(float(drawdown.min()), 2)
    max_drawdown_date = str(drawdown.idxmin())
    equity_curve = [{"date": d, "day_pnl": round(float(day_series[d]), 2), "cum_pnl": round(float(cum[d]), 2)}
                     for d in day_series.index]

    best_days = day_series.sort_values(ascending=False).head(10)
    worst_days = day_series.sort_values(ascending=True).head(10)

    # --- per-regime split ---
    def regime_of(d: str) -> str:
        dd = dt.date.fromisoformat(d)
        if dd <= dt.date(2025, 6, 30):
            return "2025H1"
        if dd <= dt.date(2025, 12, 31):
            return "2025H2"
        return "2026"

    df["regime"] = df["date"].apply(regime_of)
    per_regime = {}
    for reg, g in df.groupby("regime"):
        reg_wins = g[g["dollar_pnl"] > 0]
        per_regime[reg] = {
            "n_trades": len(g), "total_pnl": round(g["dollar_pnl"].sum(), 2),
            "win_rate": round(len(reg_wins) / len(g), 4) if len(g) else None,
            "avg_trade": round(g["dollar_pnl"].mean(), 2) if len(g) else None,
        }

    # --- per-setup / per-direction / per-tier attribution ---
    per_setup = {}
    for setup, g in df.groupby("setup"):
        per_setup[setup] = {"n_trades": len(g), "total_pnl": round(g["dollar_pnl"].sum(), 2),
                             "win_rate": round((g["dollar_pnl"] > 0).mean(), 4)}
    per_side = {}
    for side, g in df.groupby("side"):
        per_side[side] = {"n_trades": len(g), "total_pnl": round(g["dollar_pnl"].sum(), 2),
                           "win_rate": round((g["dollar_pnl"] > 0).mean(), 4)}
    per_tier = {}
    for tier, g in df.groupby("tier"):
        per_tier[tier] = {"n_trades": len(g), "total_pnl": round(g["dollar_pnl"].sum(), 2),
                           "win_rate": round((g["dollar_pnl"] > 0).mean(), 4)}
    per_exit_reason = {}
    for reason, g in df.groupby("exit_reason"):
        per_exit_reason[str(reason)] = {"n_trades": len(g), "total_pnl": round(g["dollar_pnl"].sum(), 2)}

    # --- sanity anchors (task step 5), trade-level not just P&L-sum-level ---
    def replay_entries_for(d: dt.date) -> list[dict]:
        g = df.loc[df["date"] == str(d)]
        return [{"time_et": row["entry_time_et"][11:16], "strike": None, "side": row["side"],
                  "tier": row["tier"], "symbol": row["symbol"], "dollar_pnl": row["dollar_pnl"]}
                 for _, row in g.iterrows()]

    def match_entries(expected: list[tuple], d: dt.date) -> dict:
        replayed = replay_entries_for(d)
        matched, unmatched_expected = [], []
        for (t_et, strike, side, tier, live_pnl) in expected:
            hit = None
            for r_ in replayed:
                if r_["side"] == side and f"{strike:05d}000" in r_["symbol"]:
                    hit = r_
                    break
            if hit is not None:
                matched.append({"expected_time": t_et, "expected_tier": tier,
                                 "expected_pnl": live_pnl, "replay_time": hit["time_et"],
                                 "replay_tier": hit["tier"], "replay_pnl": hit["dollar_pnl"]})
            else:
                unmatched_expected.append({"expected_time": t_et, "strike": strike, "side": side,
                                            "tier": tier, "live_pnl": live_pnl})
        extra_replay = [r_ for r_ in replayed
                         if not any(f"{e[1]:05d}000" in r_["symbol"] and r_["side"] == e[2] for e in expected)]
        return {
            "n_expected": len(expected), "n_matched_by_strike_side": len(matched),
            "matched": matched, "unmatched_expected_live_entries": unmatched_expected,
            "extra_replay_entries_not_in_live": extra_replay,
        }

    anchor_day_pnl = round(float(day_series.get(str(ANCHOR_DAY), 0.0)), 2)
    anchor_day_pnl_pass = abs(anchor_day_pnl - ANCHOR_DAY_EXPECT_PNL) <= ANCHOR_DAY_TOL
    anchor_day_trade_match = match_entries(ANCHOR_DAY_EXPECT_ENTRIES, ANCHOR_DAY)
    anchor_day_trade_level_pass = (
        anchor_day_trade_match["n_matched_by_strike_side"] == anchor_day_trade_match["n_expected"]
    )

    anchor_quiet_match = match_entries(ANCHOR_QUIET_DAY_EXPECT_ENTRIES, ANCHOR_QUIET_DAY)
    anchor_quiet_pass = (
        anchor_quiet_match["n_matched_by_strike_side"] == anchor_quiet_match["n_expected"]
    )

    n_entries_zero_day = int((df["date"] == str(ANCHOR_ZERO_DAY)).sum())
    anchor_zero_pass = n_entries_zero_day == 0

    anchors_all_trade_level_pass = anchor_day_trade_level_pass and anchor_quiet_pass and anchor_zero_pass

    # --- J-framing number ---
    j_framing = {
        "goal_dollar_per_day_low": 100, "goal_dollar_per_day_high": 200,
        "goal_basis": "FOCUS-DOCTRINE $100-200/day at $2K account (per task brief)",
        "actual_dollar_per_calendar_day_avg": dollar_per_calendar_day_avg,
        "actual_dollar_per_trading_day_avg": dollar_per_trading_day_avg,
        "pct_days_traded": pct_days_traded,
        "meets_goal_on_calendar_day_basis": (
            dollar_per_calendar_day_avg >= 100 if dollar_per_calendar_day_avg is not None else None
        ),
        "meets_goal_on_trading_day_basis": (
            dollar_per_trading_day_avg >= 100 if dollar_per_trading_day_avg is not None else None
        ),
    }

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "window": {"start": FULL_START.isoformat(), "end": FULL_END.isoformat(),
                    "n_calendar_rth_days": n_calendar_days},
        "config": {
            "account": "core_safe (Gamma-Safe-2, PA3DHPT7KIQE)",
            "safe_base_live": {k: (str(v) if isinstance(v, (dt.time, tuple)) else v)
                                for k, v in SAFE_BASE_LIVE.items()},
            "correct_exit_shape": correct_shape_for_doc(),
            "structure_stop_enabled": True,
        },
        "data_quality": {
            "n_raw_entries_from_orchestrator": len(r.trades),
            "n_replayed": n_trades,
            "n_excluded_no_opra_cache": n_no_opra,
            "n_excluded_no_spy_day": n_no_spy_day,
            "note": "run_backtest(use_real_fills=True) itself already refuses (returns no trade) "
                     "any entry whose OPRA contract isn't cached (simulator_real.py:420-422) -- "
                     "the raw entry population is already real-fills-only. n_excluded_* here is "
                     "this script's OWN independent re-check during the exit re-derivation pass.",
        },
        "headline": {
            "total_pnl": total_pnl, "n_trades": n_trades, "win_rate": win_rate,
            "profit_factor": profit_factor, "avg_pnl_per_trade": avg_trade,
            "max_drawdown": max_drawdown, "max_drawdown_date": max_drawdown_date,
            "dollar_per_calendar_day_avg": dollar_per_calendar_day_avg,
            "dollar_per_calendar_day_median": dollar_per_calendar_day_median,
            "dollar_per_trading_day_avg": dollar_per_trading_day_avg,
            "dollar_per_trading_day_median": dollar_per_trading_day_median,
            "n_trading_days": n_trading_days, "n_calendar_days": n_calendar_days,
            "pct_days_traded": pct_days_traded,
        },
        "j_framing": j_framing,
        "per_regime": per_regime,
        "per_setup": per_setup,
        "per_side": per_side,
        "per_tier": per_tier,
        "per_exit_reason": per_exit_reason,
        "best_10_days": [{"date": d, "pnl": round(float(v), 2)} for d, v in best_days.items()],
        "worst_10_days": [{"date": d, "pnl": round(float(v), 2)} for d, v in worst_days.items()],
        "equity_curve": equity_curve,
        "sanity_anchors": {
            "_note": "Task brief's anchor wording was imprecise (corrected against journal/"
                     "trades.csv ground truth, account_id=='safe'): 2026-07-17's +$342 is "
                     "core_safe+core_bold COMBINED (core_safe alone=$151.00, 4 ribbon_ride "
                     "entries); 2026-07-21 genuinely has ONE near-zero core_safe entry, not zero.",
            "2026-07-17_core_safe_pnl_sum": {
                "replayed_pnl": anchor_day_pnl, "expected": ANCHOR_DAY_EXPECT_PNL,
                "tolerance": ANCHOR_DAY_TOL, "pnl_sum_pass": anchor_day_pnl_pass,
            },
            "2026-07-17_core_safe_TRADE_LEVEL_match": anchor_day_trade_match,
            "2026-07-17_trade_level_pass": anchor_day_trade_level_pass,
            "2026-07-21_quiet_day_TRADE_LEVEL_match": anchor_quiet_match,
            "2026-07-21_trade_level_pass": anchor_quiet_pass,
            "2026-07-22_expect_zero_entries": {"n_entries": n_entries_zero_day, "pass": anchor_zero_pass},
            "all_anchors_trade_level_pass": anchors_all_trade_level_pass,
        },
        "runtime_seconds": {"entry_layer": round(entry_elapsed, 1), "exit_layer": round(exit_elapsed, 1),
                              "total": round(total_elapsed, 1)},
        "trades": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"HEADLINE: total_pnl=${total_pnl:+.2f} n_trades={n_trades} WR={win_rate} "
        f"$/calendar-day={dollar_per_calendar_day_avg} $/trading-day={dollar_per_trading_day_avg} "
        f"pct_days_traded={pct_days_traded}% max_dd=${max_drawdown}")
    log(f"ANCHORS (trade-level): 07-17 matched {anchor_day_trade_match['n_matched_by_strike_side']}/"
        f"{anchor_day_trade_match['n_expected']} live entries by strike+side "
        f"(pnl_sum=${anchor_day_pnl} vs live $151.00, pass={anchor_day_trade_level_pass}); "
        f"07-21 matched {anchor_quiet_match['n_matched_by_strike_side']}/{anchor_quiet_match['n_expected']} "
        f"(pass={anchor_quiet_pass}); 07-22 zero-entries pass={anchor_zero_pass}; "
        f"ALL_TRADE_LEVEL_PASS={anchors_all_trade_level_pass}")


def correct_shape_for_doc() -> dict:
    return fleet_strategies.by_name("ribbon_ride").exit.to_dict()


def write_markdown(out: dict) -> None:
    h = out["headline"]
    jf = out["j_framing"]
    sa = out["sanity_anchors"]
    L = [
        "# Engine full-history replay -- CURRENT LIVE core-Safe engine, 2025-01-02..2026-07-22",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/engine_fullhist_replay.py`.",
        f"Runtime: entry={out['runtime_seconds']['entry_layer']}s exit={out['runtime_seconds']['exit_layer']}s "
        f"total={out['runtime_seconds']['total']}s.",
        "",
        "## Scope disclosure",
        "",
        "RIDE_THE_RIBBON family only (BEARISH_REJECTION + BULLISH_RECLAIM) -- the two setups "
        "`orchestrator.run_backtest` models. Extra setups (bollinger_squeeze, vwap_continuation, "
        "vwap_reclaim_failed_break, vix_regime_dayside, double_bottom_base_quiet, gap_and_go) are "
        "NOT included -- no full-history batch-replay harness exists for them yet. This "
        "UNDERSTATES total Safe P&L. Safe account only (Bold/aggressive not run).",
        "",
        "Exit shape: REAL `exit_manager.plan_exit_actions` via `strategies.py#RIBBON_RIDE.exit` "
        "(NOT `simulate_trade_real`'s params.json-top-level-keys shape, which is KNOWN-DIVERGENT "
        "-- see SIM-EXIT-SHAPE-PARITY-AUDIT). Every raw entry's `dollar_pnl` was discarded and "
        "re-derived via `exit_manager_walk.walk_exit_manager`.",
        "",
        f"Correct exit shape used: `{out['config']['correct_exit_shape']}`",
        "",
        "## Sanity anchors (fidelity check, task step 5 -- TRADE-LEVEL, corrected vs ground truth)",
        "",
        f"> {sa['_note']}",
        "",
        f"- 2026-07-17 core_safe: replayed P&L sum ${sa['2026-07-17_core_safe_pnl_sum']['replayed_pnl']:+.2f} "
        f"vs live $151.00 (pnl_sum_pass={sa['2026-07-17_core_safe_pnl_sum']['pnl_sum_pass']}); "
        f"TRADE-LEVEL match: {sa['2026-07-17_core_safe_TRADE_LEVEL_match']['n_matched_by_strike_side']}"
        f"/{sa['2026-07-17_core_safe_TRADE_LEVEL_match']['n_expected']} live entries reproduced by "
        f"strike+side (pass={sa['2026-07-17_trade_level_pass']})",
        f"- 2026-07-21 (quiet day, 1 near-zero entry expected): matched "
        f"{sa['2026-07-21_quiet_day_TRADE_LEVEL_match']['n_matched_by_strike_side']}/"
        f"{sa['2026-07-21_quiet_day_TRADE_LEVEL_match']['n_expected']} (pass={sa['2026-07-21_trade_level_pass']})",
        f"- 2026-07-22 (expect zero entries): n_entries={sa['2026-07-22_expect_zero_entries']['n_entries']} "
        f"(pass={sa['2026-07-22_expect_zero_entries']['pass']})",
        f"- **ALL TRADE-LEVEL ANCHORS PASS: {sa['all_anchors_trade_level_pass']}**",
        "",
        "### 2026-07-17 detail",
        "",
        "| Expected (live core_safe) | Replay match |",
        "|---|---|",
    ] + [
        f"| {m['expected_time']} tier={m['expected_tier']} pnl=${m['expected_pnl']:+.0f} | "
        f"time={m['replay_time']} tier={m['replay_tier']} pnl=${m['replay_pnl']:+.2f} |"
        for m in out["sanity_anchors"]["2026-07-17_core_safe_TRADE_LEVEL_match"]["matched"]
    ] + [
        f"| {u['expected_time']} strike={u['strike']}{u['side']} tier={u['tier']} live_pnl=${u['live_pnl']:+.0f} | **NO MATCH -- replay never took this trade** |"
        for u in out["sanity_anchors"]["2026-07-17_core_safe_TRADE_LEVEL_match"]["unmatched_expected_live_entries"]
    ] + [
        f"| *(none expected)* | **EXTRA:** {e['time_et']} {e['symbol']} tier={e['tier']} pnl=${e['dollar_pnl']:+.2f} -- replay took a trade live never took |"
        for e in out["sanity_anchors"]["2026-07-17_core_safe_TRADE_LEVEL_match"]["extra_replay_entries_not_in_live"]
    ] + [
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total P&L (18mo) | ${h['total_pnl']:+,.2f} |",
        f"| N trades | {h['n_trades']} |",
        f"| Win rate | {h['win_rate']} |",
        f"| Profit factor | {h['profit_factor']} |",
        f"| Avg P&L / trade | ${h['avg_pnl_per_trade']:+.2f} |",
        f"| Max drawdown | ${h['max_drawdown']:+,.2f} on {h['max_drawdown_date']} |",
        f"| $/calendar-day (avg over all {h['n_calendar_days']} RTH days) | ${h['dollar_per_calendar_day_avg']:+.2f} |",
        f"| $/calendar-day (median) | ${h['dollar_per_calendar_day_median']:+.2f} |",
        f"| $/trading-day (avg, only the {h['n_trading_days']} days it fired) | ${h['dollar_per_trading_day_avg']:+.2f} |",
        f"| $/trading-day (median) | ${h['dollar_per_trading_day_median']:+.2f} |",
        f"| % of days it trades at all | {h['pct_days_traded']}% |",
        "",
        "## J-framing: FOCUS-DOCTRINE $100-200/day goal at $2K",
        "",
        f"- Actual $/calendar-day: ${jf['actual_dollar_per_calendar_day_avg']:+.2f} "
        f"(meets $100 floor: {jf['meets_goal_on_calendar_day_basis']})",
        f"- Actual $/trading-day (days it fires): ${jf['actual_dollar_per_trading_day_avg']:+.2f} "
        f"(meets $100 floor: {jf['meets_goal_on_trading_day_basis']})",
        f"- Fires on {jf['pct_days_traded']}% of trading days",
        "",
        "## Per-regime",
        "",
        "| Regime | N | Total P&L | WR | Avg/trade |",
        "|---|---|---|---|---|",
    ]
    for reg in ("2025H1", "2025H2", "2026"):
        v = out["per_regime"].get(reg, {})
        if v:
            L.append(f"| {reg} | {v['n_trades']} | ${v['total_pnl']:+,.2f} | {v['win_rate']} | ${v['avg_trade']:+.2f} |")
    L += ["", "## Per-setup / per-side / per-tier", "",
          "| Setup | N | Total P&L | WR |", "|---|---|---|---|"]
    for k, v in out["per_setup"].items():
        L.append(f"| {k} | {v['n_trades']} | ${v['total_pnl']:+,.2f} | {v['win_rate']} |")
    L += ["", "| Side | N | Total P&L | WR |", "|---|---|---|---|"]
    for k, v in out["per_side"].items():
        L.append(f"| {k} | {v['n_trades']} | ${v['total_pnl']:+,.2f} | {v['win_rate']} |")
    L += ["", "| Tier | N | Total P&L | WR |", "|---|---|---|---|"]
    for k, v in out["per_tier"].items():
        L.append(f"| {k} | {v['n_trades']} | ${v['total_pnl']:+,.2f} | {v['win_rate']} |")
    L += ["", "## Best 10 days", "", "| Date | P&L |", "|---|---|"]
    for d in out["best_10_days"]:
        L.append(f"| {d['date']} | ${d['pnl']:+,.2f} |")
    L += ["", "## Worst 10 days", "", "| Date | P&L |", "|---|---|"]
    for d in out["worst_10_days"]:
        L.append(f"| {d['date']} | ${d['pnl']:+,.2f} |")
    L += [
        "",
        "## Data quality",
        "",
        f"- Raw entries from run_backtest: {out['data_quality']['n_raw_entries_from_orchestrator']}",
        f"- Replayed (correct-shape exit derived): {out['data_quality']['n_replayed']}",
        f"- Excluded, no OPRA cache: {out['data_quality']['n_excluded_no_opra_cache']}",
        f"- Excluded, no SPY day: {out['data_quality']['n_excluded_no_spy_day']}",
        "",
        "---",
        "_Source: `backtest/tools/engine_fullhist_replay.py`. Raw JSON with full trade log + "
        "equity curve: `analysis/recommendations/engine-fullhist-replay-2026-07-23.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
