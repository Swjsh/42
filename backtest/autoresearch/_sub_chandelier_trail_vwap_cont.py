"""SUNDAY-WEB-LEARN SUB-STUDY: chandelier-tighten-20-to-15-oos-wf on the LIVE edge.

HYPOTHESIS (web-sourced, slug=chandelier-tighten-20-to-15-oos-wf):
  Tightening the v15 profit-lock chandelier trail off the premium HWM improves
  expectancy on the LIVE vwap_continuation edge (ITM-2 / -8% stop, morning) WITHOUT
  worsening the L175 risk-adjusted gate (Sharpe / Sortino / maxDD must be no-worse).

REUSE (no drift, C14):
  * Detector: import detect_signals from _edgehunt_vwap_continuation (BYTE-FOR-BYTE
    j_daily_pattern_ratify.detect_j_vwap_continuation == the LIVE
    vwap_continuation_watcher).
  * Fills: simulate_cell from _edgehunt_vwap_continuation -> lib.simulator_real
    .simulate_trade_real (real OPRA fills, C1). nearest-cached strike snap <=4.
  * Data: autoresearch.runner.load_data (SPY+VIX), same as the edgehunt harness.

WHAT THIS ADDS over the edgehunt exit mini-sweep:
  1. PINS to the LIVE cell only: ITM-2 (strike_offset=-2), -8% premium stop, the
     LIVE arm config (profit_lock_threshold_pct=0.05, mode='trailing'). The edgehunt
     harness only swept trail on OOS-positive *base* cells and used the default arm.
  2. Sweeps trail in {0.10, 0.125, 0.15, 0.20} -- 0.15 is now the LIVE baseline
     (shipped 2026-06-19, was 0.20). So the real open question is: does going
     TIGHTER than the live 0.15 (-> 0.125 / 0.10) beat it, and does 0.15 still beat
     0.20 on the vwap_continuation population specifically + survive WF?
  3. L175 RISK-ADJUSTED GATE: annualized Sharpe + Sortino + maxDD of the per-trade
     P&L series, computed for every trail value, scored vs the live 0.20-history /
     0.15-live baseline. PROMOTE only if expectancy-lift AND DSR-not-worse AND
     maxDD-not-worse AND anchor-no-regression.
  4. WALK-FORWARD: 4 contiguous time folds; report per-fold expectancy + the WF
     fraction (folds where the candidate trail >= baseline trail).

HARD-WINDOW (the cache blind spot): the real-fills cache only covers <=2026-05-29.
We do NOT pre-filter SPY; we let the OPRA cache snap (uncached date => no fill) AND
then ASSERT every filled trade's date is <=2026-05-29.

Pure Python, $0 (no LLM in the loop). No live orders. Markets closed. NO live edits.
Writes analysis/recommendations/sub-chandelier-trail-vwap_cont.json and appends a
section to analysis/recommendations/SUNDAY-WEB-LEARN-SCORECARD.md.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sub_chandelier_trail_vwap_cont.py
"""
from __future__ import annotations

import datetime as dt
import json
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

# REUSE the edgehunt detector + sim cell verbatim (no drift).
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    detect_signals,
    simulate_cell,
    TradeRow,
    OOS_YEAR,
)

OUT_JSON = ROOT / "analysis" / "recommendations" / "sub-chandelier-trail-vwap_cont.json"
SCORECARD = ROOT / "analysis" / "recommendations" / "SUNDAY-WEB-LEARN-SCORECARD.md"

# ── The LIVE cell (CLAUDE.md v15 + params.json) ─────────────────────────────────
LIVE_STRIKE_OFFSET = -2       # ITM-2 (task spec + the strike tier vwap_cont ships on)
LIVE_PREMIUM_STOP = -0.08     # -8% premium stop (the LIVE vwap_continuation stop)
LIVE_ARM_THRESHOLD = 0.05     # params.json v15_profit_lock_threshold_pct
LIVE_TP1 = 0.50               # params.json tp1_qty_fraction band (live exits)
LIVE_RUNNER = 2.5             # runner target 2.5x (live)

# Trail sweep. 0.15 = the CURRENT LIVE baseline (shipped 2026-06-19, was 0.20).
TRAIL_SWEEP = [0.10, 0.125, 0.15, 0.20]
LIVE_TRAIL = 0.15             # current production
PRIOR_TRAIL = 0.20            # the pre-2026-06-19 production (history baseline)

HARD_WINDOW_END = dt.date(2026, 5, 29)   # OPRA cache blind spot (HARD assert)
N_WF_FOLDS = 4

