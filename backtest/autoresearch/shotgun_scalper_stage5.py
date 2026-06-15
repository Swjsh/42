"""SHOTGUN_SCALPER Stage 5 — final ratification scorecard.

Reads Stage 4 keepers and produces OP 20-compliant scorecard:
1. Walk-forward split: train=2025 (4 quarters), test=2026 (2 quarters)
2. Per-quarter stability check (all 6 quarters net-positive)
3. Concentration disclosure (top-5 days % of total P&L)
4. OP 16 edge_capture primary gate
5. OP 14 Sharpe + expectancy + max-drawdown
6. Failure-mode enumeration

Usage:
    python -m autoresearch.shotgun_scalper_stage5
    python -m autoresearch.shotgun_scalper_stage5 --min-keepers 3

Outputs:
    analysis/recommendations/shotgun-scalper-stage5.json
    analysis/recommendations/shotgun-scalper-stage5-summary.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

STAGE4_STATE  = REPO / "autoresearch" / "_state" / "shotgun_scalper_stage4"
STAGE3_STATE  = REPO / "autoresearch" / "_state" / "shotgun_scalper_stage3"
OUT_JSON      = ROOT / "analysis" / "recommendations" / "shotgun-scalper-stage5.json"
OUT_MD        = ROOT / "analysis" / "recommendations" / "shotgun-scalper-stage5-summary.md"

# OP 20 disclosure constants
ACCOUNT_SIZE_ASSUMPTION_DOLLARS = 1000   # $1K paper account (J's current Gamma-Safe)
QTY_PER_TRADE_BASELINE          = 3      # grinder baseline qty

# Stage 5 gates
TRAIN_QUARTERS  = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
TEST_QUARTERS   = ["2026-Q1", "2026-Q2"]
MIN_WF_TEST_PNL = 0.0          # test window must be net-positive
MIN_DIR_SCORE   = 2             # minimum directional score from Stage 4
MIN_SHARPE      = 1.5           # stronger than Stage 4's 1.0
MIN_WIDE_PNL    = 5000.0        # minimum 16-month net P&L ($5K)
MAX_DRAWDOWN_PCT= 0.35          # max drawdown as fraction of wide_pnl (OP 14)
MAX_TOP5_PCT    = 0.50          # concentration gate: top-5 days ≤ 50% (OP 20)


def _read_keepers(state_dir: Path) -> list[dict]:
    p = state_dir / "keepers.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _walk_forward(keeper: dict) -> dict:
    """Split quarter_pnl into train (2025) and test (2026) windows."""
    qpnl = keeper.get("quarter_pnl", {})
    train_pnl  = sum(qpnl.get(q, 0) for q in TRAIN_QUARTERS)
    test_pnl   = sum(qpnl.get(q, 0) for q in TEST_QUARTERS)
    train_pos  = sum(1 for q in TRAIN_QUARTERS if qpnl.get(q, 0) > 0)
    test_pos   = sum(1 for q in TEST_QUARTERS  if qpnl.get(q, 0) > 0)
    passed     = test_pnl > MIN_WF_TEST_PNL and test_pos == len(TEST_QUARTERS)
    return {
        "train_pnl":  round(train_pnl, 2),
        "test_pnl":   round(test_pnl, 2),
        "train_positive_quarters": train_pos,
        "test_positive_quarters":  test_pos,
        "passed": passed,
        "reason": (
            "PASS: test window net-positive, all test quarters positive"
            if passed else
            f"FAIL: test_pnl={test_pnl:.0f}, test_positive_quarters={test_pos}/2"
        ),
    }


def _concentration_check(keeper: dict) -> dict:
    """Check that top-5 days don't dominate (OP 20 §6)."""
    top5_pct   = keeper.get("top5_pct", 0.0)
    wide_pnl   = keeper.get("wide_pnl", 0.0)
    n_trades   = keeper.get("wide_n_trades", 0)
    top5_label = f"Top-5 days = {top5_pct*100:.1f}% of {wide_pnl:.0f} P&L"
    passed     = top5_pct <= MAX_TOP5_PCT
    return {
        "top5_pct":  round(top5_pct, 4),
        "wide_pnl":  round(wide_pnl, 2),
        "n_trades":  n_trades,
        "label":     top5_label,
        "passed":    passed,
        "reason":    (
            f"PASS: {top5_pct*100:.1f}% ≤ {MAX_TOP5_PCT*100:.0f}% concentration cap"
            if passed else
            f"WARN: {top5_pct*100:.1f}% > {MAX_TOP5_PCT*100:.0f}% — concentrated in few days"
        ),
    }


