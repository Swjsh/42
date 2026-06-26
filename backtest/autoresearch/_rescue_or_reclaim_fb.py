"""RESCUE / STRUCTURAL-GENERALIZE: or_reclaim_fb — opening-range FAILED-BREAK reclaim.

HYPOTHESIS (J, 2026-06-21): GENERALIZE the proven winning SHAPE — a FAILED
counter-trend break that RECLAIMS with-trend (struct_vwap_reclaim_failed_break,
8/8 gates @ ITM-2) — from the VWAP primitive to the OPENING-RANGE primitive.

    Day's WITH-TREND side is fixed FIRST (identical to the validated
    vwap_continuation / struct_vwap_reclaim definition: the first TREND_BARS (3)
    RTH closes are all on the SAME side of the as-of session VWAP). Then:
      1. Build the OPENING RANGE (OR) over the first OR_BARS RTH bars (15-min = 3
         x 5m bars, 30-min = 6 x 5m bars). OR is FROZEN once those bars close.
      2. COUNTER-TREND OR BREAK: a later bar (<= ENTRY_CUTOFF) CLOSES beyond the OR
         edge AGAINST the morning trend (bullish trend -> close below OR-low;
         bearish trend -> close above OR-high). The "failed counter-trend move."
      3. FAILS + RECLAIMS WITH-TREND: a still-later bar (<= ENTRY_CUTOFF) CLOSES
         back through that broken edge in the ORIGINAL trend direction -> the
         counter-trend break failed and price reclaimed the OR with-trend. THAT
         reclaim bar is the ONE causal entry (side = the morning trend side).
    Chart stop = the counter-trend excursion extreme (for a CALL: the LOW printed
    during the failed downside break = the level that must hold; for a PUT: the
    HIGH printed during the failed upside break). Structural invalidation of the
    "failed counter-trend move" thesis.

WHY THIS, NOT MORE CONFLUENCE (the campaign's thesis — C4/L122/L154/L166):
  * ADDITIVE confluence is DEAD on 0DTE (theta-trap / single-regime / over-
    constraint). The two real edges the campaign produced were SUBTRACTIVE (skip
    the worst VIX tercile) and STRUCTURAL (one causal with-trend entry/day). The
    failed-break-reclaim SHAPE is the structural winner; this RESCUE asks whether
    that SHAPE generalizes to a DIFFERENT structural primitive (the OR edge instead
    of VWAP), and CRITICALLY whether it survives at the OTM-2 strike tier Safe-2's
    $2K account actually trades (the VWAP version FAILED @ OTM-2 — C29).

DISTINCT FROM the two prior ORB studies (no duplication):
  * vs _edgehunt_vwap_continuation / _sub_struct_vwap_reclaim_failed_break: same
    SHAPE, DIFFERENT structural primitive (OR edge vs session VWAP).
  * vs _sub_struct_orb_reclaim: that detector defines the trade side PURELY by the
    reclaim direction (no pre-established trend), so it fires on BOTH a "break-down-
    then-reclaim-up" AND a "break-up-then-reclaim-down" regardless of the morning
    trend. THIS detector fixes the morning trend FIRST and ONLY takes the reclaim
    that is WITH that trend (a failed COUNTER-trend break) — the exact winning VWAP
    shape, ported. It is therefore a strictly tighter, trend-conditioned variant.

CAUSALITY (C6 — no look-ahead):
  * Trend side reads only closes[:TREND_BARS] vs as-of VWAP[:TREND_BARS].
  * OR is frozen from bars[:OR_BARS]; entries only on bars j >= OR_BARS.
  * The break/reclaim test at bar j reads only closes[:j+1] and the FROZEN OR.
  * Entry fills the NEXT bar open (the sim handles it). stop_level uses only the
    excursion extreme printed up to the reclaim bar.

REAL FILLS (C1): lib.simulator_real.simulate_trade_real on real OPRA bars
  (nearest-cached strike snap <=4, causal next-bar-open entry, chart-stop via
  rejection_level, entry_vix). Reuses the EXACT edgehunt data normalizers + sim +
  metrics path so the real-fills authority is byte-for-byte identical (no drift, C14).

ALL 8 GATES MANDATORY (anti-cherry-pick 2.10; reported for EVERY (OR x strike) cell):
  G1 OOS(2026) per-trade > 0
  G2 positive_quarters >= 4/6
  G3 top5_day_pct < 200
  G4 n_trades >= 20
  G5 drop-top5-day per-trade > 0          (day-concentration robustness)
  G6 IS(2025) FIRST-HALF per-trade > 0    (in-sample stability, sub-window sign)
  G7 beats random-entry null (L172): STANDARD coin-flip null (null_baseline) AND a
     same-day/same-side null (the harder control: isolates reclaim TIMING from
     day+side selection). Require BOTH.
  G8 no-truncation (L171): per-trade SIGN holds from -8% stop -> chart-stop-only
     (-0.99), full AND OOS (truncation_guard).

A Safe-2-TRADEABLE winner must clear ALL 8 gates at a strike whose premium fits the
$2K 30% cap (OTM-2 here = Safe-2's actual tier), not merely at ITM-2.

Pure Python, $0 (no LLM, no live orders). Markets closed.
Writes analysis/recommendations/rescue-or_reclaim_fb.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_rescue_or_reclaim_fb.py
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
# REUSE the edgehunt data normalizers + shape constants so the bar series + trend
# definition + cutoff are byte-for-byte identical to the validated campaign (C14).
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    TREND_BARS,        # 3 — morning-trend definition (same as vwap_continuation)
    ENTRY_CUTOFF,      # 10:30 ET morning cutoff (matches the winning shape)
    MAX_STRIKE_STEPS,  # nearest-cached snap radius (4)
    QTY,               # 3 (2 TP + 1 runner)
    OOS_YEAR,          # 2026
)
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.truncation_guard import is_truncation_artifact  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "rescue-or_reclaim_fb.json"

# ── Config ──────────────────────────────────────────────────────────────────
OR_BAR_CHOICES = {"15min": 3, "30min": 6}    # OR windows (RTH bars are 5m)
# Strike tiers (C29: report ALL; OTM-2 = Safe-2's actual $2K tier is the rescue target).
STRIKE_OFFSETS = {"ITM2": -2, "OTM2": 2}
PRIMARY_TIER = "OTM2"          # the RESCUE target (Safe-2's $2K tradeable tier)
SURV_PREMIUM_STOP = -0.08      # -8% premium stop (survivor config)
CHART_STOP_ONLY = -0.99        # for the no-truncation fraud gate (G8)
N_NULL_SEEDS = 20              # L172
RTH_OPEN = dt.time(9, 30)


# ─────────────────────────────────────────────────────────────────────────────
# Morning trend side — IDENTICAL to the validated vwap_continuation definition.
# ─────────────────────────────────────────────────────────────────────────────
def _trend_side(closes, vwap, n) -> Optional[str]:
    """Day's with-trend side: first n RTH closes all same side of as-of VWAP."""
    head_c = closes[:n]
    head_v = vwap[:n]
    if len(head_c) < n:
        return None
    if np.all(head_c > head_v):
        return "C"
    if np.all(head_c < head_v):
        return "P"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# DETECTOR — opening-range FAILED-BREAK reclaim. One causal with-trend entry/day.
