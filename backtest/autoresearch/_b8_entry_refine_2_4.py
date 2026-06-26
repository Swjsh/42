"""B8 — GENERALIZE the 2-bar touch-and-go ENTRY refinement to the DORMANT edges #2 + #4.

ANGLE C of the edge-hunt campaign.

THE ONE THING THAT WORKED IN B7 (Angle A) = a tighter 2-bar STRUCTURAL entry
confirmation (S1 "VWAP touch-and-go": pull back to TOUCH VWAP, then the NEXT bar
RESUMES with-trend AND extends past the touch bar's with-trend extreme) lifted the
LIVE #1 vwap_continuation shape. The question Angle C answers:

  Does the SAME CLASS of entry refinement — replace the first-trigger bar with a
  2-bar WITH-TREND confirmation (a touch-and-resume / reclaim-and-extend) — also
  LIFT the two DORMANT edges?

    #2  vwap_reclaim_failed_break  (the #2 reclaim harness:
        _sub_struct_vwap_reclaim_failed_break) — native entry = the RECLAIM bar
        (first close back across VWAP with-trend after a failed counter-trend break).
        REFINED entry = require the bar AFTER the reclaim to CONFIRM: close stays on
        the trend side of VWAP AND EXTENDS past the reclaim bar's with-trend extreme.
        Entry shifts from the reclaim bar -> the confirmation bar. (A reclaim-and-
        extend, i.e. the 2-bar with-trend confirmation form of #2's shape.)

    #4  vix_regime_dayside  (the #4 _b5_vix_regime_dayside harness) — native entry =
        the FIRST favorable-VIX-regime bar after the day-trend side is established.
        REFINED entry = the first bar that is BOTH (a) favorable-regime AND (b) a
        VWAP touch-and-RESUME confirmation (B7 S1: prior bar touched VWAP, this bar
        resumes with-trend + extends past the touch bar's with-trend extreme). i.e.
        instead of taking the first regime bar, wait for a 2-bar VWAP touch-and-go
        inside the favorable regime.

For EACH edge: A/B baseline (native first-trigger) vs the 2-bar-confirmation variant
on REAL OPRA fills (C1, lib.simulator_real.simulate_trade_real), at the edge's
validated tier(s) (ATM Safe-2 + ITM-2 Bold), through the FULL 9-gate bar incl
OOS-ALONE drop-top5 (L173), AND a NO-REGRESSION check (the refinement must NOT remove
net-winning days — it may only drop net-negative/neutral days).

VERDICT per edge:
  LIVE_EDGE_IMPROVEMENT  iff refined lifts OOS per-trade AND clears all 9 gates AND
                         passes no-regression (does not remove net-winning days).
  else DEAD/RELABEL.

HONEST (C7): every number is PASTED from actually running the script. No fabrication.
Pure Python, $0. No live orders. Markets closed.

Writes analysis/recommendations/B8-ENTRY-REFINE-2-4-SCORECARD.md (+ .json).
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b8_entry_refine_2_4.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[1]   # backtest/
ROOT = REPO.parent                            # repo root (42/)
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    causal_vix_median,
    favorable_regime,
    vix_slope,
    VIX_MEDIAN_BARS,
    VIX_SLOPE_BARS,
)
from autoresearch._edgehunt_vwap_continuation import _align_vix, _normalize_spy  # noqa: E402
from autoresearch.fraud_gates import CandidateSignal, verify_candidate  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    DayCtx,
    Signal,
    _nearest_cached_strike,
    _strike_from_spot,
    build_day_contexts,
    session_vwap_asof,
)
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT_MD = ROOT / "analysis" / "recommendations" / "B8-ENTRY-REFINE-2-4-SCORECARD.md"
OUT_JSON = ROOT / "analysis" / "recommendations" / "B8-ENTRY-REFINE-2-4-SCORECARD.json"

# ── Shared params (byte-aligned to the source #2 / #4 harnesses) ─────────────────
TREND_BARS = 3
ENTRY_CUTOFF = dt.time(11, 0)          # one causal entry/day; matches #2/#4 morning windows
MAX_STRIKE_STEPS = 4
QTY = 3
PREMIUM_STOP_PCT = -0.08               # v15 tight stop (the validated tier stop)
CHART_STOP_ONLY = -0.99
OOS_YEAR = 2026
NULL_SEEDS = 20

# Edge #4 canonical regime config = the ROBUST clearing cell from the B5 baseline
# (slope_rule=not_rising, low_margin=0.25 -> ATM clears 8/8 at oos_n=21). Fixed, not
# swept here: B8 isolates the ENTRY-REFINEMENT effect, holding the regime cut constant.
VIX_LOW_MARGIN = 0.25
VIX_SLOPE_RULE = "not_rising"

TIERS = {"ATM": 0, "ITM2": -2}         # C29: test both validated tiers independently
SIDES = ("BOTH",)                       # edges are day-side selected; BOTH = full population

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0


# ════════════════════════════════════════════════════════════════════════════════
# Trend side — identical definition to #1/#2/#4 (first TREND_BARS closes vs as-of VWAP)
# ════════════════════════════════════════════════════════════════════════════════
def _trend_side(closes, vwap, n) -> Optional[str]:
    head_c, head_v = closes[:n], vwap[:n]
    if len(head_c) < n:
        return None
    if np.all(head_c > head_v):
        return "C"
    if np.all(head_c < head_v):
        return "P"
    return None


# ════════════════════════════════════════════════════════════════════════════════
# EDGE #2 — vwap_reclaim_failed_break
#   baseline: entry = reclaim bar (first close back across VWAP with-trend after a
#             failed counter-trend break). [ = _sub_struct detector, byte-aligned ]
#   refined : require a NEXT-bar with-trend confirmation (close stays trend side AND
#             extends past the reclaim bar's with-trend extreme); entry = that bar.
# ════════════════════════════════════════════════════════════════════════════════
def detect_reclaim(days: list[DayCtx], *, refined: bool) -> list[Signal]:
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 3:
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
        broke = False
        excursion_ext: Optional[float] = None
        for j in range(TREND_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            v = vwap[j]
            if v <= 0:
                continue
            c = closes[j]
            if side == "C":
                if not broke:
                    if c < v:
                        broke = True
                        excursion_ext = lows[j]
                    continue
                excursion_ext = (min(excursion_ext, lows[j])
                                 if excursion_ext is not None else lows[j])
                if c > v:  # reclaim bar
                    if not refined:
                        out.append(Signal(bar_idx=int(idxs[j]), side="C",
                                          stop_level=float(excursion_ext),
                                          note="reclaim_base"))
                        break
                    # REFINED: require the NEXT bar to confirm with-trend + extend
                    k = j + 1
                    if k >= len(rth) or times[k] > ENTRY_CUTOFF:
                        break
                    confirm = closes[k] > vwap[k] and highs[k] > highs[j]
                    if confirm:
                        out.append(Signal(bar_idx=int(idxs[k]), side="C",
                                          stop_level=float(excursion_ext),
                                          note="reclaim_2bar"))
                    break
            else:
                if not broke:
                    if c > v:
                        broke = True
                        excursion_ext = highs[j]
                    continue
                excursion_ext = (max(excursion_ext, highs[j])
                                 if excursion_ext is not None else highs[j])
                if c < v:  # reclaim bar
                    if not refined:
                        out.append(Signal(bar_idx=int(idxs[j]), side="P",
                                          stop_level=float(excursion_ext),
                                          note="reclaim_base"))
                        break
                    k = j + 1
                    if k >= len(rth) or times[k] > ENTRY_CUTOFF:
                        break
                    confirm = closes[k] < vwap[k] and lows[k] < lows[j]
                    if confirm:
                        out.append(Signal(bar_idx=int(idxs[k]), side="P",
                                          stop_level=float(excursion_ext),
                                          note="reclaim_2bar"))
                    break
    return out


# ════════════════════════════════════════════════════════════════════════════════
# EDGE #4 — vix_regime_dayside
#   baseline: entry = FIRST favorable-VIX-regime bar after trend established.
#   refined : entry = first bar that is BOTH favorable-regime AND a VWAP touch-and-
#             resume confirmation (prior bar touched VWAP; this bar resumes with-trend
#             + extends past the touch bar's with-trend extreme — the B7 S1 shape).
# ════════════════════════════════════════════════════════════════════════════════
def detect_vix_regime(days: list[DayCtx], vix_g, vix_med_g, vix_slp_g,
                      *, refined: bool) -> list[Signal]:
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 3:
            continue
        gidx = rth.index.to_numpy()
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        side = _trend_side(closes, vwap, TREND_BARS)
        if side is None:
            continue
        for j in range(TREND_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            g = int(gidx[j])
            lvl = float(vix_g[g]) if g < len(vix_g) else None
            med = float(vix_med_g[g]) if g < len(vix_med_g) else None
            slp = float(vix_slp_g[g]) if g < len(vix_slp_g) else None
            fav = favorable_regime(lvl, med, slp, VIX_LOW_MARGIN, VIX_SLOPE_RULE)
            if fav is None or not fav:
                continue
            v = vwap[j]
            if v <= 0:
                continue
            if not refined:
                if side == "C":
                    stop = float(np.min(lows[: j + 1]))
                else:
                    stop = float(np.max(highs[: j + 1]))
                out.append(Signal(bar_idx=g, side=side, stop_level=stop,
                                  note="vixreg_base"))
                break
            # REFINED: this bar must be a VWAP touch-and-RESUME (prior bar touched VWAP,
            # this bar resumes with-trend + extends). j-1 is the touch bar.
            t_bar = j - 1
            if t_bar < 0:
                continue
            if side == "C":
                touched = lows[t_bar] <= vwap[t_bar]
                resume = closes[j] > v and highs[j] > highs[t_bar]
                stop = float(np.min(lows[: j + 1]))
            else:
                touched = highs[t_bar] >= vwap[t_bar]
                resume = closes[j] < v and lows[j] < lows[t_bar]
                stop = float(np.max(highs[: j + 1]))
            if touched and resume:
                out.append(Signal(bar_idx=g, side=side, stop_level=stop,
                                  note="vixreg_2bar"))
                break
    return out


# ════════════════════════════════════════════════════════════════════════════════
# REAL-FILLS SIM + METRICS  (same shapes as B7 — one source of truth)
# ════════════════════════════════════════════════════════════════════════════════
def simulate_cell(signals, spy, vix, *, strike_offset, premium_stop_pct):
    rows = []
    n_cache_miss = n_sim_none = 0
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
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=None,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "b8"],
            side=sg.side, qty=QTY, setup="B8", strike_override=strike,
            entry_vix=entry_vix, premium_stop_pct=premium_stop_pct)
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        rows.append({"date": str(d), "side": sg.side,
                     "pnl": round(float(fill.dollar_pnl), 2),
                     "exit": fill.exit_reason.name if fill.exit_reason else "NONE"})
    return rows, {"cache_miss": n_cache_miss, "sim_none": n_sim_none}


def _quarter(day: str) -> str:
    y, m, _ = day.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _per_trade(rows) -> Optional[float]:
    return round(float(np.mean([r["pnl"] for r in rows])), 2) if rows else None


def _drop_top5_per_trade(rows) -> Optional[float]:
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r["pnl"])
    if not by_day:
        return None
    day_tot = {d: sum(v) for d, v in by_day.items()}
    top5 = set(d for d, _ in sorted(day_tot.items(), key=lambda kv: kv[1],
                                    reverse=True)[:5])
    kept = [p for d, v in by_day.items() if d not in top5 for p in v]
    return round(float(np.mean(kept)), 2) if kept else None


def _top5_day_pct(rows) -> Optional[float]:
    by_day = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _is_first_half_per_trade(rows) -> Optional[float]:
    is_rows = [r for r in rows if int(r["date"][:4]) != OOS_YEAR]
    if not is_rows:
        return None
    is_days = sorted({r["date"] for r in is_rows})
    half = set(is_days[: max(1, len(is_days) // 2)])
    first = [r["pnl"] for r in is_rows if r["date"] in half]
    return round(float(np.mean(first)), 2) if first else None


def evaluate(rows: list[dict]) -> dict:
    n = len(rows)
    is_rows = [r for r in rows if int(r["date"][:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r["date"][:4]) == OOS_YEAR]
    by_q = defaultdict(list)
    for r in rows:
        by_q[_quarter(r["date"])].append(r["pnl"])
    quarters = {q: {"n": len(v), "per_trade": round(sum(v) / len(v), 2),
                    "total": round(sum(v), 2)} for q, v in sorted(by_q.items())}
    pos_q = sum(1 for v in quarters.values() if v["per_trade"] > 0)
    return {
        "n": n,
        "overall_per_trade": _per_trade(rows),
        "total": round(sum(r["pnl"] for r in rows), 2) if rows else None,
        "is_n": len(is_rows), "is_per_trade": _per_trade(is_rows),
        "oos_n": len(oos_rows), "oos_per_trade": _per_trade(oos_rows),
        "oos_total": round(sum(r["pnl"] for r in oos_rows), 2) if oos_rows else None,
        "drop_top5_full": _drop_top5_per_trade(rows),
        "drop_top5_oos": _drop_top5_per_trade(oos_rows),
        "top5_day_pct_full": _top5_day_pct(rows),
        "is_first_half_per_trade": _is_first_half_per_trade(rows),
        "positive_quarters": pos_q, "n_quarters": len(quarters),
        "quarters": quarters,
        "wr_pct": round(100 * sum(1 for r in rows if r["pnl"] > 0) / n, 1) if n else None,
    }


def map_candidate_signals(signals, spy, rth):
    out = []
    for s in signals:
        ts = spy.iloc[s.bar_idx]["timestamp_et"]
        match = rth.index[rth["timestamp_et"] == ts]
        if len(match) == 0:
            continue
        out.append(CandidateSignal(bar_idx=int(match[0]), side=s.side,
                                   rejection_level=float(s.stop_level),
                                   note=s.note or "b8"))
    return out


def gate_cell(m: dict, fraud) -> tuple[bool, dict, list[str]]:
    g = {
        "1_oos_pt_gt0": bool(m["oos_per_trade"] is not None and m["oos_per_trade"] > 0),
        "2_pos_q_ge4of6": bool(m["positive_quarters"] >= BAR_POS_Q and m["n_quarters"] >= 6),
        "3_top5_full_lt200": bool(m["top5_day_pct_full"] is not None
                                  and m["top5_day_pct_full"] < BAR_TOP5),
        "4_n_ge20": bool(m["n"] >= BAR_N),
        "5_drop_top5_full_gt0": bool(m["drop_top5_full"] is not None
                                     and m["drop_top5_full"] > 0),
        "6_is_first_half_pt_gt0": bool(m["is_first_half_per_trade"] is not None
                                       and m["is_first_half_per_trade"] > 0),
        "7_beats_random_null": bool(fraud.null_pass),
        "8_no_truncation": bool(fraud.no_truncation_pass),
        "9_oos_drop_top5_gt0": bool(m["drop_top5_oos"] is not None
                                    and m["drop_top5_oos"] > 0),
    }
    fails = [k for k, v in g.items() if not v]
    return (len(fails) == 0, g, fails)


# ════════════════════════════════════════════════════════════════════════════════
# NO-REGRESSION — the refinement may ONLY remove net-negative/neutral days, never
# net-WINNING days. For each DAY dropped by the refinement (present in baseline, gone
# in refined) compute the baseline day P&L; if any dropped day was a net WINNER, the
# refinement regressed (it threw away a winner). Reported full + OOS.
# ════════════════════════════════════════════════════════════════════════════════
def no_regression(base_rows, ref_rows) -> dict:
    def by_day(rows):
        d = defaultdict(float)
        for r in rows:
            d[r["date"]] += r["pnl"]
        return d
    bd_b, bd_r = by_day(base_rows), by_day(ref_rows)
    dropped = [d for d in bd_b if d not in bd_r]
    dropped_pnl = {d: round(bd_b[d], 2) for d in dropped}
    dropped_winners = {d: p for d, p in dropped_pnl.items() if p > 0}
    dropped_losers = {d: p for d, p in dropped_pnl.items() if p < 0}
    # OOS-only slice
    oos_winners = {d: p for d, p in dropped_winners.items() if int(d[:4]) == OOS_YEAR}
    removed_winner_pnl = round(sum(dropped_winners.values()), 2)
    removed_loser_pnl = round(sum(dropped_losers.values()), 2)
    return {
        "n_days_baseline": len(bd_b),
        "n_days_refined": len(bd_r),
        "n_days_dropped": len(dropped),
        "n_dropped_winners": len(dropped_winners),
        "n_dropped_losers": len(dropped_losers),
        "n_dropped_oos_winners": len(oos_winners),
        "removed_winner_pnl_total": removed_winner_pnl,
        "removed_loser_pnl_total": removed_loser_pnl,
        "net_removed_pnl": round(removed_winner_pnl + removed_loser_pnl, 2),
        # PASS = no net-winning DAY was removed (the refinement only pruned non-winners).
        "passes_no_regression": len(dropped_winners) == 0,
        "dropped_winner_days": dropped_winners,
    }


# ════════════════════════════════════════════════════════════════════════════════
# A/B one edge across both tiers
# ════════════════════════════════════════════════════════════════════════════════
def ab_one_edge(name, base_sigs, ref_sigs, spy, vix, rth, n_days) -> dict:
    def fire(sigs):
        sig_days = len({spy.iloc[s.bar_idx]["timestamp_et"].date() for s in sigs})
        return {"n_signals": len(sigs), "fire_day_pct": round(100 * sig_days / n_days, 1),
                "side_count": {"C": sum(1 for s in sigs if s.side == "C"),
                               "P": sum(1 for s in sigs if s.side == "P")}}

    blk = {"edge": name, "baseline_fire": fire(base_sigs), "refined_fire": fire(ref_sigs),
           "tiers": {}}
    print(f"\n[b8] === {name} ===", flush=True)
    print(f"[b8]   baseline signals={len(base_sigs)} | refined signals={len(ref_sigs)}",
          flush=True)

    for tier_name, so in TIERS.items():
        base_rows, base_cov = simulate_cell(base_sigs, spy, vix, strike_offset=so,
                                            premium_stop_pct=PREMIUM_STOP_PCT)
        ref_rows, ref_cov = simulate_cell(ref_sigs, spy, vix, strike_offset=so,
                                          premium_stop_pct=PREMIUM_STOP_PCT)
        bm, rm = evaluate(base_rows), evaluate(ref_rows)

        # gates on REFINED (the variant under test)
        if rm["n"] == 0:
            ref_clears, ref_gates, ref_fails = False, {}, ["no_fills"]
            ref_fraud = None
        else:
            cand = map_candidate_signals(ref_sigs, spy, rth)
            fraud = verify_candidate(cand, rth, strike_offset=so,
                                     premium_stop_pct=PREMIUM_STOP_PCT, qty=QTY,
                                     setup=f"B8_{name}_{tier_name}", seeds=NULL_SEEDS)
            ref_clears, ref_gates, ref_fails = gate_cell(rm, fraud)
            ref_fraud = fraud.as_dict()

        # gates on BASELINE too (so the scorecard shows where the dormant edge stands)
        if bm["n"] == 0:
            base_clears, base_gates, base_fails = False, {}, ["no_fills"]
        else:
            bcand = map_candidate_signals(base_sigs, spy, rth)
            bfraud = verify_candidate(bcand, rth, strike_offset=so,
                                      premium_stop_pct=PREMIUM_STOP_PCT, qty=QTY,
                                      setup=f"B8_{name}_{tier_name}_BASE", seeds=NULL_SEEDS)
            base_clears, base_gates, base_fails = gate_cell(bm, bfraud)

        noreg = no_regression(base_rows, ref_rows)

        # lift = refined OOS per-trade - baseline OOS per-trade
        lift = None
        if rm["oos_per_trade"] is not None and bm["oos_per_trade"] is not None:
            lift = round(rm["oos_per_trade"] - bm["oos_per_trade"], 2)

        # VERDICT for this tier
        lifts = bool(lift is not None and lift > 0)
        improvement = bool(lifts and ref_clears and noreg["passes_no_regression"])
        if improvement:
            verdict = "LIVE_EDGE_IMPROVEMENT"
        elif ref_clears and not lifts:
            verdict = "RELABEL"   # refined still an edge but does not lift the dormant base
        else:
            verdict = "DEAD"

        blk["tiers"][tier_name] = {
            "strike_offset": so,
            "baseline": {"metrics": bm, "coverage": base_cov, "clears": base_clears,
                         "gates": base_gates, "fails": base_fails},
            "refined": {"metrics": rm, "coverage": ref_cov, "clears": ref_clears,
                        "gates": ref_gates, "fails": ref_fails, "fraud": ref_fraud},
            "oos_per_trade_lift": lift,
            "no_regression": noreg,
            "verdict": verdict,
        }
        print(f"[b8]   {tier_name:>5} so={so:+d}: "
              f"BASE n={bm['n']} oos/tr=${bm['oos_per_trade']} (clears={base_clears}) "
              f"| REF n={rm['n']} oos/tr=${rm['oos_per_trade']} "
              f"dropT5_OOS=${rm['drop_top5_oos']} clears={ref_clears} "
              f"| lift=${lift} noreg={noreg['passes_no_regression']} "
              f"(droppedW={noreg['n_dropped_winners']}) -> {verdict}", flush=True)
        if ref_fails and ref_fails != ["no_fills"]:
            print(f"[b8]          refined fails: {','.join(ref_fails)}", flush=True)
    return blk


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"[b8] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    vix_med = causal_vix_median(np.asarray(vix), VIX_MEDIAN_BARS)
    vix_slp = vix_slope(np.asarray(vix), VIX_SLOPE_BARS)
    days = build_day_contexts(spy)
    n_days = len(days)
    rth = spy[(spy["t"] >= dt.time(9, 30)) & (spy["t"] < dt.time(16, 0))].reset_index(drop=True)
    vix_ser = pd.Series(vix)
    print(f"[b8] trading_days={n_days} window={spy['timestamp_et'].iloc[0].date()}.."
          f"{spy['timestamp_et'].iloc[-1].date()}", flush=True)

    edges = {}

    # EDGE #2 — reclaim
    e2_base = detect_reclaim(days, refined=False)
    e2_ref = detect_reclaim(days, refined=True)
    edges["edge2_vwap_reclaim_failed_break"] = ab_one_edge(
        "edge2_vwap_reclaim_failed_break", e2_base, e2_ref, spy, vix_ser, rth, n_days)

    # EDGE #4 — vix_regime_dayside (fixed canonical regime cut)
    e4_base = detect_vix_regime(days, vix, vix_med, vix_slp, refined=False)
    e4_ref = detect_vix_regime(days, vix, vix_med, vix_slp, refined=True)
    edges["edge4_vix_regime_dayside"] = ab_one_edge(
        "edge4_vix_regime_dayside", e4_base, e4_ref, spy, vix_ser, rth, n_days)

    summary = {
        "campaign": "B8 — generalize the 2-bar touch-and-go ENTRY refinement to dormant edges #2 + #4 (Angle C)",
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "trading_days": n_days,
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR}",
        "refinement": ("replace the first-trigger bar with a 2-bar WITH-TREND confirmation "
                       "(reclaim-and-extend for #2; VWAP touch-and-resume for #4) — "
                       "generalizes B7 S1 touch-and-go that lifted the LIVE #1"),
        "gates": "9-gate bar incl OOS-ALONE drop-top5 (L173) + random-null (L172) + no-trunc (L171) + NO-REGRESSION",
        "edge4_regime_cut": {"slope_rule": VIX_SLOPE_RULE, "low_margin": VIX_LOW_MARGIN,
                             "note": "fixed at the B5 robust clearing cell; B8 isolates the entry refinement"},
        "tiers": TIERS, "premium_stop_pct": PREMIUM_STOP_PCT, "qty": QTY,
        "edges": edges,
    }
    # roll up an overall verdict per edge (best across tiers)
    rollup = {}
    for ename, eb in edges.items():
        verdicts = {tn: t["verdict"] for tn, t in eb["tiers"].items()}
        if "LIVE_EDGE_IMPROVEMENT" in verdicts.values():
            ov = "LIVE_EDGE_IMPROVEMENT"
        elif "RELABEL" in verdicts.values():
            ov = "RELABEL"
        else:
            ov = "DEAD"
        rollup[ename] = {"overall": ov, "per_tier": verdicts}
    summary["verdict_rollup"] = rollup

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_md(summary)
    print(f"\n[b8] wrote {OUT_JSON}\n[b8] wrote {OUT_MD}", flush=True)
    print("\n=== B8 VERDICT ROLLUP ===")
    for ename, rv in rollup.items():
        print(f"  {ename}: {rv['overall']}  (per-tier {rv['per_tier']})")
    return 0


def write_md(s: dict) -> None:
    L = []
    L.append("# B8 — Generalize the 2-bar Entry Refinement to Dormant Edges #2 + #4 (Angle C)\n")
    L.append(f"- Run: {s['run_date']}  |  Window: {s['window']}  |  Trading days: {s['trading_days']}")
    L.append(f"- Fills: {s['fills_authority']}")
    L.append(f"- OOS split: {s['oos_split']}")
    L.append(f"- Refinement: {s['refinement']}")
    L.append(f"- Gate bar: {s['gates']}")
    L.append(f"- Edge#4 regime cut (fixed): {s['edge4_regime_cut']}")
    L.append(f"- Tiers: {s['tiers']}  |  premium_stop_pct: {s['premium_stop_pct']}  |  qty: {s['qty']}\n")

    L.append("## VERDICT ROLLUP\n")
    for ename, rv in s["verdict_rollup"].items():
        L.append(f"- **{ename}** -> **{rv['overall']}**  (per-tier {rv['per_tier']})")
    L.append("")

    for ename, eb in s["edges"].items():
        L.append(f"## {ename}")
        L.append(f"- baseline fires: {eb['baseline_fire']}")
        L.append(f"- refined fires:  {eb['refined_fire']}\n")
        L.append("| tier | variant | n | oos_n | OOS/tr | dropT5_OOS | dropT5_full | top5%_full | posQ | clears | fails |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for tn, t in eb["tiers"].items():
            for vlabel, v in (("baseline", t["baseline"]), ("refined", t["refined"])):
                m = v["metrics"]
                L.append(f"| {tn} | {vlabel} | {m.get('n')} | {m.get('oos_n')} | "
                         f"{m.get('oos_per_trade')} | {m.get('drop_top5_oos')} | "
                         f"{m.get('drop_top5_full')} | {m.get('top5_day_pct_full')} | "
                         f"{m.get('positive_quarters')}/{m.get('n_quarters')} | "
                         f"{'YES' if v['clears'] else 'no'} | "
                         f"{','.join(v['fails']) if v['fails'] else '-'} |")
        L.append("")
        L.append("| tier | OOS/tr lift (ref-base) | no-regression | dropped winner days | net removed $ | verdict |")
        L.append("|---|---|---|---|---|---|")
        for tn, t in eb["tiers"].items():
            nr = t["no_regression"]
            L.append(f"| {tn} | {t['oos_per_trade_lift']} | "
                     f"{'PASS' if nr['passes_no_regression'] else 'FAIL'} | "
                     f"{nr['n_dropped_winners']} (${nr['removed_winner_pnl_total']}) | "
                     f"{nr['net_removed_pnl']} | {t['verdict']} |")
        L.append("")

    L.append("## Disclosure")
    L.append("- Per-trade EXPECTANCY reported, not WR alone (OP-14).")
    L.append("- IS=2025 AND OOS=2026; gate 9 (OOS-ALONE drop-top5) is the decisive de-concentration gate (L173).")
    L.append("- Random-entry null (L172) + no-truncation (L171) via fraud_gates.verify_candidate on the REFINED variant.")
    L.append("- NO-REGRESSION: the refinement may only drop net-negative/neutral DAYS; dropping any net-winning day FAILS.")
    L.append("- Both validated tiers reported (ATM Safe-2 + ITM-2 Bold); C29 — knobs do not transfer across tiers.")
    L.append("- Edge#4 regime cut held FIXED (B5 robust cell) so B8 isolates the entry-refinement effect.")
    L.append("- Real OPRA fills; SPY-direction != option edge (C3/L58); WR is a theta trap (OP-14).")
    L.append("- LIVE_EDGE_IMPROVEMENT iff refined lifts OOS per-trade AND clears all 9 gates AND passes no-regression.")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