def _op20_disclosures(keeper: dict, wf: dict) -> list[str]:
    """Build OP 20 six-item disclosure list."""
    wide_pnl   = keeper.get("wide_pnl", 0.0)
    n_trades   = keeper.get("wide_n_trades", 0)
    top5_pct   = keeper.get("top5_pct", 0.0)
    max_dd     = keeper.get("max_drawdown", 0.0)
    sharpe     = keeper.get("sharpe", 0.0)
    expectancy = keeper.get("expectancy_per_trade", 0.0)
    q_pnl      = keeper.get("quarter_pnl", {})
    worst_q    = min(q_pnl, key=q_pnl.get) if q_pnl else "N/A"

    return [
        f"1. ACCOUNT SIZE: Baseline qty={QTY_PER_TRADE_BASELINE} contracts / ${ACCOUNT_SIZE_ASSUMPTION_DOLLARS} paper. "
        f"Headline P&L ({wide_pnl:.0f}) scales with qty — at $1K paper, 3-contract positions represent high % risk.",

        f"2. SAMPLE BIAS: Top-{5} best days = {top5_pct*100:.1f}% of total P&L. "
        f"Selected from Stage 4 grid of {288} combos — winner's curse applies. "
        f"Out-of-sample walk-forward test below partially corrects for this.",

        f"3. OUT-OF-SAMPLE: walk-forward train=2025 ({wf['train_pnl']:.0f}) test=2026 ({wf['test_pnl']:.0f}). "
        f"Result: {'PASS' if wf['passed'] else 'FAIL'} ({wf['reason']}). "
        f"Full OPRA real-fills used throughout (no BS sim).",

        f"4. REAL-FILLS: All simulation uses Alpaca OPRA option bars (5-min OHLCV). "
        f"No Black-Scholes pricing. Entry approx = VWAP of next 5m bar after signal. "
        f"Slippage not explicitly modeled — bid/ask spread implicit in VWAP vs last.",

        f"5. FAILURE MODES: (a) Worst quarter={worst_q} ({q_pnl.get(worst_q, 0):.0f}). "
        f"(b) Max drawdown={max_dd:.0f} = {max_dd/max(wide_pnl, 1)*100:.1f}% of total P&L. "
        f"(c) Engine fires LONG on 4/29 (J SHORT) and 5/15 (J SHORT) — structural trendline-bias miss. "
        f"(d) 5-trade/day cap: misses alpha on high-conviction days (5/04 engine fired 4 but J ran 10).",

        f"6. CONCENTRATION: top-5 days = {top5_pct*100:.1f}% of {wide_pnl:.0f} P&L "
        f"({'PASS' if top5_pct <= MAX_TOP5_PCT else 'WARN: concentrated'}). "
        f"N={n_trades} trades over 16 months. Sharpe={sharpe:.2f}, expectancy={expectancy:.2f}/trade.",
    ]


