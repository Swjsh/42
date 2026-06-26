"""B8 — ANCHORED-VWAP structural setups (Angle A, a NEW anchor never real-fills-tested).

Session-VWAP (the basis of the 3 shipped VWAP edges) is anchored at the RTH open.
ANCHORED-VWAP (aVWAP) re-anchors the cumulative typical-price*volume sum at a chosen
EVENT bar — prior-day high (PDH), prior-day low (PDL), prior-day close (PDC), or the most
recent significant intraday swing high/low — and accumulates FORWARD from that anchor.
Reading aVWAP at the current bar uses only bars[anchor..i] => causal, no look-ahead.

The anchor LEVEL (PDH/PDL/PDC price) is a static prior-day fact. The anchor BAR in today's
session is the first RTH bar whose range straddles/crosses that level (low<=level<=high).
From that bar forward we compute aVWAP; the level then acts as a dynamic with-trend S/R.

THREE one-causal-entry/day STRUCTURAL setups (next-bar-open fill, no look-ahead):

  (A1) RECLAIM-AND-HOLD aVWAP-from-PDL (bullish continuation).  On an UP day (first 3 RTH
       closes above session VWAP), price reclaims the PDL-anchored aVWAP from below and the
       NEXT bar HOLDS above it (close>aVWAP AND extends past the reclaim bar high). Entry =
       the hold bar, side C. With-trend continuation off the anchored level.

  (A2) REJECT aVWAP-from-PDH AND CONTINUE DOWN (bearish continuation).  On a DOWN day (first
       3 RTH closes below session VWAP), price tags the PDH-anchored aVWAP from below
       (high>=aVWAP) and the NEXT bar REJECTS (close<aVWAP AND makes a new low past the tag
       bar low). Entry = the rejection bar, side P.

  (A3) aVWAP-FROM-PRIOR-SWING dynamic S/R RETEST.  Anchor at the most recent significant
       intraday swing (3-bar fractal H/L formed before the entry window). In the established
       day-trend (first 3 closes vs session VWAP), price RETESTS the swing-anchored aVWAP
       (touch) and the NEXT bar RESUMES with-trend (close back with-trend AND extends past
       the touch-bar with-trend extreme). Entry = the resume bar, side = day-trend side.

THE 9-GATE BAR (every cell, both tiers, both sides — no cherry-pick, anti-pattern 2.10):
  1 OOS-2026/tr > 0   2 positive_quarters >= 4/6   3 top5-day < 200% (full)   4 n >= 20
  5 full drop-top5 > 0   6 IS-2025 first-half /tr > 0   7 beats random-null (L172)
  8 no-truncation (L171)   9 OOS-ALONE drop-top5 > 0 (L173, decisive)

Reuses the validated B7 sim/metrics/gate machinery byte-for-byte (simulate_cell, evaluate,
map_candidate_signals, gate_cell, verify_candidate) so nothing drifts (C14). Real OPRA fills
only (C1). Tiers ATM (Safe-2) + ITM-2 (Bold) (C29). Both sides. -8% tight stop + chart stop.

INDEPENDENCE CHECK (task requirement): most VWAP variants beyond the 3 shipped overlap the
LIVE #1 (vwap_continuation). For each shape we compute day-overlap vs #1's signal days; if a
shape shares >80% of its entry DAYS with #1 it is NOT materially independent and is flagged
not_independent even if it clears gates. EDGE only if all 9 gates clear AND overlap<=80%.

Pure Python, $0 (no LLM in the sim loop). No live orders. Markets closed (weekend/RESEARCH).
Writes analysis/recommendations/B8-ANCHORED-VWAP-SCORECARD.{md,json} (REAL numbers, C7).
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b8_anchored_vwap.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
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
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _align_vix,
    _normalize_spy,
    detect_signals as detect_vwap_continuation,  # the LIVE #1 detector (for overlap check)
)
from autoresearch._b7_vwap_structures import (  # noqa: E402  (REUSE validated machinery)
    NULL_SEEDS,
    PREMIUM_STOP_PCT,
    QTY,
    SIDES,
    TIERS,
    evaluate,
    gate_cell,
    map_candidate_signals,
    simulate_cell,
)
from autoresearch.fraud_gates import verify_candidate  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    DayCtx,
    Signal,
    build_day_contexts,
    session_vwap_asof,
)

OUT_MD = ROOT / "analysis" / "recommendations" / "B8-ANCHORED-VWAP-SCORECARD.md"
OUT_JSON = ROOT / "analysis" / "recommendations" / "B8-ANCHORED-VWAP-SCORECARD.json"

TREND_BARS = 3
ENTRY_CUTOFF = dt.time(11, 0)        # one causal morning entry per day
SWING_FRACTAL = 1                    # 3-bar fractal (1 bar each side) for A3 swing anchor
OVERLAP_MAX = 0.80                   # >80% day-overlap with #1 => not materially independent
OOS_YEAR = 2026
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)


# ════════════════════════════════════════════════════════════════════════════════
# PRIOR-DAY LEVELS (static prior-day facts) — PDH / PDL / PDC per trading day.
# Computed from the FULL prior session (all bars that day), look-ahead-safe: a day's
# anchor levels come only from strictly-earlier days.
# ════════════════════════════════════════════════════════════════════════════════
def prior_day_levels(spy: pd.DataFrame) -> dict[dt.date, dict[str, float]]:
    """Map date -> {pdh, pdl, pdc} using the immediately-preceding trading day's bars."""
    out: dict[dt.date, dict[str, float]] = {}
    prev: Optional[dict[str, float]] = None
    for d, day in spy.groupby("date", sort=True):
        if prev is not None:
            out[d] = prev
        prev = {
            "pdh": float(day["high"].max()),
            "pdl": float(day["low"].min()),
            "pdc": float(day["close"].iloc[-1]),
        }
    return out


