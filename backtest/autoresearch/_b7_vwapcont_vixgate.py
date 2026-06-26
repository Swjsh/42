"""B7 — vwap_continuation +VIX-REGIME-GATE A/B (refine the LIVE edge).

ANGLE C (J, 2026-06-21): does VIX-regime-gating LIFT the live ``vwap_continuation`` edge's
per-trade EXPECTANCY? vwap_continuation is LIVE (j_vwap_cont_enabled=true, ITM-2, -8%). The
convergent signal of the whole campaign = VIX-regime (level + slope) + day-trend-side is the
real predictive axis (edge#4 + the ML #1 feature + the shipped vwap VIX put-slope gate). So
this is the highest-EV move: A/B the LIVE harness BASELINE vs +VIX-REGIME-GATE.

THE A/B (one causal entry/day, identical signals, ONLY the take/skip differs):
  * BASELINE  = the live vwap_continuation signals (REUSED byte-for-byte from
    ``_edgehunt_vwap_continuation.detect_signals`` — the same detector the live watcher
    ports), simulated on real OPRA fills (C1) at the tested tier.
  * GATED     = take the SAME signal ONLY when the VIX regime as-of the entry bar is
    FAVORABLE (edge#4 ``favorable_regime``: VIX LOW vs trailing-median AND not-rising,
    computed CAUSALLY — every input read at-or-before the entry bar, the trailing median
    shifted by 1 so it never includes the entry bar's own value). REUSED byte-for-byte from
    ``_b5_vix_regime_dayside`` (causal_vix_median / vix_slope / favorable_regime).
  * SKIPPED   = BASELINE minus GATED — the days the gate REMOVES. The NO-REGRESSION test
    (c) requires the SKIPPED set to be net-negative or break-even: a good gate removes
    LOSERS, not winners.

TIERS (C29 — knobs do NOT transfer across strike tiers, so test BOTH):
  * ITM-2 / -8%   = the LIVE Bold tier (strike_offset -2, premium_stop -0.08).
  * ATM  / -8%    = the Safe-2 tier (strike_offset 0, premium_stop -0.08).

THE GATE MUST (to verdict LIVE_EDGE_IMPROVEMENT — shippable under the standing
"ship profitable-validated" authorization, since it IMPROVES a live edge):
  (a) IMPROVE per-trade expectancy (gated OOS/tr > baseline OOS/tr, AND gated full-sample
      per-trade > baseline) — over-filtering a live edge into a net loss is a FAILURE we
      report honestly.
  (b) NOT cause anchor regression (OP-16): the gate must not skip any J source-of-truth
      WINNER day, and must not turn a J-loser-day skip into a hold-the-loser.
  (c) NO-REGRESSION: SKIPPED set net per-trade <= 0 (removes losers/break-even, not winners).
  (d) Still clear ALL 9 GATES on the GATED subset (incl. the L173 OOS-ALONE drop-top5 — the
      B6 graduated gate; full-sample drop-top5 is necessary-but-NOT-sufficient), beat the
      random-entry NULL (L172), and pass NO-TRUNCATION (L171, sign holds chart-stop-only).

The VIX regime is swept (low_margin x slope_rule) as DISCLOSURE — but gate 1 (OOS per-trade)
is OOS-only and decisive, so the cut is not tuned on OOS. Best gated cell reported per tier.

Pure Python / numpy, $0, no LLM, no live orders. Markets closed.
Writes analysis/recommendations/b7-vwapcont-vixgate.json + a human scorecard .md.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b7_vwapcont_vixgate.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]          # ...\42\backtest
ROOT = REPO.parent                                  # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

# REUSE the LIVE vwap_continuation detector + data normalizers (byte-for-byte, no drift).
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    detect_signals,
    _normalize_spy,
    _align_vix,
    MAX_STRIKE_STEPS,
    QTY,
)
# REUSE edge#4's causal VIX-regime primitives (byte-for-byte).
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    causal_vix_median,
    vix_slope,
    favorable_regime,
    VIX_SLOPE_BARS,
    VIX_MEDIAN_BARS,
)
# REUSE the graduated fraud + null gates.
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402

JSON_OUT = ROOT / "analysis" / "recommendations" / "b7-vwapcont-vixgate.json"
MD_OUT = ROOT / "analysis" / "recommendations" / "B7-VWAPCONT-VIXGATE-SCORECARD.md"

OOS_YEAR = 2026

# Tiers to test (C29). (label, strike_offset, premium_stop_pct)
TIERS = [
    ("ITM2_live", -2, -0.08),   # the LIVE Bold tier
    ("ATM_safe2", 0, -0.08),    # the Safe-2 tier
]
CHART_STOP_ONLY = -0.99         # no-truncation (L171) probe stop

# VIX-regime sweep (disclosure; gate 1 is OOS-only -> not OOS-tuned).
VIX_LOW_MARGINS = [0.0, 0.25, 0.5, 1.0]
SLOPE_RULES = ["not_rising", "any"]

# 9-gate bar constants.
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0
NULL_SEEDS = 30

# OP-16 J source-of-truth anchor DAYS (the immutable winners/losers). The gate must not
# skip a WINNER day. (Dates only — strike/side detail in CLAUDE.md OP-16.)
ANCHOR_WINNER_DAYS = {"2025-04-29", "2025-05-01", "2025-05-04"}
ANCHOR_LOSER_DAYS = {"2025-05-05", "2025-05-06", "2025-05-07"}


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Row:
    date: str
    side: str
    strike: int
    pnl: float
    pct: float
    exit_reason: str
    trig: str


def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _drop_topk_per_trade(rows: list[Row], k: int = 5) -> Optional[float]:
    """per-trade after removing the k best P&L DAYS (concentration robustness)."""
    if not rows:
        return None
    by_day: dict[str, float] = defaultdict(float)
    cnt: dict[str, int] = defaultdict(int)
    for r in rows:
        by_day[r.date] += r.pnl
        cnt[r.date] += 1
    top = set(d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)[:k])
    kept = [r.pnl for r in rows if r.date not in top]
    return round(sum(kept) / len(kept), 2) if kept else None


def _top5_day_pct(rows: list[Row]) -> Optional[float]:
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def metrics(rows: list[Row]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    # IS 2025 first-half (sub-window stability, L166 / gate 6)
    is_h1 = [r.pnl for r in is_rows if int(r.date[5:7]) <= 6]

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "drop_top5_per_trade": _drop_topk_per_trade(rows, 5),
        "is_n": len(is_rows),
        "is_exp": round(float(np.mean([r.pnl for r in is_rows])), 2) if is_rows else 0.0,
        "is_h1_n": len(is_h1),
        "is_h1_exp": round(float(np.mean(is_h1)), 2) if is_h1 else 0.0,
        "oos_n": len(oos_rows),
        "oos_exp": round(float(np.mean([r.pnl for r in oos_rows])), 2) if oos_rows else 0.0,
        "oos_total": round(float(np.sum([r.pnl for r in oos_rows])), 2) if oos_rows else 0.0,
        "oos_drop_top5_per_trade": _drop_topk_per_trade(oos_rows, 5),
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos,
        "n_quarters": len(quarters),
        "top5_day_pct": _top5_day_pct(rows),
        "exit_hist": dict(sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())),
    }


def simulate(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct) -> list[Row]:
    """Re-run a list of (already-filtered) signals at one strike/stop cell on real fills."""
    rows: list[Row] = []
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
            qty=QTY, setup="B7_VWAPCONT_VIXGATE", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            continue
        rows.append(Row(date=str(d), side=sg.side, strike=int(strike),
                        pnl=round(float(fill.dollar_pnl), 2),
                        pct=round(float(fill.pct_return_on_premium), 5),
                        exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
                        trig=sg.note or "d"))
    return rows


def gate_signals(signals, vix_g, vix_med_g, vix_slp_g, low_margin, slope_rule):
    """Split the baseline signals into (taken, skipped) by favorable VIX regime as-of bar."""
    taken, skipped = [], []
    for sg in signals:
        g = sg.bar_idx
        lvl = float(vix_g[g]) if g < len(vix_g) else None
        med = float(vix_med_g[g]) if g < len(vix_med_g) and not math.isnan(vix_med_g[g]) else None
        slp = float(vix_slp_g[g]) if g < len(vix_slp_g) and not math.isnan(vix_slp_g[g]) else None
        fav = favorable_regime(lvl, med, slp, low_margin, slope_rule)
        (taken if (fav is not None and fav) else skipped).append(sg)
    return taken, skipped


def nine_gates(gated_rows: list[Row], base_rows: list[Row], skipped_rows: list[Row],
               spy_rth: pd.DataFrame, *, strike_offset, premium_stop_pct,
               base_signals_taken) -> dict:
    """Apply all 9 gates + (a)(b)(c) to the GATED subset. Returns a verdict dict."""
    gm = metrics(gated_rows)
    bm = metrics(base_rows)
    sm = metrics(skipped_rows)
    fails: list[str] = []

    # (a) IMPROVE per-trade expectancy: gated OOS/tr > baseline OOS/tr AND gated full > base.
    improves_oos = gm.get("oos_exp", -1e9) > bm.get("oos_exp", 1e9)
    improves_full = gm.get("exp_dollar", -1e9) > bm.get("exp_dollar", 1e9)
    if not improves_oos:
        fails.append(f"(a)oos_exp_no_lift gated={gm.get('oos_exp')} base={bm.get('oos_exp')}")
    if not improves_full:
        fails.append(f"(a)full_exp_no_lift gated={gm.get('exp_dollar')} base={bm.get('exp_dollar')}")

    # (b) anchor no-regression (OP-16): the gate must NOT skip a J WINNER day.
    skipped_days = {r.date for r in skipped_rows}
    # also consider signal-level skips even if a skipped signal had no fill (uses signals).
    skipped_winner_anchors = sorted(ANCHOR_WINNER_DAYS & skipped_days)
    if skipped_winner_anchors:
        fails.append(f"(b)anchor_winner_skipped={skipped_winner_anchors}")

    # (c) NO-REGRESSION: skipped set net per-trade <= 0 (removes losers/break-even).
    skipped_pt = sm.get("exp_dollar")
    skipped_removes_losers = (skipped_pt is None) or (skipped_pt <= 0.0)
    if not skipped_removes_losers:
        fails.append(f"(c)skipped_set_profitable exp={skipped_pt} (gate removed WINNERS)")

    # ── The 9 structural gates on the GATED subset ──────────────────────────
    # 1 OOS per-trade > 0
    if gm.get("oos_exp", -1) <= 0:
        fails.append(f"g1_oos_exp={gm.get('oos_exp')}<=0")
    # 2 positive_quarters >= 4/6
    if gm.get("positive_quarters_n", 0) < BAR_POS_Q:
        fails.append(f"g2_posQ={gm.get('positive_quarters')}<{BAR_POS_Q}")
    # 3 top5-day < 200%
    t5 = gm.get("top5_day_pct")
    if t5 is None or t5 >= BAR_TOP5:
        fails.append(f"g3_top5day={t5}>=200")
    # 4 n >= 20
    if gm.get("n", 0) < BAR_N:
        fails.append(f"g4_n={gm.get('n')}<20")
    # 5 full-sample drop-top5 > 0
    fd5 = gm.get("drop_top5_per_trade")
    if fd5 is None or fd5 <= 0:
        fails.append(f"g5_full_drop_top5={fd5}<=0")
    # 6 IS-2025-first-half per-trade > 0
    if gm.get("is_h1_exp", -1) <= 0:
        fails.append(f"g6_is_h1_exp={gm.get('is_h1_exp')}<=0")
    # 9 OOS-ALONE drop-top5 > 0  (L173 — the decisive B6 graduated gate)
    od5 = gm.get("oos_drop_top5_per_trade")
    if od5 is None or od5 <= 0:
        fails.append(f"g9_oos_drop_top5={od5}<=0")

    # 8 NO-TRUNCATION (L171): sign holds at chart-stop-only on the SAME gated signals.
    cso_rows = simulate(base_signals_taken, spy_rth, _RIBBON, _VIX,
                        strike_offset=strike_offset, premium_stop_pct=CHART_STOP_ONLY)
    cso_pt = metrics(cso_rows).get("exp_dollar")
    no_trunc = (gm.get("exp_dollar", 0) > 0 and cso_pt is not None and cso_pt > 0) or \
               (gm.get("exp_dollar", 0) <= 0)
    truncation = (gm.get("exp_dollar", 0) > 0 and (cso_pt is None or cso_pt <= 0))
    if truncation:
        fails.append(f"g8_truncation chart_stop_only_exp={cso_pt}<=0 while gated>0")

    # 7 beats random-entry NULL (L172) on the GATED subset (matched count + side mix).
    n_call = sum(1 for r in gated_rows if r.side == "C")
    n_put = sum(1 for r in gated_rows if r.side == "P")
    null_res = {}
    null_pass = False
    if gated_rows:
        null_res = random_entry_null(
            spy_rth, n_signals=len(gated_rows), n_call=n_call, n_put=n_put,
            strike_offset=strike_offset, premium_stop_pct=premium_stop_pct,
            qty=QTY, setup="B7_NULL", triggers=["b7_null"], seeds=NULL_SEEDS)
        ng = null_gate(gm.get("exp_dollar"), gm.get("drop_top5_per_trade"), null_res)
        null_pass = ng.get("null_pass", False)
        if not null_pass:
            fails.append(f"g7_null beats_max={ng.get('beats_null_max')} "
                         f"drop_beats_mean={ng.get('drop_top5_beats_null_mean')} "
                         f"(null_max={null_res.get('per_trade_max')} "
                         f"null_mean={null_res.get('per_trade_mean')})")
    else:
        fails.append("g7_null no_gated_rows")

    return {
        "gated_metrics": gm,
        "baseline_metrics": bm,
        "skipped_metrics": sm,
        "chart_stop_only_exp": cso_pt,
        "null": null_res,
        "improves_oos_exp": bool(improves_oos),
        "improves_full_exp": bool(improves_full),
        "skipped_winner_anchors": skipped_winner_anchors,
        "skipped_removes_losers": bool(skipped_removes_losers),
        "no_truncation_pass": bool(no_trunc),
        "null_pass": bool(null_pass),
        "all_clear": len(fails) == 0,
        "fails": fails,
        "delta_oos_exp": round(gm.get("oos_exp", 0) - bm.get("oos_exp", 0), 2),
        "delta_full_exp": round(gm.get("exp_dollar", 0) - bm.get("exp_dollar", 0), 2),
    }


# module-level handles set in main() so nine_gates' truncation probe can reuse them.
_RIBBON: Optional[pd.DataFrame] = None
_VIX: Optional[pd.Series] = None


def main() -> int:
    global _RIBBON, _VIX
    print("[b7] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[b7] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    _RIBBON = ribbon
    _VIX = vix

    # Causal VIX-regime grids (full-df aligned to spy index = signal.bar_idx).
    vix_arr = vix.to_numpy(float)
    vix_med_g = causal_vix_median(vix_arr, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_arr, VIX_SLOPE_BARS)

    # Detect the LIVE vwap_continuation signals ONCE (full pattern, no gate) — the baseline.
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[b7] baseline signals: {len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    results = {"meta": {
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "baseline_signals": len(signals),
        "baseline_signal_days": sig_days,
        "vix_median_bars": VIX_MEDIAN_BARS,
        "vix_slope_bars": VIX_SLOPE_BARS,
        "favorable_regime": "vix_level <= (trailing_median - low_margin) AND (slope_rule) vix_slope5 <= 0",
        "tiers": [t[0] for t in TIERS],
        "vix_low_margins": VIX_LOW_MARGINS,
        "slope_rules": SLOPE_RULES,
    }, "tiers": {}}

    for tier_label, so, ps in TIERS:
        print(f"\n[b7] ===== TIER {tier_label} (strike_offset={so}, stop={ps}) =====", flush=True)
        base_rows = simulate(signals, spy, ribbon, vix, strike_offset=so, premium_stop_pct=ps)
        bm = metrics(base_rows)
        print(f"  BASELINE: n={bm.get('n')} exp=${bm.get('exp_dollar')} "
              f"oos_n={bm.get('oos_n')} oos_exp=${bm.get('oos_exp')} "
              f"posQ={bm.get('positive_quarters')} top5%={bm.get('top5_day_pct')} "
              f"oos_drop5=${bm.get('oos_drop_top5_per_trade')}", flush=True)

        tier_cells = []
        best = None
        for lm in VIX_LOW_MARGINS:
            for sr in SLOPE_RULES:
                taken, skipped = gate_signals(signals, vix_arr, vix_med_g, vix_slp_g, lm, sr)
                gated_rows = simulate(taken, spy, ribbon, vix, strike_offset=so, premium_stop_pct=ps)
                skipped_rows = simulate(skipped, spy, ribbon, vix, strike_offset=so, premium_stop_pct=ps)
                verdict = nine_gates(gated_rows, base_rows, skipped_rows, spy,
                                     strike_offset=so, premium_stop_pct=ps,
                                     base_signals_taken=taken)
                gm = verdict["gated_metrics"]
                cell = {
                    "low_margin": lm, "slope_rule": sr,
                    "n_taken_signals": len(taken), "n_skipped_signals": len(skipped),
                    "verdict": verdict,
                }
                tier_cells.append(cell)
                print(f"  gate lm={lm} slope={sr:>10} | taken_sig={len(taken):>3} "
                      f"gated_n={gm.get('n','-'):>3} gated_exp=${gm.get('exp_dollar','-'):>7} "
                      f"oos_exp=${gm.get('oos_exp','-'):>7} d_oos={verdict['delta_oos_exp']:>+7} "
                      f"skip_exp=${verdict['skipped_metrics'].get('exp_dollar','-')} "
                      f"-> {'CLEAR' if verdict['all_clear'] else 'no('+';'.join(verdict['fails'][:2])+')'}",
                      flush=True)
                # pick best = all_clear with max delta_oos_exp; else max delta_oos among any
                if best is None:
                    best = cell
                else:
                    bc, cc = best["verdict"], verdict
                    if (cc["all_clear"], cc["delta_oos_exp"]) > (bc["all_clear"], bc["delta_oos_exp"]):
                        best = cell

        results["tiers"][tier_label] = {
            "strike_offset": so, "premium_stop_pct": ps,
            "baseline_metrics": bm,
            "cells": tier_cells,
            "best_cell": best,
            "any_clear": any(c["verdict"]["all_clear"] for c in tier_cells),
        }

    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n[b7] wrote {JSON_OUT}", flush=True)

    _write_md(results)
    print(f"[b7] wrote {MD_OUT}", flush=True)
    return 0


def _fmt_pct(x):
    return "-" if x is None else f"{x}%"


def _write_md(results: dict) -> None:
    meta = results["meta"]
    lines = []
    lines.append("# B7 — vwap_continuation +VIX-REGIME-GATE A/B scorecard")
    lines.append("")
    lines.append(f"Window: `{meta['window']}` | trading days: {meta['trading_days']} | "
                 f"baseline signals: {meta['baseline_signals']} on {meta['baseline_signal_days']} days")
    lines.append("")
    lines.append(f"**Favorable regime (edge#4, causal):** `{meta['favorable_regime']}` "
                 f"(median_bars={meta['vix_median_bars']}, slope_bars={meta['vix_slope_bars']})")
    lines.append("")
    lines.append("**Question (Angle C):** does VIX-regime-gating LIFT the live "
                 "`vwap_continuation` per-trade expectancy? The gate must (a) improve "
                 "per-trade exp, (b) not skip a J winner-day anchor, (c) the SKIPPED set must "
                 "be net <=0 (removes losers), (d) still clear all 9 gates on the gated subset.")
    lines.append("")
    for tier_label, td in results["tiers"].items():
        bm = td["baseline_metrics"]
        best = td["best_cell"]
        bv = best["verdict"]
        gm = bv["gated_metrics"]
        sm = bv["skipped_metrics"]
        lines.append(f"## TIER `{tier_label}` (strike_offset={td['strike_offset']}, "
                     f"stop={td['premium_stop_pct']})")
        lines.append("")
        lines.append("| metric | BASELINE | GATED (best cell) | SKIPPED set | delta (gated-base) |")
        lines.append("|---|---|---|---|---|")
        lines.append(f"| n trades | {bm.get('n')} | {gm.get('n')} | {sm.get('n')} | — |")
        lines.append(f"| full-sample per-trade $ | {bm.get('exp_dollar')} | {gm.get('exp_dollar')} "
                     f"| {sm.get('exp_dollar')} | {bv['delta_full_exp']:+} |")
        lines.append(f"| **OOS(2026) per-trade $** | {bm.get('oos_exp')} (n={bm.get('oos_n')}) "
                     f"| {gm.get('oos_exp')} (n={gm.get('oos_n')}) | {sm.get('oos_exp')} | "
                     f"**{bv['delta_oos_exp']:+}** |")
        lines.append(f"| OOS drop-top5 /tr (g9) | {bm.get('oos_drop_top5_per_trade')} "
                     f"| {gm.get('oos_drop_top5_per_trade')} | — | — |")
        lines.append(f"| full drop-top5 /tr (g5) | {bm.get('drop_top5_per_trade')} "
                     f"| {gm.get('drop_top5_per_trade')} | — | — |")
        lines.append(f"| positive quarters | {bm.get('positive_quarters')} "
                     f"| {gm.get('positive_quarters')} | — | — |")
        lines.append(f"| top5-day % | {_fmt_pct(bm.get('top5_day_pct'))} "
                     f"| {_fmt_pct(gm.get('top5_day_pct'))} | — | — |")
        lines.append(f"| WR % | {bm.get('wr_pct')} | {gm.get('wr_pct')} | {sm.get('wr_pct')} | — |")
        lines.append("")
        lines.append(f"**Best gated cell:** low_margin={best['low_margin']}, "
                     f"slope_rule={best['slope_rule']} | taken_signals={best['n_taken_signals']}, "
                     f"skipped_signals={best['n_skipped_signals']}")
        lines.append("")
        lines.append(f"- (a) improves OOS exp: **{bv['improves_oos_exp']}** | improves full exp: "
                     f"**{bv['improves_full_exp']}**")
        lines.append(f"- (b) anchor winner-days skipped: "
                     f"**{bv['skipped_winner_anchors'] or 'NONE (pass)'}**")
        lines.append(f"- (c) SKIPPED set net per-trade <=0 (removes losers): "
                     f"**{bv['skipped_removes_losers']}** (skipped exp=${sm.get('exp_dollar')})")
        lines.append(f"- (d) 9-gate clear on gated subset: **{bv['all_clear']}** "
                     f"| null_pass={bv['null_pass']} | no_truncation={bv['no_truncation_pass']} "
                     f"| chart_stop_only_exp=${bv['chart_stop_only_exp']}")
        if bv["null"]:
            lines.append(f"  - null: max=${bv['null'].get('per_trade_max')} "
                         f"mean=${bv['null'].get('per_trade_mean')}")
        if bv["fails"]:
            lines.append(f"- **FAILS:** {'; '.join(bv['fails'])}")
        verdict_word = ("LIVE_EDGE_IMPROVEMENT" if bv["all_clear"] else
                        ("LEAD" if (bv["improves_oos_exp"] and gm.get("oos_exp", -1) > 0)
                         else "DEAD (gate does not improve the live edge)"))
        lines.append("")
        lines.append(f"### TIER verdict: **{verdict_word}**")
        lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
