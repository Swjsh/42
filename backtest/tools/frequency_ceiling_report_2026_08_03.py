"""frequency_ceiling_report_2026_08_03.py -- renders markdown TABLE SNIPPETS from
FREQUENCY-CEILING-2026-08-03.json (produced by frequency_ceiling_cascade_2026_08_03.py).

Kept separate from the analysis tool on purpose: the analysis tool computes numbers, this
one only FORMATS already-computed numbers into markdown -- so a formatting bug can never
silently change a finding (the JSON is the single source of truth for every number quoted
in the .md report; this script is a convenience, not a second computation).

Run: backtest/.venv/Scripts/python.exe backtest/tools/frequency_ceiling_report_2026_08_03.py
Prints markdown snippets to stdout for hand-assembly into FREQUENCY-CEILING-2026-08-03.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IN_JSON = ROOT / "analysis" / "deep-research" / "FREQUENCY-CEILING-2026-08-03.json"


def fmt_dollars(v):
    if v is None:
        return "n/a"
    return f"+${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}"


def main() -> int:
    d = json.loads(IN_JSON.read_text(encoding="utf-8"))

    print("## Anchors\n")
    a = d["anchors"]
    print(f"- window: {d['window']['start']}..{d['window']['end']} ({d['window']['n_days']} RTH days)")
    print(f"- raw entries (r.trades): {a['n_raw_entries']}")
    print(f"- qualifying candidates (score>=8, level-tied, both sides): {a['n_qualifying_candidates']} "
          f"(bear={a['n_bear_candidates']}, bull={a['n_bull_candidates']})")
    print(f"- status counts: {a['status_counts']}")
    print(f"- gate-order cross-check: {a['gate_order_cross_check']['matched']}/"
          f"{a['gate_order_cross_check']['checked']} real-run first-SKIP actions matched\n")

    print("## Overlap matrix -- ALL layers (filter + gate + quality_lock)\n")
    o = d["overlap_matrix_all_layers"]
    print(f"n_blocked = {o['n_blocked']}\n")
    print("| Blocked by exactly N gates/filters | count | % of blocked |")
    print("|---|---:|---:|")
    for size, n in sorted(o["size_histogram"].items(), key=lambda kv: int(kv[0])):
        pct = 100.0 * n / o["n_blocked"] if o["n_blocked"] else 0
        print(f"| {size} | {n} | {pct:.1f}% |")
    print()
    print("### Sole-blocker leaderboard (all layers)\n")
    print("| Blocker | n times SOLE reason | n times appears at all (any set size) |")
    print("|---|---:|---:|")
    for b, n in sorted(o["sole_blocker_counts"].items(), key=lambda kv: -kv[1]):
        print(f"| `{b}` | {n} | {o['member_counts'].get(b, 0)} |")
    print()
    print("### Top co-firing pairs (all layers)\n")
    print("| Pair | n co-fired |")
    print("|---|---:|")
    for pair, n in sorted(o["pair_counts"].items(), key=lambda kv: -kv[1])[:20]:
        print(f"| `{pair}` | {n} |")
    print()

    print("## Overlap matrix -- GATE LAYER ONLY (post-filter, post-routing -- the genuinely novel cut)\n")
    g = d["overlap_matrix_gate_layer_only"]
    print(f"n_blocked = {g['n_blocked']} (routing_loss excluded, separately: {d['routing_loss_n']})\n")
    print("| Blocked by exactly N gates | count |")
    print("|---|---:|")
    for size, n in sorted(g["size_histogram"].items(), key=lambda kv: int(kv[0])):
        print(f"| {size} | {n} |")
    print()
    print("### Sole-blocker leaderboard (gate layer only)\n")
    print("| Gate | n times SOLE reason | n times appears at all |")
    print("|---|---:|---:|")
    for b, n in sorted(g["sole_blocker_counts"].items(), key=lambda kv: -kv[1]):
        print(f"| `{b}` | {n} | {g['member_counts'].get(b, 0)} |")
    print()
    print("### Co-firing pairs (gate layer only)\n")
    print("| Pair | n co-fired |")
    print("|---|---:|")
    for pair, n in sorted(g["pair_counts"].items(), key=lambda kv: -kv[1]):
        print(f"| `{pair}` | {n} |")
    print()

    print("## Sole-blocker cohorts -- counterfactual $ (real OPRA + real exit walk, oracle, hindsight)\n")
    print("| Blocker | n_blocked | n_priced | n_synthetic_excluded | total $ | $/trade | WR | BH-sig q=0.10 |")
    print("|---|---:|---:|---:|---:|---:|---:|:---:|")
    bh = d["sole_blocker_bh_fdr_q010"]
    all_sole = {**o["sole_blocker_counts"]}
    for b, n in sorted(all_sole.items(), key=lambda kv: -kv[1]):
        p = d["sole_blocker_cohorts_priced"].get(b)
        if not p:
            continue
        sig = bh.get(b)
        sig_s = "n/a" if sig is None else ("YES" if sig else "no")
        print(f"| `{b}` | {n} | {p['n_priced']} | {p['n_synthetic_excluded']} | "
              f"{fmt_dollars(p['total_dollars'])} | {fmt_dollars(p['per_trade_dollars'])} | "
              f"{p['win_rate']} | {sig_s} |")
    print()

    print("## Day participation (both sides)\n")
    print("| Cause | n days | % |")
    print("|---|---:|---:|")
    total_days = sum(d["day_participation_counts"].values())
    for cause, n in sorted(d["day_participation_counts"].items(), key=lambda kv: -kv[1]):
        print(f"| {cause} | {n} | {100.0*n/total_days:.1f}% |")
    print()

    print("## AXIS 2 -- no-trade-day oracle classification\n")
    print("| Classification | n days |")
    print("|---|---:|")
    for cls, n in sorted(d["axis2_classification_counts"].items(), key=lambda kv: -kv[1]):
        print(f"| {cls} | {n} |")
    print()
    genuine_gap = [r for r in d["axis2_no_trade_day_scan"] if r["classification"] == "NO_DETECTOR_GENUINE_GAP"]
    genuine_gap.sort(key=lambda r: -(r["oracle_bound_dollars"] or 0))
    print(f"### NO_DETECTOR_GENUINE_GAP candidates ({len(genuine_gap)} days), ranked by oracle $\n")
    print("| Date | oracle $ | direction | level | touch_idx | break_idx |")
    print("|---|---:|---|---:|---:|---:|")
    for r in genuine_gap[:40]:
        bc = r["best_candidate"] or {}
        print(f"| {r['date']} | {fmt_dollars(r['oracle_bound_dollars'])} | {bc.get('direction')} | "
              f"{bc.get('level')} | {bc.get('touch_idx')} | {bc.get('break_idx')} |")
    print()

    print(f"runtime_seconds = {d['runtime_seconds']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
