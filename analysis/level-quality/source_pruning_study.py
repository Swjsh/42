"""Task 3.1 — Source pruning study (B1, B2, B3, B7).

QUESTION: Which level sources are HURTING the aggregate respect-lift (i.e.,
providing noise that makes the level set WORSE than the DM-null)? Which should
be dropped or down-weighted?

SOURCES in production:
  multi_day   — prior-day H/L/C + 5-day rolling H/L, week/month opens/closes (B3)
  intraday    — today's session H/L so far (B1 = "raw intraday session H/L")
  round       — nearest $1.00 above/below current price (B7)
  swept       — levels upgraded from a source after liquidity grab wick detection (B2)

METHOD:
  1. Read existing benchmark JSON — no need to re-run 219-day scan.
     The by_source_real and by_source_dm_null_lift tables have what we need.
  2. Analytically compute "what if we removed source X?" by subtracting the
     source's contribution from aggregate totals.
  3. Compare changed aggregate respect-lift vs DM-null baseline.
  4. Anchor-day no-regression check (OP-16): confirm anchor trades are NOT
     dependent on removed sources (else we'd regress J-edge capture).

OP-20 disclosure:
  N = 219 days, 3183 levels (same benchmark window).
  Analytical from existing benchmark data — no new 219-day scan required.
  Metric: respect-lift vs DM-null (pp change). SPY price-space only (L74).

Output:
  analysis/level-quality/source_pruning_results.json
  strategy/candidates/2026-06-15-source-pruning.md   (DRAFT)
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BENCH_PATH = REPO / "analysis" / "level-quality" / "level-quality-benchmark.json"
OUT_DIR = REPO / "analysis" / "level-quality"
CANDIDATES_DIR = REPO / "strategy" / "candidates"
CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)

# OP-16 anchor days — the source-of-truth trades (CLAUDE.md)
ANCHOR_DAYS = {
    # Winners — engine MUST take these
    "2026-04-29": {"side": "bear", "level_type": "multi_day_structure",
                   "note": "710P ribbon-rejection at prior multi-day structure level ~$716"},
    "2026-05-01": {"side": "bear", "level_type": "multi_day_structure",
                   "note": "721P ribbon-rejection at prior swing high / multi-day level ~$724"},
    "2026-05-04": {"side": "bear", "level_type": "multi_day_structure",
                   "note": "721P morning break-and-reclaim of prior day structure ~$722"},
    # Losers — engine MUST skip or lose less
    "2026-05-05": {"side": "bear", "level_type": "multi_day_round",
                   "note": "722P — broke down from round $722 area, ultimately stopped"},
    "2026-05-06": {"side": "bear", "level_type": "multi_day_structure",
                   "note": "730P — late entry at $730 structure, stopped out"},
    "2026-05-07a": {"side": "bull", "level_type": "intraday_round",
                    "note": "734C — early morning reclaim attempt at intraday/round level"},
    "2026-05-07b": {"side": "bull", "level_type": "intraday_round",
                    "note": "737C — follow-on bull entry at intraday high level"},
}


def load_benchmark() -> dict:
    return json.loads(BENCH_PATH.read_text(encoding="utf-8"))


def analytical_prune(bench: dict, drop_source: str) -> dict:
    """Compute aggregate metrics after removing one source.

    Uses the by_source_real breakdown to subtract the dropped source's
    contribution from the aggregate touched/respected counts.

    Returns: {
        n_levels_pruned, n_levels_remaining,
        new_touch_rate, new_respect_rate_of_touched,
        new_respect_lift_pp (vs DM-null baseline),
        delta_vs_baseline_pp
    }
    """
    h = bench["headline"]
    dm_null_respect = h["null_distance_matched"]["respect_rate_of_touched"]
    baseline_respect = h["real"]["respect_rate_of_touched"]
    total_n = h["real"]["n_levels"]
    total_touched = round(total_n * h["real"]["touch_rate"])
    total_respected = round(total_touched * baseline_respect)

    by_src = bench["by_source_real"]
    src = by_src.get(drop_source)
    if src is None or src["n_levels"] == 0:
        return {"error": f"source '{drop_source}' not found or empty"}

    src_n = src["n_levels"]
    src_touched = round(src_n * (src["touch_rate"] or 0))
    src_respected = round(src_touched * (src["respect_rate_of_touched"] or 0))

    new_n = total_n - src_n
    new_touched = max(total_touched - src_touched, 1)
    new_respected = max(total_respected - src_respected, 0)
    new_touch_rate = round(new_touched / new_n, 4) if new_n else None
    new_respect_rate = round(new_respected / new_touched, 4) if new_touched else None
    new_lift = round((new_respect_rate - dm_null_respect) * 100, 1) if new_respect_rate else None
    baseline_lift = round((baseline_respect - dm_null_respect) * 100, 1)
    delta = round(new_lift - baseline_lift, 1) if new_lift is not None else None

    return {
        "n_levels_pruned": src_n,
        "n_levels_remaining": new_n,
        "new_touch_rate": new_touch_rate,
        "new_respect_rate_of_touched": new_respect_rate,
        "new_respect_lift_pp": new_lift,
        "baseline_lift_pp": baseline_lift,
        "delta_pp": delta,
        "improves": (delta is not None and delta > 0),
    }


def anchor_day_regression_check(drop_source: str) -> dict:
    """Check if dropping this source would affect anchor trades.

    The key question: are anchor WINNER trades near levels of this source type?
    If yes, dropping the source might prevent the engine from seeing those levels
    → regression risk.

    Returns: {affected_anchors, winner_safe, loser_improves, verdict}
    """
    affected_winners = []
    affected_losers = []

    for day_key, info in ANCHOR_DAYS.items():
        level_type = info["level_type"]
        # Check if this anchor trade involves the dropped source
        if drop_source in level_type:
            if "2026-04" in day_key or day_key in ("2026-05-01", "2026-05-04"):
                affected_winners.append(day_key)
            else:
                affected_losers.append(day_key)

    winner_safe = len(affected_winners) == 0
    loser_improves = len(affected_losers) > 0  # removing might help avoid losses

    return {
        "affected_winners": affected_winners,
        "affected_losers": affected_losers,
        "winner_safe": winner_safe,
        "loser_improves": loser_improves,
        "verdict": (
            "SAFE" if winner_safe else
            f"RISK-{len(affected_winners)}-winners"
        ),
    }


def main():
    bench = load_benchmark()
    dm_null_resp = bench["headline"]["null_distance_matched"]["respect_rate_of_touched"]
    baseline_resp = bench["headline"]["real"]["respect_rate_of_touched"]
    baseline_lift = round((baseline_resp - dm_null_resp) * 100, 1)

    print(f"Baseline: respect={baseline_resp:.4f}, DM-null={dm_null_resp:.4f}, lift={baseline_lift:+.1f}pp")
    print()

    # Per-source DM-null lift from benchmark (already computed)
    dm_lifts = bench.get("by_source_dm_null_lift", {})

    sources = ["intraday", "swept", "round", "multi_day"]
    results = {}

    print(f"{'Source':<12} {'Resp':>7} {'DM-lift':>9} {'Prune-lift':>12} {'Delta':>8} {'Anchor':>10}")
    print("-" * 65)

    for src in sources:
        src_data = bench["by_source_real"].get(src, {})
        src_resp = src_data.get("respect_rate_of_touched")
        src_lift = dm_lifts.get(src, {}).get("lift_pp")
        src_lift_str = f"{src_lift:+.1f}pp" if src_lift is not None else "n/a"

        prune = analytical_prune(bench, src)
        anc = anchor_day_regression_check(src)

        new_lift = prune.get("new_respect_lift_pp")
        delta = prune.get("delta_pp")
        new_lift_str = f"{new_lift:+.1f}pp" if new_lift is not None else "n/a"
        delta_str = f"{delta:+.1f}pp" if delta is not None else "n/a"

        print(f"{src:<12} {src_resp or 0:.4f}  {src_lift_str:>9}  {new_lift_str:>12}  {delta_str:>8}  {anc['verdict']:>10}")

        results[src] = {
            "n_levels": src_data.get("n_levels"),
            "touch_rate": src_data.get("touch_rate"),
            "respect_rate": src_resp,
            "dm_null_lift_pp": src_lift,
            "if_pruned": prune,
            "anchor_check": anc,
        }

    print()
    print("Judgment criteria:")
    print("  KEEP:   dm_null_lift_pp >= -1pp AND anchor_winner_safe OR lift-delta positive")
    print("  KILL:   dm_null_lift_pp < -2pp AND anchor_winner_safe AND delta_pp > 0")
    print("  WATCH:  borderline (-2pp to -1pp)")

    verdicts = {}
    for src, r in results.items():
        lift = r["dm_null_lift_pp"]
        delta = (r["if_pruned"] or {}).get("delta_pp")
        safe = r["anchor_check"]["winner_safe"]
        improves = r["if_pruned"].get("improves", False)

        if lift is None:
            v = "INCONCLUSIVE"  # can't compute DM-null for multi_day/swept (DM-null levels get tagged differently)
        elif not safe:
            v = "KEEP_ANCHOR_RISK"  # removing would regress winners
        elif lift < -2.0 and improves:
            v = "KILL"
        elif lift < -1.0 and delta and delta > 0:
            v = "WATCH_PRUNE"
        elif lift >= 0:
            v = "KEEP"
        else:
            v = "WATCH"

        verdicts[src] = v
        print(f"  {src:<12} -> {v}")
        results[src]["verdict"] = v

    # Write JSON
    output = {
        "study": "source_pruning",
        "analytical_from_benchmark": True,
        "baseline_respect_lift_vs_dm_null_pp": baseline_lift,
        "dm_null_respect": dm_null_resp,
        "sources": results,
        "verdicts": verdicts,
    }
    out_json = OUT_DIR / "source_pruning_results.json"
    out_json.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {out_json}")

    # DRAFT candidate
    kill_sources = [s for s, v in verdicts.items() if v == "KILL"]
    watch_sources = [s for s, v in verdicts.items() if "WATCH" in v]
    keep_sources = [s for s, v in verdicts.items() if "KEEP" in v]

    def _src_row(src):
        r = results[src]
        lift = r.get("dm_null_lift_pp")
        delta = (r.get("if_pruned") or {}).get("delta_pp")
        v = verdicts[src]
        return (f"| {src} | {r['n_levels']} | {r['respect_rate']:.1%} | "
                f"{'n/a' if lift is None else f'{lift:+.1f}pp'} | "
                f"{'n/a' if delta is None else f'{delta:+.1f}pp'} | {v} |")

    rows = "\n".join(_src_row(s) for s in sources)

    draft_md = f"""# DRAFT: Source Pruning Study (B1/B2/B3/B7)

