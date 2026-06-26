"""B7 — NEW VWAP-NATIVE STRUCTURAL SHAPES (the proven-alive vein).

ANGLE A of the edge-hunt campaign. Three of three surviving 0DTE edges are VWAP-native
(continuation, failed-break->reclaim, vix-regime-dayside). ~42 mechanical families died;
only VWAP-native / selective shapes live. This script designs + real-fills-tests 2-3 NEW
one-causal-entry/day VWAP-native structures that are STRUCTURALLY DISTINCT from the three
already shipped:

  #1 vwap_continuation         = morning established-trend, first in-trend continuation bar
  #2 vwap_reclaim_failed_break = counter-trend break of VWAP then reclaim back with-trend
  #4 vix_regime_dayside        = day-trend-side + VIX regime

THE THREE NEW SHAPES (each one causal entry/day, next-bar-open fill, no look-ahead):

  (S1) VWAP TOUCH-AND-GO  — in an established morning trend (first 3 RTH closes all the
       same side of as-of VWAP), price PULLS BACK to actually TOUCH session VWAP (the bar
       low<=VWAP for a call day / bar high>=VWAP for a put day) and then the NEXT bar
       RESUMES with-trend (closes back on the trend side AND extends past the touch bar's
       with-trend extreme). Entry = the resumption bar. DISTINCT from #1, which fires on
       the first continuation and does NOT require an actual VWAP touch (its "dip" is a
       shallow tolerance band, not a touch+resume two-bar sequence).

  (S2) VWAP STDEV-BAND RIDE — price holds OUTSIDE the +/-1 sigma session-VWAP band for
       >=2 consecutive bars on the trend side (a band-walk), entry on the confirmation
       (2nd) bar. The band is the running stdev of (close - vwap) computed as-of (causal).
       DISTINCT from #1/#2: it is a VOLATILITY-EXPANSION trend-strength shape, not a
       pullback/reclaim shape.

  (S3) OPENING-DRIVE-FROM-VWAP — the first OPENING_WINDOW (15 min = 3 bars) makes a
       directional drive measured vs VWAP; once price HOLDS above/below VWAP (close on the
       drive side for 2 straight bars AND the drive-side extreme keeps extending) AFTER the
       opening window, enter the drive direction. DISTINCT from #1: #1's "side" is decided
       by the first 3 closes vs VWAP; S3 measures the magnitude of an opening DRIVE and
       requires a hold-and-extend confirmation past the opening window, a momentum-of-open
       shape rather than a generic continuation.

THE 9-GATE BAR (every cell, both tiers, both sides — no cherry-pick, anti-pattern 2.10):
  1 OOS-2026/tr > 0
  2 positive_quarters >= 4/6
  3 top5-day < 200% (full sample)
  4 n >= 20
  5 full-sample drop-top5 > 0           (necessary, NOT sufficient — L173)
  6 IS-2025 first-half per-trade > 0
  7 beats random-entry null (L172)      via fraud_gates.verify_candidate
  8 no-truncation (L171, sign stable)   via fraud_gates.verify_candidate
  9 OOS-ALONE drop-top5 > 0             (the B6/L173 decisive de-concentration gate)

Tiers (C29 — knobs do NOT transfer across strike tiers): ATM (Safe-2) AND ITM-2 (Bold).
Stop: -8% tight premium stop + chart-stop level. Both sides. Real OPRA fills only (C1):
lib.simulator_real.simulate_trade_real. Pure Python, $0. No live orders. Markets closed.

Writes analysis/recommendations/B7-VWAP-STRUCTURES-SCORECARD.md (REAL numbers, C7).
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b7_vwap_structures.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
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
)
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

OUT_MD = ROOT / "analysis" / "recommendations" / "B7-VWAP-STRUCTURES-SCORECARD.md"
OUT_JSON = ROOT / "analysis" / "recommendations" / "B7-VWAP-STRUCTURES-SCORECARD.json"

# ── Shared detector params ──────────────────────────────────────────────────────
TREND_BARS = 3
ENTRY_CUTOFF = dt.time(11, 0)        # one causal entry per day, morning only
OPENING_WINDOW_BARS = 3              # 15 min (S3)
MAX_STRIKE_STEPS = 4
QTY = 3
PREMIUM_STOP_PCT = -0.08            # the v15 tight stop under test
CHART_STOP_ONLY = -0.99

# Tiers (C29): test BOTH independently.
TIERS = {"ATM": 0, "ITM2": -2}
SIDES = ("BOTH", "C", "P")

OOS_YEAR = 2026
NULL_SEEDS = 20

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# 9-gate bar constants
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0


# ════════════════════════════════════════════════════════════════════════════════
# DETECTORS — three NEW VWAP-native structural shapes. Each returns one causal
# Signal/day at most. bar_idx is the GLOBAL spy index (entry = next bar, sim handles).
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


def detect_touch_and_go(days: list[DayCtx]) -> list[Signal]:
    """S1: established trend -> price TOUCHES VWAP -> next bar RESUMES with-trend."""
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
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
        # walk bars; a TOUCH bar then the FOLLOWING bar must resume with-trend.
        for j in range(TREND_BARS, len(rth) - 1):
            if times[j] > ENTRY_CUTOFF:
                break
            v = vwap[j]
            if v <= 0:
                continue
            if side == "C":
                touched = lows[j] <= v               # pulled back to touch VWAP
                k = j + 1
                resume = closes[k] > vwap[k] and highs[k] > highs[j]
                stop = float(np.min(lows[:k + 1]))
            else:
                touched = highs[j] >= v
                k = j + 1
                resume = closes[k] < vwap[k] and lows[k] < lows[j]
                stop = float(np.max(highs[:k + 1]))
            if touched and resume and times[k] <= ENTRY_CUTOFF:
                out.append(Signal(bar_idx=int(idxs[k]), side=side, stop_level=stop,
                                  note="vwap_touch_and_go"))
                break
    return out


def detect_band_ride(days: list[DayCtx]) -> list[Signal]:
    """S2: price holds OUTSIDE +/-1 sigma session-VWAP band >=2 bars with-trend."""
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            continue
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        lows = rth["low"].values
        highs = rth["high"].values
        side = _trend_side(closes, vwap, TREND_BARS)
        if side is None:
            continue
        # causal running stdev of (close - vwap) up to and including each bar.
        dev = closes - vwap
        for j in range(TREND_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            v = vwap[j]
            if v <= 0:
                continue
            sigma = float(np.std(dev[: j + 1]))     # as-of, causal
            if sigma <= 0:
                continue
            if side == "C":
                upper = vwap[j] + sigma
                upper_prev = vwap[j - 1] + float(np.std(dev[:j]))
                band_walk = closes[j] > upper and closes[j - 1] > upper_prev
                stop = float(np.min(lows[:j + 1]))
            else:
                lower = vwap[j] - sigma
                lower_prev = vwap[j - 1] - float(np.std(dev[:j]))
                band_walk = closes[j] < lower and closes[j - 1] < lower_prev
                stop = float(np.max(highs[:j + 1]))
            if band_walk:
                out.append(Signal(bar_idx=int(idxs[j]), side=side, stop_level=stop,
                                  note="vwap_band_ride"))
                break
    return out


def detect_opening_drive(days: list[DayCtx]) -> list[Signal]:
    """S3: opening 15-min drive vs VWAP -> hold-and-extend confirmation post-window."""
    out: list[Signal] = []
    for dc in days:
        rth = dc.rth
        if len(rth) < OPENING_WINDOW_BARS + 3:
            continue
        vwap = session_vwap_asof(rth).values
        closes = rth["close"].values
        highs = rth["high"].values
        lows = rth["low"].values
        opens = rth["open"].values
        times = rth["t"].values
        idxs = rth.index.tolist()
        # drive measured over the opening window vs where VWAP sits at window end.
        w = OPENING_WINDOW_BARS - 1
        v_w = vwap[w]
        if v_w <= 0:
            continue
        drive = closes[w] - opens[0]
        drive_frac = drive / opens[0]
        # require a real opening drive (>= 0.10% net) and price on drive side of VWAP.
        if abs(drive_frac) < 0.0010:
            continue
        side = "C" if (drive > 0 and closes[w] > v_w) else ("P" if (drive < 0 and closes[w] < v_w) else None)
        if side is None:
            continue
        # confirmation AFTER the opening window: 2 straight closes on drive side of VWAP
        # AND the drive-side extreme keeps extending. Entry = the confirmation bar.
        for j in range(OPENING_WINDOW_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            v = vwap[j]
            if v <= 0:
                continue
            if side == "C":
                hold = closes[j] > v and closes[j - 1] > vwap[j - 1]
                extend = highs[j] >= float(np.max(highs[:j]))
                stop = float(np.min(lows[:j + 1]))
            else:
                hold = closes[j] < v and closes[j - 1] < vwap[j - 1]
                extend = lows[j] <= float(np.min(lows[:j]))
                stop = float(np.max(highs[:j + 1]))
            if hold and extend:
                out.append(Signal(bar_idx=int(idxs[j]), side=side, stop_level=stop,
                                  note="vwap_opening_drive"))
                break
    return out


DETECTORS: dict[str, Callable[[list[DayCtx]], list[Signal]]] = {
    "S1_vwap_touch_and_go": detect_touch_and_go,
    "S2_vwap_band_ride": detect_band_ride,
    "S3_vwap_opening_drive": detect_opening_drive,
}


# ════════════════════════════════════════════════════════════════════════════════
# REAL-FILLS SIM + METRICS
# ════════════════════════════════════════════════════════════════════════════════
def simulate_cell(signals, spy, vix, *, strike_offset, premium_stop_pct, side_filter):
    """Run signals at one (strike, stop, side) cell on real OPRA fills. Returns rows."""
    rows = []
    n_cache_miss = n_sim_none = 0
    for sg in signals:
        if side_filter != "BOTH" and sg.side != side_filter:
            continue
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
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "b7"],
            side=sg.side, qty=QTY, setup="B7_VWAP", strike_override=strike,
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
    top5 = set(d for d, _ in sorted(day_tot.items(), key=lambda kv: kv[1], reverse=True)[:5])
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
    """Gate 6: per-trade over the FIRST HALF of the IS (2025) trading days."""
    is_rows = [r for r in rows if int(r["date"][:4]) != OOS_YEAR]
    if not is_rows:
        return None
    is_days = sorted({r["date"] for r in is_rows})
    half = is_days[: max(1, len(is_days) // 2)]
    half_set = set(half)
    first = [r["pnl"] for r in is_rows if r["date"] in half_set]
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
        "is_n": len(is_rows), "is_per_trade": _per_trade(is_rows),
        "oos_n": len(oos_rows), "oos_per_trade": _per_trade(oos_rows),
        "drop_top5_full": _drop_top5_per_trade(rows),
        "drop_top5_oos": _drop_top5_per_trade(oos_rows),     # gate 9 (decisive)
        "top5_day_pct_full": _top5_day_pct(rows),
        "top5_day_pct_oos": _top5_day_pct(oos_rows),
        "is_first_half_per_trade": _is_first_half_per_trade(rows),
        "positive_quarters": pos_q, "n_quarters": len(quarters),
        "quarters": quarters,
        "wr_pct": round(100 * sum(1 for r in rows if r["pnl"] > 0) / n, 1) if n else None,
    }


def map_candidate_signals(signals, spy, rth, side_filter):
    """Build CandidateSignal list indexed into the RTH-reset frame for fraud_gates."""
    out = []
    for s in signals:
        if side_filter != "BOTH" and s.side != side_filter:
            continue
        ts = spy.iloc[s.bar_idx]["timestamp_et"]
        match = rth.index[rth["timestamp_et"] == ts]
        if len(match) == 0:
            continue
        out.append(CandidateSignal(bar_idx=int(match[0]), side=s.side,
                                   rejection_level=float(s.stop_level),
                                   note=s.note or "b7"))
    return out


def gate_cell(m: dict, fraud) -> tuple[bool, dict, list[str]]:
    """Apply all 9 gates. Returns (clears, gate_map, fails)."""
    g = {
        "1_oos_pt_gt0": bool(m["oos_per_trade"] is not None and m["oos_per_trade"] > 0),
        "2_pos_q_ge4of6": bool(m["positive_quarters"] >= BAR_POS_Q and m["n_quarters"] >= 6),
        "3_top5_full_lt200": bool(m["top5_day_pct_full"] is not None and m["top5_day_pct_full"] < BAR_TOP5),
        "4_n_ge20": bool(m["n"] >= BAR_N),
        "5_drop_top5_full_gt0": bool(m["drop_top5_full"] is not None and m["drop_top5_full"] > 0),
        "6_is_first_half_pt_gt0": bool(m["is_first_half_per_trade"] is not None and m["is_first_half_per_trade"] > 0),
        "7_beats_random_null": bool(fraud.null_pass),
        "8_no_truncation": bool(fraud.no_truncation_pass),
        "9_oos_drop_top5_gt0": bool(m["drop_top5_oos"] is not None and m["drop_top5_oos"] > 0),
    }
    fails = [k for k, v in g.items() if not v]
    return (len(fails) == 0, g, fails)


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"[b7] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    rth = spy[(spy["t"] >= dt.time(9, 30)) & (spy["t"] < dt.time(16, 0))].reset_index(drop=True)
    print(f"[b7] trading_days={n_days} window={spy['timestamp_et'].iloc[0].date()}.."
          f"{spy['timestamp_et'].iloc[-1].date()}", flush=True)

    results = {}
    for sname, det in DETECTORS.items():
        signals = det(days)
        sig_days = len({spy.iloc[s.bar_idx]["timestamp_et"].date() for s in signals})
        side_ct = {"C": sum(1 for s in signals if s.side == "C"),
                   "P": sum(1 for s in signals if s.side == "P")}
        fire_pct = round(100 * sig_days / n_days, 1) if n_days else 0.0
        print(f"\n[b7] {sname}: signals={len(signals)} on {sig_days} days "
              f"({fire_pct}% of {n_days}) side={side_ct}", flush=True)
        cells = []
        for tier_name, so in TIERS.items():
            for side in SIDES:
                rows, cov = simulate_cell(signals, spy, vix, strike_offset=so,
                                          premium_stop_pct=PREMIUM_STOP_PCT, side_filter=side)
                m = evaluate(rows)
                if m["n"] == 0:
                    cells.append({"tier": tier_name, "strike_offset": so, "side": side,
                                  "metrics": m, "coverage": cov, "clears": False,
                                  "gates": {}, "fails": ["no_fills"]})
                    print(f"  {tier_name:>5} {side:>4}: n=0 (no fills)", flush=True)
                    continue
                cand = map_candidate_signals(signals, spy, rth, side)
                fraud = verify_candidate(cand, rth, strike_offset=so,
                                         premium_stop_pct=PREMIUM_STOP_PCT, qty=QTY,
                                         setup=f"B7_{sname}", seeds=NULL_SEEDS)
                clears, gates, fails = gate_cell(m, fraud)
                cells.append({
                    "tier": tier_name, "strike_offset": so, "side": side,
                    "metrics": m, "coverage": cov,
                    "fraud": fraud.as_dict(),
                    "gates": gates, "clears": clears, "fails": fails,
                })
                print(f"  {tier_name:>5} {side:>4}: n={m['n']:>3} oos/tr=${m['oos_per_trade']} "
                      f"dropT5_full=${m['drop_top5_full']} dropT5_OOS=${m['drop_top5_oos']} "
                      f"posQ={m['positive_quarters']}/{m['n_quarters']} "
                      f"null={fraud.null_pass} notrunc={fraud.no_truncation_pass} "
                      f"-> {'EDGE' if clears else 'fails:'+','.join(fails)}", flush=True)
        results[sname] = {
            "n_signals": len(signals), "fire_day_pct": fire_pct, "side_count": side_ct,
            "cells": cells,
        }

    # ── verdict aggregation ─────────────────────────────────────────────────────
    edges = [(sn, c) for sn, r in results.items() for c in r["cells"] if c["clears"]]
    summary = {
        "campaign": "B7 — new VWAP-native structural shapes (Angle A)",
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "trading_days": n_days,
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR}",
        "gates": "9-gate bar incl OOS-ALONE drop-top5 (L173) + random-null (L172) + no-trunc (L171)",
        "tiers": TIERS, "premium_stop_pct": PREMIUM_STOP_PCT, "qty": QTY,
        "results": results,
        "n_edges": len(edges),
        "edges": [{"shape": sn, "tier": c["tier"], "side": c["side"],
                   "oos_per_trade": c["metrics"]["oos_per_trade"],
                   "oos_drop_top5": c["metrics"]["drop_top5_oos"]} for sn, c in edges],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_md(summary)
    print(f"\n[b7] wrote {OUT_JSON}\n[b7] wrote {OUT_MD}", flush=True)
    print(f"\n=== B7 VERDICT: {len(edges)} cell(s) clear all 9 gates ===")
    for sn, c in edges:
        print(f"  EDGE: {sn} {c['tier']} {c['side']} oos/tr=${c['metrics']['oos_per_trade']} "
              f"oos_dropT5=${c['metrics']['drop_top5_oos']}")
    if not edges:
        print("  NONE clear all 9 gates (expected — most VWAP variants die on theta).")
    return 0


def write_md(s: dict) -> None:
    L = []
    L.append("# B7 — New VWAP-Native Structural Shapes (Angle A) — Scorecard\n")
    L.append(f"- Run: {s['run_date']}  |  Window: {s['window']}  |  Trading days: {s['trading_days']}")
    L.append(f"- Fills: {s['fills_authority']}")
    L.append(f"- OOS split: {s['oos_split']}")
    L.append(f"- Gate bar: {s['gates']}")
    L.append(f"- Tiers: {s['tiers']}  |  premium_stop_pct: {s['premium_stop_pct']}  |  qty: {s['qty']}\n")
    L.append(f"## VERDICT: {s['n_edges']} cell(s) clear ALL 9 gates\n")
    if s["edges"]:
        for e in s["edges"]:
            L.append(f"- **EDGE** {e['shape']} / {e['tier']} / {e['side']} — "
                     f"OOS/tr ${e['oos_per_trade']}, OOS-drop-top5 ${e['oos_drop_top5']}")
    else:
        L.append("- **NONE** — no cell clears all 9 gates. Most VWAP variants die on theta "
                 "(C3/L58: SPY-price edge != option edge; WR is a theta trap, OP-14).")
    L.append("")
    for sn, r in s["results"].items():
        L.append(f"## {sn}")
        L.append(f"- signals={r['n_signals']}  fires {r['fire_day_pct']}% of days  side={r['side_count']}\n")
        L.append("| tier | side | n | OOS/tr | dropT5_full | dropT5_OOS | top5%_full | posQ | null | notrunc | clears | fails |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for c in r["cells"]:
            m = c["metrics"]
            fr = c.get("fraud", {})
            L.append(f"| {c['tier']} | {c['side']} | {m.get('n')} | "
                     f"{m.get('oos_per_trade')} | {m.get('drop_top5_full')} | {m.get('drop_top5_oos')} | "
                     f"{m.get('top5_day_pct_full')} | {m.get('positive_quarters')}/{m.get('n_quarters')} | "
                     f"{fr.get('null_pass')} | {fr.get('no_truncation_pass')} | "
                     f"{'YES' if c['clears'] else 'no'} | {','.join(c['fails']) if c['fails'] else '-'} |")
        L.append("")
    L.append("## Disclosure")
    L.append("- Per-trade EXPECTANCY reported, not WR alone (OP-14).")
    L.append("- IS=2025 AND OOS=2026; gate 9 (OOS-ALONE drop-top5) is the decisive de-concentration gate (L173).")
    L.append("- Random-entry null (L172) + no-truncation (L171) via fraud_gates.verify_candidate.")
    L.append("- Single fixed structure per cell; both tiers + both sides reported, no survivor cherry-pick (2.10).")
    L.append("- Real OPRA fills; SPY-direction != option edge (C3/L58).")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