# ════════════════════════════════════════════════════════════════════════════════
# ANCHORED VWAP — re-anchor cumulative TP*vol at `anchor_pos` (positional index into
# the rth slice). aVWAP[i] for i>=anchor uses only bars[anchor..i] => causal.
# For i<anchor it is NaN (the anchor hasn't happened yet).
# ════════════════════════════════════════════════════════════════════════════════
def anchored_vwap(rth: pd.DataFrame, anchor_pos: int) -> np.ndarray:
    high = rth["high"].values
    low = rth["low"].values
    close = rth["close"].values
    vol = rth["volume"].values
    n = len(rth)
    out = np.full(n, np.nan)
    tp = (high + low + close) / 3.0
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(anchor_pos, n):
        cum_pv += tp[i] * vol[i]
        cum_v += vol[i]
        out[i] = (cum_pv / cum_v) if cum_v > 0 else tp[i]
    return out


def _trend_side(closes, vwap, n) -> Optional[str]:
    head_c, head_v = closes[:n], vwap[:n]
    if len(head_c) < n:
        return None
    if np.all(head_c > head_v):
        return "C"
    if np.all(head_c < head_v):
        return "P"
    return None


def _first_cross_pos(rth: pd.DataFrame, level: float, start: int) -> Optional[int]:
    """First positional bar at/after `start` whose range straddles `level`."""
    high = rth["high"].values
    low = rth["low"].values
    for i in range(start, len(rth)):
        if low[i] <= level <= high[i]:
            return i
    return None


# ════════════════════════════════════════════════════════════════════════════════
# DETECTORS — one causal Signal/day. bar_idx = GLOBAL spy index (entry = next bar).
# Each takes (days, pdl_map). pdl_map: date -> {pdh,pdl,pdc}.
# ════════════════════════════════════════════════════════════════════════════════
def detect_reclaim_pdl_avwap(days: list[DayCtx], lv: dict) -> list[Signal]:
    """A1: UP day; reclaim PDL-anchored aVWAP from below; NEXT bar holds + extends. side C."""
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        info = lv.get(dc.date)
        if info is None or len(rth) < TREND_BARS + 3:
            continue
        svwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        if _trend_side(closes, svwap, TREND_BARS) != "C":
            continue
        anchor = _first_cross_pos(rth, info["pdl"], 0)
        if anchor is None:
            continue
        av = anchored_vwap(rth, anchor)
        for j in range(max(TREND_BARS, anchor + 1), len(rth) - 1):
            if times[j] > ENTRY_CUTOFF:
                break
            a = av[j]
            if np.isnan(a) or a <= 0:
                continue
            reclaim = closes[j - 1] <= av[j - 1] and closes[j] > a   # cross up through aVWAP
            k = j + 1
            hold = closes[k] > av[k] and highs[k] > highs[j]
            if reclaim and hold and times[k] <= ENTRY_CUTOFF:
                stop = float(np.min(lows[: k + 1]))
                out.append(Signal(bar_idx=int(idxs[k]), side="C", stop_level=stop,
                                  note="avwap_reclaim_pdl"))
                break
    return out


