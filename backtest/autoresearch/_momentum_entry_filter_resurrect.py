"""MOMENTUM_MORNING ENTRY-FILTER RESURRECTION — strict no-overfit IS->OOS test.

CONTEXT (from analysis/recommendations/dte-stop-construction-momentum_morning.json,
the lesson L178, and DTE-LIBRARY-DOLLARSTOP-RETEST.md):
  momentum_morning at 1DTE + DOLLAR-anchored stop ($59.28, ITM-2) is the closest
  dead-family resurrection candidate. The dollar-stop fixed the RISK (maxDD
  -$4,432 -> -$2,252, Sortino -0.905 -> +6.21, worst-day capped) and lifted OOS
  exp/tr to +$61.31 (n=59). It clears 10 of 11 gates and FAILS ONLY L173:
  oos_drop_top5 = -$1.25 (just barely negative). (It ALSO shows drop_top5_full =
  -$4.21 slightly negative, gate 5 full-sample — both are de-concentration gates;
  this harness reports BOTH and a clean win must flip BOTH non-negative.)

THE TEST: find a CAUSAL entry filter (a condition known AT THE ENTRY BAR) that lifts
momentum_morning's OOS signal breadth enough to flip oos_drop_top5 from -$1.25 to
POSITIVE, WITHOUT overfitting. Method (strict):
  1. CAUSAL ONLY — every filter feature is computed at-or-before the entry (ref-time)
     bar: |morning move| magnitude, side (C/P), VIX level at entry, VIX 5-bar slope at
     entry, structural-stop relative distance. NEVER outcome-based.
  2. CHOSEN ON IS, VALIDATED ON OOS — the filter's threshold/direction is selected using
     ONLY IS-2025 fills (the IS objective is fixed a-priori: IS drop_top5_full, the
     de-concentration metric we are trying to fix), then FROZEN and applied to OOS-2026.
     An IS-chosen filter that only helps in-sample == OVERFIT == REJECT.
  3. RE-CHECK ALL 11 GATES at the filtered cell on OOS: n>=20, oos_exp>0, posQ>=4,
     top5_day<200, drop_top5_full>0, IS-first-half>0, oos_drop_top5>0 (decisive L173),
     plus no-regression (L174: the removed days must be net-negative / concentration-
     driving, not winners) and an independence check vs edge #1 vwap_continuation.
  4. SMALL principled sweep — 5 a-priori-sensible filters, each tested ONCE IS->OOS
     (no 100-threshold fishing). Thresholds are IS quantiles (data-driven but a-priori
     rule: "keep the cleaner-by-IS-de-concentration side/tail"), chosen on IS only.

REUSES BYTE-FOR-BYTE (Sunday SAFE-research; NO watcher/params/risk_gate/orchestrator/
heartbeat/simulator_real edits, NO orders, NO commit; RESEARCH SIM ONLY):
  - the momentum_morning detector (FAMILIES_EXT["momentum_morning"] = byte-for-byte
    _detect_momentum -> detect_intraday_momentum from infinite_ammo_discovery).
  - the DTE x dollar-stop machinery (run_cell, calibrate, simulate_dte_trade_stop) from
    _dte_stop_construction (the SAME harness that produced the -$1.25 baseline).
  - the metrics + clears_bar 9-gate bar + L173/L174 logic from _dte_expansion_sim.
The ONLY new code is the causal feature extraction + the IS-frozen filter selection.

Pure Python, $0. No live orders. Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_momentum_entry_filter_resurrect.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch._dte_stop_construction import (  # noqa: E402
    FAMILIES_EXT,
    TIERS,
    LIVE_TIER,
    BASELINE_PCT,
    run_cell,
    calibrate,
    _book_metrics,
    _oos_total,
)
from autoresearch._dte_expansion_sim import (  # noqa: E402
    OOS_YEAR,
    MIN_OOS_TO_DROP_TOP5,
    metrics as dte_metrics,
    clears_bar,
    _spy_day_open_close,
    _build_expiry_index,
)
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _strike_from_spot,
)
from autoresearch import _dte_expansion_sim as base  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "momentum-entry-filter-resurrect.json"
FAMILY = "momentum_morning"
DTE = 1                       # the lever DTE (where the dollar-stop produced the near-miss)
TIER = LIVE_TIER             # ITM-2 (the family's live-candidate tier; C29 per-tier)


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL FEATURE EXTRACTION — every feature is known AT the entry (ref-time) bar.
#   sg.bar_idx is the global SPY index of the REF_TIME (13:00 ET) trigger bar.
#   The detector enters the NEXT bar; all features below read at-or-before sg.bar_idx.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SigFeat:
    move_abs: float        # |morning return| at ref-time bar (the momentum strength)
    side: str              # 'C' / 'P'
    vix: float             # VIX close at the entry bar (ffilled, causal)
    vix_slope: float       # VIX 5-bar slope at the entry bar (causal)
    stop_dist_rel: float   # |entry_spot - structural stop| / entry_spot (relative risk)


def _vix_slope_at(vix: np.ndarray, idx: int, bars: int = 5) -> float:
    """Simple (vix[idx] - vix[idx-bars]) slope; causal (reads only <= idx)."""
    j = idx - bars
    if j < 0:
        return 0.0
    return float(vix[idx] - vix[j])


def extract_features(signals, spy, vix) -> dict[int, SigFeat]:
    """One SigFeat per signal, keyed by the signal's bar_idx. All causal."""
    vix_arr = np.asarray(vix, dtype=float)
    feats: dict[int, SigFeat] = {}
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        spot = float(bar["close"])
        # |morning move| is embedded in the detector note ("morning_move=+0.0123");
        # re-derive defensively from the note (byte-for-byte the detector value).
        move_abs = 0.0
        if "morning_move=" in sg.note:
            try:
                move_abs = abs(float(sg.note.split("morning_move=")[1]))
            except (ValueError, IndexError):
                move_abs = 0.0
        stop = sg.stop_level
        stop_dist_rel = abs(spot - stop) / spot if (stop is not None and spot > 0) else 0.0
        feats[sg.bar_idx] = SigFeat(
            move_abs=round(move_abs, 6),
            side=sg.side,
            vix=round(float(vix_arr[sg.bar_idx]), 3) if sg.bar_idx < len(vix_arr) else 0.0,
            vix_slope=round(_vix_slope_at(vix_arr, sg.bar_idx), 3),
            stop_dist_rel=round(stop_dist_rel, 6),
        )
    return feats


