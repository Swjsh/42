"""SHOTGUN_SCALPER Stage 3 — directional-participation scoring.

Stage 2 (in progress) revealed that 729 of 876 combos are PROFITABLE on the
16-month wide window (sharpe > 0, expectancy > 0, wide_pnl > 0), yet all are
rejected because they capture less than 20% of J's dollar P&L on the 8
anchor days.

J's feedback (2026-05-16, 13:50 ET): "as long as we take the trade, I feel
like that counts for something." The dollar-match gate is too strict —
qty mismatch alone (engine baseline qty=3 vs J's actual 5-20) ensures
the engine can't match J's dollars even when it trades correctly.

Stage 3 replaces dollar-match scoring with BINARY DIRECTIONAL PARTICIPATION:

  directional_score: For each of 5 J-winner days, did engine fire >=1 trade
    in the same direction as J's trade on that day? Binary 1/0. Max 5.

  loser_avoid_score: For each of 3 J-loser days, was engine flat or
    net-positive (didn't get caught in J's loss)? Binary 1/0. Max 3.

  wide_pnl: 16-month wide-window aggregate. Must be > +$1,000.

  sharpe: 16-month risk-adjusted. Must be > 1.0.

  final_score = directional_score * 1000
              + loser_avoid_score * 500
              + log10(max(1, wide_pnl)) * 100
              + sharpe * 50

CLI::
    pythonw -m autoresearch.shotgun_scalper_stage3 --hours 3 --workers 4
    pythonw -m autoresearch.shotgun_scalper_stage3 --smoke
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from autoresearch import shotgun_scalper_grinder as g

# ── Stage 3 grid: focused around Stage 2 winners ────────────────────────────
STAGE3_TP_PREMIUM_PCTS = [0.50, 0.75, 1.00, 1.50]
STAGE3_STOP_PREMIUM_PCTS = [-0.25, -0.30, -0.35]
STAGE3_TIME_STOP_MINS = [10, 12, 15]
STAGE3_STRIKE_OFFSETS = [-1, 1, 2]
STAGE3_CHANDELIER_ARM_PCTS = [0.40, 0.50, 0.60]
STAGE3_VOL_RATIO_THRESHOLDS = [1.0, 1.2, 1.5]

# Total grid: 4 * 3 * 3 * 3 * 3 * 3 = 972 combos


# ── Stage 3 gates (directional participation, not dollar match) ─────────────
import dataclasses


@dataclasses.dataclass(frozen=True)
class Stage3Gates:
    """Permissive gates: rewards directional participation + wide profitability."""
    min_directional_score: int = 2  # at least 2 of 5 J-winner days same direction
    min_loser_avoid_score: int = 2  # at least 2 of 3 J-loser days avoided
    min_wide_pnl_dollars: float = 1000.0  # net positive over 16mo
    min_sharpe: float = 1.0
    min_n_trades: int = 100  # statistical significance


STAGE3_GATES = Stage3Gates()


# Direction mapping: J's side "P" = bearish/short; "C" = bullish/long
def _j_direction(side: str) -> str:
    return "short" if str(side).upper().startswith("P") else "long"


# Snapshot the original evaluator BEFORE any patching so the Stage 3 wrapper
# can invoke it without infinite recursion (the patch swaps the symbol on g).
_ORIGINAL_EVALUATOR = g.evaluate_shotgun_combo


def _compute_stage3_scorecard(combo_dict: dict) -> dict:
    """Run Stage 1 grinder's evaluator, then re-score with directional logic.

    Reuses the ORIGINAL evaluator (snapshotted before patch) for the heavy
    lifting (by_day per anchor + wide window stats). Then computes
    directional_score and loser_avoid_score from by_day and applies Stage 3
    gates.
    """
    base = _ORIGINAL_EVALUATOR(combo_dict)
    if "error" in base:
        return {**base, "passed_floors": False, "regressions": ["base_eval_error"]}

    by_day = base.get("by_day", {})

    # Need to know which direction engine actually traded each day. The base
    # evaluator returns dollar P&L but not direction breakdown. Re-derive by
    # calling run_shotgun_day per anchor and inspecting trades.
    import datetime as dt
    import pandas as pd
    from autoresearch import runner as _runner

    combo = g.ShotgunCombo(**{
        k: combo_dict[k] for k in combo_dict
        if k in g.ShotgunCombo.__dataclass_fields__
    })

    anchor_dates = [w["date"] for w in g.J_WINNERS] + [l["date"] for l in g.J_LOSERS]
    anchor_start = min(dt.date.fromisoformat(d) for d in anchor_dates)
    anchor_end = max(dt.date.fromisoformat(d) for d in anchor_dates)

    try:
        spy_j, _vj = _runner.load_data(anchor_start, anchor_end)
        spy_j["timestamp_et"] = (
            pd.to_datetime(spy_j["timestamp_et"], utc=True)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
        )
    except Exception as e:
        return {
            **base,
            "passed_floors": False,
            "regressions": [f"anchor_data_load_error: {e!r}"[:200]],
        }

    opra_cache: dict = {}
    directional_score = 0
    loser_avoid_score = 0
    direction_detail: dict[str, str] = {}

    # Winners: did engine fire same-direction trade?
    for w in g.J_WINNERS:
        d = dt.date.fromisoformat(w["date"])
        j_dir = _j_direction(w["side"])
        try:
            day_trades = g.run_shotgun_day(d, spy_j, combo, opra_cache)
        except Exception:
            day_trades = []
        same_dir_fires = [t for t in day_trades if t.direction == j_dir]
        if same_dir_fires:
            directional_score += 1
            direction_detail[w["date"]] = f"YES same-dir ({j_dir}), {len(same_dir_fires)} fires"
        else:
            direction_detail[w["date"]] = f"miss (j={j_dir}, engine={[t.direction for t in day_trades] or 'no-fire'})"

    # Losers: was engine net positive or flat?
    for l in g.J_LOSERS:
        pnl = by_day.get(l["date"], 0.0)
        if pnl >= 0:
            loser_avoid_score += 1
            direction_detail[l["date"]] = f"AVOIDED loss (engine ${pnl:.2f})"
        else:
            direction_detail[l["date"]] = f"caught loss (engine ${pnl:.2f})"

    # Wide window pulls (already computed by base eval).
    wide_pnl = base.get("wide_pnl", 0.0)
    sharpe = base.get("sharpe", 0.0)
    n_trades = base.get("wide_n_trades", 0)

    # Gates
    regressions = []
    if directional_score < STAGE3_GATES.min_directional_score:
        regressions.append(
            f"directional_score {directional_score} < {STAGE3_GATES.min_directional_score}"
        )
    if loser_avoid_score < STAGE3_GATES.min_loser_avoid_score:
        regressions.append(
            f"loser_avoid_score {loser_avoid_score} < {STAGE3_GATES.min_loser_avoid_score}"
        )
    if wide_pnl < STAGE3_GATES.min_wide_pnl_dollars:
        regressions.append(f"wide_pnl ${wide_pnl:.2f} < ${STAGE3_GATES.min_wide_pnl_dollars}")
    if sharpe < STAGE3_GATES.min_sharpe:
        regressions.append(f"sharpe {sharpe:.2f} < {STAGE3_GATES.min_sharpe}")
    if n_trades < STAGE3_GATES.min_n_trades:
        regressions.append(f"n_trades {n_trades} < {STAGE3_GATES.min_n_trades}")

    final_score = (
        directional_score * 1000.0
        + loser_avoid_score * 500.0
        + math.log10(max(1.0, wide_pnl)) * 100.0
        + sharpe * 50.0
    )

    return {
        **base,
        "stage3_directional_score": directional_score,
        "stage3_directional_max": len(g.J_WINNERS),
        "stage3_loser_avoid_score": loser_avoid_score,
        "stage3_loser_avoid_max": len(g.J_LOSERS),
        "stage3_direction_detail": direction_detail,
        "stage3_final_score": round(final_score, 2),
        "stage3_gates": dataclasses.asdict(STAGE3_GATES),
        "regressions": regressions,
        "passed_floors": len(regressions) == 0,
    }


def _build_stage3_grid() -> list[dict]:
    import itertools
    grid: list[dict] = []
    for tp, stop, tstop, off, arm, vol in itertools.product(
        STAGE3_TP_PREMIUM_PCTS,
        STAGE3_STOP_PREMIUM_PCTS,
        STAGE3_TIME_STOP_MINS,
        STAGE3_STRIKE_OFFSETS,
        STAGE3_CHANDELIER_ARM_PCTS,
        STAGE3_VOL_RATIO_THRESHOLDS,
    ):
        grid.append({
            "tp_premium_pct": tp,
            "stop_premium_pct": stop,
            "time_stop_min": tstop,
            "strike_offset": off,
            "chandelier_arm_pct": arm,
            "vol_ratio_threshold": vol,
        })
    return grid


def _patch_module() -> None:
    """Swap grid + gates + output paths into the grinder module."""
    g.TP_PREMIUM_PCTS = STAGE3_TP_PREMIUM_PCTS
    g.STOP_PREMIUM_PCTS = STAGE3_STOP_PREMIUM_PCTS
    g.TIME_STOP_MINS = STAGE3_TIME_STOP_MINS
    g.STRIKE_OFFSETS = STAGE3_STRIKE_OFFSETS
    g.CHANDELIER_ARM_PCTS = STAGE3_CHANDELIER_ARM_PCTS
    g.VOL_RATIO_THRESHOLDS = STAGE3_VOL_RATIO_THRESHOLDS

    # Swap output directory + paths
    new_out = g.REPO / "autoresearch" / "_state" / "shotgun_scalper_stage3"
    new_out.mkdir(parents=True, exist_ok=True)
    g.OUT_DIR = new_out
    g.PROGRESS = new_out / "progress.json"
    g.RESULTS = new_out / "results.jsonl"
    g.REJECTIONS = new_out / "rejections.jsonl"
    g.KEEPERS = new_out / "keepers.jsonl"
    g.PIDFILE = new_out / "runner.pid"
    g.LOGFILE = new_out / "grinder.log"
    g.STAGE1_FINAL = g.REPO.parent / "analysis" / "recommendations" / "shotgun-scalper-stage3.json"

    # Replace the per-combo evaluator with Stage 3's directional scorer.
    # NOTE: _ORIGINAL_EVALUATOR was snapshotted at module-import time so the
    # Stage 3 wrapper can call back into the unpatched function (avoid recursion).
    g.evaluate_shotgun_combo = _compute_stage3_scorecard


def main() -> int:
    _patch_module()
    return g.main()


if __name__ == "__main__":
    sys.exit(main())
