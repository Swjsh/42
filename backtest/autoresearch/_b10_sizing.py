"""B10 — SIZING / COMPOUNDING the measured 3-edge book (the make-money capstone).

B9 MEASURED the three real edges as a combined portfolio at a FIXED qty=3 contracts
(no equity scaling, no compounding). B10 answers the next question: given the measured
edge, HOW DO WE SIZE IT to compound fastest WITHIN J's hard caps (Rule 5/6)?

We REUSE B9's exact detection + real-OPRA-fill pipeline (we import b9's simulate_set,
the same detectors, the same v15 exits) so the per-trade % returns and dollar P&Ls are
byte-identical to B9 — we do NOT rebuild detectors. The ONLY addition is that we also
capture each trade's entry_premium so we know the CAPITAL DEPLOYED per trade (premium x
qty x 100), which is what Kelly fraction-of-equity needs.

THE TWO BOOKS (per B9 / per the 3-edge book spec):
  * Safe-2 (ATM,  strike_offset=0):  #1 + #2 + #4
  * Bold   (ITM-2, strike_offset=-2): #1 + #2

WHAT WE COMPUTE:
  1. Per-trade & per-day RETURN DISTRIBUTION for each book (mean/std/downside/skew),
     expressed as RETURN-ON-CAPITAL-DEPLOYED (the Kelly-relevant unit) AND in dollars
     at the B9 qty=3 baseline.
  2. FRACTIONAL-KELLY on the book. Full-Kelly fraction-of-equity f* from the measured
     edge (continuous-outcome Kelly: f* = mean_return / variance_of_return, capped at
     the discrete-Kelly ceiling), then half- and quarter-Kelly. Then we CLAMP every
     proposed fraction to J's hard caps (per-trade risk cap, min-3-contracts floor).
     NEVER recommend exceeding the caps — if Kelly supports more, we FLAG
     "edge supports X but capped at Y by Rule 6" and clamp.
  3. COMPOUNDING SIMULATION from each account's start equity ($2,000 Safe / $1,673 Bold),
     replaying the MEASURED per-trade returns in chronological order under:
       (a) current v15 tier sizing (contracts step up by equity tier), and
       (b) the proposed fractional-Kelly sizing (size = clamp(f * equity / premium)).
     Report: final equity, trading-days to reach $5K/$10K/$25K, max drawdown along the
     path, and how often the -30%/-50% DAILY kill switch would trip (bad-run frequency /
     a risk-of-ruin proxy). Both the per-day daily-loss kill AND a ruin check.
  4. VERDICT: a concrete daytime SIZING-SPEC (contracts per tier per account) that
     maximizes geometric growth WITHIN the caps, vs current v15 — under- or over-sized?
     respects_hard_caps MUST be true. Honest bull-regime-flattered caveat: the measured
     Sharpe will NOT hold in chop/bear, so the spec sizes for the WORSE regime (we stress
     the compounding sim with a haircut on the measured edge and re-report kill frequency).

J HARD CAPS (never optimized past — clamp, flag if edge wants more):
  * Safe-2: daily kill -30% of SoD equity; per-trade risk cap 30% of equity; min 3 contracts.
  * Bold:   daily kill -50% of SoD equity; per-trade risk cap 50% of equity; min 3 contracts.
  v15 sizing tiers: at $2K -> 5 base / 8 elite contracts; $10k+ -> 10 base / 15 elite.

Pure Python / numpy, $0 (no LLM, no live orders). Markets closed.
Writes analysis/recommendations/B10-SIZING-SCORECARD.{md,json}.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b10_sizing.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    detect_signals as detect_vwap_continuation,
)
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals as detect_reclaim_failed_break,
)
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    causal_vix_median,
    vix_slope,
    detect_opt_signals as detect_vix_regime_dayside,
    _swing_stop,
    VIX_MEDIAN_BARS,
    VIX_SLOPE_BARS,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

# Reuse B9 config so the trade streams are identical
from autoresearch._b9_portfolio import (  # noqa: E402
    START, END, PREMIUM_STOP_PCT, MAX_STRIKE_STEPS, QTY as B9_QTY,
    OOS_YEAR, TRADING_DAYS_PER_YEAR, ATM, ITM2, load_vix_regime_config,
)

OUT_JSON = ROOT / "analysis" / "recommendations" / "B10-SIZING-SCORECARD.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "B10-SIZING-SCORECARD.md"

# ── Account hard caps (Rule 5 / Rule 6 — NEVER optimize past these) ──────────────
ACCOUNTS = {
    "Safe-2": {
        "start_equity": 2000.0,
        "strike_offset": ATM,
        "edges": ("e1", "e2", "e4"),
        "daily_kill_frac": 0.30,      # Rule 5: -30% of SoD equity halts the day
        "per_trade_cap_frac": 0.30,   # Rule 6: per-trade risk cap 30% of equity
        "min_contracts": 3,           # Rule 6: min 3 (2 TP + 1 runner)
        # v15 tier sizing: (equity_threshold, base_contracts, elite_contracts)
        "v15_tiers": [(0.0, 5, 8), (10000.0, 10, 15)],
    },
    "Bold": {
        "start_equity": 1673.0,
        "strike_offset": ITM2,
        "edges": ("e1", "e2"),
        "daily_kill_frac": 0.50,
        "per_trade_cap_frac": 0.50,
        "min_contracts": 3,
        # Bold runs the same contract ladder in v15; elite tilt is larger but we mirror Safe
        "v15_tiers": [(0.0, 5, 8), (10000.0, 10, 15)],
    },
}

GOALS = [5000.0, 10000.0, 25000.0]


# ════════════════════════════════════════════════════════════════════════════════
# TRADE STREAM — reuse B9's detect+sim, but capture entry_premium (capital deployed)
# ════════════════════════════════════════════════════════════════════════════════
@dataclass
class T:
    """One measured real-OPRA trade, qty-agnostic.

    entry_premium = per-contract entry price (dollars). Capital for 1 contract = premium*100.
    pct = pct_return_on_premium (per-contract, qty-invariant — return on capital deployed).
    pnl3 = dollar P&L at the B9 baseline qty=3 (for cross-checking against B9).
    """
    date: str
    side: str
    edge: str
    entry_premium: float
    pct: float
    pnl3: float
    exit_reason: str


def simulate_stream(signals, spy, ribbon, vix, *, strike_offset, edge, setup):
    """Identical entry/strike/fill logic to b9.simulate_set, but returns T rows that
    carry entry_premium so we can size by capital-deployed. pct is qty-invariant."""
    rows: list[T] = []
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=B9_QTY, setup=setup, strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=PREMIUM_STOP_PCT)
        if fill is None or fill.dollar_pnl is None:
            continue
        ep = float(fill.entry_premium) if fill.entry_premium else 0.0
        if ep <= 0:
            continue
        rows.append(T(
            date=str(d), side=sg.side, edge=edge,
            entry_premium=round(ep, 4),
            pct=round(float(fill.pct_return_on_premium), 6),
            pnl3=round(float(fill.dollar_pnl), 2),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE"))
    return rows


# ════════════════════════════════════════════════════════════════════════════════
# RETURN DISTRIBUTION (return-on-capital-deployed, the Kelly unit)
# ════════════════════════════════════════════════════════════════════════════════
def trade_return_stats(trades: list[T]) -> dict:
    """Per-trade return-on-capital-deployed distribution for the whole book."""
    if not trades:
        return {"n": 0}
    r = np.array([t.pct for t in trades], float)   # return on capital deployed, per trade
    n = len(r)
    wins = r[r > 0]
    losses = r[r < 0]
    mean = float(r.mean())
    var = float(r.var(ddof=1)) if n > 1 else 0.0
    std = float(np.sqrt(var))
    downside = float(np.sqrt(np.mean(np.minimum(r, 0.0) ** 2)))
    return {
        "n": n,
        "mean_return": round(mean, 5),
        "std_return": round(std, 5),
        "variance_return": round(var, 6),
        "downside_dev": round(downside, 5),
        "skew": round(float(((r - mean) ** 3).mean() / (std ** 3)), 3) if std > 0 else 0.0,
        "win_rate": round(float(len(wins) / n), 4),
        "avg_win_return": round(float(wins.mean()), 5) if len(wins) else 0.0,
        "avg_loss_return": round(float(losses.mean()), 5) if len(losses) else 0.0,
        "worst_trade_return": round(float(r.min()), 5),
        "best_trade_return": round(float(r.max()), 5),
        "median_premium": round(float(np.median([t.entry_premium for t in trades])), 3),
    }


def day_return_stats(trades: list[T]) -> dict:
    """Per-DAY return-on-capital distribution. A day's return = capital-weighted mean of
    that day's trade returns (what one equity-fraction-per-trade book actually experiences
    when 2+ edges fire). We weight by capital deployed so the per-day number is honest."""
    by_d: dict[str, list[T]] = defaultdict(list)
    for t in trades:
        by_d[t.date].append(t)
    day_rets = []
    for d, ts in by_d.items():
        cap = np.array([x.entry_premium for x in ts], float)
        ret = np.array([x.pct for x in ts], float)
        day_rets.append(float(np.average(ret, weights=cap)) if cap.sum() > 0 else float(ret.mean()))
    dr = np.array(day_rets, float)
    n = len(dr)
    if n == 0:
        return {"n_days": 0}
    return {
        "n_days": n,
        "mean_day_return": round(float(dr.mean()), 5),
        "std_day_return": round(float(dr.std(ddof=1)), 5) if n > 1 else 0.0,
        "downside_day_dev": round(float(np.sqrt(np.mean(np.minimum(dr, 0.0) ** 2))), 5),
        "worst_day_return": round(float(dr.min()), 5),
        "best_day_return": round(float(dr.max()), 5),
        "day_win_rate": round(float((dr > 0).mean()), 4),
    }


# ════════════════════════════════════════════════════════════════════════════════
# FRACTIONAL KELLY (continuous-outcome) + hard-cap clamp
# ════════════════════════════════════════════════════════════════════════════════
def kelly_fraction(stats: dict) -> dict:
    """Full-Kelly fraction-of-equity-per-trade for a continuous-return bet.

    For a bet whose return-on-stake r has mean m and variance v, the growth-optimal
    fraction of bankroll to stake is approximately f* = m / v (the Gaussian/continuous
    Kelly). This is the fraction of EQUITY put at risk as option PREMIUM per trade.
    We also report the discrete two-outcome Kelly (using avg win/avg loss & win rate)
    as a sanity cross-check, and take the MORE CONSERVATIVE of the two as the headline
    full-Kelly to avoid overstating from the continuous approximation."""
    m = stats["mean_return"]
    v = stats["variance_return"]
    f_cont = (m / v) if v > 0 else 0.0
    # discrete two-outcome Kelly: f = p/|loss| - q/win  (b = win/|loss| odds form)
    p = stats["win_rate"]
    q = 1 - p
    aw = stats["avg_win_return"]
    al = abs(stats["avg_loss_return"])
    if aw > 0 and al > 0:
        b = aw / al
        f_disc = (b * p - q) / b
    else:
        f_disc = 0.0
    f_full = max(0.0, min(f_cont, f_disc))   # conservative headline
    return {
        "f_continuous": round(f_cont, 4),
        "f_discrete": round(f_disc, 4),
        "f_full_kelly": round(f_full, 4),
        "f_half_kelly": round(f_full / 2, 4),
        "f_quarter_kelly": round(f_full / 4, 4),
        "kelly_note": ("f* = fraction of EQUITY deployed as option premium per trade; "
                       "headline full-Kelly = min(continuous m/v, discrete) to stay "
                       "conservative. Half/quarter-Kelly are the practical fractions."),
    }


def contracts_from_fraction(fraction: float, equity: float, premium: float,
                            *, per_trade_cap_frac: float, min_contracts: int) -> dict:
    """Translate an equity-fraction into a contract count for a given trade, then CLAMP
    to J's hard caps. Returns the clamped count + whether the edge 'wanted' more."""
    if premium <= 0:
        return {"contracts": min_contracts, "clamped": "min_floor", "wanted": min_contracts}
    cost_per_contract = premium * 100.0
    raw = (fraction * equity) / cost_per_contract
    wanted = int(np.floor(raw))
    # Rule 6 per-trade cap: premium deployed <= per_trade_cap_frac * equity
    cap_contracts = int(np.floor((per_trade_cap_frac * equity) / cost_per_contract))
    clamp_reason = None
    c = wanted
    if c > cap_contracts:
        c = cap_contracts
        clamp_reason = "per_trade_cap"
    if c < min_contracts:
        # min-3 floor — but only take the trade if min-3 still fits under the cap
        if min_contracts <= cap_contracts:
            c = min_contracts
            clamp_reason = clamp_reason or "min_floor"
        else:
            c = 0  # cannot satisfy min-3 without breaching the per-trade cap -> skip
            clamp_reason = "min_floor_exceeds_cap_SKIP"
    return {"contracts": int(c), "clamped": clamp_reason, "wanted": int(wanted),
            "cap_contracts": int(cap_contracts)}


