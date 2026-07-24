"""exit_manager_walk.py -- ticks the REAL live exit_manager.plan_exit_actions decision core
over cached SPY/option bars. Built for GOAL-REPLAY-TODAY-GREEN's EXIT-MANAGER-REPLAY-HARNESS
(iteration 6): the FRAME AUDIT (2026-07-17, see automation/overnight/GOAL-REPLAY-TODAY-GREEN.md)
diagnosed that `backtest/lib/simulator_real.py:simulate_trade_real` -- the exit model every
prior sim-based study in this codebase runs -- is KNOWN-DIVERGENT from the live exit_manager:
live ran the 07-17 746P to +$241; the sim breakeven-zeros it in 2 minutes. Root cause (traced
this build, NOT previously documented): `simulate_trade_real` reads exit knobs from
automation/state/params.json's top-level keys (tp1_premium_pct/v15_profit_lock_mode/
runner_max_premium_pct/...), but heartbeat_core.py:1471-1477's REAL exit_manager registration
for ribbon_ride entries reads `automation/state/fleet/strategies.py#RIBBON_RIDE.exit.to_dict()`
instead -- a DIFFERENT, statically-shipped ExitShape (tp1_premium_pct=1.0 not 0.5,
profit_lock_mode="trailing" not "fixed", runner_target_pct=99.0 not 2.5, stop_mode="structure").
Every sim-based ribbon_ride study (elite_bear_level_reject_gate_ab.py included) has therefore
been testing against the WRONG exit numbers, not just an approximate mechanism -- a second,
deeper divergence than the "5-min vs 1-min bar" resolution gap iterations 2-3 diagnosed.

This module runs the SAME production code (`automation/state/fleet/exit_manager.py
plan_exit_actions`) tick-by-tick over ANY uniform-cadence bar series (1-minute for today's
real fills, 5-minute for historical backtests where only 5-min OPRA is cached) instead of
re-deriving exit decisions via simulate_trade_real's parallel (and shown-divergent) walk.

FILL-PRICE CONVENTION (extends simulator_real.py's documented, reviewed convention -- not a
new invention): limit-style triggers (TP1, premium/catastrophe stop, profit-lock floor
breach, runner_target) fill EXACTLY at the triggered premium level (a resting-order fill
model). Market-style triggers (ribbon_flip_back, time_stop, structure_stop) fill at that
bar's CLOSE minus DEFAULT_EXIT_SLIPPAGE -- structure_stop is priced this way NOT because it
is imprecise but because trigger_level is a SPY price level, not an option premium; there is
no limit-price equivalent, and exit_actuator.manage_tick places a real market_sell the instant
the break is detected (see exit_actuator.py:214-220).

TICK-MANAGED SEMANTICS (mirrors heartbeat_core.py:870-883 / exit_actuator.manage_tick exactly):
exits are managed BEFORE a new entry is evaluated each real tick, so a freshly-registered
position's FIRST managed tick is the row strictly AFTER its entry timestamp, never the entry
row itself.
"""
from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

_FLEET_DIR = Path(__file__).resolve().parents[2] / "automation" / "state" / "fleet"
if str(_FLEET_DIR) not in sys.path:
    sys.path.insert(0, str(_FLEET_DIR))
import exit_manager as em  # noqa: E402

DEFAULT_EXIT_SLIPPAGE = 0.02
_MARKET_STAGES = frozenset({"time_stop", "ribbon_flip", "structure_stop"})


@dataclass(frozen=True)
class ExitLeg:
    kind: str            # "SELL_PARTIAL" | "SELL_ALL"
    qty: int
    fill_price: float
    reason: str
    stage: str
    ts_et: dt.datetime
    leg_pnl: float


@dataclass
class WalkResult:
    entry_time_et: dt.datetime
    entry_premium: float
    side: str
    qty: int
    legs: list = field(default_factory=list)
    dollar_pnl: float = 0.0
    exit_time_et: Optional[dt.datetime] = None
    exit_reason: str = ""
    hold_minutes: int = 0
    resolved: bool = False
    n_ticks_walked: int = 0
    stop_mode: str = "premium"
    trigger_level: Optional[float] = None


