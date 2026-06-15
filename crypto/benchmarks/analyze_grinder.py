"""analyze_grinder — summarize grinder.jsonl into per-validator statistics + knob recommendations.

For each validator, computes:
  - pass rate across iterations
  - verdict distribution (ok / no_closed_bars / stale_data / future_bar)
  - foot-gun catch rate (how often the in-progress bar was actually present at fetch time)
  - indicator value distributions (RSI min/max/mean, etc.)
  - level-event frequency
  - regime distribution
  - ribbon status distribution

Knob recommendations are derived from the data:
  - If `naive_last_bar_in_progress` fires < 20% of fetches, the 5m timing is misaligned (stop the grinder, check cadence)
  - If `disagreements_above_tolerance` > 0 ever, sources are drifting — investigate
  - If RSI extremes hit 0/100 frequently, the bar series is too short (extend warmup)
  - If level-event "hold" >> "break", consider tightening the margin threshold
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


def analyze(path: Path) -> dict:
    iterations = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                iterations.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    n = len(iterations)
    if n == 0:
        return {"error": "no iterations"}

    # v01 stats
    v01_live_verdicts = Counter()
    foot_gun_catches = 0
    foot_gun_eligible = 0
    in_progress_seconds_left = []
    for it in iterations:
        res = it.get("results", {}).get("v01_live", {})
        if "verdict" in res:
            v01_live_verdicts[res["verdict"]] += 1
            if res.get("naive_last_bar_in_progress") is True:
                foot_gun_eligible += 1
                if res.get("foot_gun_caught_this_fetch") is True:
                    foot_gun_catches += 1
            if res.get("naive_last_bar_seconds_until_close") is not None:
                in_progress_seconds_left.append(res["naive_last_bar_seconds_until_close"])

    # v02 stats
    v02_disagreements = []
    v02_shared = []
    for it in iterations:
        res = it.get("results", {}).get("v02_parity", {})
        if "disagreements_above_tolerance" in res:
            v02_disagreements.append(res["disagreements_above_tolerance"])
            v02_shared.append(res["shared_bars"])

    # v03 stats
    rsi_values = []
    ema_values = []
    vwap_values = []
    for it in iterations:
        res = it.get("results", {}).get("v03_indicators_live", {})
        if res.get("rsi_14_last") is not None:
            rsi_values.append(res["rsi_14_last"])
        if res.get("ema_20_last") is not None:
            ema_values.append(res["ema_20_last"])
        if res.get("vwap_last") is not None:
            vwap_values.append(res["vwap_last"])

    # v04 stats
    pattern_counts = defaultdict(list)
    for it in iterations:
        res = it.get("results", {}).get("v04_candlesticks_live", {})
        hits = res.get("hits_by_pattern", {})
        for p, info in hits.items():
            pattern_counts[p].append(info.get("count", 0))

    def _stats(values):
        if not values:
            return None
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
        }

    recommendations = []
    if foot_gun_eligible > 0 and foot_gun_catches / foot_gun_eligible < 0.9:
        recommendations.append(
            f"foot-gun catch rate {foot_gun_catches/foot_gun_eligible:.0%} < 90% — investigate "
            "(should be ~100% when in-progress bar present)"
        )
    if v02_disagreements and max(v02_disagreements) > 0:
        recommendations.append(
            f"v02 saw disagreements_above_tolerance > 0 in at least one iteration ({max(v02_disagreements)} max)"
        )
    if rsi_values and (min(rsi_values) <= 0.1 or max(rsi_values) >= 99.9):
        recommendations.append(
            f"RSI hit boundary [0,100] (min={min(rsi_values):.2f}, max={max(rsi_values):.2f}) — "
            "expected on strong trends; flag only if persistent"
        )
    in_prog_stats = _stats(in_progress_seconds_left)
    if in_prog_stats and in_prog_stats["mean"] < 30:
        recommendations.append(
            f"avg in-progress seconds_until_close = {in_prog_stats['mean']:.0f}s — fetches landing near "
            "bar boundary; consider adding 30s pre-bar guard"
        )

    return {
        "iterations": n,
        "v01_verdict_distribution": dict(v01_live_verdicts),
        "v01_foot_gun_catches": f"{foot_gun_catches}/{foot_gun_eligible}",
        "v01_foot_gun_catch_rate_pct": round(100 * foot_gun_catches / foot_gun_eligible, 1) if foot_gun_eligible else None,
        "v01_in_progress_seconds_until_close_stats": in_prog_stats,
        "v02_disagreement_max": max(v02_disagreements) if v02_disagreements else None,
        "v02_disagreement_iters_with_drift": sum(1 for d in v02_disagreements if d > 0),
        "v02_shared_bars_min": min(v02_shared) if v02_shared else None,
        "v02_shared_bars_max": max(v02_shared) if v02_shared else None,
        "v03_rsi_14_stats": _stats(rsi_values),
        "v03_ema_20_stats": _stats(ema_values),
        "v03_vwap_stats": _stats(vwap_values),
        "v04_pattern_count_stats": {p: _stats(counts) for p, counts in pattern_counts.items()},
        "recommendations": recommendations,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grinder", type=Path, default=Path("crypto/data/scorecards/grinder.jsonl"))
    p.add_argument("--json-out", type=Path, default=Path("crypto/data/scorecards/grinder_analysis.json"))
    args = p.parse_args(argv)

    sc = analyze(args.grinder)
    print("=" * 70)
    print("GRINDER ANALYSIS")
    print("=" * 70)
    print(f"  iterations:                        {sc['iterations']}")
    print(f"  v01 verdict distribution:          {sc['v01_verdict_distribution']}")
    print(f"  v01 foot-gun catches:              {sc['v01_foot_gun_catches']}  ({sc['v01_foot_gun_catch_rate_pct']}%)")
    if sc["v01_in_progress_seconds_until_close_stats"]:
        s = sc["v01_in_progress_seconds_until_close_stats"]
        print(f"  v01 in-progress sec_until_close:   min={s['min']:.0f}  max={s['max']:.0f}  mean={s['mean']:.0f}")
    print(f"  v02 disagreement max:              {sc['v02_disagreement_max']}")
    print(f"  v02 iters with drift:              {sc['v02_disagreement_iters_with_drift']}")
    print(f"  v02 shared bars:                   {sc['v02_shared_bars_min']}-{sc['v02_shared_bars_max']}")
    if sc["v03_rsi_14_stats"]:
        s = sc["v03_rsi_14_stats"]
        print(f"  v03 RSI(14) range:                 min={s['min']:.2f}  max={s['max']:.2f}  mean={s['mean']:.2f}")
    print(f"  v04 pattern fire counts per iter:")
    for pat, stats in sc["v04_pattern_count_stats"].items():
        if stats:
            print(f"    {pat:>20s}: mean={stats['mean']:.1f}  range=[{stats['min']:.0f}, {stats['max']:.0f}]")
    print()
    print(f"  Recommendations ({len(sc['recommendations'])}):")
    for r in sc["recommendations"]:
        print(f"    - {r}")

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(sc, indent=2, default=str))
    print(f"\n  scorecard: {args.json_out}")
    print("=" * 70)


if __name__ == "__main__":
    main()
