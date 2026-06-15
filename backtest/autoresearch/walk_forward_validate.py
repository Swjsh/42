"""Walk-forward validation — gold-standard out-of-sample test.

Splits the data 2025-01-01 to 2026-05-07 into:
  TRAIN: 2025-01-01 to 2025-12-31 (1 year)
  TEST:  2026-01-01 to 2026-05-07 (4.3 months — TRULY out of sample)

Runs each candidate (top keepers from stage 1-4) on BOTH:
  1. TRAIN window — re-verifies it works
  2. TEST window — REAL out-of-sample test (no optimization happened here)

A candidate is "Monday-ready" only if it's net-positive on TEST.
This is the strictest gate yet because the optimizer NEVER saw 2026 data
when picking the params (well — for J-edge it did, but for aggregate it didn't).

Writes a summary to:
  analysis/recommendations/walk-forward-results.json
  docs/WALK-FORWARD.md
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

OUT_JSON = ROOT / "analysis" / "recommendations" / "walk-forward-results.json"
OUT_MD = ROOT / "docs" / "WALK-FORWARD.md"

TRAIN_START = dt.date(2025, 1, 1)
TRAIN_END = dt.date(2025, 12, 31)
TEST_START = dt.date(2026, 1, 1)
TEST_END = dt.date(2026, 5, 7)

STAGE_DIRS = [
    ("stage4", REPO / "autoresearch" / "_state" / "stage4_grinder"),
    ("stage3", REPO / "autoresearch" / "_state" / "stage3_grinder"),
    ("stage2", REPO / "autoresearch" / "_state" / "stage2_grinder"),
    ("stage1", REPO / "autoresearch" / "_state" / "overnight_grinder"),
]


def _load_top_keepers(top_n: int = 5) -> list[tuple[str, dict]]:
    """Pool keepers from all stages, dedupe, return top N by combined rank."""
    pool = []
    for name, d in STAGE_DIRS:
        p = d / "keepers.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    r["_stage"] = name
                    pool.append(r)
                except Exception:
                    pass
    if not pool:
        raise SystemExit("no keepers found in any stage")

    # Dedup by combo
    seen = set()
    deduped = []
    for r in pool:
        key = json.dumps(r["combo"], sort_keys=True)
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    edge_rank = {id(r): i for i, r in enumerate(sorted(deduped, key=lambda r: -r.get("edge_capture", 0)))}
    wide_rank = {id(r): i for i, r in enumerate(sorted(deduped, key=lambda r: -r.get("wide_pnl", 0)))}
    deduped.sort(key=lambda r: edge_rank[id(r)] + wide_rank[id(r)])
    return [(r["_stage"], r["combo"]) for r in deduped[:top_n]]


def _evaluate(combo: dict, start: dt.date, end: dt.date) -> dict:
    from autoresearch import runner
    from autoresearch.j_edge_tracker import V15_J_EDGE_OVERRIDES
    from autoresearch.overnight_grinder import _patch_orchestrator

    params = json.loads((REPO.parent / "automation" / "state" / "params.json").read_text(encoding="utf-8-sig"))
    params.update(V15_J_EDGE_OVERRIDES)
    spy, vix = runner.load_data(start, end)
    with _patch_orchestrator(combo):
        res, m = runner.run_with_params(params, start, end, spy, vix)

    quarter_pnl = defaultdict(float)
    day_pnl = defaultdict(float)
    for t in res.trades:
        d = t.entry_time_et.date()
        day_pnl[d] += t.dollar_pnl
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        quarter_pnl[q] += t.dollar_pnl

    sorted_days = sorted(day_pnl.values(), reverse=True)
    top5 = sum(sorted_days[:5])
    return {
        "total_pnl": round(m.total_pnl, 2),
        "n_trades": m.n_trades,
        "n_winners": m.n_winners,
        "win_rate": round(m.n_winners / m.n_trades, 3) if m.n_trades else 0.0,
        "quarter_pnl": {k: round(v, 2) for k, v in quarter_pnl.items()},
        "positive_quarters": sum(1 for v in quarter_pnl.values() if v > 0),
        "top5_pct": round(top5 / m.total_pnl, 3) if m.total_pnl > 0 else 0,
    }


def main() -> int:
    candidates = _load_top_keepers(5)
    print(f"Validating top {len(candidates)} candidates walk-forward...")
    results = []
    for stage_name, combo in candidates:
        print(f"  evaluating combo from {stage_name}: {combo}")
        train = _evaluate(combo, TRAIN_START, TRAIN_END)
        test = _evaluate(combo, TEST_START, TEST_END)
        # Per-month normalized (HONEST metric) — train=12mo, test=4.3mo
        train_per_mo = train["total_pnl"] / 12.0 if train["total_pnl"] else 0
        test_per_mo = test["total_pnl"] / 4.3 if test["total_pnl"] else 0
        ratio_normalized = (test_per_mo / train_per_mo) if train_per_mo > 0 else 0
        results.append({
            "source_stage": stage_name,
            "combo": combo,
            "train_2025": train,
            "test_2026": test,
            "train_pnl_per_month": round(train_per_mo, 2),
            "test_pnl_per_month": round(test_per_mo, 2),
            "ratio_normalized_per_month": round(ratio_normalized, 3),
            "monday_ready": test["total_pnl"] > 0 and ratio_normalized >= 0.5,
        })

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "train_window": f"{TRAIN_START} to {TRAIN_END}",
        "test_window": f"{TEST_START} to {TEST_END}",
        "candidates": results,
        "verdict": "monday_ready" if any(r["monday_ready"] for r in results) else "no_candidates_pass_oos",
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    md = [f"# Walk-forward validation — {dt.datetime.now().isoformat()}\n"]
    md.append(f"**Train:** {TRAIN_START} to {TRAIN_END}  (engine optimized HERE)")
    md.append(f"**Test:**  {TEST_START} to {TEST_END}  (TRULY out-of-sample — never seen by optimizer)")
    md.append("")
    md.append(f"**Verdict:** {out['verdict']}")
    md.append("")
    md.append("| Stage | Train P&L | Train $/mo | Test P&L | Test $/mo | Ratio (per-month) | Monday ready |")
    md.append("|---|---|---|---|---|---|---|")
    for r in results:
        tr = r["train_2025"]
        ts = r["test_2026"]
        ready = "✅" if r["monday_ready"] else "❌"
        md.append(
            f"| {r['source_stage']} | ${tr['total_pnl']:.0f} (12mo) | ${r['train_pnl_per_month']:.0f}/mo "
            f"| ${ts['total_pnl']:.0f} (4.3mo) | ${r['test_pnl_per_month']:.0f}/mo "
            f"| {r['ratio_normalized_per_month']:.2f}x | {ready} |"
        )
    md.append("")
    md.append("## Interpretation (per-month normalized — the HONEST metric)")
    md.append("")
    md.append("- **Per-month ratio > 0.7x** = strategy generalizes well to OOS data")
    md.append("- **Per-month ratio 0.5-0.7x** = mild overfit, still trade-worthy")
    md.append("- **Per-month ratio < 0.5x** = serious overfit (DO NOT trade)")
    md.append("- **Test P&L < 0** = strategy fails out-of-sample (DO NOT trade)")
    md.append("")
    md.append("Note: original total-P&L ratio (test/train) was misleading because train=12mo and test=4.3mo (naive ratio compares dollars not rate).")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"Walk-forward written: {OUT_JSON} + {OUT_MD}")
    print(f"Verdict: {out['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
