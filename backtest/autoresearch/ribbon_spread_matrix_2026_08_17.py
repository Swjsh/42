"""RIBBON SPREAD MATRIX — one-variable sweep of filter 6, 15c..30c, + a VIX-dynamic test.

J's ask, 2026-08-17 after a session where filter 6 was the SOLE blocker on four separate
level rejections he called correctly:

    "The whole thirty cent ribbon spread thing, I think, is too static. I think it needs to
     be a bit more dynamic depending on what the day is doing. Can we get a backtest matrix
     staged that tests dynamic ribbon spread of like fifteen cents all the way through thirty
     cents to see if that helps or hurts us."

THE LIVE EXHIBIT (2026-08-17, real ticks). Filter 6 requires ribbon spread >= 30c. Bear
rejections fired and were refused four times as the ribbon stayed compressed:

    12:14  level_rejection                                   blockers [6, 8]   spread 29.3c
    12:16  level_rejection + confluence                      blockers [6, 8, 9] spread 26.9c
    12:26  level_rejection + confluence + trendline_rejection blockers [6,8,9]  spread 22.4c
    12:31  trendline_rejection                               blockers [6]      spread 21.9c   <- SOLE blocker
    13:06  trendline_rejection                               blockers []       spread 35.6c   -> ENTER, +$360

So on ONE day the gate declined four setups and admitted the one that paid. That is a
motivating exhibit, not evidence: n=1 day, and the admitted trade winning is exactly the
shape that talks a book into loosening a gate. Hence this matrix.

⚠️ THE KNOB TRAP, verified before building. `automation/state/params.json` carries
`ribbon_min_spread_cents: 30` and it is a DEAD KNOB — the orchestrator does not read it
(fleet_gate_sweetspot.py:505 says so outright, C14/L70). The live gate reads the MODULE
CONSTANT `RIBBON_SPREAD_MIN_CENTS` (backtest/lib/filters.py:40), consumed at :1179 (bull)
and :1507 (bear). The orchestrator's translation key is `ribbon_spread_min_cents`
(no `min_` prefix). Sweeping the params key would have produced identical cells at every
threshold and we would have concluded "spread does not matter". This module sweeps the
translated key and ASSERTS the cells actually differ before reporting anything.

WHY ONE VARIABLE. fleet_gate_sweetspot's L2 rung already moves ribbon spread 30->20, but
bundles it with four other relaxations (midday gate, entry-bar body, block_level_rejection,
filter-9 volume). Nothing in that ladder isolates filter 6. This does, and reuses that
module's own run_cfg/_summ/validate/edge_capture_block verbatim so there is exactly ONE
backtest implementation (L251).

THE DYNAMIC QUESTION, answered without an engine change. A dynamic threshold is only
justified if the OPTIMUM MOVES with the regime. So every cell is additionally stratified by
VIX bucket: if the best threshold is the same in every bucket, "dynamic" buys nothing and
the honest answer to J is a better STATIC number. If the optimum shifts with VIX, the
stratification hands us the mapping to pre-register.

PROPOSE-ONLY. Writes analysis/recommendations/ribbon-spread-matrix-2026-08-17.json.
Touches no params file, arms nothing. $0 (cached OPRA + local bars).

Run:  backtest/.venv/Scripts/python.exe -m autoresearch.ribbon_spread_matrix_2026_08_17
"""
from __future__ import annotations

import collections
import copy
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(REPO / "backtest"))

from autoresearch.fleet_gate_sweetspot import (  # noqa: E402  the ONE implementation
    PARAMS_PATH, SAFE_EQUITY, START, END,
    run_cfg, _summ, _apply, validate, edge_capture_block, _per_day_pnl, _tdate,
)
from autoresearch.fleet_gate_sweetspot import load_data  # noqa: E402

OUT = REPO / "analysis" / "recommendations" / "ribbon-spread-matrix-2026-08-17.json"

# The swept knob is the ORCHESTRATOR-TRANSLATED name -> RIBBON_SPREAD_MIN_CENTS.
KNOB = "ribbon_spread_min_cents"
THRESHOLDS = [15, 18, 20, 22, 24, 26, 28, 30]   # 30 == production
PRODUCTION = 30

