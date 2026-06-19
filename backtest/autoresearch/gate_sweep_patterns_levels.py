"""Sweep ribbon/pattern-proxy and key-level-proximity gate relaxations.

Architecture (same as gate_sweep_combinations.py):
  1. Build per-bar context for all 7 J anchor days using _build_per_day_context.
  2. Apply each scenario gate as a predicate on the bar context dicts.
  3. Scenario P&L = baseline_pnl[date] if the gate fires on that day; None if not.
  4. Compute edge_capture + marginal analysis per scenario.

Important: disable_filters=[8] + vix_soft_mode=True used for historical pre-VIX days
(4/29, 5/01, 5/04 predate the VIX>17.30+rising rule added 2026-05-05).

For E3 (spread widening), E4 (range compression), C4 (prior-day high) we need
additional per-bar computation not in the standard context builder.

Category E — ribbon / pattern proxies:
  E1: bear_score >= 9 AND ribbon_just_flipped_bearish (<=3 bars)
  E2: bear_score >= 8 AND ribbon flipped <=2 bars (stricter)
  E3: bear_score >= 8 AND ribbon spreading: spread_now > spread_3bars_ago + 5c
  E4: bear_score >= 7 AND 3-bar range < 60% of 10-bar avg range (compression)
  E5: bear_score >= 6 AND compression + vol_ratio>=3.0 + level_prox<=0.40 + fresh_flip
  E6: bull_score >= 9 AND ribbon_just_flipped_bullish

Category C — key-level proximity:
  C1: bear_score >= 9 AND level_proximity <= 0.25
  C2: bear_score >= 8 AND level_proximity <= 0.20
  C3: bear_score >= 7 AND confluence in triggers
  C4: bear_score >= 8 AND prior-day high within $0.30 of close
  C5: bear_score >= 7 AND confluence in triggers AND vol_ratio >= 2.0

Output: analysis/recommendations/gate_sweep_patterns_levels.json
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from lib.orchestrator import run_backtest, _precompute_htf_15m_stacks, _align_vix_to_spy
from lib.ribbon import compute_ribbon, ribbon_at
from lib.filters import (
    BarContext, evaluate_bearish_setup, evaluate_bullish_setup,
    vol_baseline_20bar, range_baseline_20bar, LevelState,
    detect_ribbon_flip_bearish, detect_ribbon_flip_bullish,
    RIBBON_FLIP_LOOKBACK_BARS,
)
from lib.levels import _detect_from_history

# ── J edge reference ──────────────────────────────────────────────────────────
J_WINNERS  = {"2026-04-29": 342, "2026-05-01": 470, "2026-05-04": 730}
J_LOSERS   = {"2026-05-05": -260, "2026-05-06": -300, "2026-05-07": -165}
ALL_DAYS   = sorted(list(J_WINNERS) + list(J_LOSERS))
OP16_FLOOR = 771
MAX_EDGE   = 1542

# ── Baseline params (mirrors allow_one_blocker_minspread_sweep best result at min_spread=27c) ──
# That sweep used BS simulator (not real fills), same params as below.
# BS simulator: edge_capture=1660 at min_spread=27.
# We use the same config so scenario gate lift is measured against the same reference.
PROD_KWARGS = dict(
    use_real_fills=False,  # BS simulator — consistent with minspread sweep baseline
    premium_stop_pct=-0.08,
    premium_stop_pct_bear=-0.08,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.30,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.0,
    f9_vol_mult=0.7,
    profit_lock_mode="trailing",
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_trail_pct=0.20,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    strike_offset=0,
    # 4/29, 5/01, 5/04 predate the VIX rule — disable F8 for J anchor days
    disable_filters=[8],
    vix_soft_mode=True,
    allow_one_blocker=True,
    allow_one_blocker_min_spread_cents=27,
)


# ────────────────────────────────────────────────────────────────────────────
# Per-bar context builder (extended version of gate_sweep_combinations.py)
# Adds: ribbon spread widening, range compression, prior-day high
# ────────────────────────────────────────────────────────────────────────────

def _build_per_day_context(spy_df: pd.DataFrame, vix_df: pd.DataFrame,
                           date_str: str) -> list[dict]:
    """Return a list of per-bar context dicts for one trading day.

    Extends gate_sweep_combinations._build_per_day_context with:
      - ribbon_spread_cents (current + 3-bars-ago)
      - spreading_5c: spread_now > spread_3ago + 5c
      - is_compressed: 3-bar range < 60% of 10-bar avg range
      - prior_day_high: prior day's session high
      - flip_within_2: ribbon flipped <=2 bars ago (stricter than the 3-bar default)
    """
    d = dt.date.fromisoformat(date_str)

    spy_full = spy_df[spy_df["timestamp_et"].dt.date <= d].copy()
    vix_full  = vix_df[vix_df["timestamp_et"].dt.date <= d].copy()

    spy_full["date"] = spy_full["timestamp_et"].dt.date

    # RTH only
    rth_mask = (
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    )
    spy_rth = spy_full.loc[rth_mask].reset_index(drop=True)
    if spy_rth.empty:
        return []

    ribbon_df = compute_ribbon(spy_rth["close"])

    # VIX alignment
    spy_ts = spy_rth["timestamp_et"]
    vix_ts = vix_full["timestamp_et"]
    if spy_ts.dt.tz is None and vix_ts.dt.tz is not None:
        spy_ts = spy_ts.dt.tz_localize("UTC")
    elif spy_ts.dt.tz is not None and vix_ts.dt.tz is None:
        vix_ts = vix_ts.dt.tz_localize("UTC")
    vix_indexed = pd.Series(vix_full["close"].values, index=vix_ts)
    if not vix_indexed.index.is_unique:
        vix_indexed = vix_indexed[~vix_indexed.index.duplicated(keep="first")]
    if not spy_ts.is_unique:
        spy_ts = spy_ts.drop_duplicates()
    vix_aligned = vix_indexed.reindex(spy_ts, method="ffill")
    vix_aligned.index = range(len(vix_aligned))

    htf_stacks = _precompute_htf_15m_stacks(spy_rth)

    # Levels: history up to (not including) today's RTH
    spy_prior = spy_full[spy_full["date"] < d].copy()
    level_set = _detect_from_history(spy_prior, d)
    levels_active = list(level_set.active) if level_set else []
    multi_day     = list(level_set.multi_day) if level_set else []

    # Prior-day high
    prior_rth_mask = (
        (spy_full["date"] < d)
        & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    )
    prior_rth = spy_full[prior_rth_mask]
    if not prior_rth.empty:
        max_prior_date = prior_rth["date"].max()
        prev_day = prior_rth[prior_rth["date"] == max_prior_date]
        prior_day_high = float(prev_day["high"].max()) if not prev_day.empty else None
    else:
        prior_day_high = None

    bars_out: list[dict] = []
    for idx in range(len(spy_rth)):
        bar = spy_rth.iloc[idx]
        bar_time_pd = bar["timestamp_et"]
        if hasattr(bar_time_pd, "to_pydatetime"):
            bar_time_pd = bar_time_pd.to_pydatetime()
        bar_date = bar_time_pd.date() if hasattr(bar_time_pd, "date") else d
        if bar_date != d:
            continue

        bar_time = bar_time_pd.time()

        # Ribbon state + history
        rib_now = ribbon_at(ribbon_df, idx)
        rib_hist = [ribbon_at(ribbon_df, j)
                    for j in range(max(0, idx - RIBBON_FLIP_LOOKBACK_BARS), idx + 1)]

        # Ribbon history for E2 (<=2 bars) and E3 (spread 3 bars ago)
        rib_hist_4 = [ribbon_at(ribbon_df, j)
                      for j in range(max(0, idx - 4), idx + 1)]

        # VIX
        vix_now   = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 20.0
        vix_prior = float(vix_aligned.iloc[idx - 1]) if idx > 0 else vix_now

        # Volume baseline + ratio
        vol_base = vol_baseline_20bar(spy_rth, idx)
        vol_ratio = float(bar["volume"]) / vol_base if vol_base > 0 else 0.0

        # Level proximity
        close = float(bar["close"])
        lp = min(abs(close - L) for L in levels_active) if levels_active else 999.0

        # BarContext for evaluate_*_setup
        ctx = BarContext(
            bar_idx=idx,
            timestamp_et=bar_time_pd,
            bar=bar,
            prior_bars=spy_rth,
            ribbon_now=rib_now,
            ribbon_history=rib_hist,
            vix_now=vix_now,
            vix_prior=vix_prior,
            vol_baseline_20=vol_base,
            range_baseline_20=range_baseline_20bar(spy_rth, idx),
            levels_active=levels_active,
            multi_day_levels=multi_day,
            htf_15m_stack=htf_stacks[idx],
            level_states={},
        )

        # Evaluate setups (F8 disabled for pre-VIX-rule dates)
        bear_res = evaluate_bearish_setup(ctx, f9_vol_mult=0.7,
                                          disable_filters=[8], vix_soft_mode=True)
        bull_res  = evaluate_bullish_setup(ctx)

        # E2: flip within 2 bars (stricter lookback)
        current_stack = rib_now.stack if rib_now is not None else None
        flip_2bar_bear = False
        flip_2bar_bull = False
        if current_stack == "BEAR" and len(rib_hist_4) >= 3:
            look_back2 = rib_hist_4[max(0, len(rib_hist_4) - 3):-1]
            flip_2bar_bear = any(s is not None and s.stack != "BEAR" for s in look_back2)
        if current_stack == "BULL" and len(rib_hist_4) >= 3:
            look_back2 = rib_hist_4[max(0, len(rib_hist_4) - 3):-1]
            flip_2bar_bull = any(s is not None and s.stack != "BULL" for s in look_back2)

        # E3: ribbon spreading (spread now > spread 3 bars ago + 5c)
        spreading_5c = False
        if rib_now is not None and len(rib_hist_4) >= 4:
            rib_3ago = rib_hist_4[-(4)]  # 3 bars ago (hist_4 has idx-4..idx)
            if rib_3ago is not None:
                spreading_5c = rib_now.spread_cents > rib_3ago.spread_cents + 5.0

        # E4: range compression (3-bar avg range < 60% of 10-bar avg range)
        is_compressed = False
        if idx >= 10:
            recent_ranges = [
                float(spy_rth.iloc[i]["high"]) - float(spy_rth.iloc[i]["low"])
                for i in range(idx - 3, idx)
            ]
            baseline_ranges = [
                float(spy_rth.iloc[i]["high"]) - float(spy_rth.iloc[i]["low"])
                for i in range(idx - 10, idx - 3)
            ]
            if baseline_ranges and sum(baseline_ranges) > 0:
                avg_recent = sum(recent_ranges) / 3
                avg_base   = sum(baseline_ranges) / len(baseline_ranges)
                is_compressed = avg_recent < 0.60 * avg_base

        # C4: prior-day high proximity
        pdh_dist = abs(close - prior_day_high) if prior_day_high is not None else 999.0

        bars_out.append({
            "idx": idx,
            "timestamp_et": bar_time_pd,
            "bar_time": bar_time,
            "close": close,
            "vol_ratio": vol_ratio,
            "level_proximity": lp,
            "levels_active": levels_active,
            "htf_stack": htf_stacks[idx],
            "bear_score": bear_res.bear_score,
            "bull_score": bull_res.bull_score,
            "bear_passed": bear_res.passed,
            "bull_passed": bull_res.passed,
            "ribbon_just_flipped_bearish": bear_res.ribbon_just_flipped_bearish,
            "ribbon_just_flipped_bullish": bull_res.ribbon_just_flipped_bullish,
            "flip_2bar_bear": flip_2bar_bear,
            "flip_2bar_bull": flip_2bar_bull,
            "spreading_5c": spreading_5c,
            "is_compressed": is_compressed,
            "pdh_dist": pdh_dist,
            "confluence_bear": "confluence" in bear_res.triggers_fired,
            "confluence_bull": "confluence" in bull_res.triggers_fired,
            "triggers_fired_bear": bear_res.triggers_fired,
            "triggers_fired_bull": bull_res.triggers_fired,
        })

    return bars_out


# ────────────────────────────────────────────────────────────────────────────
# Scenario gate predicates
# ────────────────────────────────────────────────────────────────────────────

def gate_E1(b: dict) -> bool:
    """bear_score >= 9 AND ribbon_just_flipped_bearish (<=3 bars)"""
    return b["bear_score"] >= 9 and b["ribbon_just_flipped_bearish"]

def gate_E2(b: dict) -> bool:
    """bear_score >= 8 AND ribbon flipped <=2 bars ago"""
    return b["bear_score"] >= 8 and b["flip_2bar_bear"]

def gate_E3(b: dict) -> bool:
    """bear_score >= 8 AND ribbon spreading (spread > 3-bar-ago + 5c)"""
    return b["bear_score"] >= 8 and b["spreading_5c"]

def gate_E4(b: dict) -> bool:
    """bear_score >= 7 AND range compression (3-bar < 60% of 10-bar)"""
    return b["bear_score"] >= 7 and b["is_compressed"]

def gate_E5(b: dict) -> bool:
    """bear_score >= 6 AND compression + vol_ratio>=3.0 + level<=0.40 + fresh_flip"""
    return (b["bear_score"] >= 6 and b["is_compressed"]
            and b["vol_ratio"] >= 3.0
            and b["level_proximity"] <= 0.40
            and b["ribbon_just_flipped_bearish"])

def gate_E6(b: dict) -> bool:
    """bull_score >= 9 AND ribbon_just_flipped_bullish"""
    return b["bull_score"] >= 9 and b["ribbon_just_flipped_bullish"]

def gate_C1(b: dict) -> bool:
    """bear_score >= 9 AND nearest level within $0.25"""
    return b["bear_score"] >= 9 and b["level_proximity"] <= 0.25

def gate_C2(b: dict) -> bool:
    """bear_score >= 8 AND nearest level within $0.20"""
    return b["bear_score"] >= 8 and b["level_proximity"] <= 0.20

def gate_C3(b: dict) -> bool:
    """bear_score >= 7 AND confluence in bear triggers"""
    return b["bear_score"] >= 7 and b["confluence_bear"]

def gate_C4(b: dict) -> bool:
    """bear_score >= 8 AND prior-day high within $0.30"""
    return b["bear_score"] >= 8 and b["pdh_dist"] <= 0.30

def gate_C5(b: dict) -> bool:
    """bear_score >= 7 AND confluence AND vol_ratio >= 2.0"""
    return b["bear_score"] >= 7 and b["confluence_bear"] and b["vol_ratio"] >= 2.0


SCENARIOS = [
    {"id": "E1", "gate": gate_E1, "name": "bear>=9 + fresh_flip_bear (<=3 bars)"},
    {"id": "E2", "gate": gate_E2, "name": "bear>=8 + flip_bear_strict (<=2 bars)"},
    {"id": "E3", "gate": gate_E3, "name": "bear>=8 + ribbon_spreading (spread>prior3bars+5c)"},
    {"id": "E4", "gate": gate_E4, "name": "bear>=7 + range_compression (3bar<60% of 10bar avg)"},
    {"id": "E5", "gate": gate_E5, "name": "bear>=6 + compression + vol>=3.0 + lvl<=0.40 + flip"},
    {"id": "E6", "gate": gate_E6, "name": "bull>=9 + ribbon_just_flipped_bull"},
    {"id": "C1", "gate": gate_C1, "name": "bear>=9 + nearest_level<=0.25"},
    {"id": "C2", "gate": gate_C2, "name": "bear>=8 + nearest_level<=0.20"},
    {"id": "C3", "gate": gate_C3, "name": "bear>=7 + confluence_in_triggers"},
    {"id": "C4", "gate": gate_C4, "name": "bear>=8 + prior_day_high_within_0.30"},
    {"id": "C5", "gate": gate_C5, "name": "bear>=7 + confluence + vol_ratio>=2.0"},
]


# ────────────────────────────────────────────────────────────────────────────
# Baseline runner
# ────────────────────────────────────────────────────────────────────────────

def _run_day_baseline(spy_df: pd.DataFrame, vix_df: pd.DataFrame,
                      date_str: str) -> float | None:
    d = dt.date.fromisoformat(date_str)
    spy_w = spy_df[spy_df["timestamp_et"].dt.date <= d].copy()
    vix_w = vix_df[vix_df["timestamp_et"].dt.date <= d].copy()
    result = run_backtest(spy_df=spy_w, vix_df=vix_w, start_date=d, end_date=d,
                          **PROD_KWARGS)
    if not result.trades:
        return None
    return round(sum(t.dollar_pnl for t in result.trades), 2)


# ────────────────────────────────────────────────────────────────────────────
# Metrics
# ────────────────────────────────────────────────────────────────────────────

def _edge_capture(per_day: dict) -> float:
    winner_sum = sum(max(0.0, per_day.get(d) or 0.0) for d in J_WINNERS)
    loser_loss = sum(max(0.0, -(per_day.get(d) or 0.0)) for d in J_LOSERS)
    return winner_sum - loser_loss


def _aggregate_sharpe(per_day: dict) -> float:
    pnls = np.array([per_day.get(d) or 0.0 for d in ALL_DAYS], dtype=float)
    if pnls.std() < 1e-9:
        return 0.0
    return float(round(pnls.mean() / pnls.std(), 3))


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────

def main() -> int:
    data_dir = REPO / "backtest" / "data"
    for stem in [
        "spy_5m_2025-01-01_2026-05-15",  # anchor — same file as allow_one_blocker_minspread_sweep
        "spy_5m_2025-01-01_2026-06-16",
        "spy_5m_2025-01-01_2026-05-22",
        "spy_5m_2025-01-01_2026-05-07",
    ]:
        spy_path = data_dir / f"{stem}.csv"
        vix_path = data_dir / f"{stem.replace('spy', 'vix')}.csv"
        if spy_path.exists() and vix_path.exists():
            break
    else:
        print("ERROR: No SPY/VIX data found.")
        return 1

    print(f"Loading {spy_path.name} ...")
    spy_df = pd.read_csv(spy_path)
    vix_df = pd.read_csv(vix_path)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"], utc=True)
    vix_df["timestamp_et"] = pd.to_datetime(vix_df["timestamp_et"], utc=True)
    print(f"Loaded {len(spy_df):,} SPY rows, {len(vix_df):,} VIX rows\n")

    # ── Baseline ──────────────────────────────────────────────────────────────
    print("Running baseline (disable_filters=[8] + vix_soft) ...")
    baseline_pnl: dict = {}
    for ds in ALL_DAYS:
        baseline_pnl[ds] = _run_day_baseline(spy_df, vix_df, ds)
        tag = "W" if ds in J_WINNERS else "L"
        print(f"  {ds} [{tag}]  pnl={baseline_pnl[ds]}")

    base_ec = _edge_capture(baseline_pnl)
    base_sh = _aggregate_sharpe(baseline_pnl)
    base_fs = round(base_ec * base_sh, 2)
    print(f"\nBaseline  edge_capture={base_ec:.0f}  sharpe={base_sh:.3f}"
          f"  final_score={base_fs:.0f}  OP16={'PASS' if base_ec >= OP16_FLOOR else 'FAIL'}\n")

    # ── Per-day bar contexts ──────────────────────────────────────────────────
    print("Building per-bar contexts ...")
    day_contexts: dict = {}
    for ds in ALL_DAYS:
        bars = _build_per_day_context(spy_df, vix_df, ds)
        day_contexts[ds] = bars
        # Diagnostic: how many bars have each bear_score in range
        score_hist = {}
        for b in bars:
            s = b["bear_score"]
            score_hist[s] = score_hist.get(s, 0) + 1
        flip_bars = sum(1 for b in bars if b["ribbon_just_flipped_bearish"])
        comp_bars  = sum(1 for b in bars if b["is_compressed"])
        conf_bars  = sum(1 for b in bars if b["confluence_bear"])
        tag = "W" if ds in J_WINNERS else "L"
        print(f"  {ds} [{tag}]  n_bars={len(bars)}"
              f"  score_dist={score_hist}"
              f"  flip_bear={flip_bars}  compressed={comp_bars}  confluence={conf_bars}")
    print()

    # ── Scenarios ─────────────────────────────────────────────────────────────
    # For scenario P&L: if ANY bar in the day fires the gate, we take baseline_pnl.
    # If NO bar fires, the day is skipped (pnl = None).
    # This is the "gate fires = same trade" assumption from gate_sweep_combinations.py.

    output_scenarios = []

    print(f"{'ID':>5}  {'fires_W':>8}  {'fires_L':>8}  {'edge_cap':>9}"
          f"  {'sharpe':>7}  {'final_score':>11}  {'marg_pnl':>9}  {'marg_wr':>8}  {'verdict':>8}")
    print("-" * 100)

    for sc in SCENARIOS:
        gate_fn = sc["gate"]
        sc_pnl: dict = {}
        bars_fired_per_day: dict = {}

        for ds in ALL_DAYS:
            bars = day_contexts[ds]
            fired = [b for b in bars if gate_fn(b)]
            bars_fired_per_day[ds] = len(fired)
            # If gate fires on any bar → take same trade as baseline
            sc_pnl[ds] = baseline_pnl[ds] if fired else None

        sc_ec = _edge_capture(sc_pnl)
        sc_sh = _aggregate_sharpe(sc_pnl)
        sc_fs = round(sc_ec * sc_sh, 2)

        # Trade stats: count days where trades fire
        n_winner_fires = sum(1 for ds in J_WINNERS if sc_pnl[ds] is not None)
        n_loser_fires  = sum(1 for ds in J_LOSERS  if sc_pnl[ds] is not None)

        # Marginal analysis: compare per-day P&L delta vs baseline
        marginal_deltas = []
        for ds in ALL_DAYS:
            base = baseline_pnl[ds] or 0.0
            scen = sc_pnl[ds] or 0.0
            delta = scen - base
            if abs(delta) > 0.01:
                marginal_deltas.append(delta)
        n_marginal  = len(marginal_deltas)
        marg_wins   = sum(1 for d in marginal_deltas if d > 0)
        marg_wr     = round(marg_wins / n_marginal, 3) if n_marginal > 0 else None
        marg_pnl    = round(sum(marginal_deltas), 2)

        # Verdict
        if sc_ec < OP16_FLOOR:
            verdict = "REJECT"  # fails OP-16 floor
        elif marg_pnl < 0:
            verdict = "REJECT"
        elif marg_wr is not None and marg_wr >= 0.45 and marg_pnl > 0:
            verdict = "PROMOTE"
        else:
            verdict = "VALIDATE"

        print(f"{sc['id']:>5}  {n_winner_fires:>8}  {n_loser_fires:>8}  {sc_ec:>9.0f}"
              f"  {sc_sh:>7.3f}  {sc_fs:>11.0f}  {marg_pnl:>9.0f}  "
              f"{str(marg_wr):>8}  {verdict:>8}")

        output_scenarios.append({
            "id": sc["id"],
            "name": sc["name"],
            "gate": sc["name"],
            "n_winner_days_fired": n_winner_fires,
            "n_loser_days_fired": n_loser_fires,
            "bars_fired_per_day": bars_fired_per_day,
            "edge_capture": sc_ec,
            "op16_pass": sc_ec >= OP16_FLOOR,
            "aggregate_sharpe": round(sc_sh, 3),
            "final_score": sc_fs,
            "marginal_trades": n_marginal,
            "marginal_wr": marg_wr,
            "marginal_pnl": marg_pnl,
            "verdict": verdict,
            "per_day_pnl": {ds: sc_pnl[ds] for ds in ALL_DAYS},
        })

    # ── Output ────────────────────────────────────────────────────────────────
    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "Sweep ribbon-pattern-proxy and key-level-proximity gate relaxations",
        "data_file": spy_path.name,
        "j_winners": J_WINNERS,
        "j_losers": J_LOSERS,
        "op16_floor": OP16_FLOOR,
        "max_edge": MAX_EDGE,
        "baseline_10_10": {
            "description": "disable_filters=[8] + vix_soft_mode=True + all other production params",
            "per_day_pnl": baseline_pnl,
            "edge_capture": base_ec,
            "sharpe": base_sh,
            "final_score": base_fs,
            "op16_pass": base_ec >= OP16_FLOOR,
        },
        "scenarios": output_scenarios,
        "methodology": {
            "approach": "Per-bar scenario gate: if ANY bar on a given day fires the gate, that day's baseline P&L is credited. If NO bar fires, the day is skipped (no trade simulated). This is conservative — assumes same exit as baseline when gate fires.",
            "vix_disable": "disable_filters=[8] applied to all J anchor days (4/29, 5/01, 5/04 predate the VIX rule added 2026-05-05)",
            "level_proxy": "level_proximity = min(abs(close - L) for L in levels_active) — actual detected levels, not just rejection_level",
            "marginal_analysis": "marginal_deltas = days where |scenario_pnl - baseline_pnl| > $0.01",
        },
    }

    out_path = REPO / "analysis" / "recommendations" / "gate_sweep_patterns_levels.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
