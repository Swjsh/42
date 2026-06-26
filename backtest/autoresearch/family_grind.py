"""Shared family-grind harness: matrix -> funnel -> consolidation for a NEW entry family.

Drives any detector from family_detectors through the SAME real-OPRA-fills pipeline the
ribbon mass-grind uses, WITHOUT touching the production orchestrator (no live/backtest
drift). Reuses simulate_trade_real (C1 real fills), null_baseline (C3/L58/L171 beat-the-
null), and mass_grind.qty_realizability (L180 live-cap realizability).

PIPELINE (per family, edgehunt-style 2-phase + null):
  PHASE 1 (matrix)  : STRIKE x STOP (7x8=56) with the default v15 exit bracket. Every cell
                      -> mass-grind-{family}-progress.jsonl with the full metric bundle +
                      the candidate-edge bar + the qty/cap realizability frontier.
  PHASE 2 (exit)    : on candidate-OOS-positive strike/stop cells, refine the exit
                      (tp1 x sell-fraction x chandelier) and keep the best by OOS total.
  PHASE 3 (funnel)  : P2 qpf>=.60 -> P3 qpf>=.75 + live-realizable + n>=20 + top5<200 ->
                      P4 random-entry NULL with the cell's MATCHING exit bracket. Each
                      P3 survivor -> mass-grind-{family}-funnel.jsonl with its verdict.
  CONSOLIDATE       : collapse P4 elites to distinct strike|stop setups, rank by
                      edge_over_null x qpf -> elite-consolidation-{family}.json.

PASS LADDER vs the ribbon grind (the one deliberate deviation, documented): the ribbon
mass-grind gates on OP-16 edge_capture >= 771. That floor is built on J's THREE bearish
PUT anchor days (4/29, 5/01, 5/04); a brand-new (often bull, often non-anchor-day) entry
has ~0 trades there -> edge_capture is VACUOUS (STRATEGY-DIRECTION-BACKLOG #5 flags exactly
this for OTM/non-anchor cells). So new families gate on the edgehunt candidate bar + the
NULL, and edge_capture is COMPUTED FOR DISCLOSURE ONLY (with a `vacuous` flag).

Pure Python, $0. PROPOSE-ONLY (never edits params.json). Markets-closed heavy compute.
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
_ROOT = _REPO.parent
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.simulator_real import simulate_trade_real            # noqa: E402 — real OPRA fills (C1)
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402 — C3/L58/L171
from autoresearch.mass_grind import qty_realizability         # noqa: E402 — L180 cap frontier
from autoresearch.strategy_space_grind import edge_capture_block  # noqa: E402 — OP-16 (disclosure only)
from autoresearch import family_detectors as fdet             # noqa: E402

_RECO = _ROOT / "analysis" / "recommendations"
REG = _ROOT / "analysis" / "backtests" / "STRATEGY-SPACE-REGISTRY.jsonl"

START = dt.date(2025, 1, 1)
END = dt.date(2026, 6, 18)
OOS_BOUNDARY = dt.date(2026, 1, 1)
QTY = 3

# ── axes ─────────────────────────────────────────────────────────────────────
STRIKES = {"OTM-4": 4, "OTM-3": 3, "OTM-2": 2, "OTM-1": 1, "ATM": 0, "ITM-1": -1, "ITM-2": -2}
STOPS = {"-8": -0.08, "-12": -0.12, "-15": -0.15, "-20": -0.20,
         "-25": -0.25, "-30": -0.30, "-40": -0.40, "-50": -0.50}
EXIT_TP1 = [0.30, 0.50, 1.0]
EXIT_TQ = [0.667, 1.0]            # 1.0 = sell all at TP1 (no runner = pure scalp)
EXIT_TRAIL = [None, 0.15]         # None = fixed BE runner; 0.15 = chandelier trailing 15%

# ── candidate-edge bar (edgehunt; replaces the EC>=771 ribbon floor — see module docstring)
BAR_OOS_AVG = 0.0
BAR_POS_QUARTERS = 4
BAR_TOP5_PCT = 200.0
BAR_N = 20
# funnel bars
QPF_P2 = 0.60
QPF_P3 = 0.75
LIVE_KEY = "safe2000_q3"          # the minimum live order at the $2K Safe account
ADMIT_FLOOR = 0.50
N_NULL_SEEDS = 10


def _q(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _tdate(t) -> dt.date:
    ts = t.entry_time_et
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts.date()


def summarize(fills: list) -> dict:
    """Metric bundle from a cell's TradeFills: expectancy + IS/OOS + qpf + top5 + maxDD + wf
    + edge_capture (disclosure). Concentration top5 = top-5 winning DAYS as % of total."""
    if not fills:
        return {"n": 0}
    pnls = [float(f.dollar_pnl) for f in fills]
    by_day: dict[dt.date, float] = defaultdict(float)
    by_q: dict[str, float] = defaultdict(float)
    is_p, oos_p = [], []
    for f in fills:
        d = _tdate(f)
        by_day[d] += float(f.dollar_pnl)
        by_q[_q(d)] += float(f.dollar_pnl)
        (is_p if d < OOS_BOUNDARY else oos_p).append(float(f.dollar_pnl))
    total = sum(pnls)
    day_vals = sorted(by_day.values(), reverse=True)
    top5 = sum(day_vals[:5])
    # sequential max drawdown (chronological)
    ordered = sorted(fills, key=lambda f: f.entry_time_et)
    eq = peak = mdd = 0.0
    for f in ordered:
        eq += float(f.dollar_pnl); peak = max(peak, eq); mdd = min(mdd, eq - peak)
    is_total, oos_total = sum(is_p), sum(oos_p)
    wf = ((oos_total / len(oos_p)) / (is_total / len(is_p))
          if is_p and oos_p and is_total != 0 else 0.0)
    qpos = sum(1 for v in by_q.values() if v > 0)
    ec = edge_capture_block(fills)
    anchor_n = sum(d.get("engine_n", 0) for d in ec["per_anchor_day"].values())
    return {
        "n": len(fills),
        "total": round(total, 1),
        "wr": round(100 * sum(1 for p in pnls if p > 0) / len(pnls), 1),
        "exp": round(total / len(pnls), 1),
        "is_n": len(is_p), "is_total": round(is_total, 1),
        "oos_n": len(oos_p), "oos_total": round(oos_total, 1),
        "oos_exp": round(oos_total / len(oos_p), 1) if oos_p else None,
        "quarters": {k: round(by_q[k], 1) for k in sorted(by_q)},
        "qpf": round(qpos / len(by_q), 3) if by_q else 0.0,
        "top5_day_pct": round(100 * top5 / total, 0) if total > 0 else None,
        "max_dd": round(mdd, 1),
        "wf": round(wf, 3),
        "edge_capture": ec["edge_capture"],
        "edge_capture_vacuous": bool(anchor_n < 3),   # ~no trades on J's anchor days
        "n_call": sum(1 for f in fills if f.side == "C"),
        "n_put": sum(1 for f in fills if f.side == "P"),
    }


def _exit_kwargs(tp1: float, tq: float, trail: Optional[float]) -> dict:
    return dict(
        tp1_premium_pct=tp1, tp1_qty_fraction=tq,
        profit_lock_mode=("trailing" if trail else "fixed"),
        profit_lock_trail_pct=(trail or 0.0),
        runner_target_premium_pct=2.5,
    )


def sim_cell(rth, signals, so: int, stop: float, tp1=0.30, tq=0.667, trail=None):
    """Run simulate_trade_real over all signals for one (strike, stop, exit) cell.
    Each signal carries its own side + bar_idx + swing rejection_level. Returns (fills, metrics).
    no_data (uncached strike) fills are skipped + counted, never faked (anti-pattern, honest n)."""
    ek = _exit_kwargs(tp1, tq, trail)
    fills, no_data = [], 0
    for s in signals:
        f = simulate_trade_real(
            entry_bar_idx=s["bar_idx"], entry_bar=rth.iloc[s["bar_idx"]], spy_df=rth,
            ribbon_df=None, rejection_level=s["rejection_level"],
            triggers_fired=[s["family"]], side=s["side"], qty=QTY, setup=s["family"].upper(),
            premium_stop_pct=stop, strike_offset=so, **ek)
        if f is None:
            no_data += 1
            continue
        fills.append(f)
    m = summarize(fills)
    m["no_data"] = no_data
    return fills, m


def candidate_bar(m: dict) -> tuple[bool, list[str]]:
    reasons = []
    if not (m.get("oos_n") and (m.get("oos_exp") or -1) > BAR_OOS_AVG):
        reasons.append(f"OOS_exp={m.get('oos_exp')} (need >0, oos_n={m.get('oos_n')})")
    if (m.get("qpf") or 0) * 6 < BAR_POS_QUARTERS:   # qpf is fraction; need >=4/6
        reasons.append(f"pos_quarters~{round((m.get('qpf') or 0)*6,1)}/6 (need >=4)")
    t5 = m.get("top5_day_pct")
    if t5 is None or t5 >= BAR_TOP5_PCT:
        reasons.append(f"top5={t5} (need <{BAR_TOP5_PCT})")
    if (m.get("n") or 0) < BAR_N:
        reasons.append(f"n={m.get('n')} (need >={BAR_N})")
    return (not reasons), reasons


def _run_null(rth, fills, so: int, stop: float, tp1, tq, trail, window) -> dict:
    """Random-entry null with the cell's MATCHING exit bracket (isolates entry timing, not
    the exit structure — stricter than the stock funnel null which uses the default bracket)."""
    n_call = sum(1 for f in fills if f.side == "C")
    n_put = sum(1 for f in fills if f.side == "P")
    # drop-top5-day per-trade (concentration robustness; the null_gate's drop-top5 input)
    by_day: dict = defaultdict(float)
    for f in fills:
        by_day[_tdate(f)] += float(f.dollar_pnl)
    top5 = {d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)[:5]}
    kept = [f for f in fills if _tdate(f) not in top5]
    drop5 = (sum(float(f.dollar_pnl) for f in kept) / len(kept)) if kept else 0.0
    sim_fn = functools.partial(simulate_trade_real, **_exit_kwargs(tp1, tq, trail))
    null = random_entry_null(
        rth, n_signals=len(fills), n_call=n_call, n_put=n_put,
        strike_offset=so, premium_stop_pct=stop, seeds=N_NULL_SEEDS,
        entry_gate=window, sim_fn=sim_fn)
    exp = sum(float(f.dollar_pnl) for f in fills) / len(fills) if fills else 0.0
    gate = null_gate(round(exp, 2), round(drop5, 2), null)
    return {
        "null_pass": bool(gate["null_pass"]),
        "per_trade": round(exp, 2), "drop_top5_per_trade": round(drop5, 2),
        "null_mean": null.get("per_trade_mean"), "null_max": null.get("per_trade_max"),
        "edge_over_null": gate.get("edge_over_null_per_trade"),
        "beats_null_max": gate.get("beats_null_max"),
        "drop_top5_beats_null_mean": gate.get("drop_top5_beats_null_mean"),
        "seeds": N_NULL_SEEDS,
    }


def run_family(rth, family: str, signals: list, log=print) -> dict:
    """Full pipeline for one family. Writes progress + funnel + consolidation JSONLs."""
    prog = _RECO / f"mass-grind-{family}-progress.jsonl"
    funnel = _RECO / f"mass-grind-{family}-funnel.jsonl"
    prog.write_text("", encoding="utf-8")     # fresh run
    funnel.write_text("", encoding="utf-8")
    window = fdet.FAMILY_WINDOW[family]
    log(f"[{family}] {len(signals)} signals; PHASE 1 strike x stop ({len(STRIKES)*len(STOPS)} cells)")

    # ── PHASE 1: strike x stop, default exit ──────────────────────────────────
    p1: list[dict] = []
    for sk, so in STRIKES.items():
        for stp, sv in STOPS.items():
            fills, m = sim_cell(rth, signals, so, sv)
            cb, reasons = candidate_bar(m)
            qf = qty_realizability(fills) if (m.get("n", 0) >= 20) else {}
            row = {"family": family, "phase": 1, "cell": f"{sk}|stop{stp}",
                   "strike": sk, "strike_offset": so, "stop": stp, "stop_pct": sv,
                   "tp1": 0.30, "tq": 0.667, "trail": None,
                   "metrics": m, "candidate_bar": cb, "fail_reasons": reasons,
                   "qty_frontier": qf}
            p1.append(row)
            with open(prog, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
    oos_pos = [r for r in p1 if r["metrics"].get("oos_n") and (r["metrics"].get("oos_exp") or -1) > 0]
    log(f"[{family}] P1 done. {sum(1 for r in p1 if r['candidate_bar'])} cells clear candidate bar; "
        f"{len(oos_pos)} OOS-positive -> PHASE 2 exit refine")

    # ── PHASE 2: exit refine on OOS-positive strike/stop cells ────────────────
    refined: list[dict] = []
    for base in oos_pos:
        so, sv = base["strike_offset"], base["stop_pct"]
        best = None
        for tp1 in EXIT_TP1:
            for tq in EXIT_TQ:
                for trail in EXIT_TRAIL:
                    fills, m = sim_cell(rth, signals, so, sv, tp1, tq, trail)
                    cb, reasons = candidate_bar(m)
                    qf = qty_realizability(fills) if (m.get("n", 0) >= 20) else {}
                    row = {"family": family, "phase": 2, "cell": base["cell"],
                           "strike": base["strike"], "strike_offset": so,
                           "stop": base["stop"], "stop_pct": sv,
                           "tp1": tp1, "tq": tq, "trail": trail,
                           "metrics": m, "candidate_bar": cb, "fail_reasons": reasons,
                           "qty_frontier": qf}
                    with open(prog, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(row, default=str) + "\n")
                    key = (cb, m.get("oos_total") or -1e9)
                    if best is None or key > best[0]:
                        best = (key, row, fills)
        if best:
            refined.append(best[1] | {"_fills": best[2]})

    # ── PHASE 3: funnel (P2/P3) + null on best-exit P3 survivors ──────────────
    elites: list[dict] = []
    p3_survivors = 0
    for row in refined:
        m = row["metrics"]
        live = (row.get("qty_frontier") or {}).get(LIVE_KEY, {})
        live_exp = float(live.get("real_exp", 0.0)); live_admit = float(live.get("admit_pct", 0.0))
        pass_p2 = (m.get("qpf") or 0) >= QPF_P2 and row["candidate_bar"]
        pass_p3 = (pass_p2 and (m.get("qpf") or 0) >= QPF_P3 and m.get("n", 0) >= BAR_N
                   and (m.get("top5_day_pct") or 1e9) < BAR_TOP5_PCT
                   and live_exp > 0 and live_admit >= ADMIT_FLOOR)
        verdict, null = "PASS-P2" if pass_p2 else "STOP-P2", None
        if pass_p3:
            p3_survivors += 1
            null = _run_null(rth, row["_fills"], row["strike_offset"], row["stop_pct"],
                             row["tp1"], row["tq"], row["trail"], window)
            verdict = "PASS-P4" if null["null_pass"] else "PASS-P3"
        elif pass_p2:
            verdict = "PASS-P2"
        out = {k: v for k, v in row.items() if k != "_fills"}
        out.update({"phase": 3, "verdict": verdict, "p3_pass": pass_p3,
                    "live_real_exp": round(live_exp, 2), "live_admit_pct": round(live_admit, 3),
                    "null": null})
        with open(funnel, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(out, default=str) + "\n")
        if verdict == "PASS-P4":
            elites.append(out)
        log(f"[{family}] {row['cell']} tp{row['tp1']}/sell{int(row['tq']*100)}/"
            f"{'trail' if row['trail'] else 'fix'} -> {verdict}"
            + (f" null[exp={null['per_trade']} vs max={null['null_max']}]" if null else ""))

    summary = {
        "family": family, "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "window": f"{START}..{END}", "n_signals": len(signals),
        "entry_window": [window[0].strftime("%H:%M"), window[1].strftime("%H:%M")],
        "p1_candidate_cells": sum(1 for r in p1 if r["candidate_bar"]),
        "p1_oos_positive": len(oos_pos), "p3_survivors": p3_survivors,
        "p4_elites": len(elites),
        "elites": sorted(elites, key=lambda e: -((e["null"]["edge_over_null"] or 0)
                                                  * (e["metrics"].get("qpf") or 0)))[:10],
        "authority": "real OPRA fills (C1); null=random-entry MATCHING-exit (C3/L58/L171); "
                     "gate=candidate-bar+null (edge_capture vacuous for non-J-anchor entries, disclosed)",
    }
    (_RECO / f"family-grind-{family}.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log(f"[{family}] DONE. P1-candidates={summary['p1_candidate_cells']} "
        f"P3-survivors={p3_survivors} P4-elites={len(elites)}")
    return summary
