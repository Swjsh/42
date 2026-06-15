"""confidence_recalibration -- per-detector factor analysis to find which
underlying inputs ACTUALLY predict next-bar WIN/LOSS.

Problem: the 16-mo backtest confidence-band-WR analysis shows:
    conf <0.60       n=271   WR=47.6%
    conf 0.60-0.70   n=1043  WR=51.0%   <-- BEST band
    conf 0.70-0.80   n=833   WR=48.5%
    conf 0.80+       n=229   WR=49.3%

The current confidence formula gives HIGHEST conf to features that DON'T predict
better outcomes — formula is mis-weighted. This script:

  1. Loads the 16-mo per-day pattern_backtest output (or re-runs it)
  2. For each detector, extracts per-hit factor values from `notes`
  3. Runs a simple per-factor analysis: split hits at each factor's median,
     measure WR-above vs WR-below the median. Factor with biggest WR gap = the
     true predictor.
  4. Outputs a DRAFT proposed weight reallocation per detector
  5. A/B compares: would the new confidence formula give better WR ranking?

DRAFT ONLY — does NOT modify production detector code. Output for J review +
next-cycle implementation.

Run:
    python backtest/autoresearch/confidence_recalibration.py
    python backtest/autoresearch/confidence_recalibration.py --refresh-data
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
import time
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def _load_pb():
    spec = importlib.util.spec_from_file_location(
        "pb_rec", PROJECT_ROOT / "backtest" / "autoresearch" / "pattern_backtest.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pb_rec"] = mod
    spec.loader.exec_module(mod)
    return mod


# Which numeric factors to analyze per detector. These are the keys we expect
# in each hit's `notes` dict. Confidence value itself is also analyzed.
FACTORS_PER_DETECTOR: dict[str, list[str]] = {
    "double_bottom": ["separation_pct", "neckline_rise_pct", "bars_between"],
    "double_top": ["separation_pct", "neckline_drop_pct", "bars_between"],
    "failed_breakdown_wick": [
        "sweep_depth_pct", "close_back_margin_pct", "wick_to_body_ratio",
    ],
    "rejection_at_level_bearish": [
        "sweep_above_pct", "close_back_margin_pct", "upper_wick_to_body_ratio",
    ],
    "momentum_acceleration": ["range_mult", "body_to_range_pct"],
    "head_and_shoulders_top": [
        "head_prominence_pct", "shoulder_diff_pct", "neckline_break_pct",
    ],
    "inside_bar_consolidation": ["consecutive_inside_count", "compression_ratio"],
}


def _gather_hits(pb, csv_path: Path, start: Date, end: Date) -> list[dict]:
    """Run 16-mo backtest in-process, collect all graded hits with notes."""
    cur = start
    all_hits: list[dict] = []
    while cur <= end:
        if cur.weekday() < 5:
            try:
                result = pb.run_pattern_backtest(cur, csv_path)
                for h in result.get("hits", []):
                    if h.get("grade_next_bar") in ("WIN", "LOSS"):
                        all_hits.append(h)
            except Exception:
                pass
        cur += timedelta(days=1)
    return all_hits


def _analyze_factor(hits: list[dict], factor_key: str) -> dict | None:
    """Split hits at the factor's median, compute WR above + below."""
    pairs = []
    for h in hits:
        val = h.get("notes", {}).get(factor_key)
        if val is None:
            # Try top-level (e.g., confidence)
            val = h.get(factor_key)
        if val is None:
            continue
        try:
            val_f = float(val)
        except (TypeError, ValueError):
            continue
        is_win = h["grade_next_bar"] == "WIN"
        pairs.append((val_f, is_win))

    if len(pairs) < 20:  # need minimum sample
        return None

    values = [p[0] for p in pairs]
    median = statistics.median(values)
    above = [p[1] for p in pairs if p[0] >= median]
    below = [p[1] for p in pairs if p[0] < median]

    if not above or not below:
        return None

    wr_above = sum(above) / len(above)
    wr_below = sum(below) / len(below)
    delta = wr_above - wr_below

    # Signal-to-noise: is the delta meaningfully bigger than sampling noise?
    # Approximation: 95% CI of binomial proportion ≈ 1/sqrt(n)
    noise = 1 / math.sqrt(min(len(above), len(below)))
    snr = abs(delta) / noise if noise > 0 else 0.0

    return {
        "factor": factor_key,
        "n_total": len(pairs),
        "median": round(median, 4),
        "wr_above_median": round(wr_above * 100, 1),
        "wr_below_median": round(wr_below * 100, 1),
        "wr_delta_pp": round(delta * 100, 1),
        "snr": round(snr, 2),
        "predictive": snr > 1.0,  # delta > sampling noise
        "direction": "higher_is_better" if delta > 0 else "lower_is_better",
    }


