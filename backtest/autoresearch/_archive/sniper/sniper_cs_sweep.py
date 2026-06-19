"""Sweep chart-stop SNIPER combos to find first positive P&L configuration.

Tests chart_stop_buffer × tp1_r × runner_r × strike_offset.
Writes results to analysis/recommendations/sniper-cs-sweep.json.

Per CLAUDE.md L100: all premium-exit SNIPER combos are ARTIFACT-INVALIDATED.
This sweep validates whether SPY-price chart stops fix the L51/L55 problem.
NEVER import or call any Alpaca tool or order function.
"""

from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch.sniper_cs_evaluator import evaluate_sniper_cs_combo  # noqa: E402

OUTPUT = REPO.parent / "analysis" / "recommendations" / "sniper-cs-sweep.json"


def build_combos() -> list[dict]:
    combos = []
    for buf, tp1_r, run_r, offset in product(
        [0.30, 0.50, 0.75, 1.00],   # chart_stop_buffer
        [1.5, 2.0, 2.5],             # tp1_r
        [2.5, 3.0, 3.5],             # runner_r
        [0, 2],                       # strike_offset: 0=ATM, 2=ITM-2
    ):
        if run_r <= tp1_r:
            continue  # nonsensical combo
        combos.append({
            "chart_stop_buffer": buf,
            "tp1_r": tp1_r,
            "runner_r": run_r,
            "strike_offset": offset,
        })
    return combos


def main() -> None:
    combos = build_combos()
    total = len(combos)
    print(f"Running {total} chart-stop SNIPER combos...")
    print(f"{'buf':>5} {'tp1_r':>5} {'run_r':>5} {'off':>3} {'pnl':>10} {'n':>5} {'WR%':>6}")

    results = []
    for i, c in enumerate(combos, 1):
        r = evaluate_sniper_cs_combo(c)
        r["_run_index"] = i
        results.append(r)

        if "error" in r:
            print(f"  [{i}/{total}] ERROR: {r['error'][:80]}")
            continue

        pnl = r.get("wide_pnl", 0)
        n = r.get("wide_n_trades", 0)
        wr = r.get("wide_wr", 0) * 100
        buf = c["chart_stop_buffer"]
        tp1_r = c["tp1_r"]
        run_r = c["runner_r"]
        off = c["strike_offset"]
        flag = " *PASS*" if r.get("passed_floors") else ""
        print(f"  {buf:>5.2f} {tp1_r:>5.1f} {run_r:>5.1f} {off:>3d} ${pnl:>9,.0f} {n:>5d} {wr:>5.1f}%{flag}")

    # Sort by edge_capture descending
    valid = [r for r in results if "error" not in r]
    valid.sort(key=lambda r: r.get("edge_capture", -999999), reverse=True)

    print("\n--- TOP 10 by edge_capture ---")
    print(f"{'buf':>5} {'tp1_r':>5} {'run_r':>5} {'off':>3} {'edge_cap':>10} {'wide_pnl':>10} {'WR%':>6} {'floors':>7}")
    for r in valid[:10]:
        c = r["combo"]
        ec = r.get("edge_capture", 0)
        wp = r.get("wide_pnl", 0)
        wr = r.get("wide_wr", 0) * 100
        pf = "PASS" if r.get("passed_floors") else "FAIL"
        print(
            f"  {c['chart_stop_buffer']:>5.2f} {c['tp1_r']:>5.1f} {c['runner_r']:>5.1f} "
            f"{c['strike_offset']:>3d} ${ec:>9,.0f} ${wp:>9,.0f} {wr:>5.1f}% {pf:>7}"
        )

    best = valid[0] if valid else None
    if best:
        print(f"\nBEST: buf={best['combo']['chart_stop_buffer']} tp1_r={best['combo']['tp1_r']} "
              f"runner_r={best['combo']['runner_r']} offset={best['combo']['strike_offset']} "
              f"edge_capture=${best.get('edge_capture', 0):,.0f} "
              f"wide_pnl=${best.get('wide_pnl', 0):,.0f} "
              f"n={best.get('wide_n_trades', 0)} WR={best.get('wide_wr', 0)*100:.1f}%")
        print(f"  by_day={best.get('by_day', {})}")
        print(f"  regressions={best.get('regressions', [])}")
        positive_count = sum(1 for r in valid if r.get("wide_pnl", 0) > 0)
        print(f"\n{positive_count}/{len(valid)} combos have positive wide_pnl")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"results": results, "best": best}, indent=2, default=str), encoding="utf-8")
    print(f"\nResults saved to {OUTPUT}")


if __name__ == "__main__":
    main()
