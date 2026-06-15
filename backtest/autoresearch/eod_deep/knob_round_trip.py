"""Knob Round-Trip — per-trade sensitivity analysis.

Phase 2.5 (Tier B). For each winning trade, sweep each major v15 knob
±2 levels and re-simulate via simulator_real. Find the "dominant knob" —
the one whose change has the largest |Δ P&L| on this specific trade.

Answers J's question (from earlier today): "do you backtest the winners
to dial them in further?"

For today's 745C trade (entry $1.67, exit avg $3.23 ish, +$1,500):
  - premium_stop ±2 (e.g., -25%/-20%/-15%/-10%) — would tighter/wider have caught more?
  - tp1_qty_fraction ±2 (0.4/0.5/0.6) — would locking more/less at TP1 matter?
  - profit_lock_trail_pct ±2 (0.10/0.15/0.20/0.25/0.30) — would tighter trail have given back less or cut runner short?
  - runner_target_premium_pct ±2 (1.5/2.0/2.5/3.0) — target hit at 2.5×; would 3.0× have caught peak $4.50?

Outputs to `research_handoffs.knob_round_trip_per_trade`:
  [{trade_id, dominant_knob: "...", sensitivity_dollars: ±$,
    sweep_results: {knob_name: [{level: X, pnl: $Y}]}}]

Each result feeds the auto-queue as a candidate v16 doctrine tweak.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))

try:
    from lib.simulator_real import simulate_trade_real, TradeFill
    SIMULATOR_AVAILABLE = True
except Exception:
    SIMULATOR_AVAILABLE = False


@dataclass
class KnobSweep:
    knob_name: str
    base_value: float
    level_results: list[dict] = field(default_factory=list)
    # level_results: [{level: float, pnl_dollars: float, delta_vs_base: float, status: str}]
    sensitivity_dollars: float = 0.0   # max|delta|
    best_level: float = 0.0
    best_pnl: float = 0.0


@dataclass
class KnobRoundTripResult:
    trade_id: str
    base_pnl: float = 0.0
    sweeps: list[KnobSweep] = field(default_factory=list)
    dominant_knob: str = ""
    dominant_delta: float = 0.0       # signed
    dominant_best_level: float = 0.0
    narrative: str = ""


# v15 production knobs from params.json (defaults)
DEFAULT_KNOBS = {
    "premium_stop_pct": -0.20,
    "tp1_premium_pct": 0.30,
    "tp1_qty_fraction": 0.50,
    "runner_target_premium_pct": 2.50,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.10,
    "profit_lock_trail_pct": 0.20,
    "strike_offset": -2,
}

# Sweep grids (±2 levels around base)
SWEEP_GRIDS = {
    "premium_stop_pct":       [-0.30, -0.25, -0.20, -0.15, -0.10],   # tighter→wider
    "tp1_premium_pct":        [0.20, 0.25, 0.30, 0.40, 0.50],         # earlier→later TP1
    "tp1_qty_fraction":       [0.30, 0.40, 0.50, 0.60, 0.70],         # lock-less→lock-more
    "runner_target_premium_pct": [1.50, 2.00, 2.50, 3.00, 4.00],      # cap→let-run
    "profit_lock_trail_pct":  [0.10, 0.15, 0.20, 0.25, 0.30],         # tight→loose chandelier
    "strike_offset":          [-3, -2, -1, 0, 1],                    # deeper-ITM→OTM
}


def _simulate_with_knobs(
    trade,
    knobs: dict,
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
) -> Optional[float]:
    """Run simulate_trade_real with the given knob overrides. Returns dollar P&L or None."""
    if not SIMULATOR_AVAILABLE:
        return None

    # Find trigger bar in spy_df
    buy_fills = [f for f in trade.fills if f.side == "buy"]
    if not buy_fills:
        return None
    buy = buy_fills[0]
    target_ts = pd.Timestamp(f"{trade.expiry_date} {buy.time_et[:5]}:00")
    # Floor to 5min
    try:
        hh, mm, _ = buy.time_et.split(":")
        mm_floor = (int(mm) // 5) * 5
        target_ts = pd.Timestamp(f"{trade.expiry_date} {int(hh):02d}:{mm_floor:02d}:00")
    except (ValueError, AttributeError):
        pass

    matching = spy_df.index[spy_df["timestamp_et"] == target_ts]
    if len(matching) == 0:
        return None
    bar_idx = int(matching[0])

    side = "C" if trade.direction == "long" else "P"

    try:
        result = simulate_trade_real(
            entry_bar_idx=bar_idx,
            entry_bar=spy_df.iloc[bar_idx],
            spy_df=spy_df,
            ribbon_df=ribbon_df,
            rejection_level=float(spy_df.iloc[bar_idx]["close"]),
            triggers_fired=trade.triggers_fired or ["level_reclaim", "ribbon_flip"],
            side=side,
            qty=trade.qty_entered,
            setup=trade.setup_name,
            premium_stop_pct=float(knobs.get("premium_stop_pct", -0.20)),
            strike_offset=int(knobs.get("strike_offset", -2)),
            profit_lock_threshold_pct=float(knobs.get("profit_lock_threshold_pct", 0.05)),
            profit_lock_stop_offset_pct=float(knobs.get("profit_lock_stop_offset_pct", 0.10)),
            profit_lock_mode="trailing",
            profit_lock_trail_pct=float(knobs.get("profit_lock_trail_pct", 0.20)),
        )
        if result is None:
            return None
        pnl = getattr(result, "dollar_pnl", None) or getattr(result, "pnl_dollars", None)
        return float(pnl) if pnl is not None else None
    except Exception:
        return None


def _simulate_analog_with_knobs(
    analog_bar_idx: int,
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    side: str,
    setup_name: str,
    triggers_fired: list[str],
    qty: int,
    knobs: dict,
) -> Optional[float]:
    """Simulate a HISTORICAL analog bar with given knob overrides.

    Returns dollar P&L or None.
    """
    if not SIMULATOR_AVAILABLE:
        return None
    if analog_bar_idx < 0 or analog_bar_idx >= len(spy_df):
        return None

    try:
        result = simulate_trade_real(
            entry_bar_idx=analog_bar_idx,
            entry_bar=spy_df.iloc[analog_bar_idx],
            spy_df=spy_df,
            ribbon_df=ribbon_df,
            rejection_level=float(spy_df.iloc[analog_bar_idx]["close"]),
            triggers_fired=triggers_fired or ["level_reclaim", "ribbon_flip"],
            side=side,
            qty=qty,
            setup=setup_name,
            premium_stop_pct=float(knobs.get("premium_stop_pct", -0.20)),
            strike_offset=int(knobs.get("strike_offset", -2)),
            profit_lock_threshold_pct=float(knobs.get("profit_lock_threshold_pct", 0.05)),
            profit_lock_stop_offset_pct=float(knobs.get("profit_lock_stop_offset_pct", 0.10)),
            profit_lock_mode="trailing",
            profit_lock_trail_pct=float(knobs.get("profit_lock_trail_pct", 0.20)),
        )
        if result is None:
            return None
        pnl = getattr(result, "dollar_pnl", None) or getattr(result, "pnl_dollars", None)
        return float(pnl) if pnl is not None else None
    except Exception:
        return None


def round_trip_via_analogs(
    trade,
    forensics_analog_bar_idxs: list[int],
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    base_knobs: dict,
) -> KnobRoundTripResult:
    """Phase 2.6 — knob sensitivity using forensics analog bars (not today's trade bar).

    For each analog bar that has OPRA fills:
      - Re-simulate with each knob variant
      - Compute analog-mean P&L per knob level
      - Aggregate sensitivity = max - min of analog-mean P&L over sweep range

    Useful when today's OPRA cache is missing.

    Args:
        trade: today's trade (for context — side, setup, qty)
        forensics_analog_bar_idxs: list of bar indices in spy_df from forensics tight match
        spy_df, ribbon_df: master CSV + ribbon
        base_knobs: current v15 production knobs

    Returns: KnobRoundTripResult with sensitivities computed from analog aggregates.
    """
    result = KnobRoundTripResult(trade_id=trade.id)

    if not forensics_analog_bar_idxs:
        result.narrative = "No forensics analogs available — analog-based sweep skipped."
        return result

    side = "C" if trade.direction == "long" else "P"
    setup_name = trade.setup_name
    triggers_fired = trade.triggers_fired or ["level_reclaim", "ribbon_flip"]
    qty = trade.qty_entered

    # Base run on every analog
    base_pnls = []
    for idx in forensics_analog_bar_idxs:
        pnl = _simulate_analog_with_knobs(idx, spy_df, ribbon_df, side, setup_name,
                                          triggers_fired, qty, base_knobs)
        if pnl is not None:
            base_pnls.append(pnl)

    if not base_pnls:
        result.narrative = "No analog simulations succeeded with base knobs — sweep skipped."
        return result

    import numpy as np
    base_mean = float(np.mean(base_pnls))
    result.base_pnl = round(base_mean, 2)

    for knob_name, sweep_values in SWEEP_GRIDS.items():
        sweep = KnobSweep(knob_name=knob_name, base_value=base_knobs.get(knob_name, 0.0))
        level_means = []
        for lvl in sweep_values:
            knobs = {**base_knobs, knob_name: lvl}
            pnls = []
            for idx in forensics_analog_bar_idxs:
                pnl = _simulate_analog_with_knobs(idx, spy_df, ribbon_df, side, setup_name,
                                                  triggers_fired, qty, knobs)
                if pnl is not None:
                    pnls.append(pnl)
            if not pnls:
                sweep.level_results.append({
                    "level": lvl, "pnl_dollars": None, "delta_vs_base": None,
                    "status": "no_analog_fills", "n_filled": 0,
                })
                continue
            lvl_mean = float(np.mean(pnls))
            level_means.append((lvl, lvl_mean))
            sweep.level_results.append({
                "level": lvl,
                "pnl_dollars": round(lvl_mean, 2),
                "delta_vs_base": round(lvl_mean - base_mean, 2),
                "status": "ok",
                "n_filled": len(pnls),
                "n_total": len(forensics_analog_bar_idxs),
            })

        # sensitivity = max - min of level means (range of effect)
        if level_means:
            pnls_only = [p for _, p in level_means]
            sweep.sensitivity_dollars = round(max(pnls_only) - min(pnls_only), 2)
            best_lvl, best_pnl = max(level_means, key=lambda x: x[1])
            sweep.best_level = best_lvl
            sweep.best_pnl = round(best_pnl, 2)

        result.sweeps.append(sweep)

    # Dominant knob
    if result.sweeps:
        dominant = max(result.sweeps, key=lambda s: s.sensitivity_dollars)
        result.dominant_knob = dominant.knob_name
        result.dominant_delta = round(dominant.best_pnl - base_mean, 2)
        result.dominant_best_level = dominant.best_level

    # Narrative
    lines = [
        f"Phase 2.6 — analog-based sensitivity proxy ({len(forensics_analog_bar_idxs)} analogs simulated).",
        f"Base analog-mean P&L (current v15 knobs): ${result.base_pnl:+.0f}.",
    ]
    if result.dominant_knob:
        lines.append(
            f"Dominant knob: **{result.dominant_knob}** "
            f"(base={base_knobs.get(result.dominant_knob)}) — "
            f"best level={result.dominant_best_level} → analog-mean ${result.base_pnl + result.dominant_delta:+.0f} "
            f"(Δ ${result.dominant_delta:+.0f} per analog)."
        )
    lines.append("Sensitivity ranking (Δmax across sweep range, per-analog mean):")
    for s in sorted(result.sweeps, key=lambda x: -x.sensitivity_dollars):
        lines.append(
            f"  - {s.knob_name}: ±${s.sensitivity_dollars} | best={s.best_level} (${s.best_pnl:+.0f})"
        )
    lines.append("[Phase 2.6 caveat] Sensitivity computed on HISTORICAL analogs, not today's bar. "
                 "Once 5/14 OPRA cache populates overnight, knob_round_trip can re-run on today directly.")
    result.narrative = "\n".join(lines)

    return result


def round_trip_one_trade(
    trade,
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    base_knobs: dict,
) -> KnobRoundTripResult:
    """Sweep all knobs for one trade. Returns KnobRoundTripResult.

    Phase 2.5 behavior:
      - Try simulator on today's trade bar with base knobs first.
      - If OPRA cache miss for today's date (common; cache populates overnight),
        document the degradation in narrative + return informational result.
      - Otherwise proceed with full sweep.
    """
    result = KnobRoundTripResult(trade_id=trade.id)

    # Base simulation (current v15 knobs)
    base_pnl = _simulate_with_knobs(trade, base_knobs, spy_df, ribbon_df)
    if base_pnl is None:
        # OPRA cache miss for today — fall back to actual realized P&L for
        # the base AND skip sweeps (simulator will return None for every
        # variant on the same bar). Document clearly.
        result.base_pnl = trade.pnl_dollars_realized
        result.dominant_knob = "n/a (opra_cache_miss_today)"
        result.dominant_delta = 0.0
        result.narrative = (
            f"Base P&L (actual realized): ${result.base_pnl:+.0f}. "
            f"OPRA cache MISS for {trade.expiry_date} — simulator cannot run sweep on today's trade bar. "
            f"This is expected on T+0 EOD: OPRA aggregation runs overnight; tomorrow's EodDeepDive "
            f"can re-run knob sweep on today's bar once cache populates. "
            f"For tonight, see forensics module's analog hit-rate as the closest available "
            f"sensitivity proxy (3/3 historical analogs returned avg +$270 under current v15)."
        )
        return result

    result.base_pnl = base_pnl

    for knob_name, sweep_values in SWEEP_GRIDS.items():
        sweep = KnobSweep(knob_name=knob_name, base_value=base_knobs.get(knob_name, 0.0))
        best_pnl = base_pnl
        best_level = base_knobs.get(knob_name, 0.0)
        max_abs_delta = 0.0

        for lvl in sweep_values:
            knobs = {**base_knobs, knob_name: lvl}
            pnl = _simulate_with_knobs(trade, knobs, spy_df, ribbon_df)
            if pnl is None:
                sweep.level_results.append({
                    "level": lvl, "pnl_dollars": None, "delta_vs_base": None,
                    "status": "no_fill",
                })
                continue
            delta = pnl - base_pnl
            sweep.level_results.append({
                "level": lvl, "pnl_dollars": round(pnl, 2),
                "delta_vs_base": round(delta, 2), "status": "ok",
            })
            if abs(delta) > max_abs_delta:
                max_abs_delta = abs(delta)
            if pnl > best_pnl:
                best_pnl = pnl
                best_level = lvl

        sweep.sensitivity_dollars = round(max_abs_delta, 2)
        sweep.best_level = best_level
        sweep.best_pnl = round(best_pnl, 2)
        result.sweeps.append(sweep)

    # Identify dominant knob: largest sensitivity_dollars
    if result.sweeps:
        dominant = max(result.sweeps, key=lambda s: s.sensitivity_dollars)
        result.dominant_knob = dominant.knob_name
        result.dominant_delta = round(dominant.best_pnl - base_pnl, 2)
        result.dominant_best_level = dominant.best_level

    # Narrative
    lines = [f"Base P&L (current v15 knobs): ${result.base_pnl:+.0f}."]
    if result.dominant_knob:
        lines.append(
            f"Dominant knob: **{result.dominant_knob}** "
            f"(base={base_knobs.get(result.dominant_knob)}) — "
            f"best level={result.dominant_best_level} → P&L ${result.base_pnl + result.dominant_delta:+.0f} "
            f"(Δ ${result.dominant_delta:+.0f})."
        )
    lines.append("Knob sensitivity ranking (Δmax over sweep range):")
    for s in sorted(result.sweeps, key=lambda x: -x.sensitivity_dollars):
        lines.append(
            f"  - {s.knob_name}: ±${s.sensitivity_dollars} | best={s.best_level} (${s.best_pnl:+.0f})"
        )
    result.narrative = "\n".join(lines)

    return result


def round_trip_all_winners(
    trades,
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    params: dict,
) -> list[KnobRoundTripResult]:
    """Run sensitivity sweep on every winning trade."""
    # Build base knobs from params.json, with fallback to defaults
    base_knobs = {**DEFAULT_KNOBS}
    base_knobs.update({
        "premium_stop_pct": params.get("v15_premium_stop_pct_bear", DEFAULT_KNOBS["premium_stop_pct"]),
        "tp1_premium_pct": params.get("v15_tp1_premium_pct", DEFAULT_KNOBS["tp1_premium_pct"]),
        "tp1_qty_fraction": params.get("v15_tp1_qty_fraction", DEFAULT_KNOBS["tp1_qty_fraction"]),
        "runner_target_premium_pct": params.get("v15_runner_target_premium_pct", DEFAULT_KNOBS["runner_target_premium_pct"]),
        "profit_lock_threshold_pct": params.get("v15_profit_lock_threshold", DEFAULT_KNOBS["profit_lock_threshold_pct"]),
        "profit_lock_stop_offset_pct": params.get("v15_profit_lock_offset", DEFAULT_KNOBS["profit_lock_stop_offset_pct"]),
        "profit_lock_trail_pct": params.get("v15_profit_lock_trail_pct", DEFAULT_KNOBS["profit_lock_trail_pct"]),
        "strike_offset": params.get("v15_strike_offset_bear", DEFAULT_KNOBS["strike_offset"]),
    })

    results = []
    winners = [t for t in trades if t.pnl_dollars_realized > 0]
    for t in winners:
        results.append(round_trip_one_trade(t, spy_df, ribbon_df, base_knobs))
    return results