def detect_reject_pdh_avwap(days: list[DayCtx], lv: dict) -> list[Signal]:
    """A2: DOWN day; tag PDH-anchored aVWAP from below; NEXT bar rejects + new low. side P."""
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        info = lv.get(dc.date)
        if info is None or len(rth) < TREND_BARS + 3:
            continue
        svwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        if _trend_side(closes, svwap, TREND_BARS) != "P":
            continue
        anchor = _first_cross_pos(rth, info["pdh"], 0)
        if anchor is None:
            continue
        av = anchored_vwap(rth, anchor)
        for j in range(max(TREND_BARS, anchor + 1), len(rth) - 1):
            if times[j] > ENTRY_CUTOFF:
                break
            a = av[j]
            if np.isnan(a) or a <= 0:
                continue
            tag = highs[j] >= a and closes[j] < a    # poked the anchored level, closed below
            k = j + 1
            reject = closes[k] < av[k] and lows[k] < lows[j]
            if tag and reject and times[k] <= ENTRY_CUTOFF:
                stop = float(np.max(highs[: k + 1]))
                out.append(Signal(bar_idx=int(idxs[k]), side="P", stop_level=stop,
                                  note="avwap_reject_pdh"))
                break
    return out


def detect_swing_avwap_retest(days: list[DayCtx], lv: dict) -> list[Signal]:
    """A3: anchor aVWAP at most-recent 3-bar swing; retest+resume with day-trend. side=trend."""
    out: list[Signal] = []
    f = SWING_FRACTAL
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 4:
            continue
        svwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        side = _trend_side(closes, svwap, TREND_BARS)
        if side is None:
            continue
        for j in range(TREND_BARS, len(rth) - 1):
            if times[j] > ENTRY_CUTOFF:
                break
            # most-recent CONFIRMED swing strictly before j (fractal needs f bars each side;
            # the right-side bars must all be <= j-1 so it is causal at bar j).
            anchor = None
            for c in range(j - 1 - f, f - 1, -1):
                if side == "C":
                    # swing LOW (support) to anchor a bullish retest
                    if lows[c] == min(lows[c - f: c + f + 1]) and lows[c] < lows[c - 1] and lows[c] < lows[c + 1]:
                        anchor = c
                        break
                else:
                    if highs[c] == max(highs[c - f: c + f + 1]) and highs[c] > highs[c - 1] and highs[c] > highs[c + 1]:
                        anchor = c
                        break
            if anchor is None:
                continue
            av = anchored_vwap(rth, anchor)
            a = av[j]
            if np.isnan(a) or a <= 0:
                continue
            if side == "C":
                touched = lows[j] <= a
                k = j + 1
                resume = closes[k] > av[k] and highs[k] > highs[j]
                stop = float(np.min(lows[: k + 1]))
            else:
                touched = highs[j] >= a
                k = j + 1
                resume = closes[k] < av[k] and lows[k] < lows[j]
                stop = float(np.max(highs[: k + 1]))
            if touched and resume and times[k] <= ENTRY_CUTOFF:
                out.append(Signal(bar_idx=int(idxs[k]), side=side, stop_level=stop,
                                  note="avwap_swing_retest"))
                break
    return out


