"""multi/lib/signal.py — per-symbol signal builder for the multi-symbol options lane.

The analogue of automation/state/fleet/build_shared_signal.py, but with a different data
source by necessity: build_shared_signal.py DERIVES a fleet signal from the SPY heartbeat's
already-written decisions.jsonl ledger (a per-tick ledger that only exists for SPY). There is
no such ledger for ~70 other symbols, so this module does not derive — it SCORES directly:
given a symbol's own OHLCV bars (and, optionally, a market-wide VIX read + candidate levels),
it builds a `multi.lib.filters.BarContext` and runs `evaluate_bearish_setup` /
`evaluate_bullish_setup` from the sibling fork in this same package, then assembles a signal
dict in the same SHAPE as shared-signal.json (spot/vix/vix_dir/ribbon_stack/production-verdict/
bear{}/bull{}) so anything already written against that shape reads this one the same way.

HARD RULES (per the task):
  * SCORING ONLY. No order placement of any kind lives in this file.
  * No import from backtest/lib/filters.py, automation/state/fleet/*, or any SPY-lane module.
    The only in-repo import is the sibling fork, `multi.lib.filters` (this package).
  * Thresholds read from automation/state/multi/params.json where a key exists there; never
    hardcoded when params.json defines it. As of 2026-08-19 params.json defines NO
    scoring-threshold keys (its `entry`/`risk`/`exits`/`scanners` blocks are execution/risk
    concerns owned by sibling modules, not signal-scoring ones) — the one exception is
    `ACTIVE_BAND_PCT_OF_PRICE` below, which params.json can override via a `signal.
    active_band_pct_of_price` key if a future revision adds one (see _PARAMS_OVERRIDES).
  * Fail loudly: missing/short/malformed bar data raises — this module never substitutes a
    default score for data it could not actually read.
  * No look-ahead: the caller supplies only CLOSED bars (see build_bar_context's docstring for
    the exact contract); `bar_idx` defaults to the LAST row, matching filters.BarContext's own
    "the bar that just closed" convention.
  * Paths anchored to __file__ (REPO_ROOT below), never relative to cwd.

WHAT THIS FILE DOES NOT DO (deliberately out of scope for the four owned files):
  * Fetch market data itself (no Alpaca/network calls) — bars are a parameter, supplied by
    whichever sibling module owns market-data retrieval (the params.json `scanners` block
    names that concern; it is not this file's job).
  * Detect swing-high/low or prior-day levels — `candidate_levels`/`candidate_multi_day_levels`
    are parameters; this file only narrows a given candidate set down to the ones "in play"
    near spot (the $12-ACTIVE_BAND-equivalent proximity gate), it does not generate them.
  * Persist cross-tick LevelState/bounce-history — `level_states` is a parameter; whichever
    module owns level tracking across ticks builds and persists it.
  * Place orders, size trades, or pick a strike/expiry.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd

from multi.lib import filters as mf

REPO_ROOT = Path(__file__).resolve().parents[2]
PARAMS_PATH = REPO_ROOT / "automation" / "state" / "multi" / "params.json"

_REQUIRED_OHLCV_COLUMNS = {"open", "high", "low", "close", "volume"}

# Ribbon needs its slow EMA (48 bars) warmed up to produce a non-None RibbonState; ATR(14)
# needs 15; the volume/range baselines need 20. 50 is the smallest round number clearing all
# three with a small safety margin — below it, ribbon_now/atr_14 would come back None/NaN and
# the filters would silently under-score, which the fail-loud rule forbids.
MIN_BARS_REQUIRED = 50

# was ACTIVE_BAND = 12.0 (setup/scripts/refresh_levels_intraday.py) -- "the engine only
# considers levels within $12 of spot." $12 on SPY at the task's own $700 reference =
# 12/700 = 1.714286% of price. Converted to percent-of-price for the SAME reason
# RIBBON_SPREAD_MIN_PCT_OF_PRICE is (see multi/lib/filters.py's module docstring): this is a
# "how far away in absolute price terms is a level still relevant to today's action" concept,
# which scales with the underlying's price level, not with 5-minute bar noise -- ATR would
# make the window balloon on a volatile day for reasons unrelated to whether a level is still
# structurally in play.
ACTIVE_BAND_PCT_OF_PRICE = 12.0 / mf.REFERENCE_PRICE_ANCHOR_USD  # ≈ 0.0171429 (1.71429%)


class SignalBuildError(ValueError):
    """Raised loudly on missing/short/malformed input — never swallowed into a default score."""


def _load_multi_params(path: Path = PARAMS_PATH) -> dict:
    """Read-only load of automation/state/multi/params.json. This module NEVER writes to it
    (it is one of the four files this task must not modify)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SignalBuildError(f"cannot read multi params at {path}: {e}") from e


