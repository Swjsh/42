# Vision-vs-Heartbeat Divergence Report

**Status:** DRAFT: INSUFFICIENT_DATA
**Date:** 2026-06-15
**Phase:** 4 — Live-path robustness
**Task:** AC-4.1

## Summary

| Metric | Value |
|--------|-------|
| Vision (SPY) obs | 3 |
| Decision ticks (safe) | 56 |
| Paired ticks | 3 |
| ALIGNED_ACTIVE | 0 |
| ALIGNED_HOLD | 1 |
| DIVERGED | 0 |
| Vision-only | 2 |
| Heartbeat-only | 47 |
| D1 (level miss) | 1 |
| D2 (direction mismatch) | 0 |
| Evidence n vs min-20 | 3 / 20 |

## Data Sparsity Finding

The vision observer (`chart_vision_observer`) has only fired **3 times** across **1 trading day** (2026-05-19). This is far below the OP-11 minimum evidence_n=20 required for any statistical conclusion. All D1/D2/multi-hour-context verdicts are tagged INSUFFICIENT_DATA.

**Root cause:** The vision observer runs as an optional parallel path during heartbeat ticks but has not been consistently wired to persist observations across sessions. The `vision-observations.jsonl` file exists but coverage is sparse.

## Paired Observations (2026-05-19)

- `2026-05-19 10:48` vis=bear(conf=6) eng=hold type=ALIGNED_HOLD level=none truth=FLAT
- `2026-05-19 15:24` vis=bear(conf=8) eng=none type=vision-only level=734.48 Support truth=WRONG
- `2026-05-19 15:36` vis=unclear(conf=4) eng=none type=vision-only level=none truth=None

## D1 — Level Placement Divergence

**Definition:** Vision reports a named level (q3_level_interaction.named_level != null) but the engine heartbeat had no trigger_fired for that tick.

**Count:** 1 events
**Next-bar accuracy:** 0.0% (n=1)
**Verdict:** INSUFFICIENT_DATA — framework ready, needs >=20 obs

The D1 signal would be actionable if: vision-identified levels show >=3pp better next-bar accuracy than the DM-null baseline (25.7%). This threshold was derived from the benchmark study.

## D2 — Direction Classification Divergence

**Definition:** Vision q5_direction_call (bull/bear) disagrees with engine action direction.

**Count:** 0 events
**Verdict:** INSUFFICIENT_DATA

Proposed resolution rule: if vision confidence >= 8 AND D2 diverges, emit VISION_ALERT to decisions.jsonl as advisory field (not to override engine action).

## Multi-Hour Context Feature Prototype

**Feature:** `ctx_level_tests_today` = count of prior vision obs TODAY that saw the same named_level. Hypothesis: repeated-level observations refine our confidence in that level holding.

| ctx_level_tests | n obs | Next-bar accuracy |
|-----------------|-------|------------------|
| 0 (first touch) | 1 | 0.0% |
| >=1 (repeat) | 0 | None% |

**Verdict:** INSUFFICIENT_DATA. Feature logic is implemented in `_build_multihr_context()`. Re-run when N>=20.

## Known Limitations

- Vision observer has only fired on 1 date (2026-05-19) — systematic gaps in coverage
- Some lines in decisions.jsonl are malformed (2 objects concatenated) and were skipped
- Next-bar truth uses 5m close delta; option P&L accuracy would require real-fills
- Missing date field on some decision rows (9/56) due to format drift
- N=3 usable paired obs is far below evidence_min=20 — no statistical conclusions possible

## When to Rerun

Rerun after vision observer accumulates >=20 SPY obs across >=5 trading days. Set HEADLINE_REACT and HEADLINE_K to match the level quality benchmark.

## Activation Path

To increase vision coverage without J involvement (engine-benefit work per OP-22):

1. Ensure `chart_vision_observer` is called every heartbeat tick (not just HOT ticks)
2. Wire the vision output to append to `automation/state/vision-observations.jsonl` on every SPY 5m observation
3. Once N>=20 obs across >=5 days, rerun this script — the full D1/D2/multi-hour framework will activate automatically

**Cost estimate (per OP-3):** Vision observer uses Haiku ($0.25/1M tokens input). At 127 ticks/day, each tick appends ~500 tokens of structured JSON. Estimated: 127 x 500 / 1M x $0.25 = ~$0.016/day incremental. Negligible.

## Verdict

DRAFT: INSUFFICIENT_DATA. Framework validated; D1/D2/multi-hour logic is complete and ready. Rerun when vision-observations.jsonl has >=20 SPY observations across >=5 trading days.