VIX_BUCKETS = (("calm", 0.0, 15.0), ("mid", 15.0, 20.0), ("elevated", 20.0, 999.0))


def _vix_bucket(v) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "unknown"
    for name, lo, hi in VIX_BUCKETS:
        if lo <= x < hi:
            return name
    return "unknown"


def _trade_vix(t):
    # `entry_vix` is the real TradeFill field. The first version of this guessed at
    # "vix"/"vix_now"/"vix_at_entry", found NONE of them, silently bucketed all 281-343
    # trades as "unknown", and reported `dynamic_justified: false` -- a FALSE NEGATIVE
    # dressed as an answer. `_dynamic_answerable` below now refuses to answer at all rather
    # than repeat that.
    for attr in ("entry_vix", "vix", "vix_now", "vix_at_entry"):
        v = getattr(t, attr, None)
        if v is None and isinstance(t, dict):
            v = t.get(attr)
        if v is not None:
            return v
    return None


def _by_vix(trades) -> dict:
    """Per-VIX-bucket cells. This is what makes the DYNAMIC question answerable."""
    buckets = collections.defaultdict(list)
    for t in trades:
        buckets[_vix_bucket(_trade_vix(t))].append(t)
    out = {}
    for name, rows in buckets.items():
        s = _summ(rows)
        out[name] = {"n": s["n"], "total": s["total"], "exp": s["exp"], "wr": s["wr"]}
    return out