# (The struct_vwap_reclaim_failed_break SHAPE, ported to the OR primitive.)
# ─────────────────────────────────────────────────────────────────────────────
def detect_or_reclaim_fb(days: list[DayCtx], *, or_bars: int) -> list[Signal]:
    """One causal OR failed-break reclaim entry/day.

    Sequence (all reads causal, bars[0..j] only):
      morning trend side (TREND_BARS vs as-of VWAP)
      -> COUNTER-trend OR break (a bar closes beyond the OR edge AGAINST the trend)
      -> WITH-trend reclaim (a later bar closes back through that edge in the trend
         direction) BEFORE ENTRY_CUTOFF -> entry on the reclaim bar.
    Stop = the failed-break excursion extreme (the structural invalidation).

    BULLISH (CALL trend): counter-trend break = close BELOW OR-low; reclaim = close
      back ABOVE OR-low. stop = min low over the failed break leg.
    BEARISH (PUT trend): counter-trend break = close ABOVE OR-high; reclaim = close
      back BELOW OR-high. stop = max high over the failed break leg.
    """
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < or_bars + 2:
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

        or_high = float(np.max(highs[:or_bars]))
        or_low = float(np.min(lows[:or_bars]))
        if or_high <= or_low:
            continue

        broke = False                          # counter-trend OR break happened yet?
        excursion_ext: Optional[float] = None  # extreme during the failed break (stop)
        for j in range(or_bars, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            c = closes[j]
            if side == "C":
                # Phase 2: counter-trend break = close BELOW OR-low (against bullish trend)
                if not broke:
                    if c < or_low:
                        broke = True
                        excursion_ext = lows[j]
                    continue
                # During the failed break, track the deepest LOW (the level that must hold)
                excursion_ext = (min(excursion_ext, lows[j])
                                 if excursion_ext is not None else lows[j])
                # Phase 3: reclaim = close BACK ABOVE OR-low in the trend direction -> entry
                if c > or_low:
                    stop = float(excursion_ext)
                    out.append(Signal(bar_idx=int(idxs[j]), side="C", stop_level=stop,
                                      note=f"or{or_bars}_reclaim_fb_low"))
                    break
            else:
                # Phase 2: counter-trend break = close ABOVE OR-high (against bearish trend)
                if not broke:
                    if c > or_high:
                        broke = True
                        excursion_ext = highs[j]
                    continue
                excursion_ext = (max(excursion_ext, highs[j])
                                 if excursion_ext is not None else highs[j])
                # Phase 3: reclaim = close BACK BELOW OR-high -> entry
                if c < or_high:
                    stop = float(excursion_ext)
                    out.append(Signal(bar_idx=int(idxs[j]), side="P", stop_level=stop,
                                      note=f"or{or_bars}_reclaim_fb_high"))
                    break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIM one signal set on real OPRA fills (v15 default exits) — validated path.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    pct: float
    exit_reason: str
    trig: str


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
            qty=QTY, setup="OR_RECLAIM_FB", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
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
            trig=sg.note,
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
    """Per-trade mean after removing the k highest-P&L DAYS entirely (G5)."""
    if not rows:
        return None
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.pnl)
    day_tot = {d: sum(v) for d, v in by_day.items()}
    drop_days = set(sorted(day_tot, key=day_tot.get, reverse=True)[:k])
    kept = [r.pnl for r in rows if r.date not in drop_days]
    return round(float(np.mean(kept)), 2) if kept else None