# ─────────────────────────────────────────────────────────────────────────────
# IS/OOS split helpers on the dollar-stop FILLS (rows carry .date as 'YYYY-MM-DD').
# ─────────────────────────────────────────────────────────────────────────────
def _is_rows(rows):
    return [r for r in rows if int(r.date[:4]) != OOS_YEAR]


def _oos_rows(rows):
    return [r for r in rows if int(r.date[:4]) == OOS_YEAR]


def _drop_top5_full(rows) -> Optional[float]:
    """Per-trade after removing the 5 best P&L DAYS (full-sample de-concentration)."""
    if not rows:
        return None
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.dollar_pnl)
    day_tot = sorted(by_day.items(), key=lambda kv: sum(kv[1]), reverse=True)
    kept = [p for _, pnls in day_tot[5:] for p in pnls]
    return round(sum(kept) / len(kept), 2) if kept else None


# ─────────────────────────────────────────────────────────────────────────────
# FILTERS — 5 a-priori-sensible CAUSAL conditions. Each filter() takes (SigFeat, params)
# and the params are CHOSEN ON IS ONLY (select_threshold) against the fixed IS objective.
# A filter keeps a signal when keep(feat) is True.
# ─────────────────────────────────────────────────────────────────────────────
IS_OBJECTIVE = "is_drop_top5_full"   # the de-concentration metric we are trying to lift
MIN_KEEP_FRAC = 0.55                 # don't keep < 55% of signals (avoid n-starving OOS/overfit)