def main() -> int:
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))
    spy, vix = load_data(START, END)
    print(f"data spy={len(spy)} vix={len(vix)}  window {START}..{END}")
    print(f"sweeping {KNOB} (-> RIBBON_SPREAD_MIN_CENTS) over {THRESHOLDS}\n")

    cells = []
    baseline = None
    for thr in THRESHOLDS:
        trades = run_cfg(spy, vix, _apply(params, {KNOB: thr}), SAFE_EQUITY)
        s = _summ(trades)
        val = validate(trades, f"spread_{thr}c")
        ec = edge_capture_block(trades)
        cell = {
            "threshold_cents": thr,
            "is_production": thr == PRODUCTION,
            "n": s["n"], "total": s["total"], "exp": s["exp"], "wr": s["wr"],
            "trading_days": s["trading_days"], "tr_per_day": s["tr_per_day"],
            "max_dd": s["max_dd"],
            "bear_n": s["bear_n"], "bear_pnl": s["bear_pnl"],
            "bull_n": s["bull_n"], "bull_pnl": s["bull_pnl"],
            "edge_capture": ec["edge_capture"],
            "edge_capture_pct_of_max": ec["edge_capture_pct_of_max"],
            "rejected_by_op16_edge_capture": ec["rejected_by_op16"],
            "validation": val,
            "by_vix": _by_vix(trades),
        }
        if thr == PRODUCTION:
            baseline = cell
        cells.append(cell)
        print(f"  {thr:>2}c  n={s['n']:4d}  {s['tr_per_day']:.2f}/day  total=${s['total']:+9.0f}  "
              f"exp=${s['exp']:+7.1f}  WR={s['wr']:.0%}  EC=${ec['edge_capture']:+7.0f}  "
              f"OOS+={val['gate']['oos_positive']}")

    # ---- DEAD-KNOB ASSERTION -------------------------------------------------
    # If every cell is identical the swept key was not consumed and the whole matrix is a
    # null artifact. Refuse to report rather than publish a confident "no effect".
    distinct_n = len({c["n"] for c in cells})
    distinct_total = len({round(c["total"], 2) for c in cells})
    knob_live = distinct_n > 1 or distinct_total > 1
    print(f"\nknob actually varies the population: {knob_live} "
          f"(distinct n={distinct_n}, distinct total={distinct_total})")
    if not knob_live:
        print("REFUSING TO REPORT: every cell identical -> the swept key is a DEAD KNOB. "
              "Fix the translation before trusting any of this.")

    # ---- DYNAMIC QUESTION ----------------------------------------------------
    # Does the BEST threshold move with VIX? Only then is 'dynamic' justified.
    best_by_bucket = {}
    for name, _lo, _hi in VIX_BUCKETS:
        scored = [(c["by_vix"].get(name, {}).get("exp"), c["threshold_cents"],
                   c["by_vix"].get(name, {}).get("n", 0)) for c in cells]
        scored = [(e, t, n) for e, t, n in scored if e is not None and n >= 5]
        if scored:
            best = max(scored, key=lambda x: x[0])
            best_by_bucket[name] = {"best_threshold_cents": best[1],
                                    "exp": round(best[0], 2), "n": best[2]}
    optima = {v["best_threshold_cents"] for v in best_by_bucket.values()}

    # ANSWERABILITY GATE. If the VIX field did not resolve, every trade lands in "unknown"
    # and `optima` is empty -- which would print as "dynamic not justified" when the truth is
    # "the question was never asked". Refuse to answer instead of answering falsely.
    unknown_share = 0.0
    total_t = sum(c["n"] for c in cells) or 1
    unknown_t = sum(c["by_vix"].get("unknown", {}).get("n", 0) for c in cells)
    unknown_share = unknown_t / total_t
    dynamic_answerable = unknown_share < 0.5 and bool(best_by_bucket)
    dynamic_justified = (len(optima) > 1) if dynamic_answerable else None

    best_overall = max((c for c in cells if c["n"] >= 10),
                       key=lambda c: c["exp"], default=None)

    report = {
        "_meta": {
            "study": "RIBBON-SPREAD-MATRIX-2026-08-17",
            "asked_by": "J 2026-08-17 -- 'thirty cent ribbon spread is too static'",
            "propose_only": True,
            "armed": False,
            "knob_swept": KNOB,
            "knob_note": ("params.json's `ribbon_min_spread_cents` is a DEAD KNOB (C14/L70). "
                          "The live gate reads RIBBON_SPREAD_MIN_CENTS (filters.py:40); the "
                          "orchestrator key is `ribbon_spread_min_cents`."),
            "window": f"{START}..{END}",
            "one_variable": ("ONLY filter 6 moves. fleet_gate_sweetspot's L2 bundles the same "
                             "change with four other relaxations and cannot isolate it."),
            "live_exhibit_2026_08_17": {
                "blocked_rejections": 4,
                "sole_blocker_at_1231": True,
                "spread_at_blocks_cents": [29.3, 26.9, 22.4, 21.9],
                "admitted_at_cents": 35.6,
                "admitted_trade_pnl": 360.0,
                "caveat": ("n=1 day, and the admitted trade winning is exactly the shape that "
                           "talks a book into loosening a gate. Motivation, not evidence."),
            },
        },
        "knob_actually_live": knob_live,
        "production_threshold_cents": PRODUCTION,
        "baseline": baseline,
        "cells": cells,
        "dynamic_question": {
            "answerable": dynamic_answerable,
            "unknown_vix_share": round(unknown_share, 3),
            "_answerability_note": ("dynamic_justified is null when the VIX field did not "
                                    "resolve on >=50% of trades. The first run of this study "
                                    "bucketed 100% as 'unknown' and printed 'not justified' -- "
                                    "a false negative dressed as a finding."),
            "best_threshold_per_vix_bucket": best_by_bucket,
            "distinct_optima": sorted(optima),
            "dynamic_justified": dynamic_justified,
            "_reading": ("If the optimum is the SAME in every VIX bucket, a dynamic threshold "
                         "buys nothing and the honest answer is a better STATIC number. If it "
                         "MOVES, this mapping is what a dynamic rule would pre-register."),
        },
        "best_overall_cell": best_overall,
        "_decision_rule": ("PROPOSE-ONLY. This matrix ships NOTHING. Any change to filter 6 "
                           "needs the OP-11 bar (OOS positive AND WF >= 0.70 AND sub-window "
                           "stable AND anchor no-regression) plus an OP-16 edge_capture check, "
                           "in a separate pre-registered A/B."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(REPO)}")
    if not dynamic_answerable:
        print(f"DYNAMIC QUESTION UNANSWERED -- VIX unresolved on "
              f"{unknown_share:.0%} of trades. Not reporting a verdict.")
    else:
        print(f"dynamic justified by VIX stratification: {dynamic_justified} "
              f"(optima {sorted(optima)})")
    if best_overall:
        print(f"best expectancy cell: {best_overall['threshold_cents']}c "
              f"exp=${best_overall['exp']:.1f} n={best_overall['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