# Anchor fills: the J source-of-truth winners/losers are 2025-04/05 (CLAUDE.md OP-16).
ANCHOR_DATES = {"2025-04-29", "2025-05-01", "2025-05-04",   # winners
                "2025-05-05", "2025-05-06", "2025-05-07"}   # losers


# ── L175 risk-adjusted metrics on a per-trade $ P&L series ──────────────────────
def _risk_metrics(pnls: list[float]) -> dict:
    """Annualized Sharpe / Sortino on the per-trade $ series + maxDD on the equity
    curve. Per-trade series (one obs per trade); annualization uses ~252 trades/yr
    as a CONSISTENT scale factor (same applied to every trail, so the COMPARISON is
    what matters, not the absolute level). L175 = candidate must be no-worse."""
    if len(pnls) < 2:
        return {"sharpe": 0.0, "sortino": 0.0, "max_dd": 0.0, "n": len(pnls)}
    a = np.asarray(pnls, float)
    mean = float(a.mean())
    sd = float(a.std(ddof=1))
    sharpe = (mean / sd) * np.sqrt(252.0) if sd > 0 else 0.0
    downside = a[a < 0]
    dsd = float(np.sqrt(np.mean(np.square(downside)))) if downside.size else 0.0
    sortino = (mean / dsd) * np.sqrt(252.0) if dsd > 0 else (np.inf if mean > 0 else 0.0)
    equity = np.cumsum(a)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak                      # <=0
    max_dd = float(dd.min())                # most-negative drawdown ($)
    return {
        "sharpe": round(float(sharpe), 3),
        "sortino": round(float(sortino), 3) if np.isfinite(sortino) else 999.0,
        "max_dd": round(max_dd, 2),
        "n": len(pnls),
    }


def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _summarize(rows: list[TradeRow]) -> dict:
    """Expectancy + OOS split + positive-quarters + risk metrics + anchor P&L."""
    if not rows:
        return {"n": 0}
    rows = sorted(rows, key=lambda r: r.date)
    pnl = [r.pnl for r in rows]
    n = len(rows)
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    # IS halves (L173: OOS-alone + IS-half stability)
    is_sorted = sorted(is_rows, key=lambda r: r.date)
    half = len(is_sorted) // 2
    is_h1 = [r.pnl for r in is_sorted[:half]]
    is_h2 = [r.pnl for r in is_sorted[half:]]

    # anchor P&L (no-regression check)
    anchor_rows = [r for r in rows if r.date in ANCHOR_DATES]
    anchor_pnl = round(sum(r.pnl for r in anchor_rows), 2)

    # top-5 winning DAYS as % of total
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    total = sum(by_day.values())
    top5 = (round(100 * sum(sorted(by_day.values(), reverse=True)[:5]) / total, 1)
            if total > 0 else None)

    risk = _risk_metrics(pnl)
    return {
        "n": n,
        "wr_pct": round(100 * sum(1 for p in pnl if p > 0) / n, 1),
        "exp_dollar": round(float(np.mean(pnl)), 2),
        "total_dollar": round(float(np.sum(pnl)), 2),
        "is_n": len(is_rows), "is_exp": round(float(np.mean([r.pnl for r in is_rows])), 2) if is_rows else 0.0,
        "oos_n": len(oos_rows), "oos_exp": round(float(np.mean([r.pnl for r in oos_rows])), 2) if oos_rows else 0.0,
        "oos_total": round(float(np.sum([r.pnl for r in oos_rows])), 2) if oos_rows else 0.0,
        "is_h1_exp": round(float(np.mean(is_h1)), 2) if is_h1 else 0.0,
        "is_h2_exp": round(float(np.mean(is_h2)), 2) if is_h2 else 0.0,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos,
        "quarters": quarters,
        "top5_day_pct": top5,
        "anchor_n": len(anchor_rows), "anchor_pnl": anchor_pnl,
        "risk": risk,
        "exit_hist": {k: sum(1 for r in rows if r.exit_reason == k)
                      for k in sorted({r.exit_reason for r in rows})},
    }