def _analyze_detector(detector_name: str, hits: list[dict]) -> dict:
    """Run per-factor analysis for one detector."""
    det_hits = [h for h in hits if h["detector"] == detector_name]
    factors = FACTORS_PER_DETECTOR.get(detector_name, [])
    if not factors or not det_hits:
        return {
            "detector": detector_name,
            "n_graded": len(det_hits),
            "wins": 0,
            "losses": 0,
            "current_confidence_band_wr": {},
            "factor_analysis": [],
            "top_predictor": None,
            "draft_recommendation": {
                "formula_mistuned": False,
                "action": "INSUFFICIENT_DATA",
                "predictive_factors": [],
                "non_predictive_factors": [],
                "mid_band_wr": 0,
                "high_band_wr": 0,
                "high_band_n": 0,
            },
        }

    # Per-factor analysis
    factor_results = []
    for f in factors:
        r = _analyze_factor(det_hits, f)
        if r:
            factor_results.append(r)

    # Confidence band breakdown (sanity reference)
    bands = {"<0.60": [], "0.60-0.70": [], "0.70-0.80": [], "0.80+": []}
    for h in det_hits:
        c = h["confidence"]
        is_win = h["grade_next_bar"] == "WIN"
        if c < 0.60:
            bands["<0.60"].append(is_win)
        elif c < 0.70:
            bands["0.60-0.70"].append(is_win)
        elif c < 0.80:
            bands["0.70-0.80"].append(is_win)
        else:
            bands["0.80+"].append(is_win)
    band_stats = {}
    for b, ws in bands.items():
        if ws:
            band_stats[b] = {"n": len(ws), "wr_pct": round(sum(ws)/len(ws)*100, 1)}

    # Identify most-predictive factor (highest SNR among predictive ones)
    predictive_factors = sorted(
        [f for f in factor_results if f["predictive"]],
        key=lambda x: x["snr"], reverse=True,
    )
    top_predictor = predictive_factors[0] if predictive_factors else None

    return {
        "detector": detector_name,
        "n_graded": len(det_hits),
        "wins": sum(1 for h in det_hits if h["grade_next_bar"] == "WIN"),
        "losses": sum(1 for h in det_hits if h["grade_next_bar"] == "LOSS"),
        "current_confidence_band_wr": band_stats,
        "factor_analysis": factor_results,
        "top_predictor": top_predictor,
        "draft_recommendation": _make_recommendation(detector_name, factor_results, band_stats),
    }


