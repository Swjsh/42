"""Post-run analysis for sniper_vix_trend_grinder results.

Same structure as _analyze_vix18_results.py but pointing at the
VIX-trend (VIX>=18 AND VIX>5d_avg) stage dir.

Usage:
  python autoresearch/_analyze_vix_trend_results.py
  python autoresearch/_analyze_vix_trend_results.py --top-n 20 --ratif-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

STAGE_DIR = REPO / "autoresearch" / "_state" / "sniper_vix_trend_stage1"
PROGRESS_FILE = STAGE_DIR / "progress.json"
KEEPERS_FILE = STAGE_DIR / "keepers.jsonl"
RESULTS_FILE = STAGE_DIR / "results.jsonl"

# Reference baselines
BASELINE_VIX18 = {
    "wide_pnl": 3297.6, "wide_wr": 0.562, "positive_quarters": 4, "quarter_count": 5,
    "wide_n_trades": 73, "label": "VIX>=18 only (best combo off=1)",
}
BASELINE_VIX_TREND_SINGLE = {
    "wide_pnl": 4738.0, "wide_wr": 0.667, "positive_quarters": 5, "quarter_count": 5,
    "wide_n_trades": 39, "label": "VIX-trend single-combo diagnostic (off=1)",
}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def _deduplicate(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        key = json.dumps(r.get("combo", {}), sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _gate_check(r: dict) -> dict:
    return {
        "pnl_2k": r.get("wide_pnl", 0) > 2_000,
        "wr_45": r.get("wide_wr", 0) >= 0.45,
        "q4": r.get("positive_quarters", 0) >= 4,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--ratif-only", action="store_true")
    args = parser.parse_args()

    if not PROGRESS_FILE.exists():
        print("ERROR: progress.json not found -- grinder not started?")
        return 1

    prog = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    status = prog.get("status", "?")
    completed = prog.get("completed", 0)
    total = prog.get("total_combos", 432)

    keepers = _deduplicate(_load_jsonl(KEEPERS_FILE))
    results = _deduplicate(_load_jsonl(RESULTS_FILE))

    print("=" * 80)
    print("SNIPER VIX-TREND GRINDER RESULTS ANALYSIS")
    print("Filter: VIX>=18 AND VIX>5d_avg (escalating regime)")
    print("=" * 80)
    print(f"Status: {status}  |  {completed}/{total} combos ({100*completed/total:.0f}%)")
    print(f"Passed floors: {prog.get('passed_floors', 0)}  |  Rejected: {prog.get('rejected', 0)}")
    print(f"Ratification candidates: {prog.get('ratification_candidates', 0)}")
    print(f"Best wide_pnl: ${prog.get('best_wide_pnl', 'n/a')}")
    print()

    if not results:
        print("No passed-floor results yet.")
        return 0

    sorted_results = sorted(results, key=lambda r: r.get("wide_pnl", -9e9), reverse=True)
    ratif_cands = [r for r in sorted_results if r.get("is_ratification_candidate")]

    if args.ratif_only:
        print(f"RATIFICATION CANDIDATES ({len(ratif_cands)}):")
        show = ratif_cands
    else:
        print(f"TOP {min(args.top_n, len(sorted_results))} COMBOS BY WIDE_PNL:")
        show = sorted_results[:args.top_n]

    print()
    hdr = (
        f"{'#':<3} {'pnl':>8} {'wr':>6} {'+q':>5} {'n':>5} {'edge':>7} "
        f"{'dd':>7} {'top5%':>6}  strike stop  tp1  runner  lock"
    )
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(show[:20], 1):
        gc = _gate_check(r)
        ratif = "R" if all(gc.values()) else " "
        c = r.get("combo", {})
        print(
            f"{i:<3} ${r.get('wide_pnl', 0):>7,.0f} "
            f"{r.get('wide_wr', 0):>6.1%} "
            f"{r.get('positive_quarters', 0):>2}/{r.get('quarter_count', 0):<2} "
            f"{r.get('wide_n_trades', 0):>5} "
            f"${r.get('edge_capture', 0):>+6,.0f} "
            f"${r.get('max_drawdown', 0):>6,.0f} "
            f"{r.get('top5_pct', 0):>6.2f}  "
            f"{ratif}  "
            f"off={c.get('strike_offset', '?')} "
            f"stp={c.get('premium_stop_pct', '?')} "
            f"tp1={c.get('tp1_premium_pct', '?')} "
            f"run={c.get('runner_target_pct', '?')} "
            f"lk={c.get('profit_lock_threshold_pct', '?')}/{c.get('profit_lock_stop_offset_pct', '?')}"
        )

    print()
    print("GATE DISTRIBUTION across all passed-floor combos:")
    pnl_pass = sum(1 for r in results if r.get("wide_pnl", 0) > 2_000)
    wr_pass = sum(1 for r in results if r.get("wide_wr", 0) >= 0.45)
    q_pass = sum(1 for r in results if r.get("positive_quarters", 0) >= 4)
    all_pass = len(ratif_cands)
    n = len(results)
    print(f"  pnl>$2K:  {pnl_pass:>3}/{n}  ({100*pnl_pass/n:.0f}%)" if n else "  (no results)")
    print(f"  WR>=45%:  {wr_pass:>3}/{n}  ({100*wr_pass/n:.0f}%)" if n else "")
    print(f"  +q>=4:    {q_pass:>3}/{n}  ({100*q_pass/n:.0f}%)" if n else "")
    print(f"  ALL 3:    {all_pass:>3}/{n}  ({100*all_pass/n:.0f}%)" if n else "")

    print()
    print("COMPARISON vs BASELINES:")
    print(f"  {'label':<50} {'pnl':>8} {'wr':>6} {'+q':>5} {'n':>5}")
    print(f"  {'-'*68}")
    for bl in [BASELINE_VIX18, BASELINE_VIX_TREND_SINGLE]:
        print(
            f"  {bl['label']:<50} ${bl['wide_pnl']:>7,.0f} "
            f"{bl['wide_wr']:>6.1%} "
            f"{bl['positive_quarters']:>2}/{bl['quarter_count']:<2} "
            f"{bl['wide_n_trades']:>5}"
        )
    if sorted_results:
        best = sorted_results[0]
        print(
            f"  {'VIX-trend grinder best (this run)':<50} ${best.get('wide_pnl', 0):>7,.0f} "
            f"{best.get('wide_wr', 0):>6.1%} "
            f"{best.get('positive_quarters', 0):>2}/{best.get('quarter_count', 0):<2} "
            f"{best.get('wide_n_trades', 0):>5}"
        )

    if sorted_results:
        best = sorted_results[0]
        print()
        print("BEST COMBO DETAIL:")
        gc = _gate_check(best)
        print(f"  wide_pnl:     ${best.get('wide_pnl', 0):,.2f}  ({'PASS' if gc['pnl_2k'] else 'FAIL'} $2K)")
        print(f"  WR:           {best.get('wide_wr', 0):.1%}  ({'PASS' if gc['wr_45'] else 'FAIL'} 45%)")
        print(f"  +quarters:    {best.get('positive_quarters', 0)}/{best.get('quarter_count', 0)}  ({'PASS' if gc['q4'] else 'FAIL'} 4/6)")
        print(f"  edge_capture: ${best.get('edge_capture', 0):+,.0f}")
        print(f"  max_drawdown: ${best.get('max_drawdown', 0):,.0f}")
        print(f"  top5_pct:     {best.get('top5_pct', 0):.2f}x")
        print(f"  skipped_low:  {best.get('skipped_low', 0)} (VIX<18)")
        print(f"  skipped_trend:{best.get('skipped_trend', 0)} (VIX<5d_avg)")
        c = best.get("combo", {})
        print()
        print("  PARAMETERS:")
        print(f"    strike_offset:             {c.get('strike_offset', '?')}")
        print(f"    premium_stop_pct:          {c.get('premium_stop_pct', '?')}")
        print(f"    tp1_premium_pct:           {c.get('tp1_premium_pct', '?')}")
        print(f"    runner_target_pct:         {c.get('runner_target_pct', '?')}")
        print(f"    profit_lock_threshold_pct: {c.get('profit_lock_threshold_pct', '?')}")
        print(f"    profit_lock_stop_offset:   {c.get('profit_lock_stop_offset_pct', '?')}")
        print()
        qp = best.get("quarter_pnl", {})
        print("  QUARTER P&L:")
        for q in sorted(qp):
            v = qp[q]
            print(f"    {q}: {'+' if v >= 0 else ''}${v:,.0f}  [{'PASS' if v >= 0 else 'FAIL'}]")

        print()
        if all(gc.values()):
            print("  VERDICT: RATIFICATION_READY [ALL GATES PASS]")
        else:
            failed = [k for k, v in gc.items() if not v]
            print(f"  VERDICT: NEEDS-MORE-DATA  (failed: {failed})")

    print()
    if status == "completed":
        print(f"Grinder COMPLETE: {completed}/{total} combos.")
    else:
        print(f"In progress: {completed}/{total} ({100*completed/total:.0f}%)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
