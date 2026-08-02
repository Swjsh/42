"""ZERO-FOR-TWELVE-POSTMORTEM -- HISTORICAL OOS(2026) day-cluster pass (the
"STILL NOT DONE" step named by the 2026-07-25 21:12-21:50 ET progress note in
automation/overnight/queue.md).

Question: for vwap_continuation and vix_regime_dayside -- the two setups
disarmed 2026-07-25 after 0-for-12 live -- how many GENUINELY INDEPENDENT
day+side trials underlie each setup's OOS(2026) validation population, and
how much do the two setups' OOS signal populations OVERLAP (the L174
"vix_regime_dayside is a 100% same-side subset of vwap_continuation days"
caveat already written into
analysis/recommendations/vix_regime_dayside.json#L174, quoted verbatim below)?

This is DETECTION ONLY (no full real-fills sim re-run) -- pure signal
generation via the byte-identical detectors already used by each setup's
own autoresearch script, reused verbatim (C14: no re-derivation):
  * vwap_continuation:   backtest.autoresearch._edgehunt_vwap_continuation.detect_signals
  * vix_regime_dayside:  backtest.autoresearch._b5_vix_regime_dayside.detect_opt_signals
    (called at the LIVE-ARMED cell's own knobs: low_margin=0.25, slope_rule=
    'not_rising' -- automation/state/params.json#_j_vix_dayside_doc)

Pure Python, $0, no LLM. Zero trading-path touched (analysis/tooling only).
Writes analysis/recommendations/zero-for-twelve-oos-day-cluster-2026-08-02.json.

Run: backtest/.venv/Scripts/python.exe backtest/tools/zero_for_twelve_oos_day_cluster_2026_08_02.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy as _norm_a,
    _align_vix as _align_a,
    detect_signals as detect_vwap_continuation,
)
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    _normalize_spy as _norm_b,
    _align_vix as _align_b,
    causal_vix_median,
    vix_slope,
    detect_opt_signals as detect_vix_regime_dayside,
    VIX_MEDIAN_BARS,
    VIX_SLOPE_BARS,
)

OUT = ROOT / "analysis" / "recommendations" / "zero-for-twelve-oos-day-cluster-2026-08-02.json"

# Live-armed cell knobs (automation/state/params.json _j_vix_dayside_doc):
# strike_offset 0 (ATM), premium_stop -0.08, tp1 0.30, low_margin 0.25, slope_rule not_rising.
LOW_MARGIN = 0.25
SLOPE_RULE = "not_rising"

OOS_YEAR = 2026

# The L174 caveat already on record (verbatim, analysis/recommendations/vix_regime_dayside.json:83):
L174_CAVEAT = (
    "L174 NOT INDEPENDENT of #1: 100% same-side subset of vwap_continuation "
    "(VIX-gated re-cut). Net incremental value over already-live #1 is UNPROVEN "
    "here ('#4 VIX-favorable sub-pool vs the rest of #1' comparison not run). "
    "Treat as a VIX-overlay refinement of #1, not a parallel independent allocation."
)


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def main() -> int:
    start, end = dt.date(2025, 1, 1), dt.date(2026, 7, 22)
    print(f"[zft-daycluster] loading SPY+VIX {start}..{end} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(start, end)

    # ---- vwap_continuation population (its own normalize/align, byte-identical) ----
    spy_a = _norm_a(spy_raw)
    vix_a = _align_a(spy_a, vix_raw)
    days_a = build_day_contexts(spy_a)
    sigs_a = detect_vwap_continuation(days_a, vix_a)
    pop_a = [(str(s.side), str(spy_a.iloc[s.bar_idx]["date"])) for s in sigs_a]

    # ---- vix_regime_dayside population (its own normalize/align, byte-identical) ----
    spy_b = _norm_b(spy_raw)
    vix_g = _align_b(spy_b, vix_raw)
    vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
    days_b = build_day_contexts(spy_b)
    sigs_b = detect_vix_regime_dayside(days_b, spy_b, vix_g, vix_med_g, vix_slp_g,
                                        low_margin=LOW_MARGIN, slope_rule=SLOPE_RULE)
    pop_b = [(str(s.side), str(s.date)) for s in sigs_b]

    def split(pop):
        is_ = [(sd, d) for sd, d in pop if int(d[:4]) != OOS_YEAR]
        oos = [(sd, d) for sd, d in pop if int(d[:4]) == OOS_YEAR]
        return is_, oos

    is_a, oos_a = split(pop_a)
    is_b, oos_b = split(pop_b)

    def cluster(oos_rows, label):
        by_day = defaultdict(list)
        for sd, d in oos_rows:
            by_day[d].append(sd)
        distinct_days = len(by_day)
        distinct_day_side = len({(sd, d) for sd, d in oos_rows})
        multi_side_days = {d: sides for d, sides in by_day.items() if len(set(sides)) > 1}
        by_q = defaultdict(int)
        for sd, d in oos_rows:
            by_q[_quarter(dt.date.fromisoformat(d))] += 1
        print(f"[zft-daycluster] {label}: n_oos_signals={len(oos_rows)} "
              f"distinct_days={distinct_days} distinct_day_side={distinct_day_side} "
              f"multi_side_days={len(multi_side_days)}", flush=True)
        return {
            "n_oos_signals": len(oos_rows),
            "distinct_days": distinct_days,
            "distinct_day_side_buckets": distinct_day_side,
            "multi_side_days": multi_side_days,
            "by_quarter": dict(by_q),
        }

    cluster_a = cluster(oos_a, "vwap_continuation")
    cluster_b = cluster(oos_b, "vix_regime_dayside")

    # ---- subset / overlap check: is vix_regime_dayside's OOS pop really a
    # subset of vwap_continuation's OOS pop, at (date,side) resolution? ----
    set_a = {(sd, d) for sd, d in oos_a}
    set_b = {(sd, d) for sd, d in oos_b}
    overlap = set_a & set_b
    b_not_in_a = set_b - set_a
    subset_fraction = round(len(overlap) / len(set_b), 4) if set_b else None

    # effective independent trials if the two setups are pooled (dedupe by date+side,
    # since a shared (date,side) is ONE trend classification, not two independent bets)
    pooled = set_a | set_b
    pooled_days = {d for _, d in pooled}

    result = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "purpose": ("Quantify the 'day+side selection / L174 NOT INDEPENDENT' caveat "
                    "at the OOS(2026) VALIDATION level (the historical half of the "
                    "2026-07-25 postmortem thread; the LIVE-sample half was already "
                    "closed same day via trade_to_learn_digest.py n_distinct_days)."),
        "data_window": {"start": str(start), "end": str(end),
                         "note": "master file coverage as of this run; does not include "
                                 "2026-07-23..07-31 (separate rolling window file, not "
                                 "merged into the 2025-01-01-start master yet) -- OOS "
                                 "population below is therefore a subset of the full "
                                 "2026 OOS window used at arm-time (n=42/n=21 in "
                                 "params.json), not a mismatch, just an earlier cutoff."},
        "live_armed_cell": {"vix_regime_dayside": {"low_margin": LOW_MARGIN,
                                                     "slope_rule": SLOPE_RULE,
                                                     "strike_offset": "ATM(0)"},
                             "vwap_continuation": {"strike_offset": "ATM(0)"}},
        "l174_caveat_on_record": L174_CAVEAT,
        "vwap_continuation": {**cluster_a, "n_is_signals": len(is_a)},
        "vix_regime_dayside": {**cluster_b, "n_is_signals": len(is_b)},
        "overlap_2026_oos": {
            "vwap_continuation_oos_day_side_n": len(set_a),
            "vix_regime_dayside_oos_day_side_n": len(set_b),
            "shared_day_side_n": len(overlap),
            "vix_regime_dayside_subset_fraction_of_itself_found_in_vwap_continuation":
                subset_fraction,
            "vix_regime_dayside_day_side_NOT_in_vwap_continuation": sorted(b_not_in_a),
            "pooled_distinct_day_side_n": len(pooled),
            "pooled_distinct_days_n": len(pooled_days),
        },
        "verdict": None,  # filled below
    }

    naive_sum = len(set_a) + len(set_b)
    if subset_fraction is not None and subset_fraction >= 0.90:
        verdict = (
            f"CONFIRMED at the OOS-validation level (subset_fraction={subset_fraction}, "
            f"{len(overlap)}/{len(set_b)} of vix_regime_dayside's OOS day+side signals also "
            f"fired as vwap_continuation OOS signals): vix_regime_dayside's OOS(2026, through "
            f"{end}) signal population is ALMOST ENTIRELY a same-day/same-side sub-selection "
            f"of vwap_continuation's own OOS population, matching the L174 caveat that was "
            f"already on record at arm-time (analysis/recommendations/vix_regime_dayside.json) "
            f"but never quantified until this run. Within THIS window (through {end}, "
            f"earlier cutoff than the {{n=42,n=21}} arm-time figures in params.json, which "
            f"used data through ~2026-05-15/07): naive sum of the two setups' own OOS signal "
            f"counts is {naive_sum} ({len(set_a)}+{len(set_b)}), but pooling by (date,side) "
            f"collapses that to only {len(pooled)} distinct trials on {len(pooled_days)} "
            f"distinct days -- a {round(100*(1-len(pooled)/naive_sum),1)}% reduction once the "
            f"overlap is removed. A live 0-for-12 spanning BOTH setups is therefore closer to "
            f"a 0-for-N run on N << 12 independent day-outcomes (matching the LIVE-sample "
            f"finding already closed 2026-07-25 21:12-21:50 ET: the 12 live CSV rows were only "
            f"4 distinct day+side buckets, with 2026-07-21 firing BOTH setups on the same PUT "
            f"call). This REFRAMES (does not reverse) the disarm decision: the correct read of "
            f"the evidence that triggered the disarm was never 'p<1% across 12 independent "
            f"trials' -- it was a much smaller, correlated sample all along, at BOTH the "
            f"live-sample and the OOS-validation layer. Recommendation: any re-arm decision for "
            f"either setup should score n by DISTINCT DAYS TOUCHED (or pooled distinct "
            f"day+side buckets across BOTH setups), not raw trade-row counts, and should NOT "
            f"treat vix_regime_dayside as adding independent coverage beyond vwap_continuation "
            f"-- it is a VIX-favorable subset of the same edge, per the setup's own doc."
        )
    else:
        verdict = (
            f"NOT confirmed as a near-total subset in this window (subset_fraction="
            f"{subset_fraction}) -- the two OOS populations diverge more than the L174 "
            f"caveat implies at arm-time framing; the RE-CUT (low_margin={LOW_MARGIN}, "
            f"slope_rule={SLOPE_RULE}) used for THIS run may differ from whichever sweep "
            f"cell the original L174 caveat was written against. Needs the original cell's "
            f"exact knobs cross-checked before drawing a conclusion either way."
        )
    result["verdict"] = verdict
    print("\n" + verdict + "\n", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[zft-daycluster] wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