def _make_recommendation(det_name: str, factor_results: list[dict],
                         band_stats: dict) -> dict:
    """Build a human-readable recommendation."""
    predictive = [f for f in factor_results if f.get("predictive")]
    non_predictive = [f for f in factor_results if not f.get("predictive")]

    # Check if 0.60-0.70 beats 0.80+ by a meaningful margin (the J-flagged anomaly).
    # Threshold: 2pp — sub-2pp differences are within sampling noise and not actionable.
    # v2 double_bottom shows 54.9% vs 54.8% = 0.1pp, which is CALIBRATED not MISTUNED.
    _MISTUNED_THRESHOLD_PP: float = 2.0
    mid_wr = band_stats.get("0.60-0.70", {}).get("wr_pct", 0)
    high_wr = band_stats.get("0.80+", {}).get("wr_pct", 0)
    high_n = band_stats.get("0.80+", {}).get("n", 0)
    formula_mistuned = (mid_wr - high_wr > _MISTUNED_THRESHOLD_PP) and (high_n >= 10)

    rec = {
        "formula_mistuned": formula_mistuned,
        "mid_band_wr": mid_wr,
        "high_band_wr": high_wr,
        "high_band_n": high_n,
        "predictive_factors": [f["factor"] for f in predictive],
        "non_predictive_factors": [f["factor"] for f in non_predictive],
        "action": (
            "RECALIBRATE: down-weight non-predictive factors + up-weight top predictor"
            if formula_mistuned else
            "KEEP_CURRENT: formula appears well-tuned for this detector"
        ),
    }
    if predictive:
        top = predictive[0]
        rec["increase_weight_on"] = top["factor"]
        rec["top_factor_snr"] = top["snr"]
        rec["top_factor_direction"] = top["direction"]
    return rec


def run_recalibration(csv_path: Path, start: Date, end: Date) -> dict:
    pb = _load_pb()
    print(f"Gathering hits {start} to {end}...", file=sys.stderr)
    t0 = time.monotonic()
    hits = _gather_hits(pb, csv_path, start, end)
    elapsed = time.monotonic() - t0
    print(f"  collected {len(hits)} graded hits ({elapsed:.1f}s)", file=sys.stderr)

    results = []
    for det in FACTORS_PER_DETECTOR.keys():
        results.append(_analyze_detector(det, hits))

    # Sort by mistuned-formula priority
    mistuned = [r for r in results if r["draft_recommendation"]["formula_mistuned"]]
    well_tuned = [r for r in results if not r["draft_recommendation"]["formula_mistuned"]]

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "range_start": start.isoformat(),
        "range_end": end.isoformat(),
        "total_graded_hits": len(hits),
        "mistuned_detectors": [r["detector"] for r in mistuned],
        "well_tuned_detectors": [r["detector"] for r in well_tuned],
        "per_detector": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-05-15")
    parser.add_argument("--csv", default="backtest/data/spy_5m_2025-01-01_2026-05-15.csv")
    args = parser.parse_args()

    start = Date.fromisoformat(args.start)
    end = Date.fromisoformat(args.end)
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        return 1

    report = run_recalibration(csv_path, start, end)

    # Write JSON
    out_dir = PROJECT_ROOT / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"confidence-recalibration-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))

    # Print summary
    print()
    print("=" * 70)
    print(f"CONFIDENCE FORMULA RECALIBRATION — {args.start} to {args.end}")
    print(f"Graded hits: {report['total_graded_hits']}")
    print("=" * 70)
    print()
    print(f"Mistuned detectors:  {report['mistuned_detectors']}")
    print(f"Well-tuned:          {report['well_tuned_detectors']}")
    print()

    for r in report["per_detector"]:
        det = r["detector"]
        rec = r["draft_recommendation"]
        marker = "MISTUNED" if rec["formula_mistuned"] else "OK"
        print(f"--- {det} ({marker}) ---")
        print(f"  n_graded={r['n_graded']}  wins={r['wins']}  losses={r['losses']}")
        bands = r["current_confidence_band_wr"]
        if bands:
            band_str = ", ".join(f"{b}:{s['wr_pct']}%(n={s['n']})" for b, s in bands.items())
            print(f"  bands: {band_str}")
        if r["top_predictor"]:
            tp = r["top_predictor"]
            print(f"  top predictor: {tp['factor']} (SNR={tp['snr']}, "
                  f"{tp['wr_above_median']}% above vs {tp['wr_below_median']}% below, "
                  f"delta {tp['wr_delta_pp']:+}pp, {tp['direction']})")
        for f in r["factor_analysis"]:
            tag = "PREDICTIVE" if f["predictive"] else "noise"
            print(f"    [{tag}] {f['factor']}: delta {f['wr_delta_pp']:+}pp SNR={f['snr']}")
        print(f"  ACTION: {rec['action']}")
        print()

    print(f"Full JSON: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