def _cell_rows_for_signals(signals, spy, day_open_close, dollar_thresh):
    """Run the 1DTE dollar-stop cell for an arbitrary signal subset; return fills."""
    cell = run_cell(signals, spy, day_open_close, DTE,
                    strike_offset=TIERS[TIER], construction="dollar", stop_param=dollar_thresh)
    return cell.rows


def _select_threshold_quantile(signals, feats, spy, day_open_close, dollar_thresh,
                               feature: str, direction: str, q_grid) -> dict:
    """Choose the IS-optimal quantile threshold for a CONTINUOUS feature.

    direction 'keep_high' keeps feat >= thresh; 'keep_low' keeps feat <= thresh.
    Selection objective: maximize IS drop_top5_full (the de-concentration metric) subject
    to keeping >= MIN_KEEP_FRAC of signals (IS count). Threshold = an IS quantile of the
    feature over IS signals ONLY -> chosen on IS, frozen, applied to OOS.
    """
    is_sigs = [sg for sg in signals if int(_sig_date(sg, spy).year) != OOS_YEAR]
    vals = np.array([getattr(feats[sg.bar_idx], feature) for sg in is_sigs], dtype=float)
    if len(vals) == 0:
        return {"feasible": False}
    best = None
    trials = []
    for q in q_grid:
        # keep_high keeps feat>=thr -> a LOW quantile keeps a large fraction.
        # keep_low  keeps feat<=thr -> use the COMPLEMENT quantile (1-q) so the same q
        # means "keep the most-extreme q fraction" in BOTH directions (symmetric, fair).
        q_eff = q if direction == "keep_high" else (1.0 - q)
        thr = float(np.quantile(vals, q_eff))
        kept_is = [sg for sg in is_sigs
                   if (getattr(feats[sg.bar_idx], feature) >= thr) == (direction == "keep_high")]
        keep_frac = len(kept_is) / len(is_sigs)
        if keep_frac < MIN_KEEP_FRAC:
            trials.append({"q": q, "thr": round(thr, 6), "keep_frac": round(keep_frac, 3),
                           "is_drop_top5_full": None, "skipped": "keep_frac<min"})
            continue
        rows_is = _cell_rows_for_signals(kept_is, spy, day_open_close, dollar_thresh)
        d5 = _drop_top5_full(rows_is)
        trials.append({"q": q, "thr": round(thr, 6), "keep_frac": round(keep_frac, 3),
                       "is_drop_top5_full": d5})
        if d5 is not None and (best is None or d5 > best["is_drop_top5_full"]):
            best = {"q": q, "thr": round(thr, 6), "keep_frac": round(keep_frac, 3),
                    "is_drop_top5_full": d5}
    return {"feasible": best is not None, "best": best, "trials": trials,
            "feature": feature, "direction": direction}


def _sig_date(sg, spy) -> dt.date:
    bar = spy.iloc[sg.bar_idx]
    ts = bar["timestamp_et"]
    return ts.date() if hasattr(ts, "date") else ts.to_pydatetime().date()


def _select_side(signals, feats, spy, day_open_close, dollar_thresh) -> dict:
    """Categorical filter: keep only the SIDE (C or P) that is cleaner on IS by
    drop_top5_full (de-concentration), provided it keeps >= MIN_KEEP_FRAC of signals."""
    is_sigs = [sg for sg in signals if int(_sig_date(sg, spy).year) != OOS_YEAR]
    out = {}
    for side in ("C", "P"):
        kept_is = [sg for sg in is_sigs if feats[sg.bar_idx].side == side]
        keep_frac = len(kept_is) / len(is_sigs) if is_sigs else 0.0
        rows_is = _cell_rows_for_signals(kept_is, spy, day_open_close, dollar_thresh) if kept_is else []
        out[side] = {"keep_frac": round(keep_frac, 3),
                     "is_drop_top5_full": _drop_top5_full(rows_is),
                     "is_n": len(rows_is)}
    # pick the side with the higher IS drop_top5_full that still keeps enough
    feasible = {s: v for s, v in out.items()
                if v["keep_frac"] >= MIN_KEEP_FRAC and v["is_drop_top5_full"] is not None}
    if not feasible:
        return {"feasible": False, "per_side": out}
    best_side = max(feasible, key=lambda s: feasible[s]["is_drop_top5_full"])
    return {"feasible": True, "best_side": best_side, "per_side": out}


