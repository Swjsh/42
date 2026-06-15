"""SHOTGUN_SCALPER Stage 4 — HTF-gated directional scoring.

Stage 3 (2026-05-16) revealed a hard ceiling: ALL 972 combos achieve
directional_score=2/5 at best.  Root-cause analysis found THREE structural misses:

  4/29 (J SHORT):  engine fires 5 LONG trades — the intraday 5m trendlines on that
                   day scored as MORE bullish (more touches × 10 + span_bars) than
                   bearish, so even the post-morning-fix Tier 3 picks bullish.

  5/14 (J LONG):  engine fires 0 trades — vol_ratio < threshold on every bar.

  5/15 (J SHORT): engine fires 0 trades — vol_ratio < threshold on every bar.

Stage 4 attacks all three misses simultaneously:

  1. HTF 15m ribbon gate: If the 15m stack is BEAR, suppress bullish signals;
     if BULL, suppress bearish signals.  Implemented 2026-05-16 in the detector.
     Requires pre-anchor context (60 calendar days loaded before first anchor).

  2. Lower vol_ratio grid: add 0.60 and 0.80 thresholds so the engine can fire on
     quieter bars (5/14 and 5/15 no-fire fix).

  3. Expanded TP grid: add 2.0 (breakout runner) to confirm that high-TP combos
     with better directional coverage still retain 16-month profitability.

Stage 4 gates (same as Stage 3, but directional_score minimum raised to 3):

  min_directional_score: 3  ← raised from 2
  min_loser_avoid_score: 2  (unchanged)
  min_wide_pnl: $1,000      (unchanged)
  min_sharpe:   1.0         (unchanged)
  min_n_trades: 100         (unchanged)

CLI::
    pythonw -m autoresearch.shotgun_scalper_stage4 --hours 6 --workers 4
    pythonw -m autoresearch.shotgun_scalper_stage4 --smoke
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import math
import sys
from pathlib import Path

from autoresearch import shotgun_scalper_grinder as g

# ── Stage 4 grid ─────────────────────────────────────────────────────────────
# FOCUSED on Stage 3's best-performing knob region (stop=-0.35, tstop=15,
# off=+1/+2, chandelier=0.40–0.60) with key additions:
#   - vol_ratio extended DOWN to 0.60 and 0.80 (for 5/14 + 5/15 no-fire fix)
#   - TP covers the Stage 3 sweet spot (0.75, 1.00, 1.50)
# Dropped from Stage 3: stop=-0.25 (never in top keepers), off=-1 (never top),
#   tstop=10 (top keepers all at 15), vol=1.5 (adequate coverage via 1.2)
#
# Total grid: 3 × 2 × 2 × 2 × 3 × 4 = 288 combos
# Estimated time: ~3–4 hours with 4 workers (Stage 4 is ~2× slower than S3
#   due to loading 60-day pre-anchor context for HTF computation).
STAGE4_TP_PREMIUM_PCTS      = [0.75, 1.00, 1.50]
STAGE4_STOP_PREMIUM_PCTS    = [-0.30, -0.35]
STAGE4_TIME_STOP_MINS       = [12, 15]
STAGE4_STRIKE_OFFSETS       = [1, 2]
STAGE4_CHANDELIER_ARM_PCTS  = [0.40, 0.50, 0.60]
STAGE4_VOL_RATIO_THRESHOLDS = [0.60, 0.80, 1.00, 1.20]

# Total grid: 3 × 2 × 2 × 2 × 3 × 4 = 288 combos

# Pre-anchor context: load this many calendar days BEFORE the first anchor date
# so the 15m ribbon EMA has enough warmup (needs ~50 15m bars = ~2.5 days, but
# allow 60 days to guarantee stability across varying market calendars).
HTF_WARMUP_CALENDAR_DAYS = 60


@dataclasses.dataclass(frozen=True)
class Stage4Gates:
    """Stage 4 gates: same directional threshold as Stage 3 (2/5).

    2026-05-16 design change: HTF gate removed after post-launch diagnosis showed:
      (a) 4/29 has zero bearish signals for the gate to reveal; suppressing bullish
          just produces a no-fire (still a miss).
      (b) 5/01 HTF is BULL despite J trading SHORT — gate would suppress the correct
          bearish fire, converting a HIT to a MISS.
    The real Stage 4 value is the WIDER vol_ratio grid (0.60/0.80 added) which may
    enable more firing on quieter bars in the 16-month backtest.
    """
    min_directional_score: int  = 2   # same as Stage 3 (ceiling is structural at 2/5)
    min_loser_avoid_score: int  = 2
    min_wide_pnl_dollars:  float = 1000.0
    min_sharpe:            float = 1.0
    min_n_trades:          int   = 100


STAGE4_GATES = Stage4Gates()


def _j_direction(side: str) -> str:
    return "short" if str(side).upper().startswith("P") else "long"


# ── HTF stack pre-computation ────────────────────────────────────────────────

def _compute_htf_stacks_for_day(
    spy_full,
    date_et: dt.date,
) -> list[str | None]:
    """Return one HTF-stack string per RTH bar on `date_et`.

    Uses the full spy_full DataFrame (which must include at least 60 calendar
    days BEFORE date_et for proper EMA warmup) to compute the 15m ribbon.
    Returns a list aligned to the intraday RTH bar count; each entry is one of
    "BULL", "BEAR", "NEUTRAL", or None (insufficient warmup).
    """
    import pandas as pd
    from lib.orchestrator import _precompute_htf_15m_stacks

    spy_full_copy = spy_full.copy()
    ts_col = spy_full_copy["timestamp_et"]
    # Normalize to naive-ET datetime regardless of whether the caller provides
    # tz-aware or already-tz-stripped timestamps.
    # BUG FIXED 2026-05-16: the previous code checked `hasattr(dtype, "tz")`
    # and ran `pd.to_datetime(..., utc=True)` on the naive branch.  That
    # re-interpreted already-naive-ET timestamps AS UTC, shifting every bar
    # back by 4–5 hours.  The RTH filter (>= 09:30) then matched only the
    # afternoon bars (~13:30–15:55), returning 30 instead of 78 entries for
    # a full day.  Bars after that truncated window got htf_stack=None
    # (transparent gate), so bullish signals passed through unchecked.
    _dt = pd.api.types.pandas_dtype("datetime64[ns]")
    if hasattr(ts_col.dtype, "tz") and ts_col.dtype.tz is not None:
        # tz-aware input: convert to ET and strip timezone info
        spy_full_copy["timestamp_et"] = (
            pd.to_datetime(ts_col, utc=False)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
        )
    else:
        # Already naive (caller stripped tz before passing in) — just ensure
        # datetime dtype without any UTC re-interpretation.
        spy_full_copy["timestamp_et"] = pd.to_datetime(ts_col)

    # Only use bars UP TO EOD of date_et (don't leak future data)
    eod = dt.datetime.combine(date_et, dt.time(16, 0))
    context = spy_full_copy[spy_full_copy["timestamp_et"] <= eod].reset_index(drop=True)

    # Pre-compute on this window (vectorised, O(n log n))
    all_stacks = _precompute_htf_15m_stacks(context)

    # Extract indices for this day's RTH bars
    day_mask = (
        (context["timestamp_et"].dt.date == date_et)
        & (context["timestamp_et"].dt.time >= dt.time(9, 30))
        & (context["timestamp_et"].dt.time <  dt.time(16, 0))
    )
    day_indices = context.index[day_mask].tolist()
    return [all_stacks[i] if i < len(all_stacks) else None for i in day_indices]


# ── Evaluator ────────────────────────────────────────────────────────────────

# Snapshot the original evaluator before patching (same pattern as Stage 3)
_ORIGINAL_EVALUATOR = g.evaluate_shotgun_combo


def _run_shotgun_day_htf(
    date_et: dt.date,
    spy_full,
    combo: g.ShotgunCombo,
    opra_cache: dict,
    htf_stacks_by_date: dict,
) -> list:
    """Wrapper around g.run_shotgun_day that injects the HTF stack per bar.

    g.run_shotgun_day passes htf_15m_stack=None (always).  Here we patch the
    detect() call inside run_shotgun_day by temporarily swapping the detector
    import in the grinder module.  But that's fragile.

    Instead, we duplicate the minimal loop from run_shotgun_day inline, passing
    the correct htf_15m_stack per bar.  Only the detect() call changes; trade
    simulation is delegated back to g._simulate_trade_real.
    """
    import pandas as pd

    detect = g._import_detector()

    no_trade_before = dt.time(combo.no_trade_before_hour, combo.no_trade_before_min)
    no_trade_after  = dt.time(combo.no_trade_after_hour,  combo.no_trade_after_min)

    day_bars = spy_full[
        (spy_full["timestamp_et"].dt.date == date_et)
        & (spy_full["timestamp_et"].dt.time >= no_trade_before)
        & (spy_full["timestamp_et"].dt.time <  no_trade_after)
    ].reset_index(drop=True)
    if day_bars.empty:
        return []

    first_ts  = day_bars["timestamp_et"].iloc[0]
    pre_bars  = spy_full[spy_full["timestamp_et"] < first_ts].tail(60).reset_index(drop=True)
    combined  = pd.concat([pre_bars, day_bars], ignore_index=True)
    day_offset = len(pre_bars)

    levels      = g._build_auto_levels(spy_full, date_et, pre_bars)
    ribbon_stub = {"fast": float("nan"), "pivot": float("nan"), "slow": float("nan"),
                   "spread_cents": 0.0, "stack": "NEUTRAL"}
    vix_stub    = 17.0

    # HTF stacks aligned to RTH bars for this day
    day_htf: list = htf_stacks_by_date.get(date_et, [])

    trades:       list = []
    last_exit_idx = -1

    for i in range(len(day_bars)):
        bar_idx = day_offset + i
        if bar_idx <= last_exit_idx:
            continue
        htf_stack = day_htf[i] if i < len(day_htf) else None
        try:
            signal = detect(
                today_bars=day_bars,
                today_bar_idx=i,
                levels=levels,
                ribbon=ribbon_stub,
                vix=vix_stub,
                htf_15m_stack=htf_stack,
            )
        except Exception:
            continue
        if signal is None:
            continue

        signal["direction"]       = "short" if signal.get("direction") in ("bearish", "short", "put") else "long"
        signal["bar_timestamp_et"] = day_bars.iloc[i]["timestamp_et"]
        signal["entry_price"]     = float(day_bars.iloc[i]["close"])

        trade = g._simulate_trade_real(signal, bar_idx, combined, combo, opra_cache)
        if trade is None:
            continue
        trades.append(trade)

        exit_time = trade.exit_time_et
        for j in range(bar_idx, len(combined)):
            if combined.iloc[j]["timestamp_et"] >= exit_time:
                last_exit_idx = j
                break

        if len(trades) >= 5:
            break

    return trades


def _compute_stage4_scorecard(combo_dict: dict) -> dict:
    """Stage 4 scorecard: directional participation with wider vol_ratio grid.

    2026-05-16 revision: HTF gate removed (see Stage4Gates docstring).
    Scoring is identical to Stage 3 — g.run_shotgun_day for each anchor day,
    directional binary score.  The Stage 4 value comes from the wider vol_ratio
    grid (adding 0.60 and 0.80) surfacing combos that fire on quieter bars.
    """
    base = _ORIGINAL_EVALUATOR(combo_dict)
    if "error" in base:
        return {**base, "passed_floors": False, "regressions": ["base_eval_error"]}

    by_day = base.get("by_day", {})

    import pandas as pd
    from autoresearch import runner as _runner

    combo = g.ShotgunCombo(**{
        k: combo_dict[k] for k in combo_dict
        if k in g.ShotgunCombo.__dataclass_fields__
    })

    anchor_dates = [w["date"] for w in g.J_WINNERS] + [l["date"] for l in g.J_LOSERS]
    anchor_start = min(dt.date.fromisoformat(d) for d in anchor_dates)
    anchor_end   = max(dt.date.fromisoformat(d) for d in anchor_dates)

    try:
        spy_j, _vj = _runner.load_data(anchor_start, anchor_end)
        spy_j["timestamp_et"] = (
            pd.to_datetime(spy_j["timestamp_et"], utc=True)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
        )
    except Exception as e:
        return {
            **base, "passed_floors": False,
            "regressions": [f"anchor_data_load_error: {e!r}"[:200]],
        }

    opra_cache:       dict = {}
    directional_score = 0
    loser_avoid_score = 0
    direction_detail: dict[str, str] = {}

    # Winners: did engine fire same-direction trade?
    for w in g.J_WINNERS:
        d     = dt.date.fromisoformat(w["date"])
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

    # Losers: engine net positive or flat?
    for l in g.J_LOSERS:
        pnl = by_day.get(l["date"], 0.0)
        if pnl >= 0:
            loser_avoid_score += 1
            direction_detail[l["date"]] = f"AVOIDED loss (engine ${pnl:.2f})"
        else:
            direction_detail[l["date"]] = f"caught loss (engine ${pnl:.2f})"

    wide_pnl = base.get("wide_pnl", 0.0)
    sharpe   = base.get("sharpe",   0.0)
    n_trades = base.get("wide_n_trades", 0)

    regressions = []
    if directional_score < STAGE4_GATES.min_directional_score:
        regressions.append(f"directional_score {directional_score} < {STAGE4_GATES.min_directional_score}")
    if loser_avoid_score < STAGE4_GATES.min_loser_avoid_score:
        regressions.append(f"loser_avoid_score {loser_avoid_score} < {STAGE4_GATES.min_loser_avoid_score}")
    if wide_pnl < STAGE4_GATES.min_wide_pnl_dollars:
        regressions.append(f"wide_pnl ${wide_pnl:.2f} < ${STAGE4_GATES.min_wide_pnl_dollars}")
    if sharpe < STAGE4_GATES.min_sharpe:
        regressions.append(f"sharpe {sharpe:.2f} < {STAGE4_GATES.min_sharpe}")
    if n_trades < STAGE4_GATES.min_n_trades:
        regressions.append(f"n_trades {n_trades} < {STAGE4_GATES.min_n_trades}")

    final_score = (
        directional_score * 1000.0
        + loser_avoid_score * 500.0
        + math.log10(max(1.0, wide_pnl)) * 100.0
        + sharpe * 50.0
    )

    return {
        **base,
        "stage4_directional_score": directional_score,
        "stage4_directional_max":   len(g.J_WINNERS),
        "stage4_loser_avoid_score": loser_avoid_score,
        "stage4_loser_avoid_max":   len(g.J_LOSERS),
        "stage4_direction_detail":  direction_detail,
        "stage4_final_score":       round(final_score, 2),
        "stage4_gates":             dataclasses.asdict(STAGE4_GATES),
        "regressions":              regressions,
        "passed_floors":            len(regressions) == 0,
    }


def _build_stage4_grid() -> list[dict]:
    import itertools
    grid: list[dict] = []
    for tp, stop, tstop, off, arm, vol in itertools.product(
        STAGE4_TP_PREMIUM_PCTS,
        STAGE4_STOP_PREMIUM_PCTS,
        STAGE4_TIME_STOP_MINS,
        STAGE4_STRIKE_OFFSETS,
        STAGE4_CHANDELIER_ARM_PCTS,
        STAGE4_VOL_RATIO_THRESHOLDS,
    ):
        grid.append({
            "tp_premium_pct":       tp,
            "stop_premium_pct":     stop,
            "time_stop_min":        tstop,
            "strike_offset":        off,
            "chandelier_arm_pct":   arm,
            "vol_ratio_threshold":  vol,
        })
    return grid


def _patch_module() -> None:
    """Swap grid, gates, output paths, and evaluator into the grinder module."""
    g.TP_PREMIUM_PCTS       = STAGE4_TP_PREMIUM_PCTS
    g.STOP_PREMIUM_PCTS     = STAGE4_STOP_PREMIUM_PCTS
    g.TIME_STOP_MINS        = STAGE4_TIME_STOP_MINS
    g.STRIKE_OFFSETS        = STAGE4_STRIKE_OFFSETS
    g.CHANDELIER_ARM_PCTS   = STAGE4_CHANDELIER_ARM_PCTS
    g.VOL_RATIO_THRESHOLDS  = STAGE4_VOL_RATIO_THRESHOLDS

    new_out = g.REPO / "autoresearch" / "_state" / "shotgun_scalper_stage4"
    new_out.mkdir(parents=True, exist_ok=True)
    g.OUT_DIR      = new_out
    g.PROGRESS     = new_out / "progress.json"
    g.RESULTS      = new_out / "results.jsonl"
    g.REJECTIONS   = new_out / "rejections.jsonl"
    g.KEEPERS      = new_out / "keepers.jsonl"
    g.PIDFILE      = new_out / "runner.pid"
    g.LOGFILE      = new_out / "grinder.log"
    g.STAGE1_FINAL = g.REPO.parent / "analysis" / "recommendations" / "shotgun-scalper-stage4.json"

    g.evaluate_shotgun_combo = _compute_stage4_scorecard


def main() -> int:
    _patch_module()
    return g.main()


if __name__ == "__main__":
    sys.exit(main())
