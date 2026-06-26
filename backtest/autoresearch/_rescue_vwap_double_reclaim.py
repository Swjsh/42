"""RESCUE / STRUCTURAL-MIMIC edge test: struct_vwap_double_reclaim.

THESIS (extends the winning SHAPE — C4/L122/L154/L166):
  The hunt found a real STRUCTURAL edge — struct_vwap_reclaim_failed_break: trend
  side -> ONE failed counter-trend VWAP break -> with-trend VWAP reclaim <=10:30 ET
  (8/8 gates @ ITM-2, but FAILS @ OTM-2 on the random-null — C29 OTM theta/delta
  eats the alpha). The winning SHAPE = a failed counter-trend move that reclaims
  with-trend.

  This NEW primitive asks: is a STRONGER version of that shape — TWO failed
  counter-trend VWAP pokes, entry on the 2nd reclaim — a better-confirmed
  failed-counter-move that survives at a $2K-tradeable OTM strike? The hypothesis
  is that requiring two failed pokes is a higher bar of "the counter-move keeps
  failing" -> a cleaner with-trend continuation, possibly with enough edge to clear
  the random-null even after OTM theta drag.

THE DETECTOR — "double failed counter-trend move" (one entry/day):
  1. Morning trend side (IDENTICAL to vwap_continuation / failed_break, no drift):
     the first TREND_BARS (3) RTH closes all on the SAME side of as-of session VWAP
     -> that is the day's WITH-TREND side (closes>VWAP -> CALL; closes<VWAP -> PUT).
  2. POKE #1: after the trend bars, a bar CLOSES on the WRONG side of VWAP (counter-
     trend break begins) ... then a later bar CLOSES BACK with-trend (reclaim #1).
     That first reclaim is NOT the entry — it only proves the counter-move failed
     once. Track the excursion extreme of poke #1.
  3. POKE #2: after reclaim #1, price must break VWAP AGAINST the trend AGAIN
     (another counter-trend close on the wrong side), then CLOSE BACK with-trend a
     second time (reclaim #2) BEFORE ENTRY_CUTOFF. THAT 2nd reclaim bar is the
     entry (one causal entry/day, side = the morning trend side). Fill = NEXT bar
     open (sim handles it). No look-ahead: every read (VWAP as-of, trend, both
     pokes, both reclaims) uses only bars[0..j].
  Chart stop = the DEEPER of the two failed-poke excursion extremes (for a CALL:
  the lowest LOW printed across BOTH failed breaks = the level that must hold; for
  a PUT: the highest HIGH). If price takes out the deepest failed-break extreme,
  the "counter-move keeps failing" read was wrong -> structural invalidation.

  DISTINCT from struct_vwap_reclaim_failed_break (which enters on the FIRST reclaim
  after a SINGLE failed break) and from vwap_continuation (no counter-trend cross
  required). This requires TWO completed+failed counter-trend pokes.

REAL FILLS (C1): lib.simulator_real.simulate_trade_real on real OPRA bars
  (nearest-cached strike snap <=4, causal next-bar-open entry, chart-stop via
  rejection_level). Report strike_offset=+2 (OTM-2 = Safe-2's $2K tier) PRIMARY,
  +1 (OTM-1), 0 (ATM) — all $2K-tradeable tiers — and -2 (ITM-2) as the reference
  against the parent edge. Per C29 (gates do not transfer across strike tiers);
  ALL gates reported for EVERY tier (anti-cherry-pick 2.10). A Safe-2-tradeable
  winner must clear ALL 8 gates at OTM-2/OTM-1/ATM, not just ITM-2.

ALL 8 GATES MANDATORY (anti-cherry-pick 2.10; reported for EVERY strike tier):
  G1 OOS(2026) per-trade > 0
  G2 positive_quarters >= 4/6
  G3 top5_day_pct < 200
  G4 n_trades >= 20
  G5 drop-top5-day per-trade > 0          (concentration robustness)
  G6 IS(2025) FIRST-HALF per-trade > 0    (in-sample stability, not just full IS)
  G7 beats random-entry null (L172: ~20 seeds) -- STANDARD coin-flip null
     (autoresearch.null_baseline) AND a same-day/same-side null (the harder
     control): the SIGNAL must beat the null, not the bracket.
  G8 no-truncation (L171): per-trade SIGN holds from -8% stop -> chart-stop-only
     (-0.99). Sign inversion = pure stop-truncation of a SPY-price tilt
     (truncation_guard).

Pure Python, $0 (no LLM, no live orders). Markets closed.
Writes analysis/recommendations/rescue-vwap_double_reclaim.json.

Run: backtest/.venv/Scripts/python.exe \
       backtest/autoresearch/_rescue_vwap_double_reclaim.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    session_vwap_asof,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
    DayCtx,
)
# Reuse the edgehunt data normalizers so the bar series is byte-for-byte identical.
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    TREND_BARS,
    ENTRY_CUTOFF,
    MAX_STRIKE_STEPS,
    QTY,
    OOS_YEAR,
)
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.truncation_guard import is_truncation_artifact  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "rescue-vwap_double_reclaim.json"

# ── Config ──────────────────────────────────────────────────────────────────
# $2K-tradeable tiers FIRST (the rescue target), ITM-2 reference last.
TIER_OFFSETS = [
    (+2, "OTM2_safe2"),    # OTM-2 = Safe-2's actual $2K tier  -- PRIMARY (rescue target)
    (+1, "OTM1_safe2"),    # OTM-1 = also $2K-tradeable
    (0, "ATM_safe2"),      # ATM   = also $2K-tradeable
    (-2, "ITM2_ref"),      # ITM-2 = reference vs the parent failed_break edge
]
PRIMARY_TIER_LABEL = "OTM2_safe2"
SURV_PREMIUM_STOP = -0.08      # -8% premium stop
CHART_STOP_ONLY = -0.99        # for the no-truncation fraud gate (G8)

N_NULL_SEEDS = 20              # L172
RTH_OPEN = dt.time(9, 30)


# ─────────────────────────────────────────────────────────────────────────────
# DETECTOR — VWAP DOUBLE-reclaim (two failed counter-trend pokes, one entry/day)
# ─────────────────────────────────────────────────────────────────────────────
def _trend_side(closes, vwap, n) -> Optional[str]:
    """Day's with-trend side: first n RTH closes all same side of as-of VWAP.

    Identical to the validated vwap_continuation/failed_break trend definition."""
    head_c = closes[:n]
    head_v = vwap[:n]
    if len(head_c) < n:
        return None
    if np.all(head_c > head_v):
        return "C"
    if np.all(head_c < head_v):
        return "P"
    return None


def detect_signals(days: list[DayCtx]) -> list[Signal]:
    """One causal struct_vwap_double_reclaim entry/day.

    State machine (all reads causal, bars[0..j] only):
      trend side (TREND_BARS)
        -> POKE1 break (close wrong side) -> RECLAIM1 (close back with-trend)
        -> POKE2 break (close wrong side again) -> RECLAIM2 (close back) = ENTRY,
      all BEFORE ENTRY_CUTOFF.
    Stop = the DEEPER of the two failed-poke excursion extremes (structural
    invalidation: the level that has now held twice).
    """
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        # Need the trend bars + room for break/reclaim/break/reclaim (>=4 more bars).
        if len(rth) < TREND_BARS + 4:
            continue
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        side = _trend_side(closes, vwap, TREND_BARS)
        if side is None:
            continue

        # phase: 0 = awaiting POKE1 break, 1 = in POKE1 (awaiting reclaim1),
        #        2 = awaiting POKE2 break, 3 = in POKE2 (awaiting reclaim2=entry)
        phase = 0
        # Deepest counter-trend excursion across BOTH failed pokes (the chart stop).
        # CALL -> deepest LOW; PUT -> highest HIGH.
        stop_ext: Optional[float] = None
        for j in range(TREND_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            v = vwap[j]
            if v <= 0:
                continue
            c = closes[j]
            if side == "C":
                wrong_side = c < v          # counter-trend (bearish) close
                with_trend = c > v          # reclaim (bullish) close
                if phase == 0:
                    if wrong_side:          # POKE1 break opens
                        phase = 1
                        stop_ext = lows[j]
                    continue
                if phase == 1:
                    stop_ext = min(stop_ext, lows[j]) if stop_ext is not None else lows[j]
                    if with_trend:          # RECLAIM1 -> failed once; arm for POKE2
                        phase = 2
                    continue
                if phase == 2:
                    if wrong_side:          # POKE2 break opens
                        phase = 3
                        stop_ext = min(stop_ext, lows[j]) if stop_ext is not None else lows[j]
                    continue
                if phase == 3:
                    stop_ext = min(stop_ext, lows[j]) if stop_ext is not None else lows[j]
                    if with_trend:          # RECLAIM2 -> ENTRY (the 2nd reclaim)
                        out.append(Signal(bar_idx=int(idxs[j]), side="C",
                                          stop_level=float(stop_ext),
                                          note="struct_vwap_double_reclaim"))
                        break
            else:  # PUT / bearish trend
                wrong_side = c > v          # counter-trend (bullish) close
                with_trend = c < v          # reclaim (bearish) close
                if phase == 0:
                    if wrong_side:          # POKE1 break opens
                        phase = 1
                        stop_ext = highs[j]
                    continue
                if phase == 1:
                    stop_ext = max(stop_ext, highs[j]) if stop_ext is not None else highs[j]
                    if with_trend:          # RECLAIM1 -> arm for POKE2
                        phase = 2
                    continue
                if phase == 2:
                    if wrong_side:          # POKE2 break opens
                        phase = 3
                        stop_ext = max(stop_ext, highs[j]) if stop_ext is not None else highs[j]
                    continue
                if phase == 3:
                    stop_ext = max(stop_ext, highs[j]) if stop_ext is not None else highs[j]
                    if with_trend:          # RECLAIM2 -> ENTRY
                        out.append(Signal(bar_idx=int(idxs[j]), side="P",
                                          stop_level=float(stop_ext),
                                          note="struct_vwap_double_reclaim"))
                        break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIM one signal set on real OPRA fills (v15 default exits)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    pct: float
    exit_reason: str


def simulate_set(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct
                 ) -> tuple[list[TradeRow], dict]:
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup="STRUCT_VWAP_DOUBLE_RECLAIM", strike_override=strike,
            entry_vix=entry_vix, premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(d), side=sg.side,
            pnl=round(float(fill.dollar_pnl), 2),
            pct=round(float(fill.pct_return_on_premium), 5),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
        ))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# METRICS (OP-20 disclosure)
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _by_day_top5_pct(rows: list[TradeRow]) -> Optional[float]:
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _drop_topN_day_per_trade(rows: list[TradeRow], k: int = 5) -> Optional[float]:
    """Per-trade mean after removing the k highest-P&L DAYS entirely."""
    if not rows:
        return None
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.pnl)
    day_tot = {d: sum(v) for d, v in by_day.items()}
    drop_days = set(sorted(day_tot, key=day_tot.get, reverse=True)[:k])
    kept = [r.pnl for r in rows if r.date not in drop_days]
    return round(float(np.mean(kept)), 2) if kept else None


def _max_drawdown_dollar(rows: list[TradeRow]) -> Optional[float]:
    """Peak-to-trough drawdown of the chronological cumulative-P&L curve (<=0)."""
    if not rows:
        return None
    ordered = sorted(rows, key=lambda r: r.date)
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for r in ordered:
        cum += r.pnl
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return round(float(mdd), 2)


def metrics(rows: list[TradeRow]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    # IS FIRST-HALF (G6): split IS (2025) rows chronologically in half, require the
    # first half to be per-trade positive (stricter in-sample stability — L166).
    is_sorted = sorted(is_rows, key=lambda r: r.date)
    half = len(is_sorted) // 2
    is_first_half = is_sorted[:half] if half else []

    def _exp(rs):
        return round(float(np.mean([r.pnl for r in rs])), 2) if rs else 0.0

    def _tot(rs):
        return round(float(np.sum([r.pnl for r in rs])), 2) if rs else 0.0

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    by_side = {}
    for sd in ("C", "P"):
        s = [r.pnl for r in rows if r.side == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                           "total": round(sum(s), 2)}

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "max_drawdown_dollar": _max_drawdown_dollar(rows),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "is_first_half_n": len(is_first_half), "is_first_half_exp": _exp(is_first_half),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _by_day_top5_pct(rows),
        "drop_top5_day_per_trade": _drop_topN_day_per_trade(rows, 5),
        "by_side": by_side,
        "exit_hist": {k: int(v) for k, v in sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())},
    }


# ─────────────────────────────────────────────────────────────────────────────
# G7 — same-day/same-side random null (the HARD control: isolates trigger TIMING
# from day+side selection). Pick a RANDOM eligible morning bar on the same day,
# same side, same stop geometry, simulate. Reported alongside the STANDARD
# coin-flip null (null_baseline) which randomizes the entry bar across all RTH.
# ─────────────────────────────────────────────────────────────────────────────
def sameday_null(signals, spy, ribbon, vix, days, *, seeds, strike_offset,
                 premium_stop_pct) -> dict:
    day_bars: dict[dt.date, list[int]] = {}
    for dc in days:
        rth = dc.rth
        times = rth["t"].values
        idxs = rth.index.tolist()
        elig = [int(idxs[j]) for j in range(TREND_BARS, len(rth)) if times[j] <= ENTRY_CUTOFF]
        if elig:
            day_bars[dc.date] = elig
    sig_specs = []
    for sg in signals:
        d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
        sig_specs.append((d, sg.side, sg.stop_level))
    per_seed_exp, per_seed_oos_exp = [], []
    for seed in range(seeds):
        rng = np.random.default_rng(7000 + seed)
        rand_sigs = []
        for d, sd, stop in sig_specs:
            elig = day_bars.get(d)
            if not elig:
                continue
            bidx = int(rng.choice(elig))
            rand_sigs.append(Signal(bar_idx=bidx, side=sd, stop_level=stop, note="rand"))
        rows, _ = simulate_set(rand_sigs, spy, ribbon, vix, strike_offset=strike_offset,
                               premium_stop_pct=premium_stop_pct)
        if rows:
            m = metrics(rows)
            per_seed_exp.append(m["exp_dollar"])
            per_seed_oos_exp.append(m["oos_exp"])
    if not per_seed_exp:
        return {"seeds": 0}
    return {
        "seeds": len(per_seed_exp),
        "null_exp_mean": round(float(np.mean(per_seed_exp)), 2),
        "null_exp_min": round(float(np.min(per_seed_exp)), 2),
        "null_exp_max": round(float(np.max(per_seed_exp)), 2),
        "null_exp_std": round(float(np.std(per_seed_exp)), 2),
        "null_oos_exp_mean": round(float(np.mean(per_seed_oos_exp)), 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Evaluate one strike tier: all 8 gates
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_tier(signals, spy, ribbon, vix, days, *, strike_offset, tier_label) -> dict:
    rows, cov = simulate_set(signals, spy, ribbon, vix, strike_offset=strike_offset,
                             premium_stop_pct=SURV_PREMIUM_STOP)
    m = metrics(rows)
    strike_tier_name = (f"ITM{abs(strike_offset)}" if strike_offset < 0
                        else ("ATM" if strike_offset == 0 else f"OTM{strike_offset}"))
    if not m.get("n"):
        return {"tier": tier_label, "strike_offset": strike_offset,
                "strike_tier_name": strike_tier_name, "coverage": cov,
                "metrics": m, "gates": {}, "clears_all_gates": False,
                "n_gates_passed": 0, "caveats": [], "note": "no filled trades"}

    # G8 no-truncation: same signals at chart-stop-only
    cs_rows, _ = simulate_set(signals, spy, ribbon, vix, strike_offset=strike_offset,
                              premium_stop_pct=CHART_STOP_ONLY)
    cs_m = metrics(cs_rows)
    trunc_artifact = is_truncation_artifact(
        best_per_trade=m["exp_dollar"],
        chart_stop_only_per_trade=cs_m.get("exp_dollar"),
        best_premium_stop_pct=SURV_PREMIUM_STOP,
    )
    sign_stable_full = bool(cs_m.get("n") and (m["exp_dollar"] > 0) == (cs_m["exp_dollar"] > 0))
    sign_stable_oos = bool(cs_m.get("oos_n") and (m.get("oos_exp", 0) > 0) == (cs_m.get("oos_exp", 0) > 0))
    truncation_safe = bool((not trunc_artifact) and sign_stable_full and sign_stable_oos)

    # G7 nulls
    rth_all = pd.concat([dc.rth for dc in days]).sort_index().reset_index(drop=True)
    n_call = sum(1 for s in signals if s.side == "C")
    n_put = sum(1 for s in signals if s.side == "P")
    coin = random_entry_null(
        rth_all, n_signals=len(signals), n_call=n_call, n_put=n_put,
        strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP, seeds=N_NULL_SEEDS)
    coin_g = null_gate(m["exp_dollar"], m.get("drop_top5_day_per_trade"), coin)
    sameday = sameday_null(signals, spy, ribbon, vix, days, seeds=N_NULL_SEEDS,
                           strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP)
    beats_sameday = bool(
        sameday.get("seeds") and
        m["exp_dollar"] > sameday["null_exp_mean"] + sameday.get("null_exp_std", 0.0))
    oos_beats_sameday = bool(
        sameday.get("seeds") and (m.get("oos_exp", 0) or 0) > sameday.get("null_oos_exp_mean", 9e9))
    beats_null = bool(coin_g["null_pass"] and beats_sameday)

    gates = {
        "G1_oos_per_trade_positive": {"pass": bool(m.get("oos_exp", -1) > 0),
                                      "value": m.get("oos_exp"), "oos_n": m.get("oos_n")},
        "G2_positive_quarters_ge_4": {"pass": bool(m.get("positive_quarters_n", 0) >= 4),
                                      "value": m.get("positive_quarters")},
        "G3_top5_day_pct_lt_200": {"pass": bool(m.get("top5_day_pct") is not None
                                                and m["top5_day_pct"] < 200.0),
                                   "value": m.get("top5_day_pct")},
        "G4_n_ge_20": {"pass": bool(m.get("n", 0) >= 20), "value": m.get("n")},
        "G5_drop_top5_per_trade_positive": {"pass": bool(m.get("drop_top5_day_per_trade") is not None
                                                         and m["drop_top5_day_per_trade"] > 0),
                                            "value": m.get("drop_top5_day_per_trade")},
        "G6_is_first_half_positive": {"pass": bool(m.get("is_first_half_exp", -1) > 0
                                                   and m.get("is_first_half_n", 0) > 0),
                                      "value": m.get("is_first_half_exp"),
                                      "is_first_half_n": m.get("is_first_half_n")},
        "G7_beats_random_null": {
            "pass": beats_null,
            "coinflip_null": {**coin, **coin_g},
            "sameday_null": {**sameday, "beats_sameday_mean_plus_std": beats_sameday,
                             "oos_beats_sameday_mean": oos_beats_sameday},
        },
        "G8_no_truncation": {
            "pass": truncation_safe,
            "stop8_exp": m["exp_dollar"], "chartstop_exp": cs_m.get("exp_dollar"),
            "stop8_oos_exp": m.get("oos_exp"), "chartstop_oos_exp": cs_m.get("oos_exp"),
            "stop8_total": m["total_dollar"], "chartstop_total": cs_m.get("total_dollar"),
            "is_truncation_artifact": trunc_artifact,
            "sign_stable_full": sign_stable_full, "sign_stable_oos": sign_stable_oos,
        },
    }
    clears_all = all(g["pass"] for g in gates.values())
    caveats = []
    if clears_all and not oos_beats_sameday:
        caveats.append("oos_lift_within_sameday_null_band: OOS per-trade is below the same-day "
                       "random-entry null OOS mean -> the OOS edge is largely day+side selection, "
                       "not trigger precision (the trigger DOES beat the full-sample null and the "
                       "coin-flip null; full-sample clears every gate).")
    return {
        "tier": tier_label,
        "strike_offset": strike_offset,
        "strike_tier_name": strike_tier_name,
        "coverage": cov,
        "metrics": m,
        "gates": gates,
        "clears_all_gates": clears_all,
        "n_gates_passed": sum(1 for g in gates.values() if g["pass"]),
        "caveats": caveats,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[rescue-vwap-double-reclaim] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[rescue] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    signals = detect_signals(days)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[rescue] struct_vwap_double_reclaim signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    tiers = {}
    for off, lbl in TIER_OFFSETS:
        blk = evaluate_tier(signals, spy, ribbon, vix, days,
                            strike_offset=off, tier_label=lbl)
        tiers[lbl] = blk
        m = blk.get("metrics", {})
        print(f"\n[{lbl} off={off:+d} {blk.get('strike_tier_name')}] "
              f"n={m.get('n')} exp=${m.get('exp_dollar')} oos_exp=${m.get('oos_exp')} "
              f"(oos_n={m.get('oos_n')}) posQ={m.get('positive_quarters')} "
              f"top5%={m.get('top5_day_pct')} droptop5=${m.get('drop_top5_day_per_trade')} "
              f"isH1=${m.get('is_first_half_exp')} maxDD=${m.get('max_drawdown_dollar')}",
              flush=True)
        for gname, g in blk.get("gates", {}).items():
            print(f"    {gname}: {'PASS' if g['pass'] else 'FAIL'} "
                  f"(value={g.get('value', '-')})", flush=True)
        print(f"    => clears_all_gates={blk.get('clears_all_gates')} "
              f"({blk.get('n_gates_passed')}/8)", flush=True)

    # PRIMARY = the rescue target (OTM-2, Safe-2's $2K tier).
    primary = tiers[PRIMARY_TIER_LABEL]
    pm = primary.get("metrics", {})
    pg = primary.get("gates", {})

    # Find the best $2K-tradeable tier that clears all 8 gates (OTM-2/OTM-1/ATM).
    safe2_tier_order = ["OTM2_safe2", "OTM1_safe2", "ATM_safe2"]
    best_tradeable = None
    for lbl in safe2_tier_order:
        if tiers.get(lbl, {}).get("clears_all_gates"):
            best_tradeable = lbl
            break
    safe2_tradeable = best_tradeable is not None
    # Report best tradeable strike string (per task): the tier name if one clears.
    if best_tradeable:
        best_tradeable_strike = tiers[best_tradeable]["strike_tier_name"]
        best_config = best_tradeable
    else:
        best_tradeable_strike = "NONE (no $2K-tradeable tier clears all 8 gates)"
        best_config = PRIMARY_TIER_LABEL

    # Schema-shaped fields for the StructuredOutput return (primary = OTM-2 rescue target)
    beats_null = bool(pg.get("G7_beats_random_null", {}).get("pass"))
    truncation_safe = bool(pg.get("G8_no_truncation", {}).get("pass"))
    is_half_positive = bool(pg.get("G6_is_first_half_positive", {}).get("pass"))
    clears_all_primary = bool(primary.get("clears_all_gates"))

    if safe2_tradeable:
        bt = tiers[best_tradeable]
        verdict = (f"PROMOTABLE @ {bt['strike_tier_name']} ({best_tradeable}) — "
                   f"clears all 8 gates on a $2K-tradeable strike "
                   f"(oos_exp=${bt['metrics'].get('oos_exp')}/tr, n={bt['metrics'].get('n')})")
        if bt.get("caveats"):
            verdict += " [CAVEAT: OOS lift sits inside the same-day null band -> day+side selection]"
    else:
        # Honest negative: which gate(s) the primary $2K tier failed.
        failed = [g for g, v in pg.items() if not v["pass"]]
        verdict = (f"REJECTED for Safe-2 — no $2K-tradeable tier (OTM-2/OTM-1/ATM) clears all 8 "
                   f"gates. Primary OTM-2 failed: {', '.join(failed) if failed else '(no fills)'}. "
                   f"The double-reclaim shape does not survive OTM theta/delta drag (C29) on the "
                   f"random-null at a Safe-2 strike.")

    summary = {
        "hypothesis": ("struct_vwap_double_reclaim: morning-trend side -> TWO failed counter-trend "
                       "VWAP pokes -> entry on the 2nd with-trend reclaim <=10:30 ET (a stronger "
                       "'failed-counter-move' confirmation than the single-reclaim parent edge). "
                       "STRUCTURAL-mimic of vwap_continuation in the winning mold; one causal "
                       "entry/day, chart stop = deeper of the two failed-poke extremes. RESCUE "
                       "target = a $2K-tradeable OTM strike (OTM-2/OTM-1/ATM), not just ITM-2."),
        "kind": "structural_one_entry_per_day",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "opra_fill_cutoff": "2026-05-29 (signals after drop as cache_miss; OOS fills = Jan..May 2026)",
        "detector": ("clean causal one-entry/day: trend side (first 3 RTH closes same side of "
                     "as-of session VWAP) -> POKE1 counter-trend break (close wrong side) -> "
                     "RECLAIM1 (close back with-trend) -> POKE2 break -> RECLAIM2 (close back) = "
                     "entry, all <=10:30 ET; fill=next bar open; chart stop = deeper of the two "
                     "failed-poke excursion extremes. DISTINCT from single-reclaim failed_break "
                     "(this needs TWO failed pokes) and from vwap_continuation (no counter cross)."),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "config": {"premium_stop_pct": SURV_PREMIUM_STOP, "qty": QTY,
                   "exits": "v15 default (tp1=0.30, runner=2.5x, profit_lock=OFF)",
                   "primary_tier": PRIMARY_TIER_LABEL,
                   "tiers_tested": [lbl for _, lbl in TIER_OFFSETS]},
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "eight_gates": {
            "G1": "OOS(2026) per-trade > 0",
            "G2": "positive_quarters >= 4/6",
            "G3": "top5_day_pct < 200",
            "G4": "n_trades >= 20",
            "G5": "drop-top5-day per-trade > 0",
            "G6": "IS(2025) first-half per-trade > 0",
            "G7": "beats random-entry null (coin-flip null_pass AND same-day mean+std, ~20 seeds)",
            "G8": "no-truncation: sign holds -8% -> chart-stop-only (-0.99)",
        },
        "tiers": tiers,
        "PRIMARY_TIER": PRIMARY_TIER_LABEL,
        "best_tradeable_tier": best_tradeable,
        "best_tradeable_strike": best_tradeable_strike,
        "safe2_tradeable": safe2_tradeable,
        "verdict": verdict,
        "DISCLOSURE": {
            "no_cherry_pick": ("ALL 8 gates reported for EVERY strike tier (OTM-2 primary + OTM-1 + "
                               "ATM + ITM-2 reference); a tier that fails any gate is marked "
                               "clears_all_gates=false (anti-pattern 2.10)."),
            "structural_not_additive": ("ONE causal entry/day with a structural chart stop; no "
                                        "stacked confirmations — the SECOND reclaim is a stronger "
                                        "failed-counter-move shape, not additive confluence."),
            "strike_tier_caveat": ("C29 — gates do not transfer across strike tiers; the rescue bar "
                                   "is clearing ALL 8 gates at a $2K-tradeable OTM strike, not ITM-2."),
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58).",
            "fraud_gates": ("G7 random-entry null (coin-flip + same-day/same-side, 20 seeds) + "
                            "G8 no-truncation (sign must hold -8% -> chart-stop-only)."),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[rescue] wrote {OUT}", flush=True)

    print("\n=== STRUCT_VWAP_DOUBLE_RECLAIM VERDICT ===")
    print(f"n_signals={len(signals)}  fired {summary['signal_fire_day_pct']}% of {n_days} days")
    print(f"PRIMARY OTM-2: n={pm.get('n')} exp=${pm.get('exp_dollar')} oos_exp=${pm.get('oos_exp')} "
          f"posQ={pm.get('positive_quarters')} top5%={pm.get('top5_day_pct')} "
          f"maxDD=${pm.get('max_drawdown_dollar')}")
    print(f"safe2_tradeable={safe2_tradeable}  best_tradeable_strike={best_tradeable_strike}")
    print(f"clears_all(OTM-2)={clears_all_primary}  beats_null={beats_null}  "
          f"truncation_safe={truncation_safe}  is_half_positive={is_half_positive}")
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
