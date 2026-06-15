"""Post-run analysis for sniper_vix18_grinder results.

Reads the keepers.jsonl + results.jsonl from the VIX18 grinder and produces:
  1. Top-10 combos by wide_pnl
  2. All ratification candidates (pnl>$2K, WR>=45%, +quarters>=4)
  3. Gate distribution across all combos
  4. Comparison table vs unfiltered baseline ($-91, VIX>=18 applied post-hoc $1,472)
  5. Quarter analysis for best combo
  6. Recommendation: RATIFICATION_READY or NEEDS-MORE-DATA

Usage:
  python autoresearch/_analyze_vix18_results.py
  python autoresearch/_analyze_vix18_results.py --top-n 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

STAGE1_DIR = REPO / "autoresearch" / "_state" / "sniper_vix18_stage1"
PROGRESS_FILE = STAGE1_DIR / "progress.json"
KEEPERS_FILE = STAGE1_DIR / "keepers.jsonl"
RESULTS_FILE = STAGE1_DIR / "results.jsonl"
REJECTIONS_FILE = STAGE1_DIR / "rejections.jsonl"

# Reference points for comparison table
BASELINE_UNFILTERED = {"wide_pnl": -90.8, "wide_wr": 0.500, "positive_quarters": 2, "quarter_count": 6, "wide_n_trades": 150, "label": "Unfiltered best (no VIX gate)"}
BASELINE_VIX18_POSTHOC = {"wide_pnl": 1472.0, "wide_wr": 0.543, "positive_quarters": 3, "quarter_count": 5, "wide_n_trades": 70, "label": "VIX>=18 applied post-hoc to best combo"}


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
    """Deduplicate by combo dict (handles double-logging in early runs)."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        key = json.dumps(r.get("combo", {}), sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _gate_check(r: dict) -> dict:
    """Return per-gate pass/fail for a result row."""
    return {
        "pnl_2k": r.get("wide_pnl", 0) > 2_000,
        "wr_45": r.get("wide_wr", 0) >= 0.45,
        "q4": r.get("positive_quarters", 0) >= 4,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=10, help="Show top N combos by pnl (default 10)")
    parser.add_argument("--ratif-only", action="store_true", help="Only show ratification candidates")
    args = parser.parse_args()

    # ── Load data ──
    if not PROGRESS_FILE.exists():
        print("ERROR: progress.json not found — grinder not started yet?")
        return 1

    prog = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    status = prog.get("status", "?")
    completed = prog.get("completed", 0)
    total = prog.get("total_combos", 432)
    vix_threshold = prog.get("vix_threshold", 18)

    keepers = _deduplicate(_load_jsonl(KEEPERS_FILE))
    results = _deduplicate(_load_jsonl(RESULTS_FILE))

    print("=" * 80)
    print(f"SNIPER VIX>={vix_threshold} GRINDER RESULTS ANALYSIS")
    print("=" * 80)
    print(f"Status: {status}  |  {completed}/{total} combos ({100*completed/total:.0f}%)")
    print(f"Passed floors: {prog.get('passed_floors', 0)}  |  Rejected: {prog.get('rejected', 0)}")
    print(f"Ratification candidates: {prog.get('ratification_candidates', 0)}")
    print(f"Best wide_pnl: ${prog.get('best_wide_pnl', 'n/a')}")
    print()

    if not results:
        print("No passed-floor results yet.")
        return 0

    # ── Sort all passed combos by wide_pnl ──
    sorted_results = sorted(results, key=lambda r: r.get("wide_pnl", -9e9), reverse=True)

    # ── Top-N table ──
    show = sorted_results if args.ratif_only else sorted_results[:args.top_n]
    ratif_cands = [r for r in sorted_results if r.get("is_ratification_candidate")]

    if args.ratif_only:
        print(f"RATIFICATION CANDIDATES ({len(ratif_cands)}):")
        show = ratif_cands
    else:
        print(f"TOP {min(args.top_n, len(sorted_results))} COMBOS BY WIDE_PNL:")

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
    total_pass = len(results)
    print(f"  pnl>$2K:  {pnl_pass:>3}/{total_pass}  ({100*pnl_pass/total_pass:.0f}%)")
    print(f"  WR>=45%:  {wr_pass:>3}/{total_pass}  ({100*wr_pass/total_pass:.0f}%)")
    print(f"  +q>=4:    {q_pass:>3}/{total_pass}  ({100*q_pass/total_pass:.0f}%)")
    print(f"  ALL 3:    {all_pass:>3}/{total_pass}  ({100*all_pass/total_pass:.0f}%)")

    print()
    print("COMPARISON vs BASELINES:")
    print(f"  {'label':<45} {'pnl':>8} {'wr':>6} {'+q':>5} {'n':>5}")
    print(f"  {'-'*65}")
    for bl in [BASELINE_UNFILTERED, BASELINE_VIX18_POSTHOC]:
        print(
            f"  {bl['label']:<45} ${bl['wide_pnl']:>7,.0f} "
            f"{bl['wide_wr']:>6.1%} "
            f"{bl['positive_quarters']:>2}/{bl['quarter_count']:<2} "
            f"{bl['wide_n_trades']:>5}"
        )
    if sorted_results:
        best = sorted_results[0]
        bl = best
        print(
            f"  {'VIX18 grinder best (this run)':<45} ${bl.get('wide_pnl', 0):>7,.0f} "
            f"{bl.get('wide_wr', 0):>6.1%} "
            f"{bl.get('positive_quarters', 0):>2}/{bl.get('quarter_count', 0):<2} "
            f"{bl.get('wide_n_trades', 0):>5}"
        )

    # ── Best combo detail ──
    if sorted_results:
        best = sorted_results[0]
        print()
        print("BEST COMBO DETAIL:")
        gc = _gate_check(best)
        print(f"  wide_pnl:    ${best.get('wide_pnl', 0):,.2f}  ({'PASS' if gc['pnl_2k'] else 'FAIL'} $2K gate)")
        print(f"  WR:          {best.get('wide_wr', 0):.1%}  ({'PASS' if gc['wr_45'] else 'FAIL'} 45% gate)")
        print(f"  +quarters:   {best.get('positive_quarters', 0)}/{best.get('quarter_count', 0)}  ({'PASS' if gc['q4'] else 'FAIL'} 4/6 gate)")
        print(f"  edge_capture: ${best.get('edge_capture', 0):+,.0f}")
        print(f"  max_drawdown: ${best.get('max_drawdown', 0):,.0f}")
        print(f"  top5_pct:     {best.get('top5_pct', 0):.2f}x  (top 5 days = {best.get('top5_pct', 0):.0%} of total P&L)")
        print(f"  OPRA missing: {best.get('opra_missing_days', 0)} days")
        print(f"  skipped_days: {best.get('skipped_days', 0)} (VIX<{vix_threshold})")
        print()
        c = best.get("combo", {})
        print(f"  PARAMETERS:")
        print(f"    strike_offset:             {c.get('strike_offset', '?')}  (ITM-{c.get('strike_offset', '?')})")
        print(f"    premium_stop_pct:          {c.get('premium_stop_pct', '?')}")
        print(f"    tp1_premium_pct:           {c.get('tp1_premium_pct', '?')}  ({c.get('tp1_premium_pct', 0)*100:.0f}% gain -> exit 50%)")
        print(f"    runner_target_pct:         {c.get('runner_target_pct', '?')}  ({c.get('runner_target_pct', 0):.1f}x entry premium)")
        print(f"    profit_lock_threshold_pct: {c.get('profit_lock_threshold_pct', '?')}")
        print(f"    profit_lock_stop_offset:   {c.get('profit_lock_stop_offset_pct', '?')}")
        print()
        qp = best.get("quarter_pnl", {})
        print(f"  QUARTER P&L:")
        for q in sorted(qp):
            sign = "+" if qp[q] >= 0 else ""
            pos = "PASS" if qp[q] >= 0 else "FAIL"
            print(f"    {q}: {sign}${qp[q]:,.0f}  [{pos}]")

        print()
        # Ratification verdict
        all_gates = all(gc.values())
        if all_gates:
            print("  VERDICT: RATIFICATION_READY [ALL GATES PASS]")
            print("  -> Queue for J weekend ratification (Rule 9)")
        else:
            failed = [k for k, v in gc.items() if not v]
            print(f"  VERDICT: NEEDS-MORE-DATA  (failed gates: {failed})")

    print()
    if status == "completed":
        print(f"Run complete: {completed}/{total} combos in total")
    else:
        print(f"Run still in progress: {completed}/{total} ({100*completed/total:.0f}%)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
