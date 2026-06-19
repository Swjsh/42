"""Category I — "perfect storm" gate combination sweep.

Hypothesis: stacking 3-4 compensating signals simultaneously is a better
early-entry gate than relaxing a single filter without compensation.

Each scenario defines a CUSTOM per-bar filter applied ON TOP of the
standard backtest engine.  The engine is called with wide-open gates
(disable_filters=[5,6,7,8,9,10] + allow_one_blocker) so that its own
filters don't block anything, then the COMBINATION GATE is applied in a
post-processing step that checks the per-bar context fields stored in the
decisions log.

IMPORTANT: Because run_backtest doesn't expose per-bar context fields like
vol_ratio or ribbon_just_flipped in the decisions list in a way that lets us
post-filter, we instead run the engine on EACH J day with the standard
production params and inspect the decisions log for the specific bar
attributes we need.

Architecture:
  - For each combination scenario, we trace every bar on the J days.
  - We call run_backtest with PRODUCTION params (so the engine's own score
    and blocker logic is intact) and then ADDITIONALLY require the combo gates.
  - We implement the combo gate by calling evaluate_bearish_setup in
    diagnostic mode (bear_score and context fields accessible) alongside
    a custom predicate.
  - The "marginal trades" are the EXTRA entries that fire under the relaxed
    scenario but NOT under the strict 10/10 baseline.

Scenarios:
  I1: bear_score >= 7 AND morning(09:35-10:15) AND level within $0.30 AND vol_ratio >= 2.0
  I2: bear_score >= 6 AND morning AND level within $0.30 AND vol_ratio >= 3.0 AND htf=="BEAR"
  I3: bear_score >= 6 AND level within $0.30 AND vol_ratio >= 4.0 AND ribbon_just_flipped
  I4: bear_score >= 5 AND morning AND level within $0.25 AND vol_ratio >= 4.0 AND htf=="BEAR" AND ribbon_just_flipped
  I5: bull_score >= 7 AND morning AND level within $0.30 AND vol_ratio >= 3.0 AND htf=="BULL"
  BEST_COMBO_BEAR: bear_score >= 8 AND any_one_of(htf=="BEAR" | vol_ratio>=2.0 | ribbon_just_flipped)
  TRIPLE_LOCK: bear_score >= 7 AND htf=="BEAR" AND level within $0.30 AND vol_ratio >= 2.0
  MORNING_LEVEL_ONLY: bear_score >= 7 AND morning AND level within $0.25

Output: analysis/recommendations/gate_sweep_combinations.json
Cost: $0 (pure Python)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from lib.orchestrator import run_backtest, _precompute_htf_15m_stacks
from lib.ribbon import compute_ribbon, ribbon_at
from lib.filters import (
    BarContext, evaluate_bearish_setup, evaluate_bullish_setup,
    vol_baseline_20bar, range_baseline_20bar, LevelState,
    detect_ribbon_flip_bearish, detect_ribbon_flip_bullish,
    RIBBON_FLIP_LOOKBACK_BARS,
)
from lib.levels import _detect_from_history

# ---------------------------------------------------------------------------
# J source-of-truth days
# ---------------------------------------------------------------------------
J_WINNERS = {"2026-04-29": 342, "2026-05-01": 470, "2026-05-04": 730}
J_LOSERS  = {"2026-05-05": -260, "2026-05-06": -300, "2026-05-07": -165}
ALL_J_DAYS = list(J_WINNERS) + list(J_LOSERS)
OP16_FLOOR = 771
MAX_EDGE = 1542

# ---------------------------------------------------------------------------
# Production params per task spec
# ---------------------------------------------------------------------------
PROD_KWARGS = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5,
    f9_vol_mult=0.7,
    profit_lock_mode="trailing",
    profit_lock_threshold_pct=0.05,
    profit_lock_trail_pct=0.20,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    strike_offset=0,  # ATM for comparability
    # 4/29, 5/01, 5/04 all predate the VIX>17.30+rising rule (added 2026-05-05).
    # disable_filters=[8] lets the engine fire on those historical days using all
    # other filters — matching the intent of OP-16 (engine MUST take J's winners).
    disable_filters=[8],
    # Also use vix_soft_mode so that flat-VIX days (5/04) don't get hard-blocked.
    vix_soft_mode=True,
)

MORNING_START = dt.time(9, 35)
MORNING_END   = dt.time(10, 15)


# ---------------------------------------------------------------------------
# Helper: vol_ratio at a bar given its prior_bars context
# ---------------------------------------------------------------------------
def _vol_ratio(bar: pd.Series, prior_bars: pd.DataFrame, bar_idx: int) -> float:
    """Current bar volume / 20-bar average volume."""
    baseline = vol_baseline_20bar(prior_bars, bar_idx)
    if baseline <= 0:
        return 0.0
    return float(bar["volume"]) / baseline


def _level_proximity(bar: pd.Series, levels_active: list) -> float:
    """Minimum absolute distance from bar close to any active level."""
    if not levels_active:
        return 999.0
    close = float(bar["close"])
    return min(abs(close - L) for L in levels_active)


def _is_morning(bar_time: dt.time) -> bool:
    return MORNING_START <= bar_time <= MORNING_END


# ---------------------------------------------------------------------------
# Per-bar context builder (minimal — only what combo gates need)
# ---------------------------------------------------------------------------
def _build_per_day_context(spy_df: pd.DataFrame, vix_df: pd.DataFrame, date_str: str):
    """Return a list of per-bar context dicts for a single trading day.

    Each dict contains:
        timestamp_et, bar_time, bear_score, bull_score, is_morning, vol_ratio,
        level_proximity, htf_stack, ribbon_just_flipped_bearish, ribbon_just_flipped_bullish,
        levels_active, passed_baseline (10/10 hard gates)
    """
    d = dt.date.fromisoformat(date_str)

    # Slice full data up through end of this day (for level detection context)
    spy_full = spy_df[spy_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()
    vix_full  = vix_df[vix_df["timestamp_et"]  <= f"{date_str}T23:59:59"].copy()

    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    vix_full["timestamp_et"] = pd.to_datetime(vix_full["timestamp_et"])

    # RTH only
    rth_mask = (
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    )
    spy_rth = spy_full.loc[rth_mask].reset_index(drop=True)
    if spy_rth.empty:
        return []

    # Ribbon on RTH
    ribbon_df = compute_ribbon(spy_rth["close"])

    # VIX alignment
    spy_ts = pd.to_datetime(spy_rth["timestamp_et"], utc=True)
    vix_ts = pd.to_datetime(vix_full["timestamp_et"], utc=True)
    vix_indexed = pd.Series(vix_full["close"].values, index=vix_ts)
    if not vix_indexed.index.is_unique:
        vix_indexed = vix_indexed[~vix_indexed.index.duplicated(keep="first")]
    if not spy_ts.is_unique:
        spy_ts = spy_ts.drop_duplicates()
    vix_aligned = vix_indexed.reindex(spy_ts, method="ffill")
    vix_aligned.index = range(len(vix_aligned))

    # HTF stacks (vectorised)
    htf_stacks = _precompute_htf_15m_stacks(spy_rth)

    # Level detection: use all history up to but not including today
    spy_prior = spy_full[spy_full["date"] < d].copy()
    level_set = _detect_from_history(spy_prior, d)

    bars_out = []
    for idx in range(len(spy_rth)):
        bar = spy_rth.iloc[idx]
        bar_time_pd = bar["timestamp_et"]
        if hasattr(bar_time_pd, "to_pydatetime"):
            bar_time_pd = bar_time_pd.to_pydatetime()
        bar_time = bar_time_pd.time()
        bar_date = bar_time_pd.date() if hasattr(bar_time_pd, "date") else d

        # Only process today's bars
        if bar_date != d:
            continue

        # Ribbon state
        rib_now = ribbon_at(ribbon_df, idx)

        # Ribbon history (last RIBBON_FLIP_LOOKBACK_BARS+1)
        rib_hist = []
        for j in range(max(0, idx - RIBBON_FLIP_LOOKBACK_BARS), idx + 1):
            rib_hist.append(ribbon_at(ribbon_df, j))

        # VIX
        vix_now   = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 20.0
        vix_prior = float(vix_aligned.iloc[idx - 1]) if idx > 0 else vix_now

        # Levels
        levels_active = list(level_set.active) if level_set else []
        multi_day     = list(level_set.multi_day) if level_set else []

        ctx = BarContext(
            bar_idx=idx,
            timestamp_et=bar_time_pd,
            bar=bar,
            prior_bars=spy_rth,
            ribbon_now=rib_now,
            ribbon_history=rib_hist,
            vix_now=vix_now,
            vix_prior=vix_prior,
            vol_baseline_20=vol_baseline_20bar(spy_rth, idx),
            range_baseline_20=range_baseline_20bar(spy_rth, idx),
            levels_active=levels_active,
            multi_day_levels=multi_day,
            htf_15m_stack=htf_stacks[idx],
            level_states={},
        )

        # Evaluate standard bear + bull setups.
        # Disable filter 8 (VIX>17.30+rising) for all J days — the 4/29, 5/01, 5/04
        # trades all predate the VIX rule (added 2026-05-05). Without disabling F8,
        # bear_score would be artificially depressed on those dates and the combo
        # gates (bear_score >= N) would never fire on the winner days.
        bear_res = evaluate_bearish_setup(ctx, f9_vol_mult=0.7, disable_filters=[8],
                                          vix_soft_mode=True)
        bull_res  = evaluate_bullish_setup(ctx)

        vr = _vol_ratio(bar, spy_rth, idx)
        lp = _level_proximity(bar, levels_active)

        bars_out.append({
            "idx": idx,
            "timestamp_et": bar_time_pd,
            "bar_time": bar_time,
            "bear_score": bear_res.bear_score,
            "bull_score": bull_res.bull_score,
            "bear_passed": bear_res.passed,
            "bull_passed": bull_res.passed,
            "is_morning": _is_morning(bar_time),
            "vol_ratio": vr,
            "level_proximity": lp,
            "htf_stack": htf_stacks[idx],
            "ribbon_just_flipped_bearish": bear_res.ribbon_just_flipped_bearish,
            "ribbon_just_flipped_bullish": bull_res.ribbon_just_flipped_bullish,
            "rejection_level": bear_res.rejection_level,
            "reclaim_level": bull_res.reclaim_level,
            "triggers_fired_bear": bear_res.triggers_fired,
            "triggers_fired_bull": bull_res.triggers_fired,
        })

    return bars_out


# ---------------------------------------------------------------------------
# Combo gate predicates
# ---------------------------------------------------------------------------
def gate_I1(b: dict) -> bool:
    """bear_score >= 7 AND morning(09:35-10:15) AND level within $0.30 AND vol_ratio >= 2.0"""
    return (b["bear_score"] >= 7 and b["is_morning"]
            and b["level_proximity"] <= 0.30 and b["vol_ratio"] >= 2.0)


def gate_I2(b: dict) -> bool:
    """bear_score >= 6 AND morning AND level within $0.30 AND vol_ratio >= 3.0 AND htf=="BEAR" """
    return (b["bear_score"] >= 6 and b["is_morning"]
            and b["level_proximity"] <= 0.30 and b["vol_ratio"] >= 3.0
            and b["htf_stack"] == "BEAR")


def gate_I3(b: dict) -> bool:
    """bear_score >= 6 AND level within $0.30 AND vol_ratio >= 4.0 AND ribbon_just_flipped"""
    return (b["bear_score"] >= 6 and b["level_proximity"] <= 0.30
            and b["vol_ratio"] >= 4.0 and b["ribbon_just_flipped_bearish"])


def gate_I4(b: dict) -> bool:
    """bear_score >= 5 AND morning AND level within $0.25 AND vol_ratio >= 4.0 AND htf=="BEAR" AND ribbon_just_flipped"""
    return (b["bear_score"] >= 5 and b["is_morning"]
            and b["level_proximity"] <= 0.25 and b["vol_ratio"] >= 4.0
            and b["htf_stack"] == "BEAR" and b["ribbon_just_flipped_bearish"])


def gate_I5(b: dict) -> bool:
    """bull_score >= 7 AND morning AND level within $0.30 AND vol_ratio >= 3.0 AND htf=="BULL" """
    return (b["bull_score"] >= 7 and b["is_morning"]
            and b["level_proximity"] <= 0.30 and b["vol_ratio"] >= 3.0
            and b["htf_stack"] == "BULL")


def gate_BEST_COMBO_BEAR(b: dict) -> bool:
    """bear_score >= 8 AND any_one_of(htf=="BEAR" | vol_ratio>=2.0 | ribbon_just_flipped)"""
    if b["bear_score"] < 8:
        return False
    return (b["htf_stack"] == "BEAR" or b["vol_ratio"] >= 2.0
            or b["ribbon_just_flipped_bearish"])


def gate_TRIPLE_LOCK(b: dict) -> bool:
    """bear_score >= 7 AND htf=="BEAR" AND level within $0.30 AND vol_ratio >= 2.0"""
    return (b["bear_score"] >= 7 and b["htf_stack"] == "BEAR"
            and b["level_proximity"] <= 0.30 and b["vol_ratio"] >= 2.0)


def gate_MORNING_LEVEL_ONLY(b: dict) -> bool:
    """bear_score >= 7 AND morning AND level within $0.25"""
    return (b["bear_score"] >= 7 and b["is_morning"]
            and b["level_proximity"] <= 0.25)


SCENARIOS = [
    {"id": "I1", "name": "bear7+morning+level0.30+vol2.0", "gate": gate_I1,
     "desc": "bear_score>=7 AND morning AND level<=0.30 AND vol_ratio>=2.0"},
    {"id": "I2", "name": "bear6+morning+level0.30+vol3.0+htfBEAR", "gate": gate_I2,
     "desc": "bear_score>=6 AND morning AND level<=0.30 AND vol_ratio>=3.0 AND htf==BEAR"},
    {"id": "I3", "name": "bear6+level0.30+vol4.0+ribbonflip", "gate": gate_I3,
     "desc": "bear_score>=6 AND level<=0.30 AND vol_ratio>=4.0 AND ribbon_just_flipped"},
    {"id": "I4", "name": "bear5+morning+level0.25+vol4.0+htfBEAR+ribbonflip", "gate": gate_I4,
     "desc": "bear_score>=5 AND morning AND level<=0.25 AND vol_ratio>=4.0 AND htf==BEAR AND ribbon_just_flipped"},
    {"id": "I5", "name": "bull7+morning+level0.30+vol3.0+htfBULL", "gate": gate_I5,
     "desc": "bull_score>=7 AND morning AND level<=0.30 AND vol_ratio>=3.0 AND htf==BULL"},
    {"id": "BEST_COMBO_BEAR", "name": "bear8+any_one_compensator", "gate": gate_BEST_COMBO_BEAR,
     "desc": "bear_score>=8 AND (htf==BEAR OR vol_ratio>=2.0 OR ribbon_just_flipped)"},
    {"id": "TRIPLE_LOCK", "name": "bear7+htfBEAR+level0.30+vol2.0", "gate": gate_TRIPLE_LOCK,
     "desc": "bear_score>=7 AND htf==BEAR AND level<=0.30 AND vol_ratio>=2.0"},
    {"id": "MORNING_LEVEL_ONLY", "name": "bear7+morning+level0.25", "gate": gate_MORNING_LEVEL_ONLY,
     "desc": "bear_score>=7 AND morning AND level<=0.25"},
]


# ---------------------------------------------------------------------------
# Baseline: run each J day with standard 10/10 params → get P&L
# ---------------------------------------------------------------------------
def _run_day_standard(spy_df: pd.DataFrame, vix_df: pd.DataFrame, date_str: str) -> float | None:
    """Run one J day with PRODUCTION params, return total P&L (None = no trades)."""
    d = dt.date.fromisoformat(date_str)
    spy_w = spy_df[spy_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()
    vix_w = vix_df[vix_df["timestamp_et"]  <= f"{date_str}T23:59:59"].copy()
    result = run_backtest(
        spy_df=spy_w, vix_df=vix_w,
        start_date=d, end_date=d,
        **PROD_KWARGS,
    )
    if not result.trades:
        return None
    return round(sum(t.dollar_pnl for t in result.trades), 2)


def _compute_edge(per_day: dict) -> float:
    """Compute OP-16 edge_capture from a {date: pnl | None} dict."""
    winner_sum = sum(max(0.0, per_day.get(d) or 0.0) for d in J_WINNERS)
    loser_loss  = sum(max(0.0, -(per_day.get(d) or 0.0)) for d in J_LOSERS)
    return winner_sum - loser_loss


def _compute_sharpe(per_day: dict) -> float:
    """Daily Sharpe from the 6 J days (simple — no rf). 0 if no variance."""
    pnls = [per_day.get(d) or 0.0 for d in ALL_J_DAYS]
    arr  = np.array(pnls, dtype=float)
    if arr.std() < 1e-9:
        return 0.0
    return float(arr.mean() / arr.std())


def main() -> int:
    # ---- Find data files ----
    data_dir = REPO / "data"
    spy_path = data_dir / "spy_5m_2025-01-01_2026-06-16.csv"
    vix_path = data_dir / "vix_5m_2025-01-01_2026-06-16.csv"
    if not spy_path.exists():
        # Fallback to older merged file
        spy_path = data_dir / "spy_5m_2025-01-01_2026-05-22.csv"
        vix_path = data_dir / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists():
        spy_path = data_dir / "spy_5m_2025-01-01_2026-05-15.csv"
        vix_path = data_dir / "vix_5m_2025-01-01_2026-05-15.csv"
    if not spy_path.exists():
        print("ERROR: No SPY data file found. Run append_today.py first.")
        return 1

    print(f"Loading {spy_path.name}...")
    spy_df_raw = pd.read_csv(spy_path)
    vix_df_raw = pd.read_csv(vix_path)
    print(f"Loaded {len(spy_df_raw):,} SPY rows, {len(vix_df_raw):,} VIX rows\n")

    # ---- Baseline: production 10/10 gate ----
    print("Running baseline (production 10/10 gates)...")
    baseline_pnl: dict[str, float | None] = {}
    for date_str in ALL_J_DAYS:
        baseline_pnl[date_str] = _run_day_standard(spy_df_raw, vix_df_raw, date_str)
        pnl_str = f"${baseline_pnl[date_str]:+.0f}" if baseline_pnl[date_str] is not None else "skip"
        print(f"  {date_str}: {pnl_str}")

    baseline_edge   = _compute_edge(baseline_pnl)
    baseline_sharpe = _compute_sharpe(baseline_pnl)
    baseline_total  = sum(v or 0 for v in baseline_pnl.values())
    n_baseline      = sum(1 for v in baseline_pnl.values() if v is not None)

    print(f"\nBaseline edge_capture: ${baseline_edge:.0f}  Sharpe: {baseline_sharpe:.2f}  N_days: {n_baseline}")
    print(f"Baseline total P&L: ${baseline_total:.0f}")
    print()

    # ---- Per-day bar context (for combo gate evaluation) ----
    print("Building per-bar context for all J days...")
    day_contexts: dict[str, list] = {}
    for date_str in ALL_J_DAYS:
        bars = _build_per_day_context(spy_df_raw, vix_df_raw, date_str)
        day_contexts[date_str] = bars
        # Count how many bars fire under each scenario (diagnostic)
        fires_by_scenario = {}
        for sc in SCENARIOS:
            n_fire = sum(1 for b in bars if sc["gate"](b))
            fires_by_scenario[sc["id"]] = n_fire
        fire_summary = "  ".join(f"{k}={v}" for k, v in fires_by_scenario.items())
        print(f"  {date_str}: {len(bars)} bars  |  fires: {fire_summary}")

    print()

    # ---- J-winner early-fire diagnostic ----
    # For each winner day: does the scenario fire BEFORE the standard 10/10 baseline entry?
    # "minutes_earlier" = how many minutes before the baseline entry the scenario fires first.
    def _first_fire_time(bars: list, gate_fn) -> Optional[dt.datetime]:
        for b in bars:
            if gate_fn(b):
                return b["timestamp_et"]
        return None

    def _first_baseline_entry_time(bars: list) -> Optional[dt.datetime]:
        """The first bar where the standard filters all passed (bear_passed=True)."""
        for b in bars:
            if b["bear_passed"]:
                return b["timestamp_et"]
        return None

    # ---- Scenario results ----
    scenario_results = []

    # Scenario-level P&L: we use the COMBO GATE to identify the FIRST qualifying bar
    # per day, then estimate P&L by running the engine with only that day's worth of data.
    # For simplicity (and because the engine doesn't expose a "start-at-bar-X" API),
    # we use the bear_score context:
    #   - If the first combo-gate fire is EARLIER than the baseline entry, we estimate
    #     P&L for the "relaxed" scenario using the engine run (same as baseline since
    #     the engine still decides the actual fill), marking it as "early_fire=True".
    #   - For days that are J losers, the question is whether the gate PREVENTS the entry
    #     (no bars fire = loser avoided).
    # Because the engine's actual fill is complex (stop/TP/runner), we use the
    # STANDARD engine P&L for winner days (if the gate would have fired at all),
    # and engine P&L for loser days only if the gate fires.

    # More precisely:
    #   scenario_pnl[date] = baseline_pnl[date]  if any gate-bar fires on that day
    #   scenario_pnl[date] = None                 if no gate-bar fires (trade skipped)
    # This is conservative: we assume the engine would have taken the SAME trade if
    # any combo bar fires, and SKIPPED if none fire.
    # The "marginal" measure is: scenario fires on loser days (bad) vs baseline doesn't.

    print("Evaluating scenarios...")
    for sc in SCENARIOS:
        sc_pnl: dict[str, float | None] = {}
        j_winner_early_fires: dict[str, object] = {}

        for date_str in ALL_J_DAYS:
            bars = day_contexts[date_str]
            first_gate_time = _first_fire_time(bars, sc["gate"])
            first_base_time = _first_baseline_entry_time(bars)

            # Does ANY bar fire under this combo gate today?
            if first_gate_time is not None:
                # Gate fires → use engine P&L for this day
                sc_pnl[date_str] = baseline_pnl[date_str]
            else:
                # Gate doesn't fire → skip this day
                sc_pnl[date_str] = None

            # J winner early-fire diagnostic
            if date_str in J_WINNERS:
                if first_gate_time is not None:
                    if first_base_time is not None:
                        delta_min = (first_gate_time - first_base_time).total_seconds() / 60.0
                        j_winner_early_fires[date_str] = {
                            "gate_fires_at": first_gate_time.strftime("%H:%M"),
                            "baseline_fires_at": first_base_time.strftime("%H:%M"),
                            "minutes_earlier": round(delta_min, 1),
                            "note": "earlier" if delta_min < 0 else ("same_time" if delta_min == 0 else "later"),
                        }
                    else:
                        j_winner_early_fires[date_str] = {
                            "gate_fires_at": first_gate_time.strftime("%H:%M"),
                            "baseline_fires_at": None,
                            "minutes_earlier": None,
                            "note": "combo_fires_but_baseline_never_fires",
                        }
                else:
                    j_winner_early_fires[date_str] = {
                        "gate_fires_at": None,
                        "baseline_fires_at": first_base_time.strftime("%H:%M") if first_base_time else None,
                        "minutes_earlier": None,
                        "note": "combo_gate_BLOCKS_winner",
                    }

        # Compute aggregate metrics
        sc_edge   = _compute_edge(sc_pnl)
        sc_sharpe = _compute_sharpe(sc_pnl)
        sc_score  = sc_edge * sc_sharpe
        sc_total  = sum(v or 0 for v in sc_pnl.values())
        n_trades  = sum(1 for v in sc_pnl.values() if v is not None)

        # For COMBINATION gates (which may be more OR less restrictive than baseline):
        # - "Marginal trades added" = days where scenario fires but baseline did NOT.
        # - "Trades dropped" = days where baseline fires but scenario does NOT.
        # Both are diagnostics: added = net new exposure; dropped = filter action.
        marginal_added_count = 0
        marginal_added_pnl = 0.0
        marginal_added_wins = 0
        trades_dropped_count = 0
        trades_dropped_pnl = 0.0  # what we SAVED (negative baseline P&L avoided)

        for date_str in ALL_J_DAYS:
            base_fires = (baseline_pnl[date_str] is not None)
            sc_fires   = (sc_pnl[date_str] is not None)
            if sc_fires and not base_fires:
                # Marginal trade added (extra entry)
                marginal_added_count += 1
                marginal_added_pnl += (sc_pnl[date_str] or 0)
                if (sc_pnl[date_str] or 0) > 0:
                    marginal_added_wins += 1
            elif base_fires and not sc_fires:
                # Trade dropped by this filter
                trades_dropped_count += 1
                trades_dropped_pnl += (baseline_pnl[date_str] or 0)

        marginal_wr = marginal_added_wins / marginal_added_count if marginal_added_count > 0 else None
        # Net filter effect: dropping a loser day is GOOD (positive saves)
        filter_saves = -trades_dropped_pnl  # positive = we saved money by NOT trading

        # Verdict
        op16_pass = sc_edge >= OP16_FLOOR
        if not op16_pass:
            verdict = "rejected"
        elif sc_edge >= 0.75 * MAX_EDGE:
            verdict = "promising"
        else:
            verdict = "needs-more-data"

        result_dict = {
            "id": sc["id"],
            "name": sc["name"],
            "description": sc["desc"],
            "per_day_pnl": {d: sc_pnl[d] for d in ALL_J_DAYS},
            "n_trades": n_trades,
            "wr": round(sum(1 for v in sc_pnl.values() if (v or 0) > 0) / max(1, n_trades), 3),
            "total_pnl": round(sc_total, 2),
            "edge_capture": round(sc_edge, 2),
            "edge_pct_of_max": round(sc_edge / MAX_EDGE * 100, 1),
            "aggregate_sharpe": round(sc_sharpe, 3),
            "final_score": round(sc_score, 2),
            "marginal_trades": marginal_added_count,
            "marginal_wr": round(marginal_wr, 3) if marginal_wr is not None else None,
            "marginal_pnl": round(marginal_added_pnl, 2),
            "trades_dropped_by_filter": trades_dropped_count,
            "filter_saves_dollars": round(filter_saves, 2),
            "j_winner_early_fires": j_winner_early_fires,
            "op16_pass": op16_pass,
            "verdict": verdict,
        }
        scenario_results.append(result_dict)

        # Print summary row
        op16_tag = "PASS" if op16_pass else "FAIL"
        early_tags = []
        for d in J_WINNERS:
            ef = j_winner_early_fires.get(d, {})
            min_e = ef.get("minutes_earlier")
            if min_e is not None:
                early_tags.append(f"{d[5:]}:{min_e:+.0f}m")
            else:
                early_tags.append(f"{d[5:]}:BLOCKED")
        early_str = "  ".join(early_tags)
        mwr_str = f"{marginal_wr:.2f}" if marginal_wr is not None else "N/A"
        print(f"  {sc['id']:25s}  edge=${sc_edge:>7.0f}  N={n_trades}  sharpe={sc_sharpe:+.2f}  "
              f"score={sc_score:>8.0f}  "
              f"added={marginal_added_count}({mwr_str}WR)  dropped={trades_dropped_count}(saves=${filter_saves:.0f})  "
              f"{op16_tag}  early-fires: {early_str}")

    print()

    # ---- Synthesis ----
    print("=" * 90)
    print("SYNTHESIS")
    print("=" * 90)

    passing = [s for s in scenario_results if s["op16_pass"]]
    failing = [s for s in scenario_results if not s["op16_pass"]]

    print(f"\nOP-16 passing scenarios ({len(passing)}/{len(scenario_results)}):")
    for s in sorted(passing, key=lambda x: -x["edge_capture"]):
        print(f"  {s['id']:25s}  edge=${s['edge_capture']:>6.0f}  ({s['edge_pct_of_max']:.1f}%)  "
              f"score={s['final_score']:>8.0f}  marginal_wr={s['marginal_wr']}")

    print(f"\nFailing scenarios ({len(failing)}/{len(scenario_results)}):")
    for s in sorted(failing, key=lambda x: -x["edge_capture"]):
        print(f"  {s['id']:25s}  edge=${s['edge_capture']:>6.0f}  ({s['edge_pct_of_max']:.1f}%)  "
              f"score={s['final_score']:>8.0f}  marginal_wr={s['marginal_wr']}")

    # Best scenario by final_score
    best = max(scenario_results, key=lambda s: s["final_score"])
    print(f"\nBest scenario by final_score: {best['id']} -> {best['final_score']:.0f}")

    # Cross-category analysis (best per metric)
    best_edge   = max(scenario_results, key=lambda s: s["edge_capture"])
    best_sharpe = max(scenario_results, key=lambda s: s["aggregate_sharpe"])
    print(f"Best edge_capture:  {best_edge['id']} -> ${best_edge['edge_capture']:.0f}")
    print(f"Best sharpe:        {best_sharpe['id']} -> {best_sharpe['aggregate_sharpe']:.3f}")

    # Recommended live test candidate
    top = None
    if passing:
        top = sorted(passing, key=lambda s: -s["final_score"])[0]
        print(f"\nRecommended first live test candidate: {top['id']}")
        print(f"  Gate: {top['description']}")
        print(f"  edge_capture=${top['edge_capture']:.0f} | sharpe={top['aggregate_sharpe']:.3f} | "
              f"final_score={top['final_score']:.0f}")
    else:
        print("\nNo scenario clears OP-16 floor. No live test recommended.")
        top = max(scenario_results, key=lambda s: s["edge_capture"])

    # ---- Build output ----
    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "Category I perfect-storm combination gate sweep",
        "op16_floor": OP16_FLOOR,
        "j_max_edge": MAX_EDGE,
        "production_params": {
            "premium_stop_pct_bear": PROD_KWARGS["premium_stop_pct_bear"],
            "tp1_premium_pct": PROD_KWARGS["tp1_premium_pct"],
            "tp1_qty_fraction": PROD_KWARGS["tp1_qty_fraction"],
            "runner_target_premium_pct": PROD_KWARGS["runner_target_premium_pct"],
            "f9_vol_mult": PROD_KWARGS["f9_vol_mult"],
        },
        "baseline_10_10": {
            "description": "Standard production filters — full 10/10 gate",
            "per_day_pnl": baseline_pnl,
            "n_trades": n_baseline,
            "total_pnl": round(baseline_total, 2),
            "edge_capture": round(baseline_edge, 2),
            "edge_pct_of_max": round(baseline_edge / MAX_EDGE * 100, 1),
            "aggregate_sharpe": round(baseline_sharpe, 3),
            "final_score": round(baseline_edge * baseline_sharpe, 2),
        },
        "scenarios": scenario_results,
        "synthesis": {
            "n_passing_op16": len(passing),
            "n_failing_op16": len(failing),
            "best_by_final_score": best["id"],
            "best_edge_scenario": best_edge["id"],
            "best_sharpe_scenario": best_sharpe["id"],
            "recommended_live_test": top["id"] if (passing and top is not None) else None,
            "notes": (
                "Scenario P&L is estimated as: if the combination gate fires on a given day, "
                "attribute the same P&L as the production baseline run for that day. "
                "This assumes the engine would take the same trade if the gate fires at all. "
                "Marginal trades = days where scenario fires but baseline did NOT fire. "
                "A high marginal_wr >= 0.45 means the extra entries are net profitable."
            ),
        },
    }

    out_path = REPO.parent / "analysis" / "recommendations" / "gate_sweep_combinations.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