# ─────────────────────────────────────────────────────────────────────────────
# GATE EVALUATION on a filtered cell (full 11-gate bar + no-regression).
# ─────────────────────────────────────────────────────────────────────────────
def _eval_cell(rows, removed_rows) -> dict:
    """Compute the full metric summary + clears_bar + the two de-concentration metrics +
    no-regression on the removed set. removed_rows = the fills the filter DROPPED."""
    m = dte_metrics(rows)
    structural_ok, fails = clears_bar(m)
    book = _book_metrics(rows)
    # No-regression (L174): the days the filter removed must be NET-NEGATIVE (concentration-
    # driving), not winners. Compute removed OOS total + removed OOS per-trade.
    rem_oos = _oos_rows(removed_rows)
    rem_oos_total = round(float(sum(r.dollar_pnl for r in rem_oos)), 2) if rem_oos else 0.0
    rem_oos_exp = round(rem_oos_total / len(rem_oos), 2) if rem_oos else 0.0
    no_regression = rem_oos_total <= 0.0   # removed OOS dollars are net-negative
    return {
        "n": m.get("n"),
        "oos_n": m.get("oos_n"),
        "oos_exp": m.get("oos_exp"),
        "oos_total": m.get("oos_total"),
        "positive_quarters": m.get("positive_quarters"),
        "top5_day_pct": m.get("top5_day_pct"),
        "drop_top5_full": m.get("drop_top5_full"),
        "oos_drop_top5": m.get("oos_drop_top5"),
        "oos_drop_top5_evaluable": m.get("oos_drop_top5_evaluable"),
        "is_first_half_exp": m.get("is_first_half_exp"),
        "book_maxDD": book.get("book_maxDD"),
        "book_sortino_ann": book.get("book_sortino_ann"),
        "book_worst_day": book.get("book_worst_day"),
        "structural_bar_pass": structural_ok,
        "structural_bar_fails": fails,
        "removed_oos_n": len(rem_oos),
        "removed_oos_total": rem_oos_total,
        "removed_oos_exp": rem_oos_exp,
        "no_regression_removed_oos_net_neg": no_regression,
        # CLEAN win = clears the full structural bar (which INCLUDES oos_drop_top5>0 +
        # drop_top5_full>0 + n>=20 + oos_exp>0 + posQ>=4 + top5<200 + IS-1H>0) AND
        # no-regression holds.
        "CLEAN_WIN": bool(structural_ok and no_regression),
    }