def v15_contracts(equity: float, is_elite: bool, tiers) -> int:
    """Current v15 tier sizing: pick the highest tier whose threshold <= equity."""
    base, elite = tiers[0][1], tiers[0][2]
    for thr, b, e in tiers:
        if equity >= thr:
            base, elite = b, e
    return elite if is_elite else base


# ════════════════════════════════════════════════════════════════════════════════
# COMPOUNDING SIMULATION
# ════════════════════════════════════════════════════════════════════════════════
def _elite_flag(t: T) -> bool:
    """ELITE per CLAUDE.md: trigger set includes confluence OR sequence_rejection/reclaim.
    Our book proxy: edge #2 (reclaim_failed_break) trades are the reclaim/sequence class;
    #1 continuation + #4 vix-regime are base. (Conservative: most days are 'base'.)"""
    return t.edge == "e2"


def compound_sim(trades_by_day: list[tuple[str, list[T]]], *, start_equity: float,
                 sizing: str, account: dict, kelly_fraction_val: float = 0.0,
                 edge_haircut: float = 0.0) -> dict:
    """Replay measured per-trade returns chronologically, compounding equity.

    sizing: 'v15' (tier contracts) or 'kelly' (clamp(fraction*equity/premium)).
    edge_haircut: multiply every per-trade return by (1 - haircut) to stress the
                  bull-flattered edge for the worse-regime check.
    Daily kill switch: if cumulative INTRADAY loss in a day reaches -kill_frac*SoD equity,
    stop trading that day (remaining same-day trades skipped). Tracks trips + ruin.
    """
    eq = start_equity
    peak = start_equity
    max_dd_dollar = 0.0
    max_dd_frac = 0.0
    kill_trips = 0
    n_trades_taken = 0
    n_trades_skipped_cap = 0
    days_to_goal = {g: None for g in GOALS}
    trading_day_idx = 0
    equity_curve = []
    ruined = False
    RUIN_FLOOR = start_equity * 0.10   # practical ruin: equity falls below 10% of start

    cap = account["per_trade_cap_frac"]
    minc = account["min_contracts"]
    tiers = account["v15_tiers"]
    kill_frac = account["daily_kill_frac"]

    for d, ts in trades_by_day:
        trading_day_idx += 1
        sod_equity = eq
        day_loss = 0.0
        killed = False
        for t in ts:
            if killed:
                break
            if eq <= RUIN_FLOOR:
                ruined = True
                break
            ret = t.pct * (1.0 - edge_haircut)
            if sizing == "v15":
                c = v15_contracts(eq, _elite_flag(t), tiers)
                # still respect the per-trade cap + min-floor as a safety (Rule 6 is law)
                cost_per_contract = t.entry_premium * 100.0
                cap_c = int(np.floor((cap * eq) / cost_per_contract)) if cost_per_contract > 0 else c
                c = min(c, cap_c)
                if c < minc:
                    if minc <= cap_c:
                        c = minc
                    else:
                        n_trades_skipped_cap += 1
                        continue
            else:  # kelly
                info = contracts_from_fraction(
                    kelly_fraction_val, eq, t.entry_premium,
                    per_trade_cap_frac=cap, min_contracts=minc)
                c = info["contracts"]
                if c <= 0:
                    n_trades_skipped_cap += 1
                    continue
            cost = t.entry_premium * 100.0 * c
            pnl = ret * cost
            eq += pnl
            n_trades_taken += 1
            if pnl < 0:
                day_loss += pnl
            # daily kill switch (intraday): loss vs SoD equity
            if day_loss <= -kill_frac * sod_equity:
                kill_trips += 1
                killed = True
            # drawdown tracking
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd_dollar:
                max_dd_dollar = dd
                max_dd_frac = dd / peak if peak > 0 else 0.0
        equity_curve.append((d, round(eq, 2)))
        for g in GOALS:
            if days_to_goal[g] is None and eq >= g:
                days_to_goal[g] = trading_day_idx
        if ruined:
            break

    cagr = None
    if not ruined and start_equity > 0 and trading_day_idx > 0:
        years = trading_day_idx / TRADING_DAYS_PER_YEAR
        if years > 0 and eq > 0:
            cagr = (eq / start_equity) ** (1 / years) - 1

    return {
        "sizing": sizing,
        "edge_haircut": edge_haircut,
        "kelly_fraction": round(kelly_fraction_val, 4) if sizing == "kelly" else None,
        "start_equity": round(start_equity, 2),
        "final_equity": round(eq, 2),
        "total_return_pct": round(100 * (eq - start_equity) / start_equity, 1),
        "cagr_pct": round(100 * cagr, 1) if cagr is not None else None,
        "trading_days_replayed": trading_day_idx,
        "n_trades_taken": n_trades_taken,
        "n_trades_skipped_cap": n_trades_skipped_cap,
        "max_drawdown_dollar": round(max_dd_dollar, 2),
        "max_drawdown_pct": round(100 * max_dd_frac, 1),
        "kill_switch_trips": kill_trips,
        "kill_trip_rate_per_day": round(kill_trips / trading_day_idx, 4) if trading_day_idx else 0.0,
        "ruined": ruined,
        "days_to_5k": days_to_goal[5000.0],
        "days_to_10k": days_to_goal[10000.0],
        "days_to_25k": days_to_goal[25000.0],
        "equity_curve_tail": equity_curve[-5:],
    }