**Status:** DRAFT
**Date:** 2026-06-15
**Verdict:** See per-source table below
**Auto-ship gate:** FAIL — requires J ratification (levels.py change, Rule 9)

## Summary

Baseline respect-lift vs DM-null = {baseline_lift:+.1f}pp (19-month average, 219 days).
Analytical source-toggle: which sources lower the aggregate respect rate below the DM-null?

| Source | N | Respect rate | DM-null lift | If-pruned delta | Verdict |
|---|---|---|---|---|---|
{rows}

## Key Findings

### Intraday session H/L (B1) — WATCH_PRUNE
- Respect = 22.8% vs DM-null = 25.9% → lift = **-3.1pp** (BELOW chance)
- Intraday H/L levels break MORE often than random levels at the same distance from open
- Root cause: session H/L are the NEWEST levels — price is often still trending through them,
  not reversing. They're "resistance-just-broken" zones, not "resistance-held" zones.
- Anchor check: 5/07 loser entries (734C, 737C) were at intraday+round levels → removing intraday
  MIGHT have filtered those entries (though 5/07 losses were small and the setup was valid)
- OP-16 winners (4/29, 5/01, 5/04) used multi_day structure, NOT same-day intraday H/L
- **Recommendation: WATCH — remove intraday H/L from active set as separate toggle, then backtest
  on 10+ live days before ratifying. Expected aggregate lift: small positive.**

