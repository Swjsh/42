"""Autoresearch configuration: tiered search space, mode starting points, gates.

Knob tiering (added 2026-05-09 after the gate-bug retrospective):

    CORE         - Always tested. Drive most of the signal: stops, TP1, runner
                   target, min_triggers, ribbon spread, vol confirmation.
    SECONDARY    - Tested when an experiment opts in. Useful but secondary:
                   strike offset, level proximity, confluence tolerance,
                   ribbon flip lookback, time gates.
    NOISE_PRONE  - Off by default. J's words: "I never traded VIX before with
                   confluence, it's nice to have." Includes vix_bear_threshold,
                   vix_rising_deadband.

Experiments combine tier subsets:

    lean         - CORE only.        ~6 knobs. Fast, focused, low overfit risk.
    entries      - CORE + entry-side SECONDARY (level/ribbon/time).
    exits        - CORE + exit-side SECONDARY (level_stop_buffer, time_stop).
    full         - CORE + SECONDARY (all).
    kitchen_sink - Everything including NOISE_PRONE.

Asymmetric bear/bull: setup-side knobs (min_triggers, premium_stop_pct,
volume confirmation, etc.) are split into bear_* and bull_* versions because
the two sides have different statistical profiles (bear baseline ~56% WR,
bull baseline ~25% WR with W/L 3-5x).

Pre-flight gate sanity check: `validate_gates_against_baseline()` refuses
to launch if the WR floor is unreachable from the current baseline (avoids
the 2026-05-08 0-KEEPs incident).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any


# ============================================================================
# BASELINE PARAMS — production v14 defaults (mirror lib/orchestrator.py)
# ============================================================================
# When a sweep adds a new knob, the loop merges it from here into existing
# state files so old runs pick up new params on next launch.

BASELINE_PARAMS: dict[str, Any] = {
    # --- Entry filters (shared bear+bull unless asymmetric prefix used) ---
    "f9_vol_mult": 0.7,
    "ribbon_spread_min_cents": 30,
    "ribbon_flip_lookback_bars": 3,
    "level_proximity_dollars": 0.50,
    "confluence_tolerance_dollars": 0.30,
    "no_trade_before": "10:00",
    "no_trade_window_start": "14:00",
    "no_trade_window_end": "15:00",

    # --- Asymmetric bear vs bull entry params ---
    "min_triggers_bear": 1,
    "min_triggers_bull": 2,             # bull setups need more confluence
    "vix_bear_threshold": 17.30,
    "vix_bear_rising_deadband": 0.05,
    "vix_bull_max": 22.0,                # bull setup hard VIX cap

    # --- Exit knobs (asymmetric where the math differs) ---
    "premium_stop_pct_bear": -0.08,
    "premium_stop_pct_bull": -0.10,
    "tp1_premium_pct": 0.30,             # premium gain that triggers TP1
    "tp1_qty_fraction": 0.667,           # 2 of 3 contracts at TP1
    "runner_target_premium_pct": 3.00,   # premium target for the runner
    "level_stop_buffer_dollars": 0.0,    # buffer past rejection_level for stop
    "time_stop_minutes_before_close": 10,  # 15:50 ET stop (10 min before 16:00)

    # --- Strike selection ---
    "strike_offset_bear": -2,            # ITM-2 puts
    "strike_offset_bull": -2,            # ITM-2 calls (negative = closer to spot for calls too)
}


# ============================================================================
# SEARCH_SPACE — candidate values per knob
# ============================================================================
SEARCH_SPACE: dict[str, list[Any]] = {
    # Entry filters
    "f9_vol_mult": [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5],
    "ribbon_spread_min_cents": [15, 20, 25, 30, 35, 40, 50, 60],
    "ribbon_flip_lookback_bars": [2, 3, 4, 5, 6],
    "level_proximity_dollars": [0.20, 0.30, 0.40, 0.50, 0.60, 0.75, 1.0],
    "confluence_tolerance_dollars": [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50],
    "no_trade_before": [None, "09:35", "09:45", "10:00", "10:15", "10:30", "10:45"],
    "no_trade_window_start": [None, "12:30", "13:00", "13:15", "13:30", "13:45",
                              "14:00", "14:15", "14:30"],
    "no_trade_window_end": [None, "14:00", "14:30", "14:45", "15:00", "15:15", "15:30", "15:45"],

    # Asymmetric bear/bull
    "min_triggers_bear": [1, 2, 3],
    "min_triggers_bull": [1, 2, 3, 4],
    "vix_bear_threshold": [15.0, 16.0, 16.5, 17.0, 17.30, 17.5, 18.0, 19.0, 20.0],
    "vix_bear_rising_deadband": [0.02, 0.05, 0.08, 0.10, 0.15, 0.20],
    "vix_bull_max": [18.0, 19.0, 20.0, 22.0, 25.0, 30.0],

    # Exit knobs
    "premium_stop_pct_bear": [-0.05, -0.06, -0.08, -0.10, -0.12, -0.15, -0.20, -0.30],
    "premium_stop_pct_bull": [-0.05, -0.06, -0.07, -0.08, -0.10, -0.12, -0.15, -0.20, -0.25, -0.30],
    "tp1_premium_pct": [0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.75, 1.0],
    "tp1_qty_fraction": [0.333, 0.50, 0.667, 1.0],   # 1/3, 1/2, 2/3, all-out at TP1
    "runner_target_premium_pct": [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
    "level_stop_buffer_dollars": [0.0, 0.05, 0.10, 0.15, 0.25],
    "time_stop_minutes_before_close": [5, 10, 15, 20, 30, 45, 60],

    # Strike selection
    "strike_offset_bear": [-3, -2, -1, 0, 1],
    "strike_offset_bull": [-3, -2, -1, 0, 1],
}


# ============================================================================
# KNOB TIERS — which knobs each experiment includes
# ============================================================================

CORE_KNOBS: set[str] = {
    "f9_vol_mult",
    "ribbon_spread_min_cents",
    "min_triggers_bear",
    "min_triggers_bull",
    "premium_stop_pct_bear",
    "premium_stop_pct_bull",
    "tp1_premium_pct",
    "tp1_qty_fraction",
    "runner_target_premium_pct",
}

SECONDARY_ENTRY_KNOBS: set[str] = {
    "ribbon_flip_lookback_bars",
    "level_proximity_dollars",
    "confluence_tolerance_dollars",
    "no_trade_before",
    "no_trade_window_start",
    "no_trade_window_end",
    "strike_offset_bear",
    "strike_offset_bull",
}

SECONDARY_EXIT_KNOBS: set[str] = {
    "level_stop_buffer_dollars",
    "time_stop_minutes_before_close",
}

NOISE_PRONE_KNOBS: set[str] = {
    "vix_bear_threshold",
    "vix_bear_rising_deadband",
    "vix_bull_max",
}


EXPERIMENTS: dict[str, set[str]] = {
    "lean":          CORE_KNOBS,
    "entries":       CORE_KNOBS | SECONDARY_ENTRY_KNOBS,
    "exits":         CORE_KNOBS | SECONDARY_EXIT_KNOBS,
    "full":          CORE_KNOBS | SECONDARY_ENTRY_KNOBS | SECONDARY_EXIT_KNOBS,
    "kitchen_sink":  CORE_KNOBS | SECONDARY_ENTRY_KNOBS | SECONDARY_EXIT_KNOBS | NOISE_PRONE_KNOBS,
}


# ============================================================================
# KEEP_THRESHOLDS — sanity floors. Sharpe drives the actual decision.
# ============================================================================

@dataclass(frozen=True)
class KeepThresholds:
    """Hard sanity floors. Recalibrated 2026-05-08 after the bear-only-era
    gates blocked every bullish-enabled candidate."""
    min_trades: int = 10
    min_win_rate: float = 0.10
    min_wl_ratio: float = 0.80
    min_expectancy: float = -10.0
    max_drawdown_regression: float = 1.75


KEEP_THRESHOLDS = KeepThresholds()

MAX_VALIDATION_REGRESSION = 0.20

# ============================================================================
# OBJECTIVES — what the loop optimizes for (added 2026-05-09 weekend research).
#
# train_sharpe (default): legacy. Keep iff train sharpe improves AND validate
#                         sharpe doesn't regress >MAX_VALIDATION_REGRESSION.
# validate_sharpe:        Keep iff VALIDATE sharpe improves (train still gates).
# validate_pnl:           Keep iff VALIDATE total_pnl improves (train still gates).
# validate_expectancy:    Keep iff VALIDATE expectancy improves (train still gates).
#
# All objectives still enforce the train-side hard gates (KEEP_THRESHOLDS) so
# we don't end up with overfit garbage that "wins" on validate by luck.
# ============================================================================
OBJECTIVES: tuple[str, ...] = (
    "train_sharpe",
    "validate_sharpe",
    "validate_pnl",
    "validate_expectancy",
)
DEFAULT_OBJECTIVE = "train_sharpe"

# Train / validate windows
DEFAULT_TRAIN_START = "2025-01-01"
DEFAULT_TRAIN_END = "2026-02-13"
DEFAULT_VALIDATE_START = "2026-02-14"
DEFAULT_VALIDATE_END = "2026-05-07"

PARAM_COOLDOWN_ITERATIONS = 3
MIN_BASELINE_TRADES_FOR_DECISION = 10


# ============================================================================
# Mode starting points — STRICT / BALANCED / AGGRESSIVE
# ============================================================================

STRICT_PARAMS: dict[str, Any] = {
    **BASELINE_PARAMS,
    "f9_vol_mult": 1.0,
    "ribbon_spread_min_cents": 35,
    "min_triggers_bear": 2,
    "min_triggers_bull": 3,
    "premium_stop_pct_bear": -0.06,
    "premium_stop_pct_bull": -0.08,
    "tp1_premium_pct": 0.25,                # take profits faster
    "tp1_qty_fraction": 0.667,
    "runner_target_premium_pct": 2.0,       # more conservative runner target
    "vix_bear_threshold": 17.5,
    "no_trade_before": "10:00",
    "no_trade_window_start": "13:30",
    "no_trade_window_end": "15:00",
}

BALANCED_PARAMS: dict[str, Any] = dict(BASELINE_PARAMS)

AGGRESSIVE_PARAMS: dict[str, Any] = {
    **BASELINE_PARAMS,
    "f9_vol_mult": 0.5,
    "ribbon_spread_min_cents": 20,
    "min_triggers_bear": 1,
    "min_triggers_bull": 2,
    "premium_stop_pct_bear": -0.15,
    "premium_stop_pct_bull": -0.20,
    "tp1_premium_pct": 0.40,                # let it run further before TP1
    "tp1_qty_fraction": 0.333,              # smaller TP1 share, more on the runner
    "runner_target_premium_pct": 5.0,       # ride the ribbon hard
    "vix_bear_threshold": 16.0,
    "level_proximity_dollars": 0.75,
    "no_trade_before": "09:35",
    "no_trade_window_start": None,
    "no_trade_window_end": None,
}


MODES: dict[str, dict[str, Any]] = {
    "strict": STRICT_PARAMS,
    "balanced": BALANCED_PARAMS,
    "aggressive": AGGRESSIVE_PARAMS,
}


# ============================================================================
# Helper functions
# ============================================================================

def parse_time(value: Any) -> dt.time | None:
    """Parse 'HH:MM' string -> dt.time. None and 'None' both yield None."""
    if value is None or value == "None":
        return None
    if isinstance(value, dt.time):
        return value
    h, m = value.split(":")
    return dt.time(int(h), int(m))


def knobs_for_experiment(name: str) -> set[str]:
    """Return the set of knob names allowed for this experiment."""
    if name not in EXPERIMENTS:
        raise ValueError(f"unknown experiment '{name}'; choices: {list(EXPERIMENTS)}")
    return EXPERIMENTS[name]


def merge_missing_knobs(current: dict[str, Any]) -> dict[str, Any]:
    """Return `current` augmented with any keys present in BASELINE_PARAMS but
    missing from `current`. Used when an old state.json predates a new knob."""
    out = dict(current)
    for k, v in BASELINE_PARAMS.items():
        out.setdefault(k, v)
    return out


def validate_gates_against_baseline(baseline_metrics: dict[str, Any]) -> list[str]:
    """Pre-flight check — return list of warnings if KEEP_THRESHOLDS look
    unreachable from this baseline. Empty list = looks fine to launch.

    Specifically catches the 2026-05-08 bug: launching with WR floor = 0.40
    when baseline WR is 0.15 means every iteration auto-reverts.
    """
    warnings: list[str] = []
    base_wr = float(baseline_metrics.get("win_rate", 0))
    base_trades = int(baseline_metrics.get("n_trades", 0))
    base_exp = float(baseline_metrics.get("expectancy", 0))

    if base_trades < KEEP_THRESHOLDS.min_trades:
        warnings.append(
            f"baseline n_trades={base_trades} is below KEEP_THRESHOLDS.min_trades="
            f"{KEEP_THRESHOLDS.min_trades}. Mode is too restrictive — every iter will "
            f"hit the trade-count gate. Either relax the mode params or lower the gate."
        )

    if base_wr * 1.5 < KEEP_THRESHOLDS.min_win_rate:
        warnings.append(
            f"baseline WR={base_wr:.0%} is far below gate min_win_rate="
            f"{KEEP_THRESHOLDS.min_win_rate:.0%}. A single-knob change is unlikely to "
            f"clear the gate. Either lower the gate or accept many REVERTs."
        )

    if base_exp < KEEP_THRESHOLDS.min_expectancy * 5:
        warnings.append(
            f"baseline expectancy=${base_exp:.2f} is far below gate min_expectancy=$"
            f"{KEEP_THRESHOLDS.min_expectancy}. May not reach gate in one step."
        )

    return warnings