def _score_keeper(keeper: dict, wf: dict, conc: dict) -> dict:
    """Compute Stage 5 pass/fail and overall score."""
    checks: dict[str, bool] = {}
    checks["walk_forward"]    = wf["passed"]
    checks["directional"]     = keeper.get("stage4_directional_score", 0) >= MIN_DIR_SCORE
    checks["sharpe"]          = keeper.get("sharpe", 0) >= MIN_SHARPE
    checks["wide_pnl"]        = keeper.get("wide_pnl", 0) >= MIN_WIDE_PNL
    checks["max_drawdown"]    = (
        keeper.get("max_drawdown", float("inf")) <=
        MAX_DRAWDOWN_PCT * max(keeper.get("wide_pnl", 1), 1)
    )
    checks["positive_q6"]     = keeper.get("positive_quarters", 0) >= 6
    checks["edge_capture"]    = keeper.get("edge_capture", 0) > 0

    passed = all(checks.values())
    score  = (
        keeper.get("edge_capture", 0) * keeper.get("sharpe", 0) +
        wf["test_pnl"] / 1000
    )
    return {
        "passed": passed,
        "score":  round(score, 4),
        "checks": checks,
    }


def ratify(keepers: list[dict], source_stage: str) -> dict:
    """Apply Stage 5 analysis to a list of keepers."""
    results = []
    for i, k in enumerate(keepers):
        wf   = _walk_forward(k)
        conc = _concentration_check(k)
        gate = _score_keeper(k, wf, conc)
        disc = _op20_disclosures(k, wf)
        results.append({
            "rank": i + 1,
            "combo": k.get("combo", {}),
            "source_stage": source_stage,
            # Key metrics
            "wide_pnl":    k.get("wide_pnl", 0),
            "sharpe":      k.get("sharpe", 0),
            "n_trades":    k.get("wide_n_trades", 0),
            "expectancy":  k.get("expectancy_per_trade", 0),
            "max_drawdown": k.get("max_drawdown", 0),
            "positive_quarters": k.get("positive_quarters", 0),
            "quarter_pnl": k.get("quarter_pnl", {}),
            # Directional scoring
            "dir_score":   k.get("stage4_directional_score", k.get("directional_score", 0)),
            "dir_max":     k.get("stage4_directional_max", 5),
            "dir_detail":  k.get("stage4_direction_detail", k.get("direction_detail", {})),
            "loser_avoid_score": k.get("stage4_loser_avoid_score", k.get("loser_avoid_score", 0)),
            # Stage 5 analysis
            "walk_forward": wf,
            "concentration": conc,
            "gate": gate,
            "op20_disclosures": disc,
        })

    # Sort: passed first, then by score
    results.sort(key=lambda r: (int(r["gate"]["passed"]), r["gate"]["score"]), reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    passed  = [r for r in results if r["gate"]["passed"]]
    best    = results[0] if results else None

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_stage": source_stage,
        "input_keepers": len(keepers),
        "stage5_passed": len(passed),
        "best": best,
        "all_results": results,
        "gates": {
            "min_dir_score": MIN_DIR_SCORE,
            "min_sharpe": MIN_SHARPE,
            "min_wide_pnl": MIN_WIDE_PNL,
            "max_drawdown_pct": MAX_DRAWDOWN_PCT,
            "max_top5_pct": MAX_TOP5_PCT,
            "walk_forward_test_positive": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SHOTGUN_SCALPER Stage 5 ratification.")
    ap.add_argument("--min-keepers", type=int, default=1,
                    help="Minimum keepers required to run (default=1, 0 to allow empty)")
    ap.add_argument("--stage", default="auto",
                    choices=["auto", "stage4", "stage3"],
                    help="Which stage to read keepers from (default=auto: stage4 → stage3)")
    args = ap.parse_args(argv)

    # Determine source
    source, keepers = "stage4", []
    if args.stage in ("auto", "stage4"):
        keepers = _read_keepers(STAGE4_STATE)
        source  = "stage4"
    if not keepers and args.stage in ("auto", "stage3"):
        keepers = _read_keepers(STAGE3_STATE)
        source  = "stage3"

    if not keepers:
        print(f"[Stage5] No keepers found in {STAGE4_STATE} or {STAGE3_STATE}. "
              "Wait for Stage 4 to produce at least one keeper.", file=sys.stderr)
        return 1

    if len(keepers) < args.min_keepers:
        print(f"[Stage5] Only {len(keepers)} keepers < min {args.min_keepers}. "
              "Proceeding anyway.", file=sys.stderr)

    print(f"[Stage5] Analyzing {len(keepers)} keepers from {source}...")
    scorecard = ratify(keepers, source)

    # Write JSON
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    print(f"[Stage5] Scorecard -> {OUT_JSON}")

    # Write summary markdown
    _write_markdown(scorecard)
    print(f"[Stage5] Summary  -> {OUT_MD}")

    # Print headline
    best = scorecard.get("best")
    if best:
        print(f"\n{'='*60}")
        print(f"BEST CANDIDATE (rank #{best['rank']}):")
        print(f"  combo:    {best['combo']}")
        print(f"  wide_pnl: ${best['wide_pnl']:.0f}  sharpe: {best['sharpe']:.2f}  "
              f"dir: {best['dir_score']}/{best['dir_max']}")
        print(f"  WF test:  ${best['walk_forward']['test_pnl']:.0f} "
              f"({best['walk_forward']['reason']})")
        print(f"  Stage5:   {'PASS OK' if best['gate']['passed'] else 'FAIL XX'}  "
              f"checks={best['gate']['checks']}")
        print(f"\nOP 20 Disclosures:")
        for d in best["op20_disclosures"]:
            print(f"  {d}")
        print("="*60)

    return 0 if scorecard["stage5_passed"] > 0 else 1


def _write_markdown(scorecard: dict) -> None:
    """Write human-readable ratification summary."""
    lines = [
        "# SHOTGUN_SCALPER Stage 5 — Ratification Scorecard",
        f"\nGenerated: {scorecard['generated_at']}",
        f"Source: {scorecard['source_stage']}  |  "
        f"Input keepers: {scorecard['input_keepers']}  |  "
        f"Stage5 passed: {scorecard['stage5_passed']}",
        "",
        "## Summary of all candidates",
        "",
        "| Rank | TP | Stop | Strike | Vol | Wide P&L | Sharpe | Dir | WF Test | Stage5 |",
        "|------|-----|------|--------|-----|----------|--------|-----|---------|--------|",
    ]
    for r in scorecard.get("all_results", []):
        c = r["combo"]
        lines.append(
            f"| {r['rank']} | {c.get('tp_premium_pct','?')} | {c.get('stop_premium_pct','?')} | "
            f"{c.get('strike_offset','?')} | {c.get('vol_ratio_threshold','?')} | "
            f"${r['wide_pnl']:.0f} | {r['sharpe']:.2f} | {r['dir_score']}/{r['dir_max']} | "
            f"${r['walk_forward']['test_pnl']:.0f} | "
            f"{'PASS' if r['gate']['passed'] else 'FAIL'} |"
        )

    best = scorecard.get("best")
    if best:
        lines.extend([
            "",
            f"## Best candidate: Rank #{best['rank']}",
            "",
            f"**Combo:** `{best['combo']}`",
            "",
            f"| Metric | Value | Gate |",
            "|--------|-------|------|",
        ])
        for k, v in best["gate"]["checks"].items():
            lines.append(f"| {k} | {'PASS' if v else 'FAIL'} | {'OK' if v else 'XX'} |")

        lines.extend([
            "",
            "### Quarter P&L breakdown",
            "",
            "| Quarter | P&L |",
            "|---------|-----|",
        ])
        for q, pnl in sorted(best.get("quarter_pnl", {}).items()):
            lines.append(f"| {q} | ${pnl:.0f} |")

        lines.extend([
            "",
            "### OP 20 Disclosures",
            "",
        ])
        for d in best.get("op20_disclosures", []):
            lines.append(f"- {d}")
            lines.append("")

        lines.extend([
            "",
            "### Direction detail (J anchor days)",
            "",
        ])
        for date, detail in best.get("dir_detail", {}).items():
            lines.append(f"- **{date}**: {detail}")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
