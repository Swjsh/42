"""multi/lib/scorer_production.py -- PRODUCTION-scorer adapter for the tickers/multi-symbol lane.

WHY THIS EXISTS. `multi/lib/signal.py::build_signal` scores a symbol's bars through the sibling
FORK, `multi/lib/filters.py` (a symbol-generic port of the live SPY engine's setup checklist,
with every SPY-dollar constant converted to ATR-relative or percent-of-price terms -- see that
file's own module docstring). This module answers a different, narrower question: **if the
multi-symbol lane scored the SAME bars through PRODUCTION's own, unmodified, FROZEN filter stack
(`backtest/lib/filters.py::evaluate_bearish_setup` / `evaluate_bullish_setup` -- the exact code
the live SPY heartbeat runs), would it agree with the fork?** That is a fidelity question, not a
scoring-strategy change: this file is an ADAPTER, not a rewrite. It builds PRODUCTION's own
`backtest.lib.filters.BarContext` (a different dataclass shape than the fork's -- no `symbol`,
no `atr_14`, no `vix_regime` on its results; see the field-by-field notes below) from the SAME
symbol-generic inputs `multi/lib/signal.py` already accepts, and returns a dict in the SAME
shape `build_signal` does, so a caller can diff the two signals for the identical bars.

`backtest/lib/filters.py` is on the CONFIG FREEZE list (`setup/hooks/doctrine.py#FROZEN_TRADING_
PATH`). This module IMPORTS it (`from backtest.lib import filters as bf`, module-qualified so a
test can monkeypatch `bf.evaluate_bullish_setup` etc. and see this module react -- a bare
`from ... import evaluate_bullish_setup` would freeze a stale reference at import time and defeat
that). It never edits it, never monkeypatches it itself, never writes to it.

LEVEL SELECTION IS BYTE-IDENTICAL TO THE FORK -- only the SETUP SCORING differs. `select_active_
levels`, `_param_override`, `_validate_bars`, `MIN_BARS_REQUIRED`, `_htf_15m_stack_at`,
`_derive_action`, `_load_multi_params`, `ACTIVE_BAND_PCT_OF_PRICE`, `write_signal` are all
REUSED BY IMPORT from `multi.lib.signal` (never copied) so the only thing that can differ between
`ms.build_signal(...)` and `scorer_production.build_signal(...)` on the same call is which filter
stack scored the setup. `_derive_action` is duck-typed (reads only `.passed`/`.bear_score`/
`.bull_score`, no isinstance checks -- verified against both `multi/lib/filters.py` and
`backtest/lib/filters.py`), so it works unmodified on PRODUCTION's SetupResult/BullishSetupResult
too.

FIELDS PRODUCTION'S BarContext / SetupResult / BullishSetupResult DO NOT HAVE (verified by
reading `backtest/lib/filters.py` in full, not assumed):
  * BarContext has no `symbol`, no `atr_14` -- `atr_14` is computed here via the FORK's
    `mf.atr_wilder` purely for the output dict's informational `atr_14` key (production's own
    filters never read it off ctx, because ctx has nowhere to put it).
  * SetupResult/BullishSetupResult have no `vix_regime` -- production computes NO regime
    descriptor anywhere in `backtest/lib/filters.py` (grepped; the only "vix_regime" hits in
    that file are the unrelated dormant VIX_REGIME_DAYSIDE edge detector, not a scoring field).
    So `vix_regime` in this module's output dict is always `None` -- documented in `_doc`, never
    invented, and it costs nothing in the key-SET-parity sense because `_doc`'s own presence is
    identical on both sides; only its text differs.
  * SetupResult has no `candlestick_pattern` -- always `None` here (`getattr(..., None)`).

RIBBON_HISTORY RANGE mirrors PRODUCTION'S OWN orchestrator construction verbatim
(`backtest/lib/orchestrator.py` ~line 935: `for j in range(max(0, idx - _rlb - 1), idx + 1)`),
NOT the fork's `build_bar_context` range (`idx - RIBBON_FLIP_LOOKBACK_BARS`, one bar shorter).
The two are functionally equivalent for `detect_ribbon_flip_*` (which windows off the END of the
list) whenever `idx` is away from the very start of the series, but this mirrors production's
literal code rather than relying on that equivalence.

HARD RULES (same as multi/lib/signal.py):
  * SCORING ONLY. No order placement of any kind lives in this file.
  * Fail loudly: missing/short/malformed bar data raises -- never a default/degraded score.
  * No look-ahead: `prior_bars` is sliced to `bars.iloc[:bar_idx+1]` before anything reads it
    (matches the fork's own convention; production's orchestrator instead hands its filter
    functions the FULL day's frame and relies on every reader staying backward-looking off
    `bar_idx` -- the slice here is the more conservative of the two safe conventions and is
    what this module's own task brief specifies).
  * Paths anchored to __file__ / REPO_ROOT, never relative to cwd.

CLI: `python multi/lib/scorer_production.py --smoke SYM1,SYM2,...` -- READ-ONLY compatibility
smoke test. Fetches live bars via `multi.core.fetch_bars_batch` (a network read), scores each
symbol through BOTH this module and the fork, and prints them side by side. No order path is
reachable from this file at all, so there is nothing for the smoke test to place even by accident.
"""