def _param_override(params: Optional[dict], key: str, default: float) -> float:
    """Read `signal.<key>` from params.json when present, else the filters.py/signal.py
    module default. As of 2026-08-19 params.json defines no `signal` block, so every call
    here falls through to `default` -- documented, not silent: see the module docstring."""
    if not params:
        return default
    block = params.get("signal")
    if not isinstance(block, dict) or key not in block:
        return default
    return float(block[key])


def select_active_levels(
    candidate_levels: Optional[list[float]], spot: float,
    active_band_pct: float = ACTIVE_BAND_PCT_OF_PRICE,
) -> list[float]:
    """Narrow a candidate level list down to the ones within `active_band_pct` of `spot` --
    the symbol-relative form of setup/scripts/refresh_levels_intraday.py's ACTIVE_BAND=$12.
    Mirrors that script's `abs(price - spot) <= ACTIVE_BAND` filter exactly, just with a
    dynamic (price-relative) band instead of a fixed dollar one."""
    if not candidate_levels or spot is None or spot <= 0:
        return []
    band = active_band_pct * spot
    return sorted({float(p) for p in candidate_levels if abs(float(p) - spot) <= band})


def _validate_bars(bars: pd.DataFrame, symbol: str) -> None:
    if bars is None:
        raise SignalBuildError(f"build_signal[{symbol}]: bars is None")
    if not isinstance(bars, pd.DataFrame):
        raise SignalBuildError(f"build_signal[{symbol}]: bars must be a pandas DataFrame, got {type(bars)}")
    if len(bars) == 0:
        raise SignalBuildError(f"build_signal[{symbol}]: bars is empty")
    missing_cols = _REQUIRED_OHLCV_COLUMNS - set(bars.columns)
    if missing_cols:
        raise SignalBuildError(f"build_signal[{symbol}]: bars missing columns {sorted(missing_cols)}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise SignalBuildError(
            f"build_signal[{symbol}]: bars.index must be a DatetimeIndex (one timestamp per "
            f"bar close) -- got {type(bars.index)}"
        )
    if len(bars) < MIN_BARS_REQUIRED:
        raise SignalBuildError(
            f"build_signal[{symbol}]: only {len(bars)} bars supplied, need >= {MIN_BARS_REQUIRED} "
            f"for ribbon/ATR/volume-baseline warmup -- refusing to score on short bar data "
            f"rather than return a default/degraded score."
        )
    if bars["close"].isna().any():
        raise SignalBuildError(f"build_signal[{symbol}]: bars contains NaN close price(s)")


def _htf_15m_stack_at(htf_bars: Optional[pd.DataFrame], as_of: dt.datetime,
                       ribbon_periods: Optional[dict]) -> Optional[str]:
    """15m-timeframe ribbon stack at the last HTF bar whose timestamp is <= `as_of`. None
    (never a guess) if htf_bars is not supplied or has no bar yet at/before `as_of` -- the
    same None-safe contract filters.BarContext.htf_15m_stack already has (htf_disagrees
    resolves to False on None, matching the SPY original's own None handling)."""
    if htf_bars is None or len(htf_bars) == 0:
        return None
    if not isinstance(htf_bars.index, pd.DatetimeIndex):
        raise SignalBuildError("htf_15m_bars.index must be a DatetimeIndex")
    eligible = htf_bars.index[htf_bars.index <= as_of]
    if len(eligible) == 0:
        return None
    ribbon_df = mf.compute_ribbon(htf_bars["close"], ribbon_periods)
    state = mf.ribbon_at(ribbon_df, eligible[-1])
    return state.stack if state is not None else None