DETECTORS: dict[str, Callable[[list[DayCtx], dict], list[Signal]]] = {
    "A1_reclaim_pdl_avwap": detect_reclaim_pdl_avwap,
    "A2_reject_pdh_avwap": detect_reject_pdh_avwap,
    "A3_swing_avwap_retest": detect_swing_avwap_retest,
}


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"[b8] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    rth = spy[(spy["t"] >= dt.time(9, 30)) & (spy["t"] < dt.time(16, 0))].reset_index(drop=True)
    lv = prior_day_levels(spy)
    print(f"[b8] trading_days={n_days} window={spy['timestamp_et'].iloc[0].date()}.."
          f"{spy['timestamp_et'].iloc[-1].date()}  prior-day levels for {len(lv)} days", flush=True)

    # LIVE #1 signal days for the independence/overlap check.
    c1_signals = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    c1_days = {spy.iloc[s.bar_idx]["timestamp_et"].date() for s in c1_signals}
    print(f"[b8] LIVE #1 vwap_continuation: {len(c1_signals)} signals on {len(c1_days)} days "
          f"(overlap reference)", flush=True)

    results = {}
    for sname, det in DETECTORS.items():
        signals = det(days, lv)
        sig_day_set = {spy.iloc[s.bar_idx]["timestamp_et"].date() for s in signals}
        sig_days = len(sig_day_set)
        side_ct = {"C": sum(1 for s in signals if s.side == "C"),
                   "P": sum(1 for s in signals if s.side == "P")}
        fire_pct = round(100 * sig_days / n_days, 1) if n_days else 0.0
        shared = sig_day_set & c1_days
        overlap = round(len(shared) / sig_days, 3) if sig_days else 0.0
        independent = overlap <= OVERLAP_MAX
        print(f"\n[b8] {sname}: signals={len(signals)} on {sig_days} days "
              f"({fire_pct}% of {n_days}) side={side_ct}  "
              f"overlap_vs_#1={overlap} ({len(shared)}/{sig_days}) "
              f"independent={independent}", flush=True)
        cells = []
        for tier_name, so in TIERS.items():
            for side in SIDES:
                rows, cov = simulate_cell(signals, spy, vix, strike_offset=so,
                                          premium_stop_pct=PREMIUM_STOP_PCT, side_filter=side)
                m = evaluate(rows)
                if m["n"] == 0:
                    cells.append({"tier": tier_name, "strike_offset": so, "side": side,
                                  "metrics": m, "coverage": cov, "clears": False,
                                  "gates": {}, "fails": ["no_fills"], "independent": independent})
                    print(f"  {tier_name:>5} {side:>4}: n=0 (no fills)", flush=True)
                    continue
                cand = map_candidate_signals(signals, spy, rth, side)
                fraud = verify_candidate(cand, rth, strike_offset=so,
                                         premium_stop_pct=PREMIUM_STOP_PCT, qty=QTY,
                                         setup=f"B8_{sname}", seeds=NULL_SEEDS)
                clears_gates, gates, fails = gate_cell(m, fraud)
                # EDGE requires all 9 gates AND material independence from #1.
                clears = clears_gates and independent
                if clears_gates and not independent:
                    fails = fails + [f"overlap_vs_#1={overlap}>{OVERLAP_MAX}"]
                cells.append({
                    "tier": tier_name, "strike_offset": so, "side": side,
                    "metrics": m, "coverage": cov, "fraud": fraud.as_dict(),
                    "gates": gates, "clears_gates": clears_gates,
                    "independent": independent, "clears": clears, "fails": fails,
                })
                print(f"  {tier_name:>5} {side:>4}: n={m['n']:>3} oos/tr=${m['oos_per_trade']} "
                      f"dropT5_full=${m['drop_top5_full']} dropT5_OOS=${m['drop_top5_oos']} "
                      f"posQ={m['positive_quarters']}/{m['n_quarters']} "
                      f"null={fraud.null_pass} notrunc={fraud.no_truncation_pass} "
                      f"-> {'EDGE' if clears else 'fails:'+','.join(fails)}", flush=True)
        results[sname] = {
            "n_signals": len(signals), "fire_day_pct": fire_pct, "side_count": side_ct,
            "overlap_vs_1": overlap, "overlap_shared_days": len(shared),
            "independent": independent, "cells": cells,
        }

    edges = [(sn, c) for sn, r in results.items() for c in r["cells"] if c["clears"]]
    # also surface "gates-only" passers blocked solely by overlap (honest disclosure)
    gates_only = [(sn, c) for sn, r in results.items() for c in r["cells"]
                  if c.get("clears_gates") and not c.get("independent")]
    summary = {
        "campaign": "B8 — anchored-VWAP structural setups (Angle A, new anchor)",
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "trading_days": n_days,
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR}",
        "gates": "9-gate bar incl OOS-ALONE drop-top5 (L173) + random-null (L172) + no-trunc (L171) + independence-vs-#1",
        "independence_check": f"day-overlap vs LIVE #1 vwap_continuation; EDGE requires overlap<={OVERLAP_MAX}",
        "live_1_signal_days": len(c1_days),
        "anchors": "A1=PDL-anchored aVWAP, A2=PDH-anchored aVWAP, A3=prior-swing-anchored aVWAP",
        "tiers": TIERS, "premium_stop_pct": PREMIUM_STOP_PCT, "qty": QTY,
        "results": results,
        "n_edges": len(edges),
        "edges": [{"shape": sn, "tier": c["tier"], "side": c["side"],
                   "oos_per_trade": c["metrics"]["oos_per_trade"],
                   "oos_drop_top5": c["metrics"]["drop_top5_oos"],
                   "overlap_vs_1": r_overlap(results, sn)} for sn, c in edges],
        "n_gates_only_blocked_by_overlap": len(gates_only),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_md(summary)
    print(f"\n[b8] wrote {OUT_JSON}\n[b8] wrote {OUT_MD}", flush=True)
    print(f"\n=== B8 VERDICT: {len(edges)} cell(s) clear all 9 gates AND are independent of #1 ===")
    for sn, c in edges:
        print(f"  EDGE: {sn} {c['tier']} {c['side']} oos/tr=${c['metrics']['oos_per_trade']} "
              f"oos_dropT5=${c['metrics']['drop_top5_oos']}")
    if not edges:
        print("  NONE (expected - most VWAP variants die on theta or overlap the live #1).")
    if gates_only:
        print(f"  ({len(gates_only)} cell(s) cleared all 9 gates but were blocked by >80% overlap with #1)")
    return 0