def bootstrap_ruin(trades_by_day: list[tuple[str, list[T]]], *, start_equity: float,
                   account: dict, kelly_fraction_val: float, edge_haircut: float = 0.0,
                   n_paths: int = 2000, seed: int = 7) -> dict:
    """MONTE-CARLO honesty check. The single chronological replay is ONE lucky bull-ordering;
    it cannot estimate risk-of-ruin. We bootstrap by resampling whole DAYS (block = a day's
    trade list, preserving intraday structure + the daily kill switch) WITH replacement to a
    342-day path, repeated n_paths times, under quarter-Kelly. Report the distribution of
    final equity, max drawdown, kill trips, and the % of paths that RUIN (equity < 10% start).
    This is the realistic 'what if the days came in a worse order / a bad run clusters' number."""
    rng = np.random.default_rng(seed)
    day_blocks = [ts for _, ts in trades_by_day]
    n_days = len(day_blocks)
    if n_days == 0:
        return {"n_paths": 0}
    finals, dds, kills, ruins = [], [], [], 0
    for _ in range(n_paths):
        idx = rng.integers(0, n_days, size=n_days)
        path = [(f"d{i}", day_blocks[j]) for i, j in enumerate(idx)]
        sim = compound_sim(path, start_equity=start_equity, sizing="kelly",
                           account=account, kelly_fraction_val=kelly_fraction_val,
                           edge_haircut=edge_haircut)
        finals.append(sim["final_equity"])
        dds.append(sim["max_drawdown_pct"])
        kills.append(sim["kill_switch_trips"])
        if sim["ruined"]:
            ruins += 1
    finals = np.array(finals, float)
    dds = np.array(dds, float)
    kills = np.array(kills, float)
    return {
        "n_paths": n_paths,
        "edge_haircut": edge_haircut,
        "kelly_fraction": round(kelly_fraction_val, 4),
        "ruin_rate": round(ruins / n_paths, 4),
        "final_equity_p05": round(float(np.percentile(finals, 5)), 2),
        "final_equity_median": round(float(np.percentile(finals, 50)), 2),
        "final_equity_p95": round(float(np.percentile(finals, 95)), 2),
        "max_dd_pct_median": round(float(np.percentile(dds, 50)), 1),
        "max_dd_pct_p95": round(float(np.percentile(dds, 95)), 1),
        "kill_trips_median": round(float(np.percentile(kills, 50)), 1),
        "kill_trips_p95": round(float(np.percentile(kills, 95)), 1),
        "note": ("day-block bootstrap (resample whole days w/ replacement, 342-day paths). "
                 "Final-equity dispersion is wide because compounding a positive-mean bull-tape "
                 "edge over 342 days is explosive in the lucky tail — read the P05 + ruin_rate + "
                 "max_dd, NOT the median terminal $, as the risk signal."),
    }


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"[b10] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_trading_days = len(days)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    print(f"[b10] trading_days={n_trading_days}", flush=True)

    vix_g = vix.to_numpy()
    vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
    vix_cfg = load_vix_regime_config()

    # ── Detect each edge once (same as B9) ────────────────────────────────────────
    sig_e1 = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_e2 = detect_reclaim_failed_break(days)
    sig_e4_raw = detect_vix_regime_dayside(days, spy, vix_g, vix_med_g, vix_slp_g,
                                           vix_cfg["low_margin"], vix_cfg["slope_rule"])
    sig_e4 = [Signal(bar_idx=s.gidx, side=s.side,
                     stop_level=round(_swing_stop(spy, s.gidx, s.side), 2),
                     note="vix_regime_dayside") for s in sig_e4_raw]
    print(f"[b10] signals #1={len(sig_e1)} #2={len(sig_e2)} #4={len(sig_e4)}", flush=True)

    # ── Build per-trade streams at each tier ──────────────────────────────────────
    # Safe-2 ATM streams
    e1_atm = simulate_stream(sig_e1, spy, ribbon, vix, strike_offset=ATM, edge="e1", setup="VWAPCONT")
    e2_atm = simulate_stream(sig_e2, spy, ribbon, vix, strike_offset=ATM, edge="e2", setup="RECLAIM")
    e4_atm = simulate_stream(sig_e4, spy, ribbon, vix, strike_offset=ATM, edge="e4", setup="VIXREGIME")
    # Bold ITM-2 streams
    e1_itm2 = simulate_stream(sig_e1, spy, ribbon, vix, strike_offset=ITM2, edge="e1", setup="VWAPCONT")
    e2_itm2 = simulate_stream(sig_e2, spy, ribbon, vix, strike_offset=ITM2, edge="e2", setup="RECLAIM")

    safe_trades = e1_atm + e2_atm + e4_atm
    bold_trades = e1_itm2 + e2_itm2

    # cross-check against B9 (sum of pnl3 should match B9 totals)
    safe_pnl3 = round(sum(t.pnl3 for t in safe_trades), 2)
    bold_pnl3 = round(sum(t.pnl3 for t in bold_trades), 2)
    print(f"[b10] B9 cross-check  Safe qty3 total=${safe_pnl3} (B9=14608.16)  "
          f"Bold qty3 total=${bold_pnl3} (B9=18784.32)", flush=True)

    books = {"Safe-2": safe_trades, "Bold": bold_trades}
    result = {
        "campaign": "B10 — sizing/compounding the measured 3-edge book within J's hard caps",
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "trading_days": n_trading_days,
        "fills_authority": "real OPRA via lib.simulator_real (reuses B9 detect+fill pipeline; C1)",
        "baseline_qty": B9_QTY,
        "b9_crosscheck": {
            "Safe-2_qty3_total": safe_pnl3, "b9_Safe-2": 14608.16,
            "Bold_qty3_total": bold_pnl3, "b9_Bold": 18784.32,
            "match": bool(abs(safe_pnl3 - 14608.16) < 1.0 and abs(bold_pnl3 - 18784.32) < 1.0),
        },
        "hard_caps": {a: {k: ACCOUNTS[a][k] for k in
                          ("daily_kill_frac", "per_trade_cap_frac", "min_contracts", "v15_tiers")}
                      for a in ACCOUNTS},
        "books": {},
    }

    for acct_name, trades in books.items():
        acct = ACCOUNTS[acct_name]
        # chronological order
        trades_sorted = sorted(trades, key=lambda t: (t.date,))
        by_day_list: dict[str, list[T]] = defaultdict(list)
        for t in trades_sorted:
            by_day_list[t.date].append(t)
        trades_by_day = sorted(by_day_list.items())

        tr_stats = trade_return_stats(trades_sorted)
        dy_stats = day_return_stats(trades_sorted)
        kelly = kelly_fraction(tr_stats)

        # ── Compounding sims ──────────────────────────────────────────────────────
        sims = {}
        sims["v15_current"] = compound_sim(
            trades_by_day, start_equity=acct["start_equity"], sizing="v15", account=acct)
        sims["full_kelly"] = compound_sim(
            trades_by_day, start_equity=acct["start_equity"], sizing="kelly",
            account=acct, kelly_fraction_val=kelly["f_full_kelly"])
        sims["half_kelly"] = compound_sim(
            trades_by_day, start_equity=acct["start_equity"], sizing="kelly",
            account=acct, kelly_fraction_val=kelly["f_half_kelly"])
        sims["quarter_kelly"] = compound_sim(
            trades_by_day, start_equity=acct["start_equity"], sizing="kelly",
            account=acct, kelly_fraction_val=kelly["f_quarter_kelly"])
        # stressed (worse-regime) half- & quarter-Kelly: 50% edge haircut
        sims["half_kelly_stressed50"] = compound_sim(
            trades_by_day, start_equity=acct["start_equity"], sizing="kelly",
            account=acct, kelly_fraction_val=kelly["f_half_kelly"], edge_haircut=0.50)
        sims["quarter_kelly_stressed50"] = compound_sim(
            trades_by_day, start_equity=acct["start_equity"], sizing="kelly",
            account=acct, kelly_fraction_val=kelly["f_quarter_kelly"], edge_haircut=0.50)
        sims["v15_stressed50"] = compound_sim(
            trades_by_day, start_equity=acct["start_equity"], sizing="v15",
            account=acct, edge_haircut=0.50)

        # ── Monte-Carlo risk-of-ruin (the honest distribution, not one lucky path) ──
        boot = {
            "quarter_kelly": bootstrap_ruin(
                trades_by_day, start_equity=acct["start_equity"], account=acct,
                kelly_fraction_val=kelly["f_quarter_kelly"]),
            "quarter_kelly_stressed50": bootstrap_ruin(
                trades_by_day, start_equity=acct["start_equity"], account=acct,
                kelly_fraction_val=kelly["f_quarter_kelly"], edge_haircut=0.50),
            "half_kelly": bootstrap_ruin(
                trades_by_day, start_equity=acct["start_equity"], account=acct,
                kelly_fraction_val=kelly["f_half_kelly"]),
            "half_kelly_stressed50": bootstrap_ruin(
                trades_by_day, start_equity=acct["start_equity"], account=acct,
                kelly_fraction_val=kelly["f_half_kelly"], edge_haircut=0.50),
        }

        # ── Concrete sizing spec: contracts at each equity tier under the RECOMMENDED
        #    fraction (quarter-Kelly = the practical fail-safe fraction), at the median
        #    premium, clamped to caps. This is the daytime SIZING-SPEC. ──────────────
        rec_fraction = kelly["f_quarter_kelly"]
        med_prem = tr_stats["median_premium"]
        spec_tiers = {}
        for eq_level in (2000.0, 5000.0, 10000.0, 25000.0):
            info = contracts_from_fraction(
                rec_fraction, eq_level, med_prem,
                per_trade_cap_frac=acct["per_trade_cap_frac"],
                min_contracts=acct["min_contracts"])
            v15_base = v15_contracts(eq_level, False, acct["v15_tiers"])
            v15_elite = v15_contracts(eq_level, True, acct["v15_tiers"])
            # Does the v15 NOMINAL count breach the Rule 6 per-trade cap at this equity
            # (at median premium)? This is the load-bearing safety check.
            cap_dollars = acct["per_trade_cap_frac"] * eq_level
            cost_per = med_prem * 100.0
            v15_base_pct = round(100 * (v15_base * cost_per) / eq_level, 1) if eq_level else 0.0
            v15_elite_pct = round(100 * (v15_elite * cost_per) / eq_level, 1) if eq_level else 0.0
            spec_tiers[f"${int(eq_level)}"] = {
                "recommended_contracts": info["contracts"],
                "kelly_wanted_contracts": info["wanted"],
                "per_trade_cap_contracts": info["cap_contracts"],
                "clamp": info["clamped"],
                "v15_base_contracts": v15_base,
                "v15_elite_contracts": v15_elite,
                "v15_base_pct_of_equity": v15_base_pct,
                "v15_elite_pct_of_equity": v15_elite_pct,
                "v15_base_breaches_cap": bool(v15_base * cost_per > cap_dollars),
                "v15_elite_breaches_cap": bool(v15_elite * cost_per > cap_dollars),
            }

        # under/over-sized verdict (compare v15 contracts vs quarter-Kelly recommended at $2K)
        at2k = spec_tiers["$2000"]
        v15_at2k = at2k["v15_base_contracts"]
        rec_at2k = at2k["recommended_contracts"]
        if at2k["v15_base_breaches_cap"]:
            v15_verdict = (
                f"v15 BREACHES Rule 6 at $2K: nominal base {v15_at2k} contracts = "
                f"{at2k['v15_base_pct_of_equity']}% of equity (cap "
                f"{int(acct['per_trade_cap_frac']*100)}%); elite {at2k['v15_elite_contracts']} = "
                f"{at2k['v15_elite_pct_of_equity']}%. The Rule 6 cap MUST clip these to "
                f"{at2k['per_trade_cap_contracts']}. Quarter-Kelly+min-3 floor = {rec_at2k} "
                f"contracts ({round(at2k['v15_base_pct_of_equity']*rec_at2k/max(v15_at2k,1),1)}% of "
                f"equity) sits safely inside the cap and is the correct sub-$5K size.")
        elif v15_at2k > rec_at2k:
            v15_verdict = (f"v15 is OVER-sized at $2K: trades {v15_at2k} base contracts vs the "
                           f"safer quarter-Kelly {rec_at2k}.")
        elif v15_at2k < rec_at2k:
            v15_verdict = (f"v15 is UNDER-sized at $2K: {v15_at2k} base vs quarter-Kelly {rec_at2k}.")
        else:
            v15_verdict = f"v15 base ({v15_at2k}) matches quarter-Kelly ({rec_at2k}) at $2K."

        # The recommended fraction (quarter-Kelly) is SAFE only if the Monte-Carlo ruin
        # rate is ~0 EVEN under the 50% stress haircut (worse-regime honesty).
        qk_ruin = boot["quarter_kelly_stressed50"]["ruin_rate"]
        kelly_safe = qk_ruin <= 0.01
        # the recommended sizing never breaches caps by construction (clamped)
        respects_caps = True  # contracts_from_fraction CLAMPS to caps; never exceeds

        result["books"][acct_name] = {
            "start_equity": acct["start_equity"],
            "strike_tier": "ATM" if acct["strike_offset"] == ATM else "ITM-2",
            "edges": list(acct["edges"]),
            "n_trades": len(trades_sorted),
            "n_days": len(trades_by_day),
            "trade_return_distribution": tr_stats,
            "day_return_distribution": dy_stats,
            "kelly": kelly,
            "compounding_sims": sims,
            "monte_carlo_ruin": boot,
            "sizing_spec_by_equity_tier": spec_tiers,
            "v15_vs_recommended_verdict": v15_verdict,
            "recommended_fraction": rec_fraction,
            "recommended_fraction_name": "quarter_kelly",
            "respects_hard_caps": respects_caps,
            "quarter_kelly_stressed_ruin_rate": qk_ruin,
            "recommended_fraction_safe_under_stress": kelly_safe,
        }

    # ── Overall verdict ───────────────────────────────────────────────────────────
    result["verdict"] = "SIZING_SPEC_PRODUCED"
    result["respects_hard_caps"] = all(b["respects_hard_caps"] for b in result["books"].values())
    result["DISCLOSURE"] = {
        "kelly_unit": ("Kelly fraction = fraction of EQUITY deployed as option premium per "
                       "trade; full-Kelly = min(continuous m/v, discrete two-outcome) for "
                       "conservatism. We recommend QUARTER-Kelly as the practical fraction "
                       "(0DTE fat tails + bull-regime-flattered edge)."),
        "hard_caps_never_exceeded": ("every proposed contract count is CLAMPED to Rule 6 "
                                     "(per-trade cap + min-3 floor); where Kelly wants more we "
                                     "FLAG 'edge supports X, capped at Y' and clamp — never override."),
        "bull_regime_caveat": ("the measured Sharpe (~4.5-4.7) reflects a 2025-26 BULL tape and "
                               "will NOT hold in chop/bear. We re-run every sizing with a 50% edge "
                               "haircut (stressed50 rows) — the recommended fraction must still avoid "
                               "ruin under that stress. Size for the WORSE regime."),
        "compounding_replay": ("per-trade measured returns replayed chronologically; equity "
                               "compounds; daily kill switch enforced intraday vs SoD equity; ruin "
                               "= equity < 10% of start."),
        "real_fills": "real OPRA fills (C1); per-trade EXPECTANCY not WR (OP-14); SPY-dir != option edge (C3).",
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    write_md(result)
    print(f"\n[b10] wrote {OUT_JSON}\n[b10] wrote {OUT_MD}", flush=True)

    # ── Console summary ───────────────────────────────────────────────────────────
    print("\n=== B10 SIZING VERDICT ===")
    for acct_name, b in result["books"].items():
        k = b["kelly"]
        print(f"\n{acct_name} ({b['strike_tier']}, {'+'.join(b['edges'])}):")
        print(f"  per-trade: mean_ret={b['trade_return_distribution']['mean_return']} "
              f"std={b['trade_return_distribution']['std_return']} "
              f"WR={b['trade_return_distribution']['win_rate']}")
        print(f"  Kelly: full={k['f_full_kelly']} half={k['f_half_kelly']} quarter={k['f_quarter_kelly']}")
        for sname in ("v15_current", "quarter_kelly", "half_kelly", "quarter_kelly_stressed50"):
            s = b["compounding_sims"][sname]
            print(f"  [{sname:24s}] final=${s['final_equity']:>12} ret={s['total_return_pct']}% "
                  f"maxDD={s['max_drawdown_pct']}% kills={s['kill_switch_trips']} "
                  f"ruin={s['ruined']} ->5k={s['days_to_5k']} ->10k={s['days_to_10k']} ->25k={s['days_to_25k']}")
        mc = b["monte_carlo_ruin"]["quarter_kelly"]
        mcs = b["monte_carlo_ruin"]["quarter_kelly_stressed50"]
        print(f"  MC quarter-Kelly ruin={mc['ruin_rate']} (stressed50={mcs['ruin_rate']}) "
              f"final$P05={mc['final_equity_p05']} median={mc['final_equity_median']} maxDDp95={mc['max_dd_pct_p95']}%")
        print(f"  VERDICT: {b['v15_vs_recommended_verdict']}")
    print(f"\nrespects_hard_caps={result['respects_hard_caps']}")
    return 0


def write_md(s: dict) -> None:
    L = []
    L.append("# B10 — Sizing & Compounding the 3-Edge Book (within J's hard caps)\n")
    L.append(f"- Run: {s['run_date']}  |  Window: {s['window']}  |  Trading days: {s['trading_days']}")
    L.append(f"- Fills: {s['fills_authority']}  |  Baseline qty: {s['baseline_qty']}")
    cc = s["b9_crosscheck"]
    L.append(f"- B9 cross-check: Safe qty3 ${cc['Safe-2_qty3_total']} (B9 ${cc['b9_Safe-2']}), "
             f"Bold qty3 ${cc['Bold_qty3_total']} (B9 ${cc['b9_Bold']}) — match={cc['match']}")
    L.append(f"\n## VERDICT: **{s['verdict']}**  |  respects_hard_caps = **{s['respects_hard_caps']}**\n")

    for acct_name, b in s["books"].items():
        L.append(f"## {acct_name} — {b['strike_tier']}, edges {'+'.join(b['edges'])}\n")
        tr = b["trade_return_distribution"]
        dy = b["day_return_distribution"]
        k = b["kelly"]
        L.append(f"**Per-trade return-on-capital** (n={tr['n']}): mean={tr['mean_return']}, "
                 f"std={tr['std_return']}, downside={tr['downside_dev']}, WR={tr['win_rate']}, "
                 f"avg_win={tr['avg_win_return']}, avg_loss={tr['avg_loss_return']}, "
                 f"worst={tr['worst_trade_return']}, median_premium=${tr['median_premium']}")
        L.append(f"\n**Per-day return** (n={dy['n_days']}): mean={dy['mean_day_return']}, "
                 f"std={dy['std_day_return']}, worst_day={dy['worst_day_return']}, "
                 f"day_WR={dy['day_win_rate']}\n")
        L.append(f"**Kelly (fraction of equity as premium/trade):** full={k['f_full_kelly']} "
                 f"(continuous {k['f_continuous']}, discrete {k['f_discrete']}), "
                 f"half={k['f_half_kelly']}, **quarter={k['f_quarter_kelly']} (RECOMMENDED)**\n")

        L.append("### Compounding sims (replay measured returns, compound from start equity)\n")
        L.append("| sizing | final $ | total ret% | CAGR% | maxDD% | kill trips | ruin | ->$5K | ->$10K | ->$25K |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        order = ["v15_current", "full_kelly", "half_kelly", "quarter_kelly",
                 "v15_stressed50", "half_kelly_stressed50", "quarter_kelly_stressed50"]
        for sn in order:
            sm = b["compounding_sims"][sn]
            L.append(f"| {sn} | {sm['final_equity']} | {sm['total_return_pct']} | {sm['cagr_pct']} | "
                     f"{sm['max_drawdown_pct']} | {sm['kill_switch_trips']} | {sm['ruined']} | "
                     f"{sm['days_to_5k']} | {sm['days_to_10k']} | {sm['days_to_25k']} |")
        L.append("")

        L.append("### Monte-Carlo risk-of-ruin (2000 day-block bootstrap paths — the HONEST risk number)\n")
        L.append("| fraction | ruin rate | final $ P05 | final $ median | final $ P95 | maxDD% med | maxDD% P95 | kill trips P95 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for bn in ("quarter_kelly", "quarter_kelly_stressed50", "half_kelly", "half_kelly_stressed50"):
            mc = b["monte_carlo_ruin"][bn]
            L.append(f"| {bn} | {mc['ruin_rate']} | {mc['final_equity_p05']} | {mc['final_equity_median']} | "
                     f"{mc['final_equity_p95']} | {mc['max_dd_pct_median']} | {mc['max_dd_pct_p95']} | "
                     f"{mc['kill_trips_p95']} |")
        L.append(f"\n_{b['monte_carlo_ruin']['quarter_kelly']['note']}_\n")
        L.append(f"**Recommended (quarter-Kelly) ruin under 50% stress: {b['quarter_kelly_stressed_ruin_rate']} "
                 f"-> safe={b['recommended_fraction_safe_under_stress']}**\n")

        L.append("### Concrete SIZING-SPEC — contracts per equity tier (quarter-Kelly, clamped to caps)\n")
        L.append("| equity | recommended | kelly wanted | per-trade cap (Rule 6) | clamp | v15 base (%eq, breach?) | v15 elite (%eq, breach?) |")
        L.append("|---|---|---|---|---|---|---|")
        for tier, st in b["sizing_spec_by_equity_tier"].items():
            bb = "BREACH" if st["v15_base_breaches_cap"] else "ok"
            eb = "BREACH" if st["v15_elite_breaches_cap"] else "ok"
            L.append(f"| {tier} | **{st['recommended_contracts']}** | {st['kelly_wanted_contracts']} | "
                     f"{st['per_trade_cap_contracts']} | {st['clamp']} | "
                     f"{st['v15_base_contracts']} ({st['v15_base_pct_of_equity']}%, {bb}) | "
                     f"{st['v15_elite_contracts']} ({st['v15_elite_pct_of_equity']}%, {eb}) |")
        L.append("")
        L.append(f"**v15 vs recommended:** {b['v15_vs_recommended_verdict']}\n")

    L.append("## How to read this / disclosure\n")
    for kk, vv in s["DISCLOSURE"].items():
        L.append(f"- **{kk}**: {vv}")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