def build_bar_context(
    symbol: str,
    bars: pd.DataFrame,
    *,
    bar_idx: Optional[int] = None,
    vix_now: Optional[float] = None,
    vix_prior: Optional[float] = None,
    vix_5d_ma: float = 0.0,
    vix_20d_ma: float = 0.0,
    candidate_levels: Optional[list[float]] = None,
    candidate_multi_day_levels: Optional[list[float]] = None,
    level_states: Optional[dict] = None,
    fhh_level: Optional[float] = None,
    htf_15m_bars: Optional[pd.DataFrame] = None,
    ribbon_periods: Optional[dict] = None,
    active_band_pct: Optional[float] = None,
) -> mf.BarContext:
    """Build a symbol-parameterized BarContext from raw bars.

    Contract (no-look-ahead, C6): `bars` must contain ONLY bars that have already closed --
    this function does not know wall-clock time and cannot detect a bar that hasn't closed
    yet. `bar_idx` (default: the LAST row, len(bars)-1) is "now" in filters.BarContext's own
    sense; `bars.iloc[:bar_idx+1]` becomes `prior_bars` and nothing after `bar_idx` is ever
    read. Passing a `bars` frame that includes a not-yet-closed bar is a caller bug this
    function cannot detect -- callers own that guarantee.

    Raises SignalBuildError (a ValueError) on any missing/short/malformed input -- never
    silently degrades to a default score.
    """
    _validate_bars(bars, symbol)
    idx = (len(bars) - 1) if bar_idx is None else bar_idx
    if idx < 0 or idx >= len(bars):
        raise SignalBuildError(f"build_bar_context[{symbol}]: bar_idx={idx} out of range for {len(bars)} bars")
    if idx + 1 < MIN_BARS_REQUIRED:
        raise SignalBuildError(
            f"build_bar_context[{symbol}]: bar_idx={idx} leaves only {idx + 1} bars of history, "
            f"need >= {MIN_BARS_REQUIRED} -- refusing to score on short bar data."
        )

    prior_bars = bars.iloc[: idx + 1].reset_index(drop=True)
    bar = prior_bars.iloc[idx]
    timestamp_et = bars.index[idx]
    if not isinstance(timestamp_et, (pd.Timestamp, dt.datetime)):
        raise SignalBuildError(f"build_bar_context[{symbol}]: bar timestamp at idx={idx} is not datetime-like")
    timestamp_et = pd.Timestamp(timestamp_et).to_pydatetime()

    periods = ribbon_periods or mf.DEFAULT_RIBBON_PERIODS
    ribbon_df = mf.compute_ribbon(prior_bars["close"], periods)
    ribbon_now = mf.ribbon_at(ribbon_df, idx)

    lookback = mf.RIBBON_FLIP_LOOKBACK_BARS + 1
    hist_start = max(0, idx - lookback + 1)
    ribbon_history = [mf.ribbon_at(ribbon_df, i) for i in range(hist_start, idx + 1)]

    vol_baseline_20 = mf.vol_baseline_20bar(prior_bars, idx)
    range_baseline_20 = mf.range_baseline_20bar(prior_bars, idx)

    atr_series = mf.atr_wilder(prior_bars, mf.ATR_LENGTH_DEFAULT)
    atr_14 = float(atr_series[idx])
    if atr_14 != atr_14:  # NaN check without importing math/numpy again
        raise SignalBuildError(
            f"build_bar_context[{symbol}]: ATR(14) is NaN at bar_idx={idx} -- insufficient "
            f"warmup despite passing MIN_BARS_REQUIRED; refusing to score without a real "
            f"volatility anchor (every converted threshold in multi.lib.filters depends on it)."
        )
    if atr_14 <= 0:
        raise SignalBuildError(
            f"build_bar_context[{symbol}]: ATR(14)={atr_14} at bar_idx={idx} is non-positive "
            f"-- degenerate/flat bar data, refusing to score (every ATR-relative tolerance "
            f"would collapse to zero, which is not 'no tolerance', it's a data problem)."
        )

    spot = float(bar["close"])
    band_pct = ACTIVE_BAND_PCT_OF_PRICE if active_band_pct is None else active_band_pct
    levels_active = select_active_levels(candidate_levels, spot, band_pct)
    multi_day_levels = select_active_levels(candidate_multi_day_levels, spot, band_pct)

    htf_stack = _htf_15m_stack_at(htf_15m_bars, timestamp_et, periods)

    return mf.BarContext(
        bar_idx=idx, timestamp_et=timestamp_et, bar=bar, prior_bars=prior_bars,
        ribbon_now=ribbon_now, ribbon_history=ribbon_history,
        vix_now=vix_now, vix_prior=vix_prior,
        vol_baseline_20=vol_baseline_20, range_baseline_20=range_baseline_20,
        atr_14=atr_14, symbol=symbol,
        levels_active=levels_active, multi_day_levels=multi_day_levels,
        htf_15m_stack=htf_stack, level_states=(level_states or {}), fhh_level=fhh_level,
        vix_5d_ma=vix_5d_ma, vix_20d_ma=vix_20d_ma,
    )


