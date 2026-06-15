"""Summarize overnight grinder results.

Usage:
    python -m autoresearch.overnight_summary [--top N]

Reads:
    autoresearch/_state/overnight_grinder/progress.json
    autoresearch/_state/overnight_grinder/results.jsonl
    autoresearch/_state/overnight_grinder/keepers.jsonl

Prints a concise scorecard:
    - Run status (running / completed / killed)
    - Coverage (N of N combos done, ETA)
    - Top-K candidates by edge_capture
    - Top-K candidates by wide_pnl
    - Best-of-both winner
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "autoresearch" / "_state" / "overnight_grinder"


def _load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=10, help="Top-K rows to show")
    args = parser.parse_args()

    progress = json.loads((OUT / "progress.json").read_text("utf-8")) if (OUT / "progress.json").exists() else {}
    results = _load_jsonl(OUT / "results.jsonl")
    keepers = _load_jsonl(OUT / "keepers.jsonl")
    rejections = _load_jsonl(OUT / "rejections.jsonl")

    print("=" * 100)
    print("OVERNIGHT GRINDER — SUMMARY")
    print("=" * 100)

    # Status
    started = progress.get("started_at", "?")
    deadline = progress.get("deadline_at", "?")
    status = progress.get("status", "?")
    completed = progress.get("completed", 0)
    total = progress.get("total_combos", 0)
    pct = (completed / total * 100) if total else 0
    eta = "?"
    try:
        s = dt.datetime.fromisoformat(started)
        elapsed = (dt.datetime.now() - s).total_seconds()
        if completed > 0:
            est_per = elapsed / completed
            remain = max(0, total - completed)
            eta_secs = remain * est_per
            eta = f"{eta_secs/3600:.1f}h"
    except Exception:
        pass

    print(f"\nstarted:   {started}")
    print(f"deadline:  {deadline}")
    print(f"status:    {status}")
    print(f"progress:  {completed}/{total} ({pct:.1f}%) — ETA {eta}")
    print(f"passed:    {progress.get('passed_floors', 0)}")
    print(f"rejected:  {progress.get('rejected', 0)}")
    print(f"keepers:   {progress.get('keepers', 0)}")
    print(f"best_edge: ${progress.get('best_edge_capture', 0):.0f}")
    print(f"best_wide: ${progress.get('best_wide_pnl', 0) or 0:.0f}")

    # Top by edge_capture
    by_edge = sorted(
        [r for r in results if "edge_capture" in r],
        key=lambda r: -r["edge_capture"],
    )[: args.top]
    print(f"\n--- TOP {args.top} BY edge_capture (J-edge primary) ---")
    print(f"{'edge':>7} {'4/29':>6} {'5/04':>7} {'wide':>7} {'wide_n':>7}  combo")
    for r in by_edge:
        c = r["combo"]
        c_str = f"super_stop={c['super_stop']} super_tp1={c['super_tp1']} runner={c['runner_target']} lvl_qty={c['level_qty']} lvl_stop={c['level_stop']} lvl_tp1={c['level_tp1']} trend_stop={c['trendline_stop']}"
        print(f"${r['edge_capture']:>6.0f} ${r['pnl_4_29']:>5.0f} ${r['pnl_5_04']:>6.0f} ${r['wide_pnl']:>6.0f} {r['wide_n_trades']:>6}  {c_str}")

    # Top by wide_pnl
    by_wide = sorted(
        [r for r in results if "wide_pnl" in r],
        key=lambda r: -r["wide_pnl"],
    )[: args.top]
    print(f"\n--- TOP {args.top} BY wide_pnl (16-month aggregate) ---")
    print(f"{'wide':>7} {'wide_n':>7} {'wide_wr':>8} {'edge':>7} {'4/29':>6} {'5/04':>7}  combo")
    for r in by_wide:
        c = r["combo"]
        c_str = f"super_stop={c['super_stop']} super_tp1={c['super_tp1']} runner={c['runner_target']} lvl_qty={c['level_qty']} lvl_stop={c['level_stop']} lvl_tp1={c['level_tp1']} trend_stop={c['trendline_stop']}"
        print(f"${r['wide_pnl']:>6.0f} {r['wide_n_trades']:>6} {r['wide_wr']*100:>6.1f}% ${r['edge_capture']:>5.0f} ${r['pnl_4_29']:>5.0f} ${r['pnl_5_04']:>6.0f}  {c_str}")

    # Combined score: rank by sum of (edge_capture rank + wide_pnl rank)
    if results:
        edge_rank = {id(r): i for i, r in enumerate(sorted(results, key=lambda r: -r.get("edge_capture", 0)))}
        wide_rank = {id(r): i for i, r in enumerate(sorted(results, key=lambda r: -r.get("wide_pnl", 0)))}
        combined = sorted(results, key=lambda r: edge_rank[id(r)] + wide_rank[id(r)])[: args.top]
        print(f"\n--- TOP {args.top} BY COMBINED RANK (edge_capture + wide_pnl) ---")
        print(f"{'edge':>7} {'wide':>7} {'4/29':>6} {'5/04':>7}  combo")
        for r in combined:
            c = r["combo"]
            c_str = f"super_stop={c['super_stop']} super_tp1={c['super_tp1']} runner={c['runner_target']} lvl_qty={c['level_qty']} lvl_stop={c['level_stop']} lvl_tp1={c['level_tp1']} trend_stop={c['trendline_stop']}"
            print(f"${r['edge_capture']:>6.0f} ${r['wide_pnl']:>6.0f} ${r['pnl_4_29']:>5.0f} ${r['pnl_5_04']:>6.0f}  {c_str}")

    # Rejection breakdown
    if rejections:
        print(f"\n--- REJECTIONS ({len(rejections)}) — sample reasons ---")
        from collections import Counter
        all_reasons = []
        for r in rejections:
            for reason in r.get("regressions", []):
                # Strip numeric details for grouping
                if "4/29" in reason:
                    all_reasons.append("4/29 regressed")
                elif "5/04" in reason:
                    all_reasons.append("5/04 regressed")
                elif "losers_added" in reason:
                    all_reasons.append("added losers")
                else:
                    all_reasons.append(reason[:50])
        counter = Counter(all_reasons)
        for reason, n in counter.most_common():
            print(f"  {n:>4}× {reason}")

    print("\n" + "=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
