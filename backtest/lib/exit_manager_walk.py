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

# This module is imported THREE different ways across the codebase (bare top-level
# `import exit_manager_walk` with backtest/lib directly on sys.path -- e.g. every test in
# backtest/tests/test_exit_manager_walk_*.py and backtest/tools/level_target_exit_study.py;
# `from lib import exit_manager_walk`; and `from backtest.lib.exit_manager_walk import ...`).
# A plain relative import breaks the first (bare top-level) form with "attempted relative
# import with no known parent package" -- found + fixed this session (2026-08-02) via the
# regression suite, not assumed. Try relative first (correct for the package-qualified forms),
# fall back to a bare absolute import (correct for the bare top-level form, where
# option_pricing_real.py sits in the same already-on-sys.path directory).
try:
    from .option_pricing_real import assert_intraday_stop_fidelity  # noqa: E402
    from .et_frame import ET_TZ, FRAME_ET_V2, FRAME_WALL_V1, parse_timestamp_et  # noqa: E402
except ImportError:
    from option_pricing_real import assert_intraday_stop_fidelity  # noqa: E402
    from et_frame import ET_TZ, FRAME_ET_V2, FRAME_WALL_V1, parse_timestamp_et  # noqa: E402

DEFAULT_EXIT_SLIPPAGE = 0.02
_MARKET_STAGES = frozenset({"time_stop", "ribbon_flip", "structure_stop"})


def _reframe_series(series: pd.Series, frame: str) -> pd.Series:
    """Frame-normalize a `timestamp_et` SERIES, safely handling ALREADY-NAIVE input.

    Found + fixed same-session (2026-08-02) via the regression suite, not assumed:
    `et_frame.parse_timestamp_et`'s docstring claims "naive input is returned as-is under
    BOTH frames", and its wall-v1 branch honors that (only strips tz if actually present) --
    but its et-v2 branch does NOT: it unconditionally calls `pd.to_datetime(series,
    utc=True)`, which on an ALREADY-NAIVE series REINTERPRETS the wall-clock digits as UTC
    and shifts them by the zone offset (confirmed live: an already-naive true-ET
    "2026-07-27 12:55:00" became "08:55:00" -- a 4-HOUR corruption, not a pass-through).
    This bit `walk_exit_manager` here specifically via `five_min_spy_df`: several confirmed
    callers (e.g. bold_fullhist_replay.py's run_anchor_validation) pre-parse+strip their SPY
    frame to already-naive et-v2 UPSTREAM before calling this module, so blindly routing that
    already-correct series back through `parse_timestamp_et(..., "et-v2")` here corrupted it
    a second time -- caught by test_bold_fullhist_replay.py failing loudly (wrong-direction
    P&L on a real anchor), not shipped silently.

    This helper is NOT a workaround for `et_frame.py` (that file is out of scope -- heavily
    used, heavily guarded by test_et_frame_guards.py, and changing its documented contract is
    a bigger, riskier change than this fix needs). It applies the SAME discipline
    simulator_real._naive_in_frame / simulator_credit._normalize_naive already use for SCALAR
    timestamps (only reframe if actually tz-aware; naive input is trusted as already being in
    the caller's stated frame) at the SERIES level, which `parse_timestamp_et` itself does not
    uniformly provide."""
    if not pd.api.types.is_datetime64_any_dtype(series):
        series = pd.to_datetime(series)
    if getattr(series.dt, "tz", None) is None:
        return series  # already naive -- trust it's already in the caller's stated frame
    return parse_timestamp_et(series, frame)


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