from __future__ import annotations

import datetime as dt
import sys
import traceback
from pathlib import Path
from typing import Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from multi.lib import filters as mf     # noqa: E402 -- FORK: atr_wilder + DEFAULT_RIBBON_PERIODS only
from multi.lib import signal as ms      # noqa: E402 -- FORK: shared helpers, reused BY IMPORT (see module docstring)
from backtest.lib import filters as bf  # noqa: E402 -- PRODUCTION, FROZEN. Imported, never edited.
from backtest.lib import ribbon as br   # noqa: E402 -- PRODUCTION ribbon (compute_ribbon/ribbon_at)


def _build_production_bar_context(
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
) -> tuple[bf.BarContext, float]:
    """Mirror of `multi.lib.signal.build_bar_context`, but builds PRODUCTION's
    `backtest.lib.filters.BarContext` instead of the fork's. Returns `(ctx, atr_14)` --
    `atr_14` travels alongside ctx (rather than on it) because production's BarContext has no
    slot for it; the caller needs the number purely for this module's output dict.

    Raises `multi.lib.signal.SignalBuildError` (a ValueError) on any missing/short/malformed
    input, matching the fork's own fail-loud contract exactly (reuses its validation, not a
    reimplementation).
    """
    ms._validate_bars(bars, symbol)
    idx = (len(bars) - 1) if bar_idx is None else bar_idx
    if idx < 0 or idx >= len(bars):
        raise ms.SignalBuildError(
            f"scorer_production[{symbol}]: bar_idx={idx} out of range for {len(bars)} bars"
        )
    if idx + 1 < ms.MIN_BARS_REQUIRED:
        raise ms.SignalBuildError(
            f"scorer_production[{symbol}]: bar_idx={idx} leaves only {idx + 1} bars of history, "
            f"need >= {ms.MIN_BARS_REQUIRED} for ribbon/ATR/volume-baseline warmup -- refusing "
            f"to score on short bar data rather than return a default/degraded score."
        )

    # No-look-ahead slice (C6): nothing at or after idx+1 is ever handed to a filter function.
    prior_bars = bars.iloc[: idx + 1].reset_index(drop=True)
    bar = prior_bars.iloc[idx]
    timestamp_et = bars.index[idx]
    if not isinstance(timestamp_et, (pd.Timestamp, dt.datetime)):
        raise ms.SignalBuildError(
            f"scorer_production[{symbol}]: bar timestamp at idx={idx} is not datetime-like"
        )
    timestamp_et = pd.Timestamp(timestamp_et).to_pydatetime()

    # Ribbon periods default to the FORK's constant (13/20/48) rather than production's own
    # ribbon_config.json file read, so that a caller who leaves ribbon_periods unset gets the
    # SAME EMA periods scored on the SAME bars through both scorers -- an apples-to-apples
    # comparison is the whole point of this module. The numbers are documented identical
    # (backtest/lib/ribbon.py's own docstring: Fast=13 Pivot=20 Slow=48), so this avoids a
    # redundant file read without changing behavior.
    periods = ribbon_periods or mf.DEFAULT_RIBBON_PERIODS
    ribbon_df = br.compute_ribbon(prior_bars["close"], periods)
    ribbon_now = br.ribbon_at(ribbon_df, idx)

    # PRODUCTION'S OWN orchestrator range (verified in backtest/lib/orchestrator.py ~line 935):
    #   _rlb = _filters_mod.RIBBON_FLIP_LOOKBACK_BARS
    #   for j in range(max(0, idx - _rlb - 1), idx + 1): ribbon_history.append(ribbon_at(df, j))
    # NOT the fork's build_bar_context range (idx - RIBBON_FLIP_LOOKBACK_BARS, one bar shorter)
    # -- see module docstring for why the two are functionally equivalent but this mirrors
    # production's literal code.
    _rlb = bf.RIBBON_FLIP_LOOKBACK_BARS
    ribbon_history = [br.ribbon_at(ribbon_df, j) for j in range(max(0, idx - _rlb - 1), idx + 1)]

    vol_baseline_20 = bf.vol_baseline_20bar(prior_bars, idx)
    range_baseline_20 = bf.range_baseline_20bar(prior_bars, idx)

    # Informational only -- production's BarContext has no atr_14 field to feed. Still fails
    # loud on a degenerate read (never publishes a NaN "volatility anchor" silently), matching
    # the fork's own refusal in build_bar_context.
    atr_series = mf.atr_wilder(prior_bars, mf.ATR_LENGTH_DEFAULT)
    atr_14 = float(atr_series[idx])
    if atr_14 != atr_14:  # NaN check
        raise ms.SignalBuildError(
            f"scorer_production[{symbol}]: ATR(14) is NaN at bar_idx={idx} -- insufficient "
            f"warmup despite passing MIN_BARS_REQUIRED."
        )

    spot = float(bar["close"])
    band_pct = ms.ACTIVE_BAND_PCT_OF_PRICE if active_band_pct is None else active_band_pct
    # Level SELECTION reused BY IMPORT from the fork -- see module docstring: only the setup
    # SCORING differs between this module and multi.lib.signal.
    levels_active = ms.select_active_levels(candidate_levels, spot, band_pct)
    multi_day_levels = ms.select_active_levels(candidate_multi_day_levels, spot, band_pct)

    htf_stack = ms._htf_15m_stack_at(htf_15m_bars, timestamp_et, periods)

    ctx = bf.BarContext(
        bar_idx=idx, timestamp_et=timestamp_et, bar=bar, prior_bars=prior_bars,
        ribbon_now=ribbon_now, ribbon_history=ribbon_history,
        vix_now=vix_now, vix_prior=vix_prior,
        vol_baseline_20=vol_baseline_20, range_baseline_20=range_baseline_20,
        levels_active=levels_active, multi_day_levels=multi_day_levels,
        htf_15m_stack=htf_stack, level_states=(level_states or {}), fhh_level=fhh_level,
        vix_5d_ma=vix_5d_ma, vix_20d_ma=vix_20d_ma,
    )
    return ctx, atr_14


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
    """PRODUCTION-scorer twin of `multi.lib.signal.build_signal` -- the SAME keyword signature
    and the SAME return shape, but the setup is scored by `backtest/lib/filters.py::
    evaluate_bearish_setup` / `evaluate_bullish_setup` (the live SPY engine's own, FROZEN,
    unmodified filter stack) instead of the sibling fork `multi/lib/filters.py`. See the module
    docstring for the full field-by-field mapping and what production's dataclasses lack.

    `ribbon_periods`/`now`/`write`/`out_path` are accepted and HONOURED (not ignored) --
    identical treatment to the fork: `ribbon_periods` feeds both the main and HTF ribbon
    computation, `now` timestamps `written_at`, `write`/`out_path` atomic-write the result via
    `multi.lib.signal.write_signal` (the SAME writer, reused by import).

    SCORING ONLY -- this function never places an order, never sizes a trade, never picks a
    strike/expiry. Raises `multi.lib.signal.SignalBuildError` on missing/short/malformed input,
    same as the fork.
    """
    p = params if params is not None else ms._load_multi_params()
    now = now or dt.datetime.now(dt.timezone.utc)

    active_band_pct = ms._param_override(p, "active_band_pct_of_price", ms.ACTIVE_BAND_PCT_OF_PRICE)
    resolved_min_triggers = (
        min_triggers if min_triggers is not None
        else int(ms._param_override(p, "min_triggers", 1))
    )
    resolved_sweep = (
        sweep_blocker_enabled if sweep_blocker_enabled is not None
        else bool(ms._param_override(p, "sweep_blocker_enabled", 0.0))
    )

    ctx, atr_14 = _build_production_bar_context(
        symbol, bars, bar_idx=bar_idx, vix_now=vix_now, vix_prior=vix_prior,
        vix_5d_ma=vix_5d_ma, vix_20d_ma=vix_20d_ma,
        candidate_levels=candidate_levels, candidate_multi_day_levels=candidate_multi_day_levels,
        level_states=level_states, fhh_level=fhh_level, htf_15m_bars=htf_15m_bars,
        ribbon_periods=ribbon_periods, active_band_pct=active_band_pct,
    )

    # Module-qualified calls (bf.evaluate_..., not a bare `from ... import evaluate_...`) so a
    # test can monkeypatch backtest.lib.filters.evaluate_bullish_setup/evaluate_bearish_setup
    # and this function will observe it -- the RED-proof that dispatch is real, not cached.
    bear = bf.evaluate_bearish_setup(
        ctx, min_triggers=resolved_min_triggers, sweep_blocker_enabled=resolved_sweep,
    )
    bull = bf.evaluate_bullish_setup(
        ctx, min_triggers=resolved_min_triggers, sweep_blocker_enabled=resolved_sweep,
    )
    # Duck-typed on .passed/.bear_score/.bull_score only (verified: no isinstance checks) --
    # works unmodified on production's SetupResult/BullishSetupResult.
    action = ms._derive_action(bear, bull)

    spot = float(ctx.bar["close"])
    # Production's RibbonState has spread_cents but no spread_pct (unlike the fork's) --
    # computed here exactly as the task specifies: spread_cents/100/spot.
    ribbon_spread_pct = (
        (ctx.ribbon_now.spread_cents / 100.0 / spot)
        if (ctx.ribbon_now is not None and spot > 0) else None
    )

    sig = {
        "_doc": "Scored from this symbol's own bars through PRODUCTION's backtest/lib/filters.py "
                "(evaluate_bearish_setup/evaluate_bullish_setup), UNMODIFIED -- the live SPY "
                "engine's own frozen filter stack, not the multi-symbol fork. Mirrors multi/lib/"
                "signal.py::build_signal's return shape exactly so a caller can diff the two. "
                "SCORING ONLY: no order was placed to produce this signal and none is placed by "
                "reading it. vix_regime is always None: production's SetupResult/"
                "BullishSetupResult carry no such field and no function in backtest/lib/filters.py "
                "computes an equivalent value anywhere (verified by grep) -- never invented here.",
        "symbol": symbol,
        "arm": p.get("arm"),
        "shadow_only": p.get("shadow_only"),
        "date": ctx.timestamp_et.strftime("%Y-%m-%d"),
        "time_et": ctx.timestamp_et.strftime("%H:%M"),
        "spot": spot,
        "atr_14": atr_14,
        "vix": vix_now,
        "vix_dir": mf.vix_direction(vix_now, vix_prior),
        "vix_regime": None,  # see module docstring / _doc above: production has no such field
        "ribbon_stack": ctx.ribbon_now.stack if ctx.ribbon_now is not None else None,
        "ribbon_spread_pct": ribbon_spread_pct,
        "htf_15m_stack": ctx.htf_15m_stack,
        "levels_active": ctx.levels_active,
        "multi_day_levels": ctx.multi_day_levels,
        "action": action,
        "bear": {
            "passed": bear.passed, "score": bear.bear_score, "blockers": bear.blockers,
            "triggers_fired": bear.triggers_fired, "rejection_level": bear.rejection_level,
            "confluence": bear.confluence_match is not None,
            "candlestick_pattern": getattr(bear, "candlestick_pattern", None),
        },
        "bull": {
            "passed": bull.passed, "score": bull.bull_score, "blockers": bull.blockers,
            "triggers_fired": bull.triggers_fired, "reclaim_level": bull.reclaim_level,
            "confluence": bull.confluence_match is not None,
            "shadow_triggers_fired": getattr(bull, "shadow_triggers_fired", []),
        },
        "written_at": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "production-filters-v1",
    }

    if write:
        if out_path is None:
            raise ms.SignalBuildError("scorer_production.build_signal: write=True requires out_path")
        ms.write_signal(sig, out_path)

    return sig


