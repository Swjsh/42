"""ab_test_historical — replay captured grinder snapshots through different knob values.

Reads `crypto/data/scorecards/grinder.jsonl`, filters iterations that have
`raw_bars_coinbase` + `raw_bars_yfinance` captured, reconstructs BarSeries
from each snapshot, and runs the v02 source-parity comparison TWO ways:
  - baseline knob value (current production)
  - candidate knob value (proposed tuning)

Aggregates per-iteration outcomes and emits an A/B verdict (PROMOTE_CANDIDATE
or KEEP_BASELINE) based on OP-19 / OP-20: candidate must beat baseline on >= 2
metrics with NO regression.

Supported knobs:
  --knob v02_tolerance  --baseline 0.05  --candidate 0.10
  --knob v02_skip       --baseline 1     --candidate 2

This is the OUTER-loop autoresearch fed by INNER-loop grinder data.
Replays 85+ snapshots in seconds instead of waiting hours for live boundary events.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar, BarSeries


def _load_snapshots(path: Path) -> list[dict]:
    """Return iterations that have both raw_bars_coinbase and raw_bars_yfinance."""
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if "raw_bars_coinbase" in d and "raw_bars_yfinance" in d:
                out.append(d)
    return out


def _reconstruct_series(rows: list[dict], source: str, symbol: str, granularity_seconds: int) -> BarSeries:
    bars = []
    for r in rows:
        ts = r["open_time"]
        if isinstance(ts, str):
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            ts_dt = ts
        bars.append(Bar(
            open_time=ts_dt, open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]),
            granularity_seconds=granularity_seconds, source=source,
        ))
    bars.sort(key=lambda b: b.open_time)
    return BarSeries(symbol=symbol, granularity_seconds=granularity_seconds, source=source, bars=tuple(bars))


def _v02_replay(cb: BarSeries, yf: BarSeries, tolerance_pct: float, skip_most_recent: int) -> dict:
    """Local re-implementation of v02_source_parity logic to make tolerance + skip tunable."""
    cb_bars = sorted(cb.bars, key=lambda b: b.open_time)
    yf_bars = sorted(yf.bars, key=lambda b: b.open_time)
    if skip_most_recent > 0:
        cb_bars = cb_bars[:-skip_most_recent] if len(cb_bars) > skip_most_recent else []
        yf_bars = yf_bars[:-skip_most_recent] if len(yf_bars) > skip_most_recent else []
    cb_map = {b.open_time: b for b in cb_bars}
    yf_map = {b.open_time: b for b in yf_bars}
    shared = sorted(set(cb_map) & set(yf_map))
    disagreements = 0
    worst_pct = 0.0
    for t in shared:
        cb_bar, yf_bar = cb_map[t], yf_map[t]
        deltas = [
            abs(cb_bar.open - yf_bar.open),
            abs(cb_bar.high - yf_bar.high),
            abs(cb_bar.low - yf_bar.low),
            abs(cb_bar.close - yf_bar.close),
        ]
        worst = max(deltas) / cb_bar.close * 100 if cb_bar.close else 0
        worst_pct = max(worst_pct, worst)
        if worst > tolerance_pct:
            disagreements += 1
    return {
        "shared": len(shared),
        "disagreements": disagreements,
        "worst_pct": worst_pct,
        "pass": len(shared) >= 3 and disagreements == 0,
    }


def replay_knob(snapshots: list[dict], knob: str, baseline, candidate) -> dict:
    a_results = []  # baseline
    b_results = []  # candidate

    for snap in snapshots:
        cb = _reconstruct_series(snap["raw_bars_coinbase"], "coinbase", "BTC-USD", 300)
        yf = _reconstruct_series(snap["raw_bars_yfinance"], "yfinance", "BTC-USD", 300)

        if knob == "v02_tolerance":
            a = _v02_replay(cb, yf, tolerance_pct=baseline, skip_most_recent=1)
            b = _v02_replay(cb, yf, tolerance_pct=candidate, skip_most_recent=1)
        elif knob == "v02_skip":
            a = _v02_replay(cb, yf, tolerance_pct=0.05, skip_most_recent=baseline)
            b = _v02_replay(cb, yf, tolerance_pct=0.05, skip_most_recent=candidate)
        else:
            raise ValueError(f"unknown knob: {knob}")

        a_results.append(a)
        b_results.append(b)

    def _summarize(rs):
        if not rs:
            return None
        passes = sum(1 for r in rs if r["pass"])
        drifts = sum(1 for r in rs if r["disagreements"] > 0)
        avg_shared = statistics.mean(r["shared"] for r in rs)
        avg_worst = statistics.mean(r["worst_pct"] for r in rs)
        max_worst = max(r["worst_pct"] for r in rs)
        return {
            "iters": len(rs),
            "passes": passes,
            "pass_rate_pct": round(100 * passes / len(rs), 2),
            "iters_with_drift": drifts,
            "drift_rate_pct": round(100 * drifts / len(rs), 2),
            "avg_shared_bars": round(avg_shared, 2),
            "avg_worst_pct": round(avg_worst, 4),
            "max_worst_pct": round(max_worst, 4),
        }

    a = _summarize(a_results)
    b = _summarize(b_results)

    metrics_won_by_b = []
    if b["pass_rate_pct"] > a["pass_rate_pct"]:
        metrics_won_by_b.append(f"pass_rate +{b['pass_rate_pct']-a['pass_rate_pct']:.2f}pp")
    if b["drift_rate_pct"] < a["drift_rate_pct"]:
        metrics_won_by_b.append(f"drift_rate -{a['drift_rate_pct']-b['drift_rate_pct']:.2f}pp")
    if b["max_worst_pct"] < a["max_worst_pct"]:
        metrics_won_by_b.append(f"max_worst -{a['max_worst_pct']-b['max_worst_pct']:.4f}pp")

    regressions = []
    # Skip increase that reduces shared bars by > 20% is a regression
    if b["avg_shared_bars"] < a["avg_shared_bars"] * 0.80:
        regressions.append(f"avg_shared_bars dropped from {a['avg_shared_bars']} to {b['avg_shared_bars']}")
    if b["pass_rate_pct"] < a["pass_rate_pct"]:
        regressions.append(f"pass_rate regressed {a['pass_rate_pct']} -> {b['pass_rate_pct']}")

    if regressions:
        verdict = "KEEP_BASELINE (regressions detected)"
    elif len(metrics_won_by_b) >= 2:
        verdict = "PROMOTE_CANDIDATE"
    elif len(metrics_won_by_b) == 1:
        verdict = "MIXED (1 metric improved, no regression)"
    else:
        verdict = "KEEP_BASELINE (no improvement)"

    return {
        "knob": knob,
        "baseline_value": baseline,
        "candidate_value": candidate,
        "snapshots_replayed": len(snapshots),
        "baseline": a,
        "candidate": b,
        "metrics_won_by_candidate": metrics_won_by_b,
        "regressions": regressions,
        "verdict": verdict,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--knob", choices=["v02_tolerance", "v02_skip"], required=True)
    p.add_argument("--baseline", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--grinder", type=Path, default=Path("crypto/data/scorecards/grinder.jsonl"))
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    snapshots = _load_snapshots(args.grinder)
    if not snapshots:
        print(f"ERROR: no snapshots with raw bars found in {args.grinder}")
        sys.exit(1)

    baseline = float(args.baseline) if args.knob == "v02_tolerance" else int(args.baseline)
    candidate = float(args.candidate) if args.knob == "v02_tolerance" else int(args.candidate)
    r = replay_knob(snapshots, args.knob, baseline, candidate)

    print("=" * 70)
    print(f"HISTORICAL A/B TEST -- knob={r['knob']}  snapshots={r['snapshots_replayed']}")
    print("=" * 70)
    print(f"  BASELINE (value={r['baseline_value']}):")
    print(f"    pass_rate:     {r['baseline']['pass_rate_pct']}%  ({r['baseline']['passes']}/{r['baseline']['iters']})")
    print(f"    drift_rate:    {r['baseline']['drift_rate_pct']}%  ({r['baseline']['iters_with_drift']} iters)")
    print(f"    avg_shared:    {r['baseline']['avg_shared_bars']} bars")
    print(f"    worst_pct:     avg {r['baseline']['avg_worst_pct']}%  max {r['baseline']['max_worst_pct']}%")
    print()
    print(f"  CANDIDATE (value={r['candidate_value']}):")
    print(f"    pass_rate:     {r['candidate']['pass_rate_pct']}%  ({r['candidate']['passes']}/{r['candidate']['iters']})")
    print(f"    drift_rate:    {r['candidate']['drift_rate_pct']}%  ({r['candidate']['iters_with_drift']} iters)")
    print(f"    avg_shared:    {r['candidate']['avg_shared_bars']} bars")
    print(f"    worst_pct:     avg {r['candidate']['avg_worst_pct']}%  max {r['candidate']['max_worst_pct']}%")
    print()
    print(f"  METRICS WON BY CANDIDATE:  {r['metrics_won_by_candidate'] or 'none'}")
    print(f"  REGRESSIONS:               {r['regressions'] or 'none'}")
    print(f"  VERDICT:                   {r['verdict']}")

    out_path = args.json_out or Path(f"crypto/data/scorecards/ab_historical_{args.knob}_{args.baseline}_vs_{args.candidate}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(r, indent=2, default=str))
    print(f"\n  scorecard: {out_path}")


if __name__ == "__main__":
    main()