def last_closed_bar_close_at(five_min_df: pd.DataFrame, as_of_ts) -> Optional[float]:
    """Latest 5-min SPY bar whose START + 5min <= as_of_ts (fully closed by then). Mirrors
    heartbeat_core.py's `bc["bar"]["close"]` (trig_idx=n-2) convention: when the walk ITSELF
    runs at 5-min cadence, this naturally resolves to the previous row; when the walk runs at
    1-min cadence (today), this independently re-derives the correct 5-min-native closed bar
    rather than approximating it from 1-min data (structure_stop is inherently 5-min-native
    per v15.3 chart-stop-primary doctrine)."""
    ts = pd.Timestamp(as_of_ts)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    ts_col = five_min_df["timestamp_et"]
    if getattr(ts_col.dt, "tz", None) is not None:
        ts_col = ts_col.dt.tz_localize(None)
    closes_at = ts_col + pd.Timedelta(minutes=5)
    eligible = five_min_df.loc[closes_at <= ts]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1]["close"])


def ribbon_stack_at(ribbon_df: Optional[pd.DataFrame], idx: int) -> Optional[str]:
    if ribbon_df is None or idx < 0 or idx >= len(ribbon_df):
        return None
    val = ribbon_df.iloc[idx]["stack"]
    return None if pd.isna(val) else str(val)


def _stage_fill_level(stage: str, state_in: em.ExitState, state_after: em.ExitState) -> Optional[float]:
    """The premium level a limit-style stage fills at, recomputed from the IMMUTABLE
    entry-time fields (never re-derived from a mutated copy) plus the evolving runner_stop
    where the stage IS the runner-stop check. Returns None for market-style stages."""
    if stage == "tp1":
        return state_in.entry_premium * (1.0 + state_in.tp1_premium_pct)
    if stage == "runner_target":
        return state_in.entry_premium * (1.0 + state_in.runner_target_pct)
    if stage in ("premium_stop", "profit_lock_floor"):
        # EXITMGR-STAGE-LABEL-CONFLATION (2026-07-23): exit_manager.py now emits
        # "profit_lock_floor" as its own stage (was hardcoded "premium_stop" even when the
        # pre-TP1 lock floor -- not the static catastrophe cap -- fired). Same runner_stop
        # check, same limit-style fill level either way; only the live journal label split.
        return (state_in.runner_stop_premium if state_in.runner_stop_premium is not None
                else state_in.entry_premium * (1.0 + state_in.premium_stop_pct))
    if stage in ("trail", "be_stop"):
        return state_after.runner_stop_premium
    return None  # time_stop / ribbon_flip / structure_stop -> market fill


def _fill_price(stage: str, level: Optional[float], bar_close: float) -> float:
    if stage in _MARKET_STAGES or level is None:
        return max(0.01, bar_close - DEFAULT_EXIT_SLIPPAGE)
    return max(0.01, level)


