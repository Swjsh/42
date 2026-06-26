"""SELECTION/SIZING: vwap_continuation real-fills per-trade distribution -> fractional-Kelly
position sizing + compounding growth curve + risk-of-ruin, gated head-to-toe.

WHY: vwap_continuation is our ONE survivor edge (ITM-2, -8% stop, v15 exits: +$78/tr
full window, OOS-2026 +$105, fires ~2/wk, both directions). A small real per-trade edge
only compounds an account if it is SIZED correctly. This script:

  1. REGENERATES the real-fills per-trade P&L *distribution* (not just aggregates) for the
     SURVIVOR config by reusing the BYTE-FOR-BYTE validated detector + real-fills sim from
     ``_edgehunt_vwap_continuation`` (C1 real-fills authority; same path the edgehunt +
     exploitation JSONs were built on -> nothing drifts).

  2. RUNS THE FULL MANDATORY GATE GAUNTLET (deterministic, no cherry-picking, anti-pattern
     2.10) on that distribution BEFORE trusting it for sizing:
        OOS(2026) per-trade > 0
        AND IS(2025) per-trade > 0          (reject IS-neg/OOS-pos single-regime artifact)
        AND positive_quarters >= 4/6
        AND top5_day_pct < 200
        AND n >= 20
        AND drop-top-5-days per-trade > 0
        AND beats RANDOM-entry null (same exit/stop/count/side-mix, ~20 seeds)
        AND sign does NOT invert at chart-stop-only (-0.99) no-truncation re-run
     If ANY gate fails -> sizing is published with edge_validated=false and a LOUD warning;
     we do NOT silently size off an unvalidated distribution.

  3. SIZING MATH on the *empirical per-trade distribution* (NOT a 2-outcome Kelly toy):
        - per-contract per-trade P&L series (the distribution is the truth).
        - full-Kelly fraction f* found by maximizing E[log(1 + f * R_i)] over the empirical
          returns R_i = (per-contract $PnL) / (per-contract $ at risk), bounded [0,1].
        - half-Kelly and quarter-Kelly as the practical operating points (full-Kelly is a
          known over-bettor on a 16-mo small sample).
        - Monte-Carlo bootstrap of the per-trade distribution (resample with replacement,
          ~2/wk cadence) for the growth curve $2K->$5K->$10K->$25K, max-drawdown, and
          risk-of-ruin at full-Kelly vs half-Kelly vs the CURRENT min-3 / 30%-cap rule.

  4. RULE-6-RESPECTING per-tier recommendation: 30% Safe equity cap, min-3 contracts,
     ~6% premium ceiling (entry premium * contracts * 100 <= ~6% of equity), mapped to the
     v15 per-tier strike ladder.

Pure Python, $0 (no LLM in the loop). No live orders. Markets closed.

Writes:  analysis/recommendations/sel-vwap-sizing.json   (the schema)
         analysis/recommendations/vwap-sizing.json        (task-named alias / sizing block)
         markdown/research/SIZING-COMPOUNDING.md           (the human doc)  [written by caller step]

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sel_vwap_sizing.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

# Reuse the BYTE-FOR-BYTE validated detector + real-fills cell from the edgehunt module so
# the per-trade distribution is identical to the survivor the JSONs were built on (no drift).
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    detect_signals,
    simulate_cell,
    metrics as cell_metrics,
    QTY,
)

OUT_SCHEMA = ROOT / "analysis" / "recommendations" / "sel-vwap-sizing.json"
OUT_SIZING = ROOT / "analysis" / "recommendations" / "vwap-sizing.json"

# ── Survivor structure (PRIMARY per task spec) ───────────────────────────────────
SURVIVOR_STRIKE_OFFSET = -2      # ITM-2 (verified: negative = ITM both sides)
SURVIVOR_PREMIUM_STOP = -0.08    # -8% premium stop (v14/v15 ratified)
CHART_STOP_ONLY = -0.99          # truncation / no-truncation control
QTY_PER = QTY                    # detector/sim run at qty=3; we normalize to per-contract

OOS_YEAR = 2026
WINDOW_START = dt.date(2025, 1, 1)
WINDOW_END = dt.date(2026, 5, 15)

# ── Gate thresholds ──────────────────────────────────────────────────────────────
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0
RANDOM_SEEDS = 20

# ── Sizing / Monte-Carlo params ──────────────────────────────────────────────────
ACCOUNT_TIERS = [2000.0, 5000.0, 10000.0, 25000.0]
GROWTH_TARGETS = [5000.0, 10000.0, 25000.0]
SAFE_RISK_CAP_FRAC = 0.30        # Rule 6 Safe: 30% of equity per trade
MIN_CONTRACTS = 3                # Rule 6: min 3 contracts (2 TP + 1 runner)
PREMIUM_CEILING_FRAC = 0.06      # ~6% premium ceiling (cost of contracts <= 6% equity)
SIGNALS_PER_WEEK = 2.0           # observed ~2/wk fire cadence
MC_PATHS = 5000
MC_MAX_TRADES = 1500             # cap per path (≈14 yrs at 2/wk) — stop at target or ruin
RUIN_FLOOR_FRAC = 0.50           # "ruin" = equity falls to <=50% of start (account impaired)
# Kelly grid extends past 1.0 so we can SEE whether f* is interior (a real ruin-bounded
# optimum) or pegged at the leverage ceiling (the in-sample worst loss never wipes out, so
# log-growth keeps rising -> Kelly is "unbounded by ruin in-sample" and the practical
# governor is Rule 6, not Kelly). Fraction = equity put at risk per trade.
KELLY_GRID = np.round(np.arange(0.0, 5.0001, 0.02), 4)


# ─────────────────────────────────────────────────────────────────────────────────
# RANDOM-ENTRY NULL (same exit/stop/count/side-mix, ~20 seeds) — mandatory gate
# ─────────────────────────────────────────────────────────────────────────────────
def run_random_null(spy: pd.DataFrame, ribbon: pd.DataFrame, vix: pd.Series,
                    n_target: int, sides: list[str], *, strike_offset: int,
                    premium_stop_pct: float, seeds: int) -> dict:
    """Random entry bars: same count, same C/P mix, same strike/stop/exit path.

    Eligible bars = RTH bars 09:30-15:50, >=3 bars into the day, room for a fill. Each seed
    draws n_target (idx, side) pairs and runs the SAME real-fills sim. The survivor must beat
    the mean of the null per-trade.
    """
    rth = spy[(spy["t"] >= dt.time(9, 33)) & (spy["t"] <= dt.time(15, 45))]
    eligible = rth.index.tolist()
    if not eligible:
        return {"per_trade_mean": None, "per_trade_seeds": [], "n_eligible": 0}
    n_call = sides.count("C")
    n_put = sides.count("P")
    per_trade_means: list[float] = []
    for seed in range(seeds):
        rng = random.Random(1000 + seed)
        picks = rng.sample(eligible, min(n_target, len(eligible)))
        side_pool = (["C"] * n_call + ["P"] * n_put)
        rng.shuffle(side_pool)
        pnls: list[float] = []
        for j, idx in enumerate(picks):
            side = side_pool[j % len(side_pool)] if side_pool else "C"
            bar = spy.loc[idx]
            look = spy.loc[max(spy.index[0], idx - 6):idx]
            rej = float(look["low"].min()) if side == "C" else float(look["high"].max())
            entry_vix = float(vix.iloc[idx]) if idx < len(vix) else 0.0
            fill = simulate_trade_real(
                entry_bar_idx=int(idx), entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
                rejection_level=rej, triggers_fired=["random_null"], side=side, qty=QTY_PER,
                setup="VWAP_SIZING_RANDOM", strike_offset=strike_offset,
                premium_stop_pct=premium_stop_pct, entry_vix=entry_vix)
            if fill is None or fill.dollar_pnl is None:
                continue
            pnls.append(float(fill.dollar_pnl))
        if pnls:
            per_trade_means.append(sum(pnls) / len(pnls))
    mean = round(sum(per_trade_means) / len(per_trade_means), 2) if per_trade_means else None
    return {
        "per_trade_mean_qty3": mean,
        "per_trade_seeds_qty3": [round(x, 1) for x in per_trade_means],
        "n_eligible": len(eligible),
        "seeds_completed": len(per_trade_means),
    }


def _drop_top5_per_trade(rows) -> tuple[Optional[float], int]:
    """Per-trade expectancy after removing the 5 best P&L days entirely (qty3 scale)."""
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    top5 = set(sorted(by_day, key=lambda d: by_day[d], reverse=True)[:5])
    kept = [r.pnl for r in rows if r.date not in top5]
    if not kept:
        return None, 0
    return round(sum(kept) / len(kept), 2), len(kept)


# ─────────────────────────────────────────────────────────────────────────────────
# KELLY on the empirical per-CONTRACT return distribution
# ─────────────────────────────────────────────────────────────────────────────────
def _growth_rate(returns: np.ndarray, f: float) -> float:
    """E[log(1 + f*R)] for fraction f; -inf if any wipeout (1 + f*R <= 0)."""
    terms = 1.0 + f * returns
    if np.any(terms <= 0):
        return -math.inf
    return float(np.mean(np.log(terms)))


def kelly_from_returns(returns: np.ndarray) -> dict:
    """Full-Kelly f* = argmax_f E[log(1+f*R)] on the empirical returns (not a 2-outcome toy).

    returns R_i = per-contract $PnL / per-contract $-AT-RISK, where $-at-risk is the
    *stop-defined* risk (the realized average loss per contract ≈ premium * |stop| + slippage),
    NOT full premium. That makes f the fraction of bankroll wagered on the part of the bet that
    can actually be lost — the correct Kelly denominator for a stopped option trade.

    The worst in-sample per-contract loss is only ~-30% of premium (the -8% premium stop caps
    downside well above -100%). So for ANY f where 1 + f*R_min stays > 0, log-growth keeps
    rising and f* pegs at the grid ceiling. We DETECT that: if f* is at the top of the grid,
    Kelly is 'unbounded by ruin in-sample' -> the binding governor is Rule 6 (30% cap) + the 6%
    premium ceiling, NOT Kelly. We report the ruin-bounded ceiling f_ruin = 1/|R_min| for honesty.
    """
    grid_g = [(_growth_rate(returns, float(f)), float(f)) for f in KELLY_GRID]
    grid_g = [(g, f) for g, f in grid_g if math.isfinite(g)]
    if not grid_g:
        return {"full_kelly_frac": 0.0, "log_growth_at_full": 0.0, "note": "no finite f"}
    best_g, best_f = max(grid_g, key=lambda t: t[0])
    r_min = float(np.min(returns))
    f_ruin = (1.0 / abs(r_min)) if r_min < 0 else math.inf  # f beyond which one R_min wipes out
    pegged = best_f >= (KELLY_GRID[-1] - 1e-9)
    return {
        "full_kelly_frac": round(best_f, 4),
        "half_kelly_frac": round(best_f / 2, 4),
        "quarter_kelly_frac": round(best_f / 4, 4),
        "kelly_pegged_at_grid_ceiling": bool(pegged),
        "kelly_unbounded_by_ruin_in_sample": bool(pegged),
        "ruin_bounded_f_ceiling": (round(f_ruin, 3) if math.isfinite(f_ruin) else None),
        "worst_in_sample_return": round(r_min, 4),
        "log_growth_at_full_kelly": round(best_g, 6),
        "log_growth_at_half_kelly": round(_growth_rate(returns, best_f / 2), 6),
        "mean_return_per_unit_risk": round(float(np.mean(returns)), 4),
        "std_return_per_unit_risk": round(float(np.std(returns, ddof=1)), 4),
        "risk_denominator": "stop-defined realized avg loss per contract (NOT full premium)",
    }


# ─────────────────────────────────────────────────────────────────────────────────
# MONTE-CARLO growth/ruin on the empirical per-CONTRACT $PnL distribution
# ─────────────────────────────────────────────────────────────────────────────────
def _contracts_for_equity(equity: float, premium: float, kelly_frac: float,
                          *, risk_cap_frac: float, premium_ceiling_frac: float,
                          min_contracts: int, avg_loss_per_contract: float,
                          use_kelly: bool) -> int:
    """Contracts to trade given equity + a sizing regime. ALL regimes respect Rule 6.

    Premium cost = premium*100 = cash to BUY one contract (the 30% cap + 6% ceiling basis).
    avg_loss_per_contract = stop-defined $-at-risk per contract (the Kelly bet denominator).

    use_kelly=True  -> contracts = floor(kelly_frac * equity / avg_loss_per_contract), then
        clamp DOWN to the 30%-cap and 6%-ceiling (both on premium cost). Floor to min-3 ONLY
        if 3 contracts fit inside the 30% premium cap; else the account cannot afford min-3 at
        this strike (the honest constraint at $2K ITM-2) -> take the capped count (may be < 3,
        signalling 'trade a cheaper strike or skip').
    use_kelly=False -> CURRENT rule: max contracts s.t. premium cost <= 30% equity, then min-3
        floor (same affordability guard).
    """
    if premium <= 0 or avg_loss_per_contract <= 0:
        return 0
    premium_cost = premium * 100.0
    cap_by_premium_ceiling = int((premium_ceiling_frac * equity) // premium_cost)
    cap_by_30pct = int((risk_cap_frac * equity) // premium_cost)  # cash-cap: spend <=30% on premium
    can_afford_min3 = (premium_cost * min_contracts) <= (risk_cap_frac * equity)
    if use_kelly:
        kelly_contracts = int((kelly_frac * equity) // avg_loss_per_contract)
        n = min(kelly_contracts, cap_by_premium_ceiling, cap_by_30pct)
    else:
        n = cap_by_30pct
    if can_afford_min3:
        n = max(n, min_contracts)
    return max(n, 0)


def monte_carlo(per_contract_pnls: np.ndarray, premiums: np.ndarray,
                avg_loss_per_contract: float, *, start_equity: float,
                kelly_frac: float, target_equity: float, use_kelly: bool,
                risk_cap_frac: float, premium_ceiling_frac: float,
                min_contracts: int, n_paths: int, max_trades: int,
                ruin_floor_frac: float, seed: int = 7) -> dict:
    """Bootstrap the empirical per-trade outcomes (joint pnl/premium) and compound.

    Each trade: draw an index i (with replacement), size contracts at current equity, apply
    n_i * per_contract_pnl_i, update equity. Stop a path at target_equity (success), at
    ruin_floor (impaired), or max_trades (timeout). Records growth + max drawdown.
    """
    rng = np.random.default_rng(seed)
    n_obs = len(per_contract_pnls)
    ruin_floor = start_equity * ruin_floor_frac
    trades_to_target: list[int] = []
    final_equities = np.empty(n_paths)
    max_dds = np.empty(n_paths)
    n_hit_target = 0
    n_ruin = 0
    # INFEASIBLE guard: if even at FULL start equity the sizer returns 0 contracts at the
    # median premium, this strike is unaffordable at this tier (e.g. ITM-2 at $2K under 30%
    # cap). That is NOT 'ruin' — it's 'can't deploy the edge here'. Report it distinctly.
    median_prem_local = float(np.median(premiums))
    feasible_at_start = _contracts_for_equity(
        start_equity, median_prem_local, kelly_frac, risk_cap_frac=risk_cap_frac,
        premium_ceiling_frac=premium_ceiling_frac, min_contracts=min_contracts,
        avg_loss_per_contract=avg_loss_per_contract, use_kelly=use_kelly) > 0
    if not feasible_at_start:
        return {
            "start_equity": start_equity, "target_equity": target_equity,
            "infeasible_strike_at_tier": True,
            "note": "median ITM-2 premium cannot be sized >=1 contract within Rule-6 30% cap "
                    "at this equity -> trade a cheaper strike (OTM ladder) or skip",
            "p_hit_target": None, "p_ruin_impaired_50pct": None,
            "median_trades_to_target": None, "median_weeks_to_target": None,
            "median_final_equity": start_equity, "p10_final_equity": start_equity,
            "p90_final_equity": start_equity, "median_max_drawdown_pct": None,
            "p90_max_drawdown_pct": None,
        }
    n_stranded = 0   # equity > ruin_floor but can no longer afford the min trade (distinct risk)
    for p in range(n_paths):
        eq = start_equity
        peak = start_equity
        max_dd = 0.0
        hit = False
        ruined = False
        stranded = False
        for t in range(max_trades):
            i = int(rng.integers(0, n_obs))
            prem = float(premiums[i])
            n_ct = _contracts_for_equity(
                eq, prem, kelly_frac, risk_cap_frac=risk_cap_frac,
                premium_ceiling_frac=premium_ceiling_frac, min_contracts=min_contracts,
                avg_loss_per_contract=avg_loss_per_contract, use_kelly=use_kelly)
            if n_ct <= 0:
                # can't size a trade. If equity is still above the 50% floor this is a STRAND
                # (the sizer's min-3/30%-cap interaction locked the account out), not a P&L ruin.
                if eq > ruin_floor:
                    stranded = True
                else:
                    ruined = True
                break
            eq += n_ct * float(per_contract_pnls[i])
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
            if eq <= ruin_floor:
                ruined = True
                break
            if eq >= target_equity:
                hit = True
                trades_to_target.append(t + 1)
                break
        final_equities[p] = eq
        max_dds[p] = max_dd
        if hit:
            n_hit_target += 1
        if stranded:
            n_stranded += 1
        if ruined:
            n_ruin += 1
    tt = np.array(trades_to_target) if trades_to_target else np.array([np.nan])
    return {
        "start_equity": start_equity,
        "target_equity": target_equity,
        "infeasible_strike_at_tier": False,
        "p_hit_target": round(n_hit_target / n_paths, 4),
        "p_ruin_impaired_50pct": round(n_ruin / n_paths, 4),
        "p_stranded_cant_afford_trade": round(n_stranded / n_paths, 4),
        "p_timeout_no_resolution": round((n_paths - n_hit_target - n_ruin - n_stranded) / n_paths, 4),
        "median_trades_to_target": (None if np.all(np.isnan(tt)) else int(np.nanmedian(tt))),
        "median_weeks_to_target": (None if np.all(np.isnan(tt))
                                   else round(float(np.nanmedian(tt)) / SIGNALS_PER_WEEK, 1)),
        "median_final_equity": round(float(np.median(final_equities)), 0),
        "p10_final_equity": round(float(np.percentile(final_equities, 10)), 0),
        "p90_final_equity": round(float(np.percentile(final_equities, 90)), 0),
        "median_max_drawdown_pct": round(float(np.median(max_dds)) * 100, 1),
        "p90_max_drawdown_pct": round(float(np.percentile(max_dds, 90)) * 100, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[sel-sizing] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(WINDOW_START, WINDOW_END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[sel-sizing] SPY bars={len(spy)} days={n_days} "
          f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    print("[sel-sizing] computing ribbon ...", flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # Detect the survivor's signals ONCE (full pattern, no extra gate — the headline survivor).
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sides = [s.side for s in signals]
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sides.count("C"), "P": sides.count("P")}
    print(f"[sel-sizing] signals={len(signals)} on {sig_days} days "
          f"(~{round(len(signals)/(n_days/5.0),2)}/wk) side={side_ct}", flush=True)

    # ── SURVIVOR cell: real-fills per-trade rows (qty=3) ─────────────────────────
    rows, cov = simulate_cell(signals, spy, ribbon, vix,
                              strike_offset=SURVIVOR_STRIKE_OFFSET,
                              premium_stop_pct=SURVIVOR_PREMIUM_STOP)
    m = cell_metrics(rows)
    print(f"[sel-sizing] survivor (ITM-2 / -8%): n={m['n']} exp(qty3)=${m['exp_dollar']} "
          f"oos_exp=${m['oos_exp']} is_exp=${m['is_exp']} posQ={m['positive_quarters']} "
          f"top5%={m['top5_day_pct']} fill_rate={cov['fill_rate']}", flush=True)

    # ── GATE GAUNTLET ────────────────────────────────────────────────────────────
    drop5_pt, drop5_n = _drop_top5_per_trade(rows)
    print("[sel-sizing] random-null control (20 seeds) ...", flush=True)
    null = run_random_null(spy, ribbon, vix, len(rows), sides,
                           strike_offset=SURVIVOR_STRIKE_OFFSET,
                           premium_stop_pct=SURVIVOR_PREMIUM_STOP, seeds=RANDOM_SEEDS)
    null_pt = null.get("per_trade_mean_qty3")

    print("[sel-sizing] truncation control (chart-stop-only -0.99) ...", flush=True)
    rows_ct, _ = simulate_cell(signals, spy, ribbon, vix,
                               strike_offset=SURVIVOR_STRIKE_OFFSET,
                               premium_stop_pct=CHART_STOP_ONLY)
    m_ct = cell_metrics(rows_ct)

    strat_pt = m["exp_dollar"]
    g = {}
    g["n>=20"] = (m["n"] >= BAR_N, f"n={m['n']}")
    g["oos_per_trade>0"] = (m["oos_exp"] > 0, f"oos_exp=${m['oos_exp']}")
    g["is_per_trade>0"] = (m["is_exp"] > 0, f"is_exp=${m['is_exp']}")
    g["positive_quarters>=4/6"] = (m["positive_quarters_n"] >= BAR_POS_Q,
                                   f"posQ={m['positive_quarters']}")
    g["top5_day<200pct"] = (m["top5_day_pct"] is not None and m["top5_day_pct"] < BAR_TOP5,
                            f"top5%={m['top5_day_pct']}")
    g["drop_top5_days>0"] = (drop5_pt is not None and drop5_pt > 0,
                             f"drop5_pt=${drop5_pt} (n={drop5_n})")
    g["beats_random_null"] = (null_pt is not None and strat_pt > null_pt,
                              f"strat=${strat_pt} vs null=${null_pt}")
    g["sign_stable_no_truncation"] = (m_ct.get("n", 0) > 0 and m_ct["exp_dollar"] > 0,
                                      f"chartstop_exp=${m_ct.get('exp_dollar')}")
    gate_results = {k: {"pass": bool(v[0]), "detail": v[1]} for k, v in g.items()}
    fails = [k for k, v in g.items() if not v[0]]
    edge_validated = len(fails) == 0
    print(f"[sel-sizing] GATES: {'ALL PASS' if edge_validated else 'FAILS=' + ','.join(fails)}",
          flush=True)
    for k, v in gate_results.items():
        print(f"    [{'PASS' if v['pass'] else 'FAIL'}] {k}: {v['detail']}", flush=True)

    # ── PER-CONTRACT distribution (normalize qty=3 sim to a single contract) ──────
    # dollar_pnl is for QTY contracts; per-contract = pnl / QTY. entry_premium is per-share, so
    # premium cost per contract = premium*100 (the cash to BUY it = what the 6% ceiling caps).
    per_contract_pnls = np.array([r.pnl / QTY_PER for r in rows], float)
    premiums = np.array([r.entry_premium for r in rows], float)
    per_contract_premium_cost = premiums * 100.0       # cash to buy 1 contract (6% ceiling basis)
    # Kelly $-AT-RISK denominator = stop-defined realized avg LOSS per contract (what actually
    # gets lost when wrong), NOT full premium — the correct Kelly bet size for a stopped trade.
    median_prem = float(np.median(premiums))
    losses = per_contract_pnls[per_contract_pnls < 0]
    avg_loss_per_contract = float(-np.mean(losses)) if len(losses) else (median_prem * 0.08 * 100)
    returns = per_contract_pnls / avg_loss_per_contract  # R in 'units of one average loss'

    kelly = kelly_from_returns(returns)
    full_k = kelly["full_kelly_frac"]
    half_k = kelly.get("half_kelly_frac", round(full_k / 2, 4))
    kelly["avg_loss_per_contract_dollars"] = round(avg_loss_per_contract, 2)

    print(f"[sel-sizing] Kelly: full f*={full_k} half={half_k} "
          f"pegged={kelly['kelly_pegged_at_grid_ceiling']} "
          f"ruin_ceiling_f={kelly['ruin_bounded_f_ceiling']} "
          f"mean_R={kelly['mean_return_per_unit_risk']} std_R={kelly['std_return_per_unit_risk']}",
          flush=True)

    # ── MONTE-CARLO growth/ruin per tier x regime ────────────────────────────────
    # full-Kelly here = the ruin-bounded ceiling (1/|R_min|) since the grid optimum is pegged
    # (in-sample edge has no wipeout trade). half/quarter are fractions of THAT ceiling — this
    # is the over-bettor benchmark that the Rule-6 cap is meant to protect against.
    f_ceiling = kelly.get("ruin_bounded_f_ceiling") or full_k
    print("[sel-sizing] Monte-Carlo growth/ruin (5k paths/cell) ...", flush=True)
    regimes = {
        "full_kelly_ruinbounded": {"use_kelly": True, "kelly_frac": f_ceiling},
        "half_kelly": {"use_kelly": True, "kelly_frac": round(f_ceiling / 2, 4)},
        "quarter_kelly": {"use_kelly": True, "kelly_frac": round(f_ceiling / 4, 4)},
        "current_rule_min3_30cap": {"use_kelly": False, "kelly_frac": 0.0},
    }
    mc: dict = {}
    # tier -> next growth target (2K->5K, 5K->10K, 10K->25K, 25K->50K)
    tier_targets = {2000.0: 5000.0, 5000.0: 10000.0, 10000.0: 25000.0, 25000.0: 50000.0}
    for tier in ACCOUNT_TIERS:
        mc[str(int(tier))] = {}
        for rname, rcfg in regimes.items():
            res = monte_carlo(
                per_contract_pnls, premiums, avg_loss_per_contract,
                start_equity=tier, kelly_frac=rcfg["kelly_frac"],
                target_equity=tier_targets[tier], use_kelly=rcfg["use_kelly"],
                risk_cap_frac=SAFE_RISK_CAP_FRAC,
                premium_ceiling_frac=PREMIUM_CEILING_FRAC, min_contracts=MIN_CONTRACTS,
                n_paths=MC_PATHS, max_trades=MC_MAX_TRADES, ruin_floor_frac=RUIN_FLOOR_FRAC)
            mc[str(int(tier))][rname] = res
            if res.get("infeasible_strike_at_tier"):
                print(f"    ${int(tier):>5}->${int(tier_targets[tier]):>5} {rname:>24}: "
                      f"INFEASIBLE (ITM-2 unaffordable within 30% cap at ${int(tier)})",
                      flush=True)
            else:
                print(f"    ${int(tier):>5}->${int(tier_targets[tier]):>5} {rname:>24}: "
                      f"P(hit)={res['p_hit_target']} P(ruin)={res['p_ruin_impaired_50pct']} "
                      f"P(strand)={res['p_stranded_cant_afford_trade']} "
                      f"medDD={res['median_max_drawdown_pct']}% "
                      f"medWk={res['median_weeks_to_target']}", flush=True)

    # ── OTM-2 fallback distribution (the AFFORDABLE strike for small Safe accounts) ──
    # At $2K, ITM-2 cannot fit min-3 within the 30% cap. The v15 ladder already trades the
    # CHEAPER OTM-2 strike below $25K. We re-sim OTM-2 (offset +2) on the SAME signals/path so
    # the $2K recommendation is concrete (real OTM-2 premium + real OTM-2 per-trade edge), and
    # we quantify the edge HAIRCUT from trading the affordable strike instead of the edge strike.
    print("[sel-sizing] OTM-2 fallback distribution (affordable strike for small accounts) ...",
          flush=True)
    rows_otm, _ = simulate_cell(signals, spy, ribbon, vix, strike_offset=2,
                                premium_stop_pct=SURVIVOR_PREMIUM_STOP)
    m_otm = cell_metrics(rows_otm)
    otm_pnls = np.array([r.pnl / QTY_PER for r in rows_otm], float)
    otm_prems = np.array([r.entry_premium for r in rows_otm], float)
    otm_median_prem = float(np.median(otm_prems)) if len(otm_prems) else 0.0
    otm_mean_pnl = float(np.mean(otm_pnls)) if len(otm_pnls) else 0.0
    otm_prem_cost = otm_median_prem * 100.0
    otm_block = {
        "strike_tier": "OTM-2", "n": m_otm.get("n"), "exp_dollar_qty3": m_otm.get("exp_dollar"),
        "oos_exp_qty3": m_otm.get("oos_exp"), "positive_quarters": m_otm.get("positive_quarters"),
        "top5_day_pct": m_otm.get("top5_day_pct"),
        "median_entry_premium_per_share": round(otm_median_prem, 2),
        "median_premium_cost_per_contract": round(otm_prem_cost, 0),
        "mean_pnl_per_contract": round(otm_mean_pnl, 2),
        "edge_haircut_vs_itm2_pct": (round(100 * (1 - (m_otm.get("exp_dollar", 0) /
                                     m["exp_dollar"])), 1) if m["exp_dollar"] else None),
    }
    print(f"    OTM-2: n={m_otm.get('n')} exp(qty3)=${m_otm.get('exp_dollar')} "
          f"median_prem=${round(otm_median_prem,2)} "
          f"haircut_vs_ITM2={otm_block['edge_haircut_vs_itm2_pct']}%", flush=True)

    # ── CONCRETE per-tier recommendation (Rule 6 + 6% premium ceiling) ───────────
    # v15 strike ladder: OTM-3 @ $1K / OTM-2 @ $2-10K / OTM-1 @ $10-25K / ITM-2 @ $25K+.
    # Survivor edge is ITM-2 specifically; recommendation pins ITM-2 sizing math, and where ITM-2
    # is unaffordable (small Safe accounts), drops to the OTM-2 affordable execution (real edge).
    recommended_frac = half_k  # half-Kelly = the standing practical operating point
    mean_pnl_per_contract = float(np.mean(per_contract_pnls))
    prem_cost = median_prem * 100.0          # cash to buy 1 ITM-2 contract (30%cap + 6%ceiling basis)
    recs = []
    for tier in ACCOUNT_TIERS:
        # half-Kelly contracts: f_half * equity-at-risk / (avg loss per contract)
        kelly_ct = int((recommended_frac * tier) // avg_loss_per_contract) if avg_loss_per_contract > 0 else 0
        # Rule-6 30% cap + 6% premium ceiling are on PREMIUM COST (cash to buy), not avg loss
        cap_risk_ct = int((SAFE_RISK_CAP_FRAC * tier) // prem_cost) if prem_cost > 0 else 0
        cap_prem_ct = int((PREMIUM_CEILING_FRAC * tier) // prem_cost) if prem_cost > 0 else 0
        binding = min(kelly_ct, cap_risk_ct, cap_prem_ct)
        affordable3 = (prem_cost * MIN_CONTRACTS) <= (SAFE_RISK_CAP_FRAC * tier)  # 3 ct within 30% cap
        final_ct = max(binding, MIN_CONTRACTS) if affordable3 else binding
        # which constraint binds the recommendation
        if not affordable3 and final_ct < MIN_CONTRACTS:
            which = "CANNOT_AFFORD_MIN3_AT_ITM2_WITHIN_30PCT_CAP"
        elif final_ct == MIN_CONTRACTS and binding < MIN_CONTRACTS:
            which = "min_3_floor"
        elif cap_prem_ct == binding and cap_prem_ct <= cap_risk_ct and cap_prem_ct < kelly_ct:
            which = "6pct_premium_ceiling"
        elif cap_risk_ct == binding and cap_risk_ct < kelly_ct:
            which = "30pct_risk_cap"
        else:
            which = "half_kelly"
        rec = {
            "tier_equity": tier,
            "edge_strike": "ITM-2 (survivor)",
            "itm2_median_entry_premium_per_share": round(median_prem, 2),
            "itm2_median_premium_cost_per_contract": round(prem_cost, 0),
            "avg_loss_per_contract": round(avg_loss_per_contract, 0),
            "half_kelly_contracts_uncapped": kelly_ct,
            "itm2_contracts_at_30pct_risk_cap": cap_risk_ct,
            "itm2_contracts_at_6pct_premium_ceiling": cap_prem_ct,
        }
        if not affordable3:
            # ITM-2 unaffordable -> drop to the OTM-2 affordable execution (v15 ladder behavior)
            otm_cap_risk = int((SAFE_RISK_CAP_FRAC * tier) // otm_prem_cost) if otm_prem_cost > 0 else 0
            otm_cap_prem = int((PREMIUM_CEILING_FRAC * tier) // otm_prem_cost) if otm_prem_cost > 0 else 0
            otm_afford3 = (otm_prem_cost * MIN_CONTRACTS) <= (SAFE_RISK_CAP_FRAC * tier)
            otm_final = max(min(otm_cap_risk, otm_cap_prem), MIN_CONTRACTS) if otm_afford3 else otm_cap_risk
            rec.update({
                "RECOMMENDED_strike": "OTM-2 (ITM-2 unaffordable within 30% cap at this equity)",
                "RECOMMENDED_contracts": otm_final,
                "binding_constraint": ("min_3_floor_OTM2" if otm_afford3 and
                                       min(otm_cap_risk, otm_cap_prem) < MIN_CONTRACTS
                                       else "30pct_cap_OTM2"),
                "otm2_median_premium_cost_per_contract": round(otm_prem_cost, 0),
                "premium_cost_pct_of_equity": (round(100 * otm_final * otm_prem_cost / tier, 1)
                                               if tier > 0 else None),
                "expected_dollar_per_trade_at_rec": round(otm_final * otm_mean_pnl, 2),
                "edge_haircut_note": (f"OTM-2 captures ~{round(otm_mean_pnl,0)}/contract vs ITM-2 "
                                      f"${round(mean_pnl_per_contract,0)}/contract "
                                      f"({otm_block['edge_haircut_vs_itm2_pct']}% haircut) — "
                                      f"this tier is structurally below where the edge lives"),
            })
            disp_ct, disp_strike = otm_final, "OTM-2"
        else:
            rec.update({
                "RECOMMENDED_strike": "ITM-2 (edge strike)",
                "RECOMMENDED_contracts": final_ct,
                "binding_constraint": which,
                "premium_cost_pct_of_equity": (round(100 * final_ct * prem_cost / tier, 1)
                                               if tier > 0 else None),
                "expected_dollar_per_trade_at_rec": round(final_ct * mean_pnl_per_contract, 2),
            })
            disp_ct, disp_strike = final_ct, "ITM-2"
        recs.append(rec)
        print(f"    tier ${int(tier):>5}: rec={disp_ct} {disp_strike} contracts "
              f"(ITM2 halfK={kelly_ct}, 30%cap={cap_risk_ct}, 6%ceil={cap_prem_ct}) "
              f"bind={rec['binding_constraint']} prem%={rec['premium_cost_pct_of_equity']}",
              flush=True)

    # ── ASSEMBLE schema ──────────────────────────────────────────────────────────
    schema = {
        "study": "vwap_continuation fractional-Kelly position sizing + compounding + risk-of-ruin",
        "slug": "vwap-sizing",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "interpreter": "backtest/.venv/Scripts/python.exe",
        "cost": "$0 pure-Python sim loop; no LLM; no live orders; markets closed",
        "survivor_config": {
            "strike_offset": SURVIVOR_STRIKE_OFFSET, "strike_tier": "ITM-2",
            "premium_stop_pct": SURVIVOR_PREMIUM_STOP, "exits": "v15 default",
            "qty_sim": QTY_PER,
        },
        "detector": ("BYTE-FOR-BYTE j_daily_pattern_ratify.detect_j_vwap_continuation "
                     "(reused from _edgehunt_vwap_continuation); live port = "
                     "backtest/lib/watchers/vwap_continuation_watcher.py"),
        "fills_authority": ("real OPRA via lib.simulator_real.simulate_trade_real (C1); "
                            "nearest-cached strike snap <=4; causal next-bar-open entry; "
                            "chart-stop = session extreme"),
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "coverage": cov,
        "distribution_qty3": {
            "n": m["n"], "wr_pct": m["wr_pct"], "exp_dollar_qty3": m["exp_dollar"],
            "total_dollar_qty3": m["total_dollar"],
            "is_n": m["is_n"], "is_exp_qty3": m["is_exp"],
            "oos_n": m["oos_n"], "oos_exp_qty3": m["oos_exp"],
            "quarters": m["quarters"], "positive_quarters": m["positive_quarters"],
            "top5_day_pct": m["top5_day_pct"], "by_side": m["by_side"],
            "exit_hist": m["exit_hist"],
        },
        "per_contract": {
            "n": int(len(per_contract_pnls)),
            "mean_pnl_per_contract": round(float(np.mean(per_contract_pnls)), 2),
            "median_pnl_per_contract": round(float(np.median(per_contract_pnls)), 2),
            "std_pnl_per_contract": round(float(np.std(per_contract_pnls, ddof=1)), 2),
            "win_pnl_mean": round(float(np.mean(per_contract_pnls[per_contract_pnls > 0])), 2)
                            if np.any(per_contract_pnls > 0) else None,
            "loss_pnl_mean": round(float(np.mean(per_contract_pnls[per_contract_pnls <= 0])), 2)
                             if np.any(per_contract_pnls <= 0) else None,
            "best_pnl": round(float(np.max(per_contract_pnls)), 2),
            "worst_pnl": round(float(np.min(per_contract_pnls)), 2),
            "median_entry_premium_per_share": round(median_prem, 2),
        },
        "GATES": {
            "all_pass": edge_validated,
            "fails": fails,
            "results": gate_results,
            "random_null": null,
            "truncation_control_chartstop": {
                "premium_stop_pct": CHART_STOP_ONLY, "n": m_ct.get("n"),
                "exp_dollar_qty3": m_ct.get("exp_dollar"), "oos_exp_qty3": m_ct.get("oos_exp"),
                "sign_stable": bool(m_ct.get("n", 0) > 0 and m_ct.get("exp_dollar", -1) > 0),
            },
            "drop_top5_days_per_trade_qty3": drop5_pt,
        },
        "edge_validated": edge_validated,
        "kelly": kelly,
        "sizing_constants": {
            "rule6_safe_risk_cap_frac": SAFE_RISK_CAP_FRAC,
            "min_contracts": MIN_CONTRACTS,
            "premium_ceiling_frac": PREMIUM_CEILING_FRAC,
            "signals_per_week": SIGNALS_PER_WEEK,
            "ruin_def": f"equity <= {int(RUIN_FLOOR_FRAC*100)}% of start (impaired)",
            "mc_paths": MC_PATHS,
        },
        "monte_carlo": mc,
        "otm2_affordable_fallback": otm_block,
        "recommendation_per_tier": recs,
        "recommended_operating_point": "half_kelly (clamped by Rule-6 30% cap + 6% premium ceiling, floored at min-3); at tiers where ITM-2 is unaffordable, drop to OTM-2 affordable execution",
        "DISCLOSURE": {
            "real_fills": "C1 — real OPRA fills, BS-sim never touched (ranking-only authority)",
            "no_cherry_pick": "anti-pattern 2.10 — every mandatory gate run deterministically; "
                              "sizing flagged edge_validated=false if ANY gate fails",
            "kelly_caveat": ("full-Kelly on a 16-mo / n~150 sample over-bets; half-Kelly is the "
                             "operating point, further clamped by Rule 6 + 6% ceiling. Kelly "
                             "fraction = fraction of equity committed as premium-at-risk."),
            "strike_ladder_mismatch": ("the EDGE is measured at ITM-2; the Safe v15 ladder runs "
                                       "OTM-2 below $25K. Sizing math is on the ITM-2 survivor; "
                                       "applying it requires trading the edge's strike, not the "
                                       "nominal ladder strike (flagged for J / Treasurer)."),
            "ruin_model": ("bootstrap resample of the joint (pnl, premium) per-trade outcomes; "
                           "assumes future trades are drawn from the observed 16-mo distribution "
                           "(stationarity assumption — the real risk to all of this)."),
        },
    }

    OUT_SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    OUT_SCHEMA.write_text(json.dumps(schema, indent=2, default=str), encoding="utf-8")
    # task-named alias = the sizing block (same content, the deliverable name)
    OUT_SIZING.write_text(json.dumps(schema, indent=2, default=str), encoding="utf-8")
    print(f"\n[sel-sizing] wrote {OUT_SCHEMA}", flush=True)
    print(f"[sel-sizing] wrote {OUT_SIZING}", flush=True)

    print("\n=== VWAP_CONTINUATION SIZING VERDICT ===")
    print(f"edge_validated={edge_validated} (fails={fails})")
    print(f"per-contract: mean=${schema['per_contract']['mean_pnl_per_contract']} "
          f"win=${schema['per_contract']['win_pnl_mean']} loss=${schema['per_contract']['loss_pnl_mean']} "
          f"wr={m['wr_pct']}%")
    print(f"full-Kelly={full_k} half-Kelly={half_k} (recommend HALF, clamped by Rule 6)")
    for r in recs:
        print(f"  ${int(r['tier_equity']):>5}: {r['RECOMMENDED_contracts']} x {r['RECOMMENDED_strike']} "
              f"(bind={r['binding_constraint']}, prem={r['premium_cost_pct_of_equity']}% equity, "
              f"E[$/trade]={r['expected_dollar_per_trade_at_rec']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