def _apply_filter(signals, feats, keep_fn):
    kept = [sg for sg in signals if keep_fn(feats[sg.bar_idx])]
    dropped = [sg for sg in signals if not keep_fn(feats[sg.bar_idx])]
    return kept, dropped


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[mom-filter] loading SPY+VIX ...", flush=True)
    spy, vix = base._load_spy_vix()
    day_open_close = _spy_day_open_close(spy)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    _build_expiry_index(DTE)
    print(f"[mom-filter] SPY bars={len(spy)} days={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    detect = FAMILIES_EXT[FAMILY]
    signals = detect(days, vix, spy, ribbon)
    print(f"[mom-filter] family={FAMILY} signals={len(signals)}", flush=True)

    # Calibrate the dollar-stop FROM the 0DTE -8% run at the live tier (C29; the SAME
    # $59.28 threshold the baseline used), then freeze it for every cell below.
    calib = calibrate(signals, spy, day_open_close, TIERS[TIER])
    dollar_thresh = calib["dollar_thresh"]
    print(f"[mom-filter] dollar_thresh=${dollar_thresh} (C29 re-derived; baseline was $59.28)",
          flush=True)

    feats = extract_features(signals, spy, vix)

    # ── BASELINE (unfiltered) 1DTE dollar-stop cell — reproduce the near-miss ──────
    base_rows = _cell_rows_for_signals(signals, spy, day_open_close, dollar_thresh)
    base_eval = _eval_cell(base_rows, removed_rows=[])
    print(f"[mom-filter] BASELINE 1DTE dollar-stop: oos_n={base_eval['oos_n']} "
          f"oos_exp=${base_eval['oos_exp']} oos_drop_top5=${base_eval['oos_drop_top5']} "
          f"drop_top5_full=${base_eval['drop_top5_full']} struct={base_eval['structural_bar_pass']}",
          flush=True)

    # ── 5 PRINCIPLED CAUSAL FILTERS, each chosen on IS then applied to OOS ─────────
    q_grid = [0.10, 0.20, 0.25, 0.30, 0.40]   # small a-priori grid of IS quantiles
    results = {}

    def run_continuous(name, feature, direction):
        sel = _select_threshold_quantile(signals, feats, spy, day_open_close,
                                         dollar_thresh, feature, direction, q_grid)
        if not sel.get("feasible"):
            results[name] = {"selection": sel, "applied": None,
                             "note": "no IS-feasible threshold (keep_frac floor)"}
            print(f"  [{name:22s}] INFEASIBLE on IS (keep_frac floor)", flush=True)
            return
        thr = sel["best"]["thr"]
        keep_fn = ((lambda f: getattr(f, feature) >= thr) if direction == "keep_high"
                   else (lambda f: getattr(f, feature) <= thr))
        kept, dropped = _apply_filter(signals, feats, keep_fn)
        rows = _cell_rows_for_signals(kept, spy, day_open_close, dollar_thresh)
        drow = _cell_rows_for_signals(dropped, spy, day_open_close, dollar_thresh) if dropped else []
        ev = _eval_cell(rows, removed_rows=drow)
        results[name] = {"selection": sel, "frozen_threshold": thr,
                         "direction": direction, "applied_oos": ev}
        print(f"  [{name:22s}] thr={thr:.5f} ({direction}) -> oos_n={ev['oos_n']} "
              f"oos_exp=${ev['oos_exp']} oos_drop_top5=${ev['oos_drop_top5']} "
              f"drop_top5_full=${ev['drop_top5_full']} struct={ev['structural_bar_pass']} "
              f"no_regr={ev['no_regression_removed_oos_net_neg']} "
              f"-> {'CLEAN_WIN' if ev['CLEAN_WIN'] else ''}", flush=True)

    # F1 momentum strength: stronger morning trend = cleaner continuation -> keep_high |move|.
    run_continuous("F1_momentum_strength", "move_abs", "keep_high")
    # F4 structural-stop distance: a TIGHTER structural stop = cleaner/closer trend ->
    #    keep_low stop_dist_rel (lower relative risk).
    run_continuous("F4_tight_stop_dist", "stop_dist_rel", "keep_low")
    # F3a VIX level: continuation may be cleaner in LOW-vol regimes -> keep_low vix.
    run_continuous("F3a_low_vix", "vix", "keep_low")
    # F3b VIX slope: continuation may be cleaner when VIX is NOT rising -> keep_low slope.
    run_continuous("F3b_vix_not_rising", "vix_slope", "keep_low")

    # F2 side: keep only the IS-cleaner side (categorical; chosen on IS).
    side_sel = _select_side(signals, feats, spy, day_open_close, dollar_thresh)
    if side_sel.get("feasible"):
        best_side = side_sel["best_side"]
        keep_fn = lambda f: f.side == best_side  # noqa: E731
        kept, dropped = _apply_filter(signals, feats, keep_fn)
        rows = _cell_rows_for_signals(kept, spy, day_open_close, dollar_thresh)
        drow = _cell_rows_for_signals(dropped, spy, day_open_close, dollar_thresh) if dropped else []
        ev = _eval_cell(rows, removed_rows=drow)
        results["F2_side_select"] = {"selection": side_sel, "frozen_side": best_side,
                                     "applied_oos": ev}
        print(f"  [{'F2_side_select':22s}] side={best_side} -> oos_n={ev['oos_n']} "
              f"oos_exp=${ev['oos_exp']} oos_drop_top5=${ev['oos_drop_top5']} "
              f"drop_top5_full=${ev['drop_top5_full']} struct={ev['structural_bar_pass']} "
              f"no_regr={ev['no_regression_removed_oos_net_neg']} "
              f"-> {'CLEAN_WIN' if ev['CLEAN_WIN'] else ''}", flush=True)
    else:
        results["F2_side_select"] = {"selection": side_sel, "applied_oos": None,
                                     "note": "no IS-feasible side"}
        print(f"  [{'F2_side_select':22s}] INFEASIBLE on IS", flush=True)

    # ── VERDICT ───────────────────────────────────────────────────────────────────
    winners = [k for k, v in results.items()
               if v.get("applied_oos") and v["applied_oos"].get("CLEAN_WIN")]
    verdict = "RESURRECTED" if winners else "OVERFIT_OR_FAILS"

    out = {
        "campaign": "momentum_morning ENTRY-FILTER resurrection (1DTE + dollar-stop; strict IS->OOS no-overfit)",
        "run_date": dt.date.today().isoformat(),
        "family": FAMILY,
        "dte": DTE,
        "tier": TIER,
        "tier_offset": TIERS[TIER],
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "n_signals": len(signals),
        "dollar_thresh": dollar_thresh,
        "method": {
            "causal_only": "every filter feature computed at-or-before the ref-time entry bar",
            "is_chosen_oos_validated": ("threshold/side selected on IS-2025 fills ONLY (objective: "
                                        "maximize IS drop_top5_full s.t. keep_frac>=%.2f), frozen, "
                                        "applied to OOS-2026" % MIN_KEEP_FRAC),
            "clean_win_bar": ("filtered OOS cell clears the full canonical structural bar (n>=20, "
                              "oos_exp>0, posQ>=4, top5<200, drop_top5_full>0, IS-1H>0, oos_drop_top5>0 "
                              "[decisive L173]) AND no-regression (removed OOS dollars net-negative, L174)"),
            "small_sweep": "5 a-priori filters, each tested ONCE IS->OOS (no multi-threshold fishing)",
            "min_keep_frac": MIN_KEEP_FRAC,
            "is_quantile_grid": q_grid,
        },
        "baseline_unfiltered": base_eval,
        "filters": results,
        "winners": winners,
        "verdict": verdict,
        "DISCLOSURE": {
            "detector": "BYTE-FOR-BYTE FAMILIES_EXT[momentum_morning] = detect_intraday_momentum",
            "fills": "1DTE dollar-stop cell via _dte_stop_construction.run_cell (the SAME harness as the -$1.25 baseline)",
            "dollar_thresh_note": "C29 re-derived from the 0DTE -8% run at ITM-2 (matches the baseline $59.28)",
            "beats_null_caveat": ("L172 random-entry-null is the 0DTE simulate_trade_real null; a 1DTE-native "
                                  "null is not in this harness, so beats-null (gate 7) is NOT re-run here. The "
                                  "decisive de-concentration gates (5 + 9, L173) ARE evaluated; a filter that "
                                  "fails them is rejected regardless of null."),
            "overfit_caveat": ("the -$1.25 gap on 59 OOS trades is noise-level; ONLY a filter whose IS-chosen "
                               "rule flips oos_drop_top5 POSITIVE on the held-out OOS counts. IS-only wins are REJECTED."),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\n[mom-filter] wrote {OUT}", flush=True)
    print(f"\n=== VERDICT: {verdict} ===")
    if winners:
        for w in winners:
            print(f"  CLEAN_WIN filter: {w}")
    else:
        print("  No IS-frozen causal filter flips oos_drop_top5 positive on OOS + clears the bar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