def _derive_action(bear: mf.SetupResult, bull: mf.BullishSetupResult) -> str:
    """production_action-equivalent verdict, derived purely from passed flags -- mirrors
    build_shared_signal.py's bear_pass/bull_pass -> action derivation. Ribbon stack is
    structurally exclusive (BULL xor BEAR xor MIXED) so both sides passing simultaneously
    should not occur, but the tie-break (higher score wins, tagged) is defensive rather than
    assumed impossible -- never silently pick a side without saying so."""
    if bear.passed and not bull.passed:
        return "ENTER_BEAR"
    if bull.passed and not bear.passed:
        return "ENTER_BULL"
    if bear.passed and bull.passed:
        return "ENTER_BEAR" if bear.bear_score >= bull.bull_score else "ENTER_BULL"
    return "HOLD"


def build_signal(
    symbol: str,
    bars: pd.DataFrame,
    *,
    bar_idx: Optional[int] = None,
    vix_now: Optional[float] = None,
    vix_prior: Optional[float] = None,
    vix_5d_ma: float = 0.0,
    vix_20d_ma: float = 0.0,
    candidate_levels: Optional[list[float]] = None,
    candidate_multi_day_levels: Optional[list[float]] = None,
    level_states: Optional[dict] = None,
    fhh_level: Optional[float] = None,
    htf_15m_bars: Optional[pd.DataFrame] = None,
    ribbon_periods: Optional[dict] = None,
    params: Optional[dict] = None,
    now: Optional[dt.datetime] = None,
    min_triggers: Optional[int] = None,
    sweep_blocker_enabled: Optional[bool] = None,
    write: bool = False,
    out_path: Optional[Path] = None,
) -> dict:
    """Score `symbol` at the latest (or `bar_idx`) closed bar and return a shared-signal-
    shaped dict: {symbol, date, time_et, spot, vix, vix_dir, vix_regime, ribbon_stack,
    ribbon_spread_pct, htf_15m_stack, action, bear{...}, bull{...}, written_at, source}.

    SCORING ONLY -- this function never places an order, never sizes a trade, never picks a
    strike/expiry. `write=True` (default False) additionally atomic-writes the dict as JSON
    to `out_path` (required when write=True) -- callers own where that file lives; this
    module does not presume a canonical output directory the way build_shared_signal.py owns
    shared-signal.json, since automation/state/multi/ already has sibling-owned files
    (scanner-*.json, decisions.jsonl, ...) this task must not collide with.
    """
    p = params if params is not None else _load_multi_params()
    now = now or dt.datetime.now(dt.timezone.utc)

    active_band_pct = _param_override(p, "active_band_pct_of_price", ACTIVE_BAND_PCT_OF_PRICE)
    resolved_min_triggers = (
        min_triggers if min_triggers is not None
        else int(_param_override(p, "min_triggers", 1))
    )
    resolved_sweep = (
        sweep_blocker_enabled if sweep_blocker_enabled is not None
        else bool(_param_override(p, "sweep_blocker_enabled", 0.0))
    )

    ctx = build_bar_context(
        symbol, bars, bar_idx=bar_idx, vix_now=vix_now, vix_prior=vix_prior,
        vix_5d_ma=vix_5d_ma, vix_20d_ma=vix_20d_ma,
        candidate_levels=candidate_levels, candidate_multi_day_levels=candidate_multi_day_levels,
        level_states=level_states, fhh_level=fhh_level, htf_15m_bars=htf_15m_bars,
        ribbon_periods=ribbon_periods, active_band_pct=active_band_pct,
    )

    bear = mf.evaluate_bearish_setup(
        ctx, min_triggers=resolved_min_triggers, sweep_blocker_enabled=resolved_sweep,
    )
    bull = mf.evaluate_bullish_setup(
        ctx, min_triggers=resolved_min_triggers, sweep_blocker_enabled=resolved_sweep,
    )
    action = _derive_action(bear, bull)

    sig = {
        "_doc": "Scored directly from this symbol's own bars by multi/lib/signal.py -- NOT "
                "derived from a per-symbol heartbeat ledger (none exists). SCORING ONLY: no "
                "order was placed to produce this signal and none is placed by reading it.",
        "symbol": symbol,
        "arm": p.get("arm"),
        "shadow_only": p.get("shadow_only"),
        "date": ctx.timestamp_et.strftime("%Y-%m-%d"),
        "time_et": ctx.timestamp_et.strftime("%H:%M"),
        "spot": float(ctx.bar["close"]),
        "atr_14": ctx.atr_14,
        "vix": vix_now,
        "vix_dir": mf.vix_direction(vix_now, vix_prior),
        "vix_regime": bear.vix_regime,  # identical object on bear/bull -- same ctx inputs
        "ribbon_stack": ctx.ribbon_now.stack if ctx.ribbon_now is not None else None,
        "ribbon_spread_pct": ctx.ribbon_now.spread_pct if ctx.ribbon_now is not None else None,
        "htf_15m_stack": ctx.htf_15m_stack,
        "levels_active": ctx.levels_active,
        "multi_day_levels": ctx.multi_day_levels,
        "action": action,
        "bear": {
            "passed": bear.passed, "score": bear.bear_score, "blockers": bear.blockers,
            "triggers_fired": bear.triggers_fired, "rejection_level": bear.rejection_level,
            "confluence": bear.confluence_match is not None,
            "candlestick_pattern": bear.candlestick_pattern,
        },
        "bull": {
            "passed": bull.passed, "score": bull.bull_score, "blockers": bull.blockers,
            "triggers_fired": bull.triggers_fired, "reclaim_level": bull.reclaim_level,
            "confluence": bull.confluence_match is not None,
            "shadow_triggers_fired": bull.shadow_triggers_fired,
        },
        "written_at": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "multi-lib-signal-v1",
    }

    if write:
        if out_path is None:
            raise SignalBuildError("build_signal: write=True requires out_path")
        write_signal(sig, out_path)

    return sig


def default_signal_path(symbol: str) -> Path:
    """Convenience only -- NOT auto-used by build_signal(). Points under
    automation/state/multi/signals/, a subdirectory this task's four owned files do not
    otherwise touch (scanner-*.json/decisions.jsonl/positions.json/exit-state.json/
    circuit-breaker.json are sibling-owned per .gitignore's multi-lane block)."""
    return REPO_ROOT / "automation" / "state" / "multi" / "signals" / f"{symbol}.json"


def write_signal(sig: dict, out_path: Path) -> None:
    """Atomic write (tmp file + os.replace) so a concurrent reader (many symbols may be
    scored in the same sweep) never observes a half-written file."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(out_path.parent), prefix=f".{out_path.name}.", suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(sig, f, indent=2)
        os.replace(tmp_name, out_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