# ─────────────────────────────────────────────────────────────────────────────
# CLI -- read-only production-vs-fork compatibility smoke test. No order path is reachable
# from this file (see module docstring), so there is nothing for --smoke to place even by
# accident.
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_sig(label: str, sig: Optional[dict], name_blockers) -> str:
    if sig is None:
        return f"  {label:<10s} RAISED -- see traceback above"
    bear, bull = sig["bear"], sig["bull"]
    return (
        f"  {label:<10s} action={sig['action']:<10s} "
        f"ribbon={str(sig['ribbon_stack']):<6s} htf={str(sig['htf_15m_stack']):<6s} "
        f"bear(score={bear['score']:>2d} blockers={name_blockers(bear['blockers'])} "
        f"triggers={bear['triggers_fired']}) "
        f"bull(score={bull['score']:>2d} blockers={name_blockers(bull['blockers'])} "
        f"triggers={bull['triggers_fired']})"
    )


def _smoke(symbols: list[str]) -> int:
    # Local imports (not module-level): multi.core imports THIS module at its own top level
    # (`from multi.lib import scorer_production as msp`) for the scorer dispatch -- importing
    # multi.core back at this module's top level would be circular. Safe here because this
    # function only runs from the CLI entry point below, after multi.core (if anything) has
    # already finished its own import.
    from multi import core as mcore
    from multi.lib import context as mctx
    from multi.lib import creds as mcreds
    from multi.lib import levels as mlv

    params = mcreds.load_params()
    creds = mcreds.resolve(params)
    print(f"[scorer_production --smoke] creds source={creds.source} account={creds.account_number}")

    bars5 = mcore.fetch_bars_batch(creds, symbols, "5Min", limit=400)
    bars15 = mcore.fetch_bars_batch(creds, symbols, "15Min", limit=200)
    vix = mctx.fetch_vix()
    print(f"[scorer_production --smoke] vix={vix.now} degraded={vix.degraded} reason={vix.reason}")

    disagreements = []
    for sym in symbols:
        print(f"\n=== {sym} ===")
        b = bars5.get(sym)
        if b is None or len(b) < ms.MIN_BARS_REQUIRED:
            print(f"  SKIP: only {0 if b is None else len(b)} closed 5Min bars "
                  f"(need >= {ms.MIN_BARS_REQUIRED})")
            continue

        try:
            active_lv, multi_lv = mlv.compute_levels(b)
        except mlv.LevelError as e:
            print(f"  SKIP: levels: {e}")
            continue

        kwargs = dict(
            candidate_levels=active_lv, candidate_multi_day_levels=multi_lv,
            level_states={}, htf_15m_bars=bars15.get(sym), params=params,
            **vix.as_kwargs(),
        )

        prod_sig: Optional[dict] = None
        try:
            prod_sig = build_signal(sym, b, **kwargs)
        except Exception:  # noqa: BLE001 -- a production-scorer exception IS a finding; never hide it
            print("  PRODUCTION scorer RAISED:")
            traceback.print_exc()

        fork_sig: Optional[dict] = None
        try:
            fork_sig = ms.build_signal(sym, b, **kwargs)
        except Exception:  # noqa: BLE001 -- same: report, never swallow
            print("  FORK scorer RAISED:")
            traceback.print_exc()

        print(_fmt_sig("PRODUCTION", prod_sig, mcore.name_blockers))
        print(_fmt_sig("FORK", fork_sig, mcore.name_blockers))

        if prod_sig is not None and fork_sig is not None and prod_sig["action"] != fork_sig["action"]:
            msg = f"{sym}: production={prod_sig['action']} fork={fork_sig['action']}"
            disagreements.append(msg)
            print(f"  ** DISAGREEMENT: {msg} **")

    print(f"\n[scorer_production --smoke] {len(symbols)} symbols, "
          f"{len(disagreements)} production/fork disagreement(s)")
    for d in disagreements:
        print(f"    - {d}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Read-only production-vs-fork scoring compatibility smoke test. "
                     "No order path is reachable from this file."
    )
    ap.add_argument("--smoke", metavar="SYM1,SYM2,...", required=True,
                     help="comma-separated symbols to score read-only (no orders placed)")
    args = ap.parse_args(argv)
    symbols = [s.strip().upper() for s in args.smoke.split(",") if s.strip()]
    if not symbols:
        raise SystemExit("--smoke requires at least one symbol")
    return _smoke(symbols)


if __name__ == "__main__":
    raise SystemExit(main())