def metrics(rows: list[TradeRow]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    # IS FIRST-HALF (G6): split IS (2025) chronologically; require first half > 0.
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

    # max drawdown on the chronological cumulative P&L curve (disclosure)
    chrono = [r.pnl for r in sorted(rows, key=lambda r: r.date)]
    cum = np.cumsum(chrono)
    running_max = np.maximum.accumulate(cum)
    max_dd = round(float(np.min(cum - running_max)), 2) if len(cum) else 0.0

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "max_drawdown": max_dd,
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
# G7 — same-day/same-side random null (HARD control: isolates reclaim TIMING from
# day+side selection). Random eligible morning bar, same day, side, stop geometry.
# Reported alongside the STANDARD coin-flip null (null_baseline).
# ─────────────────────────────────────────────────────────────────────────────
def sameday_null(signals, spy, ribbon, vix, days, *, or_bars, seeds, strike_offset,
                 premium_stop_pct) -> dict:
    day_bars: dict[dt.date, list[int]] = {}
    for dc in days:
        rth = dc.rth
        times = rth["t"].values
        idxs = rth.index.tolist()
        elig = [int(idxs[j]) for j in range(or_bars, len(rth)) if times[j] <= ENTRY_CUTOFF]
        if elig:
            day_bars[dc.date] = elig
    sig_specs = []
    for sg in signals:
        d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
        sig_specs.append((d, sg.side, sg.stop_level))
    per_seed_exp, per_seed_oos_exp = [], []
    for seed in range(seeds):
        rng = np.random.default_rng(8000 + seed)
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
# Evaluate one (OR x strike) cell: all 8 gates.
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_cell(signals, spy, ribbon, vix, days, *, or_bars, strike_offset,
                  or_window, tier_label) -> dict:
    rows, cov = simulate_set(signals, spy, ribbon, vix, strike_offset=strike_offset,
                             premium_stop_pct=SURV_PREMIUM_STOP)
    m = metrics(rows)
    strike_name = (f"ITM{abs(strike_offset)}" if strike_offset < 0
                   else ("ATM" if strike_offset == 0 else f"OTM{strike_offset}"))
    if not m.get("n"):
        return {"or_window": or_window, "tier": tier_label, "strike_offset": strike_offset,
                "strike_tier_name": strike_name, "coverage": cov, "metrics": m,
                "gates": {}, "clears_all_gates": False, "n_gates_passed": 0,
                "note": "no filled trades", "caveats": []}

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
    sign_stable_oos = bool(cs_m.get("oos_n")
                           and (m.get("oos_exp", 0) > 0) == (cs_m.get("oos_exp", 0) > 0))
    truncation_safe = bool((not trunc_artifact) and sign_stable_full and sign_stable_oos)

    # G7 nulls — STANDARD coin-flip (null_baseline) + harder same-day/same-side.
    rth_all = pd.concat([dc.rth for dc in days]).sort_index().reset_index(drop=True)
    n_call = sum(1 for s in signals if s.side == "C")
    n_put = sum(1 for s in signals if s.side == "P")
    coin = random_entry_null(
        rth_all, n_signals=len(signals), n_call=n_call, n_put=n_put,
        strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP, seeds=N_NULL_SEEDS)
    coin_g = null_gate(m["exp_dollar"], m.get("drop_top5_day_per_trade"), coin)
    sameday = sameday_null(signals, spy, ribbon, vix, days, or_bars=or_bars,
                           seeds=N_NULL_SEEDS, strike_offset=strike_offset,
                           premium_stop_pct=SURV_PREMIUM_STOP)
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
                       "not reclaim-trigger precision (the trigger DOES beat the full-sample "
                       "coin-flip null and same-day mean+std; full-sample clears every gate).")
    return {
        "or_window": or_window,
        "tier": tier_label,
        "strike_offset": strike_offset,
        "strike_tier_name": strike_name,
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
    print("[rescue-or-fb] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[rescue-or-fb] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    cells = []
    detector_meta = {}
    for or_name, or_bars in OR_BAR_CHOICES.items():
        signals = detect_or_reclaim_fb(days, or_bars=or_bars)
        sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
        side_ct = {"C": sum(1 for s in signals if s.side == "C"),
                   "P": sum(1 for s in signals if s.side == "P")}
        fire_pct = round(100 * sig_days / n_days, 1) if n_days else 0.0
        detector_meta[or_name] = {"or_bars": or_bars, "n_signals": len(signals),
                                  "fire_day_pct": fire_pct, "side_count": side_ct}
        print(f"\n[rescue-or-fb] OR={or_name} ({or_bars}bar): signals={len(signals)} on "
              f"{sig_days} days (fires {fire_pct}% of days) side={side_ct}", flush=True)
        for tier, so in STRIKE_OFFSETS.items():
            cell = evaluate_cell(signals, spy, ribbon, vix, days, or_bars=or_bars,
                                 strike_offset=so, or_window=or_name, tier_label=tier)
            cells.append(cell)
            m = cell["metrics"]
            print(f"  [{or_name}/{tier} off={so:+d}] n={m.get('n','-')} "
                  f"exp=${m.get('exp_dollar','-')} oos_exp=${m.get('oos_exp','-')} "
                  f"(oos_n={m.get('oos_n','-')}) posQ={m.get('positive_quarters','-')} "
                  f"top5%={m.get('top5_day_pct','-')} droptop5=${m.get('drop_top5_day_per_trade','-')} "
                  f"isH1=${m.get('is_first_half_exp','-')} maxDD=${m.get('max_drawdown','-')} "
                  f"-> {cell['n_gates_passed']}/8 "
                  f"{'CLEARS' if cell['clears_all_gates'] else 'no'}", flush=True)
            for gname, g in cell.get("gates", {}).items():
                print(f"      {gname}: {'PASS' if g['pass'] else 'FAIL'}", flush=True)

    # ── Headline = best TRADEABLE cell. Prefer a clearing OTM-2 (Safe-2 target);
    #    else best primary-tier cell by gates passed then OOS per-trade. ─────────
    clearing = [c for c in cells if c["clears_all_gates"]]
    primary_cells = [c for c in cells if c["tier"] == PRIMARY_TIER]
    primary_clearing = [c for c in primary_cells if c["clears_all_gates"]]

    def _rank_key(c):
        return (c["n_gates_passed"], c["metrics"].get("oos_exp", -9e9))

    if primary_clearing:
        headline = max(primary_clearing, key=_rank_key)
    elif primary_cells:
        headline = max(primary_cells, key=_rank_key)
    else:
        headline = max(cells, key=_rank_key) if cells else None

    # Best Safe-2-tradeable strike = best OTM/ATM cell that clears all 8 gates.
    safe2_clearing = [c for c in clearing if c["strike_offset"] >= 0]
    best_safe2 = max(safe2_clearing, key=_rank_key) if safe2_clearing else None
    safe2_tradeable = best_safe2 is not None
    best_tradeable_strike = (best_safe2["strike_tier_name"] if best_safe2 else
                             (max(clearing, key=_rank_key)["strike_tier_name"]
                              if clearing else "NONE"))

    if clearing:
        if safe2_tradeable:
            verdict = (f"PROMOTABLE + SAFE-2 TRADEABLE — the failed-break-reclaim SHAPE "
                       f"GENERALIZES to the OR primitive and clears all 8 gates at "
                       f"{best_safe2['strike_tier_name']} ({best_safe2['or_window']}), the $2K "
                       f"tier Safe-2 actually trades (unlike the VWAP version which failed @ OTM-2)")
        else:
            cc = max(clearing, key=_rank_key)
            verdict = (f"PROMOTABLE @ {cc['strike_tier_name']} ({cc['or_window']}) but NOT "
                       f"Safe-2-tradeable — no OTM/ATM cell clears all 8 gates (C29: gates do not "
                       f"transfer to the $2K OTM tier; same ITM-only outcome as the VWAP version)")
    else:
        verdict = ("REJECTED — no (OR x strike) cell clears all 8 mandatory gates; the failed-break-"
                   "reclaim SHAPE does NOT generalize to the OR primitive on real fills")

    # Schema fields keyed to the HEADLINE cell (the Safe-2 target tier).
    hm = headline.get("metrics", {}) if headline else {}
    hg = headline.get("gates", {}) if headline else {}
    coin = hg.get("G7_beats_random_null", {}).get("coinflip_null", {}) if hg else {}
    beats_null = bool(hg.get("G7_beats_random_null", {}).get("pass")) if hg else False
    truncation_safe = bool(hg.get("G8_no_truncation", {}).get("pass")) if hg else False
    is_half_positive = bool(hg.get("G6_is_first_half_positive", {}).get("pass")) if hg else False
    clears_all_headline = bool(headline.get("clears_all_gates")) if headline else False

    summary = {
        "study": "or_reclaim_fb (structural-generalize: failed-break-reclaim SHAPE ported to the OR primitive)",
        "slug": "or_reclaim_fb",
        "kind": "structural_one_entry_per_day",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "opra_fill_cutoff": "2026-05-29 (signals after drop as cache_miss; OOS fills = Jan..May 2026)",
        "hypothesis": ("GENERALIZE the winning struct_vwap_reclaim_failed_break SHAPE (failed "
                       "COUNTER-trend break that RECLAIMS with-trend, one causal entry/day, "
                       "8/8 gates @ ITM-2) from the VWAP primitive to the OPENING RANGE: fix the "
                       "morning trend (first 3 RTH closes same side of as-of VWAP), then price "
                       "breaks the 15/30-min OR counter-trend, fails, and reclaims with-trend -> "
                       "one entry. All 8 gates, best tradeable strike (incl. OTM-2 = Safe-2's $2K tier)."),
        "detector": ("clean causal one-entry/day: morning trend side (TREND_BARS vs as-of VWAP) -> "
                     "counter-trend OR break (close beyond the OR edge against the trend) -> "
                     "with-trend reclaim (close back through that edge) <=10:30 ET; entry=reclaim "
                     "bar, fill=next bar open; chart stop = failed-break excursion extreme. "
                     "DISTINCT from struct_orb_reclaim (which has NO pre-established trend and "
                     "takes the reclaim in EITHER direction); this is the trend-conditioned, "
                     "counter-trend-failed-break variant = the VWAP winner's shape on the OR."),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "or_windows": list(OR_BAR_CHOICES.keys()),
        "strike_tiers": {"ITM2": "strike_offset=-2 (survivor structure, reported for comparison)",
                         "OTM2": "strike_offset=+2 = Safe-2's actual $2K tier (the RESCUE target; "
                                 "C29 — gates do not transfer across strike tiers)"},
        "PRIMARY_TIER": PRIMARY_TIER,
        "config": {"premium_stop_pct": SURV_PREMIUM_STOP, "qty": QTY,
                   "exits": "v15 default (tp1=0.30, runner=2.5x, profit_lock=OFF)",
                   "trend_bars": TREND_BARS, "entry_cutoff_et": "10:30"},
        "eight_gates": {
            "G1": "OOS(2026) per-trade > 0",
            "G2": "positive_quarters >= 4/6",
            "G3": "top5_day_pct < 200",
            "G4": "n_trades >= 20",
            "G5": "drop-top5-day per-trade > 0",
            "G6": "IS(2025) first-half per-trade > 0",
            "G7": "beats random-entry null (coin-flip null_pass AND same-day mean+std, 20 seeds)",
            "G8": "no-truncation: per-trade sign holds -8% -> chart-stop-only (-0.99), full + OOS",
        },
        "detector_meta": detector_meta,
        "cells": cells,
        "n_cells": len(cells),
        "clearing_cells": [{"or_window": c["or_window"], "tier": c["tier"],
                            "strike_offset": c["strike_offset"],
                            "strike_tier_name": c["strike_tier_name"]} for c in clearing],
        "n_clearing_cells": len(clearing),
        "headline_cell": headline,
        "best_safe2_cell": best_safe2,
        "safe2_tradeable": safe2_tradeable,
        "best_tradeable_strike": best_tradeable_strike,
        "verdict": verdict,
        "DISCLOSURE": {
            "no_cherry_pick": ("ALL 8 gates reported for EVERY (OR x strike) cell (2 OR windows x "
                               "2 strike tiers = 4 cells); a cell that fails any gate is marked "
                               "clears_all_gates=false (anti-pattern 2.10)."),
            "structural_not_additive": ("ONE causal entry/day with a structural chart stop; no "
                                        "stacked confirmations (the campaign proved additive "
                                        "confluence is dead on 0DTE)."),
            "structural_generalize": ("same SHAPE as the validated struct_vwap_reclaim_failed_break, "
                                      "DIFFERENT structural primitive (OR edge vs session VWAP) — a "
                                      "generalization test, not a re-run."),
            "strike_tier_caveat": "C29 — gates do not transfer across strike tiers; reported per tier; "
                                  "Safe-2 ($2K, 30% cap) trades OTM-2, so the OTM-2 verdict is decisive.",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58).",
            "fraud_gates": ("G7 random-entry null (coin-flip + same-day/same-side, 20 seeds) + "
                            "G8 no-truncation (sign must hold -8% -> chart-stop-only)."),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[rescue-or-fb] wrote {OUT}", flush=True)

    print("\n=== OR_RECLAIM_FB VERDICT (structural-generalize) ===")
    for c in cells:
        m = c["metrics"]
        gf = [k for k, v in c.get("gates", {}).items() if not v["pass"]]
        print(f"  {c['or_window']}/{c['tier']} (off={c['strike_offset']:+d} {c['strike_tier_name']}): "
              f"n={m.get('n','-')} oos_exp=${m.get('oos_exp','-')} -> {c['n_gates_passed']}/8 "
              f"{'CLEARS ALL 8' if c['clears_all_gates'] else ('FAILS: ' + ','.join(gf) if gf else 'no trades')}")
    print(f"\nclearing_cells={[(c['or_window'], c['strike_tier_name']) for c in clearing]}")
    print(f"safe2_tradeable={safe2_tradeable}  best_tradeable_strike={best_tradeable_strike}")
    if headline:
        print(f"HEADLINE ({headline['or_window']}/{headline['strike_tier_name']}): "
              f"n={hm.get('n')} oos_exp=${hm.get('oos_exp')} posQ={hm.get('positive_quarters')} "
              f"-> {headline['n_gates_passed']}/8 clears_all={clears_all_headline} "
              f"beats_null={beats_null} truncation_safe={truncation_safe} is_half_positive={is_half_positive}")
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
