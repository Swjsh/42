"""Run a backtest with parameter overrides.

Wraps `lib.orchestrator.run_backtest`, plus monkey-patches the in-module
constants in `lib.filters` for parameters that aren't accepted as kwargs
(e.g. `RIBBON_SPREAD_MIN_CENTS`, `VIX_BEAR_THRESHOLD`).

This patching is scoped via a context manager so concurrent / repeated
calls don't leak state. Single-process serial use only — if we ever
parallelise, switch to passing these as explicit kwargs.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from lib import filters as filters_mod
from lib.orchestrator import run_backtest, BacktestResult

from . import config
from .metrics import TradeMetrics, compute_metrics

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"


# Module-level constants in lib.filters that we want to override per run.
_FILTERS_CONST_KEYS = {
    "ribbon_spread_min_cents": "RIBBON_SPREAD_MIN_CENTS",
    "vix_bear_threshold": "VIX_BEAR_THRESHOLD",
    "vix_rising_deadband": "VIX_RISING_DEADBAND",
    "confluence_tolerance_dollars": "CONFLUENCE_TOLERANCE_DOLLARS",
    "ribbon_flip_lookback_bars": "RIBBON_FLIP_LOOKBACK_BARS",
    # Asymmetric (NEW 2026-05-09)
    "vix_bear_rising_deadband": "VIX_RISING_DEADBAND",   # bear-only override
    "vix_bull_max": "VIX_BULL_HARD_CAP",
    # Trendline detection knobs (2026-06-17)
    "trendline_lookback_bars": "TRENDLINE_LOOKBACK_BARS",
    "trendline_min_swings": "TRENDLINE_MIN_SWINGS",
    # Bull VIX gate (2026-06-17)
    "vix_bull_low_threshold": "VIX_BULL_LOW_THRESHOLD",
    # Wick rejection thresholds (2026-06-17: C14 fix — were hardcoded function defaults)
    "wick_min_pct_of_range": "WICK_MIN_PCT_OF_RANGE",
    "wick_min_dollars": "WICK_MIN_DOLLARS",
    "wick_close_tolerance": "WICK_CLOSE_TOLERANCE",
    # Volume baseline window (2026-06-17: C14 fix — live: vol_baseline_20bar at orchestrator:665).
    # range_baseline_bars excluded: ctx.range_baseline_20 is never read by any filter (dead field).
    "vol_baseline_bars": "VOL_BASELINE_BARS",
    # L114 (2026-06-17): panic-extreme VIX cap for BEAR entries
    "vix_hard_cap_bear": "VIX_HARD_CAP_BEAR",
    # L115 (2026-06-17): require multi-day VIX declining for BEAR entries (L93 recommendation)
    "vix_declining_required_bear": "VIX_DECLINING_REQUIRED_BEAR",
}


@contextlib.contextmanager
def _patched_filter_constants(params: dict[str, Any]) -> Iterator[None]:
    """Temporarily swap module-level constants in lib.filters for one run."""
    saved: dict[str, Any] = {}
    for param_key, attr in _FILTERS_CONST_KEYS.items():
        if param_key in params:
            saved[attr] = getattr(filters_mod, attr)
            setattr(filters_mod, attr, params[param_key])
    try:
        yield
    finally:
        for attr, val in saved.items():
            setattr(filters_mod, attr, val)


def _dedupe_by_timestamp(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows where the parsed timestamp duplicates a prior row.

    Different CSVs in the data/ folder use different timezone-format strings
    (e.g. `-04:00` vs `-0400`), so string-level dedupe in merge_data.py is
    insufficient. Parse to UTC, sort, then keep first per timestamp.
    """
    df = df.copy()
    df["_parsed_ts"] = pd.to_datetime(df["timestamp_et"], utc=True, errors="coerce")
    df = df.dropna(subset=["_parsed_ts"])
    df = df.drop_duplicates(subset=["_parsed_ts"], keep="first")
    df = df.sort_values("_parsed_ts").reset_index(drop=True)
    return df.drop(columns=["_parsed_ts"])