def walk_exit_manager(
    *, symbol: str, side: str, entry_time_et, entry_premium: float, qty: int,
    exit_shape: dict, structure_stop_enabled: bool, trigger_level: Optional[float],
    strategy: str, time_stop_et: dt.time,
    opt_df: pd.DataFrame, ribbon_tick_df: Optional[pd.DataFrame],
    five_min_spy_df: pd.DataFrame,
) -> WalkResult:
    """Walk ONE position from entry through resolution via the REAL exit_manager decision
    core. `opt_df` (columns: timestamp_et, open/high/low/close) and `ribbon_tick_df` (same
    row cadence/count as opt_df, column 'stack') must share the SAME bar interval (1-min or
    5-min); `five_min_spy_df` is ALWAYS the 5-minute SPY series regardless of that interval
    (structure_stop is 5-min-native -- see last_closed_bar_close_at). Pure function: no I/O,
    no mutation of inputs.
    """
    state = em.ExitState.from_entry(
        symbol=symbol, side=side, entry_premium=entry_premium, qty=qty,
        exit_shape=exit_shape, strategy=strategy, trigger_level=trigger_level,
        structure_stop_enabled=structure_stop_enabled)

    opt_df = opt_df.reset_index(drop=True)
    ts_col = opt_df["timestamp_et"]
    if not pd.api.types.is_datetime64_any_dtype(ts_col):
        ts_col = pd.to_datetime(ts_col)
    if getattr(ts_col.dt, "tz", None) is not None:
        ts_col = ts_col.dt.tz_localize(None)
    opt_df = opt_df.assign(timestamp_et=ts_col)

    entry_ts = pd.Timestamp(entry_time_et)
    if entry_ts.tzinfo is not None:
        entry_ts = entry_ts.tz_localize(None)

    after = opt_df.index[opt_df["timestamp_et"] > entry_ts]
    result = WalkResult(entry_time_et=entry_time_et, entry_premium=entry_premium, side=side,
                         qty=qty, stop_mode=state.stop_mode, trigger_level=state.trigger_level)
    if len(after) == 0:
        result.exit_reason = "no_bars_after_entry"
        return result
    start_idx = int(after[0])

    open_qty = qty
    realized = 0.0
    n_ticks = 0

    for idx in range(start_idx, len(opt_df)):
        bar = opt_df.iloc[idx]
        ts = bar["timestamp_et"]
        # POINT-SAMPLE, not bar extremes (fidelity fix found building this harness, tested
        # 2026-07-17): exit_actuator's real live tick reads fleet_broker.get_option_quote_hilo
        # -- a SINGLE NBBO snapshot (ask, bid) at the instant the heartbeat fires, NOT a range
        # swept over the following 60 seconds. Using bar.high/bar.low (the established 5-min-
        # bar convention in simulator_real.py, valid there because a 5-min bar IS the natural
        # per-check window) over-triggers at 1-min cadence: a same-run test on the 14:03
        # bollinger_squeeze trade showed bar.low catching a genuine-but-fleeting $0.92
        # intra-minute wick (bar 14:04:00-05:00, open=0.95 close=1.20) that a live point-sample
        # at the tick instant would almost certainly have missed (recovered same-minute). Using
        # the bar's OPEN as both best/worst approximates "the quote value nearest this tick's
        # fire instant" -- a genuine market print, not a fabricated value, and the closest
        # available analog to a live NBBO snapshot at 1-min-bar resolution.
        best = float(bar["open"])
        worst = float(bar["open"])
        now_et = ts.time()
        n_ticks += 1

        flip = False
        if ribbon_tick_df is not None and idx < len(ribbon_tick_df) and strategy != "adopted_manual":
            stack = ribbon_stack_at(ribbon_tick_df, idx)
            if stack in ("BULL", "BEAR"):
                flip = (stack == "BULL") if side == "P" else (stack == "BEAR")

        closed5 = last_closed_bar_close_at(five_min_spy_df, ts)

        state_in = state
        dec = em.plan_exit_actions(
            state_in, best_premium=best, worst_premium=worst, open_qty=open_qty,
            now_et=now_et, ribbon_flip_back=flip, time_stop_et=time_stop_et,
            last_closed_5m_close=closed5)
        state = dec.state

        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            level = _stage_fill_level(a.stage, state_in, state)
            px = _fill_price(a.stage, level, float(bar["close"]))
            leg_pnl = (px - entry_premium) * a.qty * 100.0
            realized += leg_pnl
            open_qty -= a.qty
            result.legs.append(ExitLeg(kind=a.kind, qty=a.qty, fill_price=round(px, 4),
                                        reason=a.reason, stage=a.stage,
                                        ts_et=ts.to_pydatetime(), leg_pnl=round(leg_pnl, 2)))
        if dec.closes_position:
            result.resolved = True
            result.exit_time_et = ts.to_pydatetime()
            result.exit_reason = dec.actions[-1].reason
            break

    result.n_ticks_walked = n_ticks
    result.dollar_pnl = round(realized, 2)
    if result.exit_time_et is not None:
        delta_min = (result.exit_time_et - entry_time_et).total_seconds() / 60.0
        result.hold_minutes = int(round(delta_min))
    if not result.resolved and open_qty > 0:
        # Data exhausted before any exit fired -- force-close at the LAST available bar's
        # close so no position leaks P&L-unaccounted. Disclosed via exit_reason, never
        # silently dropped (OP-33 visibility rule).
        last_bar = opt_df.iloc[-1]
        px = max(0.01, float(last_bar["close"]) - DEFAULT_EXIT_SLIPPAGE)
        leg_pnl = (px - entry_premium) * open_qty * 100.0
        realized += leg_pnl
        result.legs.append(ExitLeg(kind="SELL_ALL", qty=open_qty, fill_price=round(px, 4),
                                    reason="data_exhausted_force_close", stage="force_close",
                                    ts_et=last_bar["timestamp_et"].to_pydatetime(),
                                    leg_pnl=round(leg_pnl, 2)))
        result.dollar_pnl = round(realized, 2)
        result.exit_time_et = last_bar["timestamp_et"].to_pydatetime()
        result.exit_reason = "data_exhausted_force_close"
        delta_min = (result.exit_time_et - entry_time_et).total_seconds() / 60.0
        result.hold_minutes = int(round(delta_min))
    return result
