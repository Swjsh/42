# DRAFT: Source Pruning Study (B1/B2/B3/B7)

**Status:** DRAFT
**Date:** 2026-06-15
**Verdict:** See per-source table below
**Auto-ship gate:** FAIL — requires J ratification (levels.py change, Rule 9)

## Summary

Baseline respect-lift vs DM-null = -0.6pp (19-month average, 219 days).
Analytical source-toggle: which sources lower the aggregate respect rate below the DM-null?

| Source | N | Respect rate | DM-null lift | If-pruned delta | Verdict |
|---|---|---|---|---|---|
| intraday | 281 | 22.8% | -3.1pp | +0.3pp | KILL |
| swept | 1569 | 24.6% | n/a | +0.7pp | INCONCLUSIVE |
| round | 274 | 26.4% | +2.1pp | -0.1pp | KEEP |
| multi_day | 1059 | 27.1% | n/a | -0.5pp | INCONCLUSIVE |

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