def _discover_csv_candidates(data_dir: Path, start: dt.date, end: dt.date) -> list[tuple[dt.date, dt.date]]:
    """Auto-discover spy_5m_*.csv files that cover [start, end].

    Returns list of (file_start, file_end) tuples, sorted by file_end descending
    (most recent first). Skips files missing a matching vix_5m_*.csv.

    This handles the rolling daily-append files created by tools/append_today.py
    (e.g. spy_5m_2026-05-08_2026-05-21.csv) that aren't in the hard-coded list.
    """
    import re
    pattern = re.compile(r"spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_merged)?\.csv$")
    found: list[tuple[dt.date, dt.date]] = []
    for p in data_dir.glob("spy_5m_*.csv"):
        m = pattern.match(p.name)
        if not m:
            continue
        try:
            fs = dt.date.fromisoformat(m.group(1))
            fe = dt.date.fromisoformat(m.group(2))
        except ValueError:
            continue
        if fs > start or fe < end:
            continue  # doesn't cover the requested window
        vix_name = p.name.replace("spy_5m_", "vix_5m_")
        if not (data_dir / vix_name).exists():
            continue  # no matching VIX file
        found.append((fs, fe))
    return sorted(found, key=lambda x: x[1], reverse=True)  # most-recent end first


def load_data(start: dt.date, end: dt.date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Locate a CSV that fully covers [start, end] and load it.

    Strategy:
    1. Hard-coded candidates (exact match + known master files).
    2. Auto-discover: scan backtest/data/ for any spy_5m_*.csv whose date range
       covers [start, end] — picks the one with the latest end date.
       This handles rolling daily-append files from tools/append_today.py.

    Dedupes by parsed timestamp (merge artefacts leave duplicate rows with
    subtly-different timezone-format strings).
    """
    candidates = [
        (start, end),
        (dt.date(2025, 1, 1), dt.date(2026, 5, 22)),  # merged master (5/16-5/22 added 2026-05-23)
        (dt.date(2025, 1, 1), dt.date(2026, 5, 15)),  # merged master (5/13-5/15 added 2026-05-16)
        (dt.date(2025, 1, 1), dt.date(2026, 5, 12)),
        (dt.date(2025, 1, 1), dt.date(2026, 5, 7)),
    ]
    for s, e in candidates:
        # Only use this candidate if its date range covers [start, end].
        # Without this check, a hardcoded master file ending at 5/15 would be
        # returned even when grading same-day (5/20) observations — causing
        # "future bars empty" because the file predates the requested window.
        if s > start or e < end:
            continue
        spy_path = DATA / f"spy_5m_{s}_{e}.csv"
        vix_path = DATA / f"vix_5m_{s}_{e}.csv"
        if spy_path.exists() and vix_path.exists():
            spy = _dedupe_by_timestamp(pd.read_csv(spy_path))
            vix = _dedupe_by_timestamp(pd.read_csv(vix_path))
            return spy, vix

    # Auto-discover rolling daily-append files (created by append_today.py)
    for s, e in _discover_csv_candidates(DATA, start, end):
        spy_path = DATA / f"spy_5m_{s}_{e}.csv"
        vix_name = f"vix_5m_{s}_{e}.csv"
        vix_path = DATA / vix_name
        if not vix_path.exists():
            # Try _merged variant
            vix_path = DATA / vix_name.replace(".csv", "_merged.csv")
        if spy_path.exists() and vix_path.exists():
            spy = _dedupe_by_timestamp(pd.read_csv(spy_path))
            vix = _dedupe_by_timestamp(pd.read_csv(vix_path))
            return spy, vix

    raise FileNotFoundError(
        f"no SPY/VIX csv found covering {start}..{end}; "
        f"run tools/extend_data_v2.py + tools/merge_data.py first"
    )


def run_with_params(
    params: dict[str, Any],
    start: dt.date,
    end: dt.date,
    spy_df: pd.DataFrame | None = None,
    vix_df: pd.DataFrame | None = None,
) -> tuple[BacktestResult, TradeMetrics]:
    """Run a backtest over [start, end] with the given parameter overrides.

    Returns (BacktestResult, TradeMetrics). Metrics are computed only on
    trades whose entry date is within [start, end] (the orchestrator already
    filters but we double-check to be safe).
    """
    if spy_df is None or vix_df is None:
        spy_df, vix_df = load_data(start, end)

    # Build kwargs accepted by run_backtest directly.
    kwargs: dict[str, Any] = {
        "start_date": start,
        "end_date": end,
        "use_real_fills": params.get("use_real_fills", False),  # default BS for speed; set params["use_real_fills"]=True for real-fill validation (e.g. the J-anchor gate). Fixes H3 (search-in-BS / validate-in-real mismatch).
    }
    # Direct passthrough kwargs (name in params → name in run_backtest)
    direct_passthrough = (
        "f9_vol_mult",
        # Asymmetric bear/bull (NEW 2026-05-09)
        "min_triggers_bear",
        "min_triggers_bull",
        "premium_stop_pct_bear",
        "premium_stop_pct_bull",
        "strike_offset_bear",
        "strike_offset_bull",
        # Exit knobs (NEW 2026-05-09)
        "tp1_premium_pct",
        "tp1_qty_fraction",
        "runner_target_premium_pct",
        "level_stop_buffer_dollars",
        "time_stop_minutes_before_close",
        # v14_enhanced profit-lock (NEW 2026-05-13)
        "profit_lock_threshold_pct",
        "profit_lock_stop_offset_pct",
        # Ribbon entry gates (confirmed live knobs, missing caused dead-knob false positive 2026-06-16)
        "min_ribbon_momentum_cents",
        "max_ribbon_duration_bars",
        # Sizing
        "per_trade_risk_cap_pct",
        "midday_trendline_gate",
        # Six ratified entry gates (2026-06-18 bugfix): without these the walk-forward /
        # params-path could not see the gates through the params dict, so any A/B or WF
        # that loaded them from params ran WITHOUT them (C14 dead-knob class). The
        # orchestrator translates+assigns all six from params_overrides; this allowlist
        # is the parallel path used by runner.run_with_params -> run_backtest kwargs.
        "vix_bear_hard_cap",
        "block_level_rejection",
        "entry_bar_body_pct_min",
        "block_bull_1100_1200",
        "block_elite_bull",
        "block_elite_bull_vix_low",
        "block_elite_bull_vix_high",
        "block_bull_morning_agg",
    )
    for k in direct_passthrough:
        if k in params:
            kwargs[k] = params[k]

    # Backward-compat: legacy unsplit names → fallback values for the orchestrator.
    if "min_triggers" in params and "min_triggers_bear" not in params:
        kwargs["min_triggers"] = params["min_triggers"]
    if "premium_stop_pct" in params and "premium_stop_pct_bear" not in params:
        kwargs["premium_stop_pct"] = params["premium_stop_pct"]
    if "strike_offset" in params and "strike_offset_bear" not in params:
        kwargs["strike_offset"] = params["strike_offset"]

    if "no_trade_before" in params:
        kwargs["no_trade_before"] = config.parse_time(params["no_trade_before"])
    # Multi-window support (2026-05-24): "no_trade_windows" is a list of [start, end] string pairs.
    # Backward-compat: single window still handled via no_trade_window_start / no_trade_window_end.
    if "no_trade_windows" in params:
        windows = params["no_trade_windows"]
        parsed = []
        for w in windows:
            s = config.parse_time(w[0] if isinstance(w, (list, tuple)) else w.get("start"))
            e = config.parse_time(w[1] if isinstance(w, (list, tuple)) else w.get("end"))
            if s is not None and e is not None:
                parsed.append((s, e))
        kwargs["no_trade_window"] = parsed if parsed else None
    elif "no_trade_window_start" in params or "no_trade_window_end" in params:
        s = config.parse_time(params.get("no_trade_window_start"))
        e = config.parse_time(params.get("no_trade_window_end"))
        kwargs["no_trade_window"] = (s, e) if (s is not None and e is not None) else None

    with _patched_filter_constants(params):
        result = run_backtest(spy_df, vix_df, **kwargs)

    metrics = compute_metrics(result.trades)
    return result, metrics