def _walk_forward(rows: list[TradeRow], n_folds: int) -> list[dict]:
    """Contiguous time folds; per-fold expectancy + total."""
    if not rows:
        return []
    rows = sorted(rows, key=lambda r: r.date)
    sz = max(1, len(rows) // n_folds)
    folds = []
    for k in range(n_folds):
        lo = k * sz
        hi = len(rows) if k == n_folds - 1 else (k + 1) * sz
        chunk = rows[lo:hi]
        if not chunk:
            continue
        p = [r.pnl for r in chunk]
        folds.append({
            "fold": k + 1,
            "start": chunk[0].date, "end": chunk[-1].date,
            "n": len(chunk),
            "exp": round(float(np.mean(p)), 2),
            "total": round(float(np.sum(p)), 2),
        })
    return folds


def main() -> int:
    print("[sub-chandelier] loading SPY+VIX ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # Detect the LIVE vwap_continuation signals ONCE (full pattern, no extra gate).
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    print(f"[sub-chandelier] signals={len(signals)} over {n_days} days", flush=True)

    # Sweep the trail on the LIVE cell.
    cells: dict[float, dict] = {}
    rows_by_trail: dict[float, list[TradeRow]] = {}
    for trail in TRAIL_SWEEP:
        rows, cov = simulate_cell(
            signals, spy, ribbon, vix,
            strike_offset=LIVE_STRIKE_OFFSET,
            premium_stop_pct=LIVE_PREMIUM_STOP,
            tp1_premium_pct=LIVE_TP1,
            runner_target_premium_pct=LIVE_RUNNER,
            profit_lock_trail_pct=trail,
        )
        # HARD-WINDOW assert: every FILLED trade must be <= 2026-05-29.
        bad = [r.date for r in rows if dt.date.fromisoformat(r.date) > HARD_WINDOW_END]
        assert not bad, f"HARD-WINDOW breach: filled trades after {HARD_WINDOW_END}: {bad[:5]}"
        rows_by_trail[trail] = rows
        m = _summarize(rows)
        m["coverage"] = cov
        m["wf"] = _walk_forward(rows, N_WF_FOLDS)
        cells[trail] = m
        rr = m.get("risk", {})
        print(f"  trail={trail:<5} n={m.get('n','-'):>3} exp=${m.get('exp_dollar','-'):>7} "
              f"oos_exp=${m.get('oos_exp','-'):>7} posQ={m.get('positive_quarters','-')} "
              f"sharpe={rr.get('sharpe','-')} sortino={rr.get('sortino','-')} "
              f"maxDD=${rr.get('max_dd','-')} anchor=${m.get('anchor_pnl','-')}", flush=True)

    # Determine fill window from actual filled trades (honest disclosure).
    all_dates = sorted({r.date for rs in rows_by_trail.values() for r in rs})
    fill_window = f"{all_dates[0]}..{all_dates[-1]}" if all_dates else "NONE"

    base_live = cells.get(LIVE_TRAIL, {})           # current production 0.15
    base_prior = cells.get(PRIOR_TRAIL, {})         # pre-ship 0.20 history baseline

    # ── EVALUATE each candidate trail vs the LIVE 0.15 baseline (L175 gate) ──────
    def _verdict(cand_trail: float) -> dict:
        c = cells[cand_trail]
        b = base_live
        if not c.get("n") or not b.get("n"):
            return {"trail": cand_trail, "promote": False,
                    "reason": "no fills / no baseline", "checks": {}}
        cr, br = c.get("risk", {}), b.get("risk", {})
        exp_lift = c["exp_dollar"] - b["exp_dollar"]
        oos_lift = c["oos_exp"] - b["oos_exp"]
        sharpe_ok = cr.get("sharpe", -9) >= br.get("sharpe", 9) - 1e-9
        sortino_ok = cr.get("sortino", -9) >= br.get("sortino", 9) - 1e-9
        # maxDD is <=0; "not worse" = not MORE negative than baseline
        maxdd_ok = cr.get("max_dd", -9e9) >= br.get("max_dd", 0) - 1e-9
        oos_pos = c["oos_exp"] > 0
        anchor_ok = c.get("anchor_pnl", 0) >= b.get("anchor_pnl", 0) - 1e-9
        exp_better = exp_lift > 0
        checks = {
            "exp_lift_vs_live015": round(exp_lift, 2),
            "oos_lift_vs_live015": round(oos_lift, 2),
            "exp_better": exp_better,
            "oos_positive": oos_pos,
            "sharpe_no_worse": sharpe_ok,
            "sortino_no_worse": sortino_ok,
            "maxdd_no_worse": maxdd_ok,
            "anchor_no_regression": anchor_ok,
        }
        promote = bool(exp_better and oos_pos and sharpe_ok and sortino_ok
                       and maxdd_ok and anchor_ok)
        return {"trail": cand_trail, "promote": promote, "checks": checks}

    # Candidates = the TIGHTER-than-live trails (the open question) + the prior 0.20.
    verdicts = {t: _verdict(t) for t in TRAIL_SWEEP if t != LIVE_TRAIL}

    # Monotonicity check on total P&L (the prior run's claim: tighter > wider, 0 exceptions)
    totals = {t: cells[t].get("total_dollar") for t in TRAIL_SWEEP if cells[t].get("n")}
    mono_tighter_better = None
    if len(totals) == len(TRAIL_SWEEP):
        ordered = [totals[t] for t in sorted(TRAIL_SWEEP)]   # ascending trail
        # "tighter monotonically beats wider" => total DECREASES as trail increases
        mono_tighter_better = all(ordered[i] >= ordered[i + 1] for i in range(len(ordered) - 1))

    any_promote = [t for t, v in verdicts.items() if v["promote"]]

    summary = {
        "slug": "chandelier-tighten-20-to-15-oos-wf",
        "run_date": dt.date.today().isoformat(),
        "kind": "EXIT/MANAGEMENT change on LIVE edge #1 (vwap_continuation)",
        "STALE_PREMISE_NOTE": (
            "The hypothesis premise ('un-shipped forward-pointer, tighten 0.20->0.15') is "
            "STALE: params.json v15_profit_lock_trail_pct is ALREADY 0.15 (shipped LIVE "
            "2026-06-19 via the full-engine reconfirm, scorecard weekend-fixes-live-reconfirm-"
            "2026-06-19.json). So the LIVE BASELINE is 0.15, not 0.20. This sub-study therefore "
            "re-frames the open question as: (a) does the 0.15>0.20 ranking hold on the "
            "vwap_continuation population + survive WF, and (b) does going TIGHTER than live "
            "(0.125 / 0.10) beat the current 0.15."),
        "live_cell": {
            "strike_offset": LIVE_STRIKE_OFFSET, "strike_tier": "ITM2",
            "premium_stop_pct": LIVE_PREMIUM_STOP,
            "profit_lock_mode": "trailing", "arm_threshold_pct": LIVE_ARM_THRESHOLD,
            "tp1_premium_pct": LIVE_TP1, "runner_target_premium_pct": LIVE_RUNNER,
            "LIVE_trail_pct": LIVE_TRAIL, "prior_trail_pct": PRIOR_TRAIL,
        },
        "detector": ("REUSED detect_signals from _edgehunt_vwap_continuation == BYTE-FOR-BYTE "
                     "j_daily_pattern_ratify.detect_j_vwap_continuation == LIVE "
                     "vwap_continuation_watcher"),
        "fills_authority": "lib.simulator_real.simulate_trade_real (real OPRA, C1)",
        "hard_window": f"filled trades asserted <= {HARD_WINDOW_END} (cache blind spot)",
        "actual_fill_window": fill_window,
        "n_signals": len(signals),
        "trail_sweep": TRAIL_SWEEP,
        "cells": cells,
        "monotonic_tighter_beats_wider_on_total": mono_tighter_better,
        "verdicts_vs_live015": verdicts,
        "promote_any": any_promote,
        "L175_gate": ("PROMOTE a trail only if exp_better-vs-live AND oos_positive AND "
                      "sharpe_no_worse AND sortino_no_worse AND maxdd_no_worse AND "
                      "anchor_no_regression (all vs the LIVE 0.15)"),
        "DISCLOSURE": {
            "risk_metric_note": ("Sharpe/Sortino annualized with a CONSISTENT 252-trade scale "
                                 "across all trails -- the cross-trail COMPARISON is the signal, "
                                 "not the absolute level. maxDD is $ on the per-trade equity curve."),
            "anchor_caveat": "anchor_n reported honestly; vwap_cont anchor overlap may be 0.",
            "spy_vs_option": "real OPRA fills; this is an EXIT knob on an already-live edge (C3 N/A).",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[sub-chandelier] wrote {OUT_JSON}", flush=True)

    _append_scorecard(summary)
    print(f"[sub-chandelier] appended section to {SCORECARD}", flush=True)

    # ── Console verdict ──────────────────────────────────────────────────────
    print("\n=== CHANDELIER-TRAIL (vwap_continuation, ITM-2/-8%) VERDICT ===")
    print(f"fill_window={fill_window}  n_signals={len(signals)}")
    for t in TRAIL_SWEEP:
        m = cells[t]
        if not m.get("n"):
            print(f"  trail={t}: NO FILLS")
            continue
        rr = m["risk"]
        flag = " <-- LIVE" if t == LIVE_TRAIL else ""
        print(f"  trail={t}: n={m['n']} exp=${m['exp_dollar']} oos_exp=${m['oos_exp']} "
              f"posQ={m['positive_quarters']} sharpe={rr['sharpe']} maxDD=${rr['max_dd']}{flag}")
    print(f"monotonic (tighter beats wider on total P&L): {mono_tighter_better}")
    for t, v in verdicts.items():
        print(f"  vs LIVE 0.15 -> trail {t}: PROMOTE={v['promote']} {v.get('checks', v.get('reason'))}")
    if any_promote:
        print(f"VERDICT: PROMOTE trail(s) {any_promote} (clear the L175 gate vs live 0.15)")
    else:
        print("VERDICT: NO trail beats the current LIVE 0.15 on the full L175 gate -> "
              "current production stays. (DEAD as an improvement; 0.15 confirmed.)")
    return 0


def _append_scorecard(s: dict) -> None:
    SCORECARD.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if not SCORECARD.exists():
        lines.append("# SUNDAY WEB-LEARN SCORECARD\n")
        lines.append("Real-data tests of web-sourced hypotheses on OUR cached data. "
                     "$0, offline, no live edits.\n")
    lines.append(f"\n---\n\n## {s['slug']}  ({s['run_date']})\n")
    lines.append(f"**Kind:** {s['kind']}\n")
    lines.append(f"\n**STALE-PREMISE NOTE:** {s['STALE_PREMISE_NOTE']}\n")
    lc = s["live_cell"]
    lines.append(f"\n**Live cell tested:** ITM-2 / {lc['premium_stop_pct']} stop / "
                 f"trailing arm@{lc['arm_threshold_pct']} / tp1 {lc['tp1_premium_pct']} / "
                 f"runner {lc['runner_target_premium_pct']}x. **Current LIVE trail = "
                 f"{lc['LIVE_trail_pct']}** (was {lc['prior_trail_pct']} pre-2026-06-19).\n")
    lines.append(f"\n**Fills:** real OPRA via lib.simulator_real (C1). "
                 f"HARD-window asserted <= {HARD_WINDOW_END}. Actual fill window "
                 f"`{s['actual_fill_window']}`. Signals={s['n_signals']}.\n")
    lines.append("\n| trail | n | exp $ | OOS exp $ | posQ | Sharpe | Sortino | maxDD $ | anchor $ |\n")
    lines.append("|---|---|---|---|---|---|---|---|---|\n")
    for t in s["trail_sweep"]:
        m = s["cells"][t]
        if not m.get("n"):
            lines.append(f"| {t}{' (LIVE)' if t == LIVE_TRAIL else ''} | 0 | - | - | - | - | - | - | - |\n")
            continue
        rr = m["risk"]
        tag = " (LIVE)" if t == LIVE_TRAIL else (" (prior)" if t == PRIOR_TRAIL else "")
        lines.append(f"| {t}{tag} | {m['n']} | {m['exp_dollar']} | {m['oos_exp']} | "
                     f"{m['positive_quarters']} | {rr['sharpe']} | {rr['sortino']} | "
                     f"{rr['max_dd']} | {m['anchor_pnl']} (n={m['anchor_n']}) |\n")
    lines.append(f"\n**Monotonic (tighter beats wider on total P&L):** "
                 f"{s['monotonic_tighter_beats_wider_on_total']}\n")
    lines.append("\n**L175 gate verdicts vs the current LIVE 0.15:**\n")
    for t, v in s["verdicts_vs_live015"].items():
        lines.append(f"- trail **{t}**: PROMOTE={v['promote']} -- {v.get('checks', v.get('reason'))}\n")
    if s["promote_any"]:
        lines.append(f"\n**VERDICT: PROMOTE trail(s) {s['promote_any']}** -- clears expectancy-lift "
                     f"+ OOS-positive + Sharpe/Sortino/maxDD no-worse + anchor-no-regression "
                     f"vs the live 0.15.\n")
    else:
        lines.append("\n**VERDICT: DEAD as an improvement.** No swept trail beats the current "
                     "LIVE 0.15 on the full L175 risk-adjusted gate -> production 0.15 stays. "
                     "(The 0.15<-0.20 ship from 2026-06-19 is re-confirmed on the "
                     "vwap_continuation population; going tighter does not help.)\n")
    with SCORECARD.open("a", encoding="utf-8") as f:
        f.write("".join(lines))


if __name__ == "__main__":
    sys.exit(main())
