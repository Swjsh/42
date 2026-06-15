"""Two-window regime detection from a daily P&L series.

Inputs:
    daily_pnl: dict[date, float]  — one entry per trading day with at least one trade
    recent_window_days: int (default 10)
    baseline_window_days: int (default 60)
    divergence_threshold: float (default 0.5)  — Sharpe-units of divergence

Outputs (RegimeSignal dataclass):
    regime: NOVEL | HISTORICAL | MIXED
    recent_sharpe: float
    baseline_sharpe: float
    delta_sharpe: float            — recent - baseline
    n_recent: int
    n_baseline: int
    threshold_adjustments: dict    — recommended overrides for the heartbeat

The recommended overrides are NEVER applied automatically — they're
written to `automation/state/regime.json` for the heartbeat to read at its
discretion. Operating principle 11 still applies: real money never moves
without a paper-validated rule change.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)
STATE_DIR = Path(__file__).resolve().parent / "_state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
REGIME_FILE = STATE_DIR / "regime.json"


# Regime constants
NOVEL_REGIME = "NOVEL_REGIME"
HISTORICAL_REGIME = "HISTORICAL_REGIME"
MIXED = "MIXED"


@dataclass(frozen=True)
class RegimeSignal:
    """Result of one detector evaluation."""

    regime: str
    recent_sharpe: float
    baseline_sharpe: float
    delta_sharpe: float
    n_recent: int
    n_baseline: int
    recent_total_pnl: float
    baseline_total_pnl: float
    detected_at: str = ""
    threshold_adjustments: dict = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _annualised_sharpe(values: Iterable[float], periods_per_year: int = 252) -> float:
    """Annualised Sharpe of a series. 0 when degenerate."""
    vals = list(values)
    n = len(vals)
    if n < 2:
        return 0.0
    mean = sum(vals) / n
    variance = sum((v - mean) ** 2 for v in vals) / (n - 1)
    if variance <= 0:
        return 0.0
    std = math.sqrt(variance)
    return (mean / std) * math.sqrt(periods_per_year)


def _last_n_dates(daily_pnl: dict[dt.date, float], n: int, ref: dt.date | None = None) -> list[dt.date]:
    """Return the latest `n` trading dates from daily_pnl, sorted ascending,
    optionally clipped to dates <= `ref`."""
    keys = sorted(daily_pnl.keys())
    if ref is not None:
        keys = [d for d in keys if d <= ref]
    return keys[-n:]


def _recommended_adjustments(regime: str, delta: float) -> dict:
    """Map a regime + delta to suggested heartbeat threshold tweaks.

    These are conservative — they bias toward fewer trades during NOVEL
    regimes (when the engine's edge is uncertain) and toward production
    defaults otherwise. Live engine reads `automation/state/regime.json`
    to apply these; doctrine still requires backtest validation before
    any rule change goes permanent.
    """
    if regime == NOVEL_REGIME:
        return {
            "min_triggers_bear_floor": 2,        # require ≥2 triggers (default 1)
            "min_triggers_bull_floor": 3,        # require ≥3 triggers (default 2)
            "ribbon_spread_bonus_cents": 5,      # tighten by +5c
            "size_modifier": 0.5,                # halve position size
            "max_trades_per_day": 1,             # one trade per day cap
        }
    if regime == HISTORICAL_REGIME:
        return {
            "min_triggers_bear_floor": 1,
            "min_triggers_bull_floor": 2,
            "ribbon_spread_bonus_cents": 0,
            "size_modifier": 1.0,
            "max_trades_per_day": None,
        }
    # MIXED — production defaults
    return {
        "min_triggers_bear_floor": 1,
        "min_triggers_bull_floor": 2,
        "ribbon_spread_bonus_cents": 0,
        "size_modifier": 1.0,
        "max_trades_per_day": None,
    }


def detect(
    daily_pnl: dict[dt.date, float],
    recent_window_days: int = 10,
    baseline_window_days: int = 60,
    divergence_threshold: float = 0.5,
    ref_date: dt.date | None = None,
) -> RegimeSignal:
    """Compute the regime signal from a daily P&L history.

    Args:
        daily_pnl: dict mapping trading date -> dollar P&L for that day.
        recent_window_days: size of the "recent" window in trading days.
        baseline_window_days: size of the "baseline" window in trading days.
            Must be >= recent_window_days; the baseline ends at the START of
            the recent window so they don't overlap.
        divergence_threshold: |delta_sharpe| above which a regime signal fires.
        ref_date: end-of-window date (default: today). Use for backtesting
            JANUS itself.
    """
    if recent_window_days <= 0 or baseline_window_days <= 0:
        raise ValueError("window sizes must be positive")
    if baseline_window_days < recent_window_days:
        raise ValueError("baseline_window_days must be >= recent_window_days")

    if not daily_pnl:
        return RegimeSignal(
            regime=MIXED,
            recent_sharpe=0.0,
            baseline_sharpe=0.0,
            delta_sharpe=0.0,
            n_recent=0,
            n_baseline=0,
            recent_total_pnl=0.0,
            baseline_total_pnl=0.0,
            detected_at=dt.datetime.utcnow().isoformat(timespec="seconds"),
            threshold_adjustments=_recommended_adjustments(MIXED, 0.0),
            notes="no trade data",
        )

    recent_dates = _last_n_dates(daily_pnl, recent_window_days, ref_date)
    if not recent_dates:
        return RegimeSignal(
            regime=MIXED, recent_sharpe=0.0, baseline_sharpe=0.0,
            delta_sharpe=0.0, n_recent=0, n_baseline=0,
            recent_total_pnl=0.0, baseline_total_pnl=0.0,
            detected_at=dt.datetime.utcnow().isoformat(timespec="seconds"),
            threshold_adjustments=_recommended_adjustments(MIXED, 0.0),
            notes="no recent dates",
        )

    # Baseline is the window ending the day BEFORE the recent window starts (no overlap).
    recent_start = recent_dates[0]
    baseline_dates = [
        d for d in sorted(daily_pnl.keys()) if d < recent_start
    ][-baseline_window_days:]

    recent_values = [daily_pnl[d] for d in recent_dates]
    baseline_values = [daily_pnl[d] for d in baseline_dates]

    recent_sharpe = _annualised_sharpe(recent_values)
    baseline_sharpe = _annualised_sharpe(baseline_values)
    delta = recent_sharpe - baseline_sharpe

    if delta < -divergence_threshold:
        regime = NOVEL_REGIME
        notes = f"recent {recent_sharpe:.2f} << baseline {baseline_sharpe:.2f} (delta={delta:+.2f})"
    elif delta > divergence_threshold:
        regime = HISTORICAL_REGIME
        notes = f"recent {recent_sharpe:.2f} >> baseline {baseline_sharpe:.2f} (delta={delta:+.2f})"
    else:
        regime = MIXED
        notes = f"|delta|={abs(delta):.2f} within deadband {divergence_threshold:.2f}"

    return RegimeSignal(
        regime=regime,
        recent_sharpe=recent_sharpe,
        baseline_sharpe=baseline_sharpe,
        delta_sharpe=delta,
        n_recent=len(recent_values),
        n_baseline=len(baseline_values),
        recent_total_pnl=sum(recent_values),
        baseline_total_pnl=sum(baseline_values),
        detected_at=dt.datetime.utcnow().isoformat(timespec="seconds"),
        threshold_adjustments=_recommended_adjustments(regime, delta),
        notes=notes,
    )


def save_regime(signal: RegimeSignal, path: Path | None = None) -> None:
    """Write the current regime signal to disk."""
    out_path = path or REGIME_FILE
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(signal.to_dict(), f, indent=2, default=str)
    tmp.replace(out_path)


def load_regime(path: Path | None = None) -> RegimeSignal | None:
    in_path = path or REGIME_FILE
    if not in_path.exists():
        return None
    with open(in_path, "r") as f:
        return RegimeSignal(**json.load(f))


# ---- helper: convert TradeFill objects to daily P&L dict ----

def trades_to_daily_pnl(trades: Iterable) -> dict[dt.date, float]:
    """Group a list of TradeFill objects by entry date, summing dollar_pnl.

    Helper for callers who already have backtest results in TradeFill form.
    """
    out: dict[dt.date, float] = {}
    for t in trades:
        ts = t.entry_time_et
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        d = ts.date()
        out[d] = out.get(d, 0.0) + float(t.dollar_pnl)
    return out