def r_overlap(results: dict, sname: str) -> float:
    return results[sname]["overlap_vs_1"]


def write_md(s: dict) -> None:
    L = []
    L.append("# B8 — Anchored-VWAP Structural Setups (Angle A) — Scorecard\n")
    L.append(f"- Run: {s['run_date']}  |  Window: {s['window']}  |  Trading days: {s['trading_days']}")
    L.append(f"- Fills: {s['fills_authority']}")
    L.append(f"- OOS split: {s['oos_split']}")
    L.append(f"- Anchors: {s['anchors']}")
    L.append(f"- Gate bar: {s['gates']}")
    L.append(f"- Independence: {s['independence_check']}  (LIVE #1 fires on {s['live_1_signal_days']} days)")
    L.append(f"- Tiers: {s['tiers']}  |  premium_stop_pct: {s['premium_stop_pct']}  |  qty: {s['qty']}\n")
    L.append(f"## VERDICT: {s['n_edges']} cell(s) clear ALL 9 gates AND are independent of #1\n")
    if s["edges"]:
        for e in s["edges"]:
            L.append(f"- **EDGE** {e['shape']} / {e['tier']} / {e['side']} — "
                     f"OOS/tr ${e['oos_per_trade']}, OOS-drop-top5 ${e['oos_drop_top5']}, "
                     f"overlap-vs-#1 {e['overlap_vs_1']}")
    else:
        L.append("- **NONE** — no cell clears all 9 gates while staying independent of the live #1. "
                 "Anchored-VWAP variants either die on theta (C3/L58: SPY-price edge != option edge; "
                 "WR is a theta trap, OP-14) or simply re-detect the same days the shipped "
                 "session-VWAP continuation already trades.")
    if s.get("n_gates_only_blocked_by_overlap"):
        L.append(f"- NOTE: {s['n_gates_only_blocked_by_overlap']} cell(s) cleared all 9 gates but were "
                 f"blocked by >80% day-overlap with the live #1 (not materially independent).")
    L.append("")
    for sn, r in s["results"].items():
        L.append(f"## {sn}")
        L.append(f"- signals={r['n_signals']}  fires {r['fire_day_pct']}% of days  side={r['side_count']}")
        L.append(f"- overlap vs LIVE #1: {r['overlap_vs_1']} ({r['overlap_shared_days']} shared days)  "
                 f"=> independent={r['independent']}\n")
        L.append("| tier | side | n | OOS/tr | dropT5_full | dropT5_OOS | top5%_full | posQ | null | notrunc | gates | indep | EDGE | fails |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for c in r["cells"]:
            m = c["metrics"]
            fr = c.get("fraud", {})
            L.append(f"| {c['tier']} | {c['side']} | {m.get('n')} | "
                     f"{m.get('oos_per_trade')} | {m.get('drop_top5_full')} | {m.get('drop_top5_oos')} | "
                     f"{m.get('top5_day_pct_full')} | {m.get('positive_quarters')}/{m.get('n_quarters')} | "
                     f"{fr.get('null_pass')} | {fr.get('no_truncation_pass')} | "
                     f"{'YES' if c.get('clears_gates') else 'no'} | {'YES' if c.get('independent') else 'no'} | "
                     f"{'YES' if c['clears'] else 'no'} | {','.join(c['fails']) if c['fails'] else '-'} |")
        L.append("")
    L.append("## Disclosure")
    L.append("- Per-trade EXPECTANCY reported, not WR alone (OP-14).")
    L.append("- IS=2025 AND OOS=2026; gate 9 (OOS-ALONE drop-top5) is the decisive de-concentration gate (L173).")
    L.append("- Random-entry null (L172) + no-truncation (L171) via fraud_gates.verify_candidate.")
    L.append("- aVWAP is causal: re-anchored cumulative TP*vol accumulated FORWARD from the anchor bar only.")
    L.append("- Independence vs LIVE #1 (vwap_continuation) by entry-DAY overlap; EDGE requires <=80% overlap.")
    L.append("- Both tiers (ATM Safe-2 + ITM-2 Bold, C29) + both sides reported, no survivor cherry-pick (2.10).")
    L.append("- Real OPRA fills; SPY-direction != option edge (C3/L58).")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