def last_closed_bar_close_at(
    five_min_df: pd.DataFrame, as_of_ts, frame: str = FRAME_WALL_V1
) -> Optional[float]:
    """Latest 5-min SPY bar whose START + 5min <= as_of_ts (fully closed by then). Mirrors
    heartbeat_core.py's `bc["bar"]["close"]` (trig_idx=n-2) convention: when the walk ITSELF
    runs at 5-min cadence, this naturally resolves to the previous row; when the walk runs at
    1-min cadence (today), this independently re-derives the correct 5-min-native closed bar
    rather than approximating it from 1-min data (structure_stop is inherently 5-min-native
    per v15.3 chart-stop-primary doctrine).

    `frame` (added 2026-08-02, DST-FRAME-BLAST-RADIUS-2026-08-02): the et_frame convention
    BOTH `as_of_ts` (if tz-aware) and `five_min_df["timestamp_et"]` are parsed/reframed into,
    via `et_frame.parse_timestamp_et`, instead of an unconditional bare `.dt.tz_localize(None)`
    strip — so a tz-aware `five_min_df` (e.g. straight off a raw CSV read) is compared in the
    SAME frame as `as_of_ts` rather than silently forced to wall-v1 regardless of what frame
    the caller's pipeline actually uses. Default "wall-v1" reproduces the prior bare-strip
    behavior byte-for-byte."""
    ts = pd.Timestamp(as_of_ts)
    if ts.tzinfo is not None:
        if frame == FRAME_ET_V2:
            ts = ts.tz_convert(ET_TZ)
        ts = ts.tz_localize(None)
    ts_col = _reframe_series(five_min_df["timestamp_et"], frame)
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
    opt_df_resolution: Optional[str] = None, allow_5min: bool = True,
    frame: str = FRAME_WALL_V1,
) -> WalkResult:
    """Walk ONE position from entry through resolution via the REAL exit_manager decision
    core. `opt_df` (columns: timestamp_et, open/high/low/close) and `ribbon_tick_df` (same
    row cadence/count as opt_df, column 'stack') must share the SAME bar interval (1-min or
    5-min); `five_min_spy_df` is ALWAYS the 5-minute SPY series regardless of that interval
    (structure_stop is 5-min-native -- see last_closed_bar_close_at). Pure function: no I/O,
    no mutation of inputs.

    `opt_df_resolution` / `allow_5min` (added 2026-08-02, OPTION-BAR-RESOLUTION-BIAS-2026-08-02
    -- see option_pricing_real.py's RESOLUTION DISCLOSURE): OPTIONAL, backward-compatible
    disclosure+guard. Every pre-existing call site leaves `opt_df_resolution=None` (the
    default) -- this is a NO-OP for them, byte-identical behavior. A caller that knows and
    states `opt_df`'s resolution (e.g. `opt_df_resolution="5min"`) can also pass
    `allow_5min=False` to turn an unacknowledged 5-minute walk into a loud ValueError instead
    of a silent under-detection of intra-bar stop/TP touches -- see
    option_pricing_real.assert_intraday_stop_fidelity for the mechanism and the measured
    magnitude ($1,821.75 aggregate swing, one-directional, on the real-fills population).

    `frame` (added 2026-08-02, DST-FRAME-BLAST-RADIUS-2026-08-02 -- the root-fix threading for
    this file, confirmed as THE KEYSTONE consumer: every one of this function's 80+ call
    sites used to get `opt_df["timestamp_et"]` UNCONDITIONALLY bare-tz-stripped -- byte-
    identical to "wall-v1" -- regardless of what frame `entry_time_et` / `five_min_spy_df`
    actually carry; see that artifact's section 2a). States the et_frame convention
    ("wall-v1" default | "et-v2") that `entry_time_et` and any ALREADY-NAIVE timestamp inside
    `five_min_spy_df` / `opt_df` are asserted to already be in. `opt_df["timestamp_et"]` and
    `five_min_spy_df["timestamp_et"]` (via last_closed_bar_close_at) are now parsed through
    `et_frame.parse_timestamp_et(..., frame)` instead of an unconditional bare
    `.dt.tz_localize(None)` -- so a tz-aware `opt_df` (e.g. straight from
    `option_pricing_real.load_contract_bars(symbol)`, the common case across every confirmed
    call site) is joined CONSISTENTLY with `entry_time_et`'s frame instead of being silently
    forced to wall-v1 no matter what `entry_time_et` actually is.

    Default "wall-v1" reproduces the PRIOR unconditional-bare-strip behavior byte-for-byte for
    every pre-2026-08-02 call site (all confirmed wall-v1-consistent today, per that audit's
    section 2c) -- a true no-op for them. A caller whose `entry_time_et` is true-ET (et-v2) --
    e.g. a real broker-fill timestamp, or a SPY series built via `build_rth(frame="et-v2")` --
    MUST pass `frame="et-v2"` explicitly, or risk exactly the ~60-minute winter misjoin this
    fix exists to close (see `bold_fullhist_replay.py`'s `ANCHOR_FILLS` / `run_anchor_
    validation`, which now passes `frame="et-v2"` -- that mechanism was live but zero-exposure
    on 2026-08-02 per that audit's section 3b, since every anchor fill was summer-dated).
    """
    if opt_df_resolution is not None:
        assert_intraday_stop_fidelity(opt_df_resolution, allow_5min=allow_5min)
    if frame not in (FRAME_WALL_V1, FRAME_ET_V2):
        raise ValueError(f"unknown timestamp frame {frame!r}; expected 'wall-v1' or 'et-v2'")
    state = em.ExitState.from_entry(
        symbol=symbol, side=side, entry_premium=entry_premium, qty=qty,
        exit_shape=exit_shape, strategy=strategy, trigger_level=trigger_level,
        structure_stop_enabled=structure_stop_enabled)

    opt_df = opt_df.reset_index(drop=True)
    opt_df = opt_df.assign(timestamp_et=_reframe_series(opt_df["timestamp_et"], frame))

    entry_ts = pd.Timestamp(entry_time_et)
    if entry_ts.tzinfo is not None:
        if frame == FRAME_ET_V2:
            entry_ts = entry_ts.tz_convert(ET_TZ)
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

        closed5 = last_closed_bar_close_at(five_min_spy_df, ts, frame=frame)

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