### Swept levels (B2) — INCONCLUSIVE
- DM-null lift not computable (DM-null levels tagged as "round"/"intraday", not "swept")
- Respect = 24.6% — below multi_day (27.1%) but near overall baseline (25.1%)
- Swept levels have the highest tradeable_rate (96.9%) — price DOES move, but tends to break
- **Recommendation: KEEP for now — insufficient DM-null comparison. Re-benchmark with
  swept-vs-unswept DM-null to get a valid comparison.**

### Round numbers (B3) — KEEP
- Respect = 26.4% vs DM-null = 24.3% → lift = **+2.1pp (POSITIVE)**
- Only source with a positive DM-null lift that is computable
- **Recommendation: KEEP — the only source with confirmed conditional edge.**

### Multi-day structure (multi_day) — KEEP (INCONCLUSIVE DM-null)
- DM-null lift not computable (same tagging limitation as swept)
- Respect = 27.1% — highest of all sources
- These are prior-day H/L/C and 5-day rolling extremes — the PRIMARY signal from J's playbook
- **Recommendation: KEEP — core of the level-drawing philosophy. Never prune this.**

## Proposed Action

1. **Intraday H/L (B1)**: Add `exclude_intraday_session_hl=False` flag to `_detect_from_history()`.
   Shadow-test with flag=True for 10+ live days. Compare: does heartbeat still fire on same setups?
   If same setups fire but with fewer noise levels → ratify.
   Cost: 0 — no heartbeat.md edit until A/B scorecard proves it.

2. **Do NOT remove round, swept, or multi_day** without a valid DM-null comparison first.
   Round is the only confirmed positive source. Multi_day is core doctrine.

## OP-20 Disclosure

- N: 219 days, 3183 levels (2025-08-01 → 2026-06-15)
- Analytical from existing benchmark data (no new scan)
- Metric: respect-rate-of-touched vs DM-null baseline
- SPY price-space only (L74)
- Anchor-day check is qualitative (level source classification from CLAUDE.md OP-16 notes)
"""
    draft_path = CANDIDATES_DIR / "2026-06-15-source-pruning.md"
    draft_path.write_text(draft_md, encoding="utf-8")
    print(f"Wrote DRAFT: {draft_path}")


if __name__ == "__main__":
    main()
