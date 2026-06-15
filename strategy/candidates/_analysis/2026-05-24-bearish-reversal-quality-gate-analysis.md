# BEARISH_REVERSAL Watcher Quality Gate Analysis
**Date:** 2026-05-24  
**Author:** Gamma (interactive session, OP-22 engine analysis)  
**Source:** watcher-observations.jsonl, N=71 deduped unique bars

---

## Summary

The production `bearish_reversal_at_level_watcher` has a hidden quality split: HIGH confidence PM
signals drive nearly all the edge, while MEDIUM confidence signals (the majority) are a consistent
drag. A quality gate similar to the V14E chop zone gate could significantly improve this watcher —
but N is currently too thin for production deployment.

---

## Cross-tab: Confidence × Time Bucket

| Tier | Time | N | WR | P&L |
|---|---|---:|---:|---:|
| **high** | **PM (13-14:xx)** | **10** | **60%** | **+$1,018** |
| high | AM (11:xx) | 3 | 33% | -$132 |
| high | NOON (12:xx) | 3 | 33% | -$20 |
| medium | PM (13-14:xx) | 24 | 38% | +$212 |
| medium | NOON (12:xx) | 14 | **29%** | **-$258** |
| medium | AM (11:xx) | 10 | 30% | -$284 |
| low | AM (11:xx) | 3 | 100% | +$275 |
| low | NOON (12:xx) | 1 | 0% | -$36 |
| low | PM (13-14:xx) | 2 | 50% | +$8 |

**Key finding:** `high_PM` (N=10) drives +$1,018 = 130% of total P&L. All other sub-tiers
combined = -$235. The medium confidence signals are the structural drag.

---

## Quarterly Breakdown

| Quarter | N | WR | P&L | Notes |
|---|---:|---:|---:|---|
| 2025-Q1 | 7 | 57% | +$90 | ✓ |
| 2025-Q2 | 28 | 36% | +$197 | Many signals, thin P&L |
| **2025-Q3** | **5** | **0%** | **-$166** | 0% WR — all stopped |
| **2025-Q4** | **10** | **30%** | **-$121** | Low WR |
| **2026-Q1** | **12** | **67%** | **+$886** | Best quarter (tariff-crash bear trend) |
| 2026-Q2 | 8 | 38% | -$103 | Mixed |

**Regime sensitivity confirmed:** BEARISH_REVERSAL thrives in strong bear regimes (2026-Q1 tariff
crash: WR=67%, +$886) and struggles in choppy/bull markets (2025-Q3/Q4: 0-30% WR). This is
expected — a "reversal at level on bull ribbon" (countertrend fade) needs a strong underlying bear
trend or J won't be attempting the setup.

---

## 5/01 Anchor Day Ground Truth

Kitchen model fabricated "10:03 and 10:34 AM trades" on 5/01 that do NOT exist in trades.csv.
Actual watcher observations on 5/01 confirm:

| Time | Watcher | Conf | P&L | Outcome |
|---|---|---|---|---|
| 09:55 | v14_enhanced_watcher | medium | +$13 | tp1_then_be_stop (BULL signal) |
| **11:50** | **bearish_reversal_at_level_watcher** | **medium** | **+$175** | **runner_hit** |
| 13:35 | v14_enhanced_watcher | low | -$30 | stopped |

The BEARISH_REVERSAL DID capture the 5/01 move correctly at 11:50 (+$175 runner).
J's 13:09 entry at +$470 was an anticipation entry (Rule 2 violation) that arrived before the
watcher-level confirmation. V14E fired at 13:35 LOW conf → -$30 (accounts for the "+$3" real-fills
on this day in the #12 param sweep).

---

## Proposed Gate (Pending Validation)

Extend the V14E chop-zone approach to BEARISH_REVERSAL:
- Block MEDIUM confidence signals during 11:xx and 12:xx (AM and NOON buckets)
- Keep all HIGH confidence signals regardless of hour
- Keep MEDIUM confidence signals in PM (13-14:xx) only

**Expected improvement:** +$542 (remove -$542 medium_AM + medium_NOON losses)
**N removed:** 24 medium AM+NOON signals (34% of all signals)
**N kept:** 47 signals (66%)

**IMPORTANT CAVEAT — N too thin for production:**
- N_high_PM = 10 (gate relies on this as the edge driver)
- N_medium_PM = 24 (keeping these is still questionable — WR=38%)
- Quarterly distribution shows regime sensitivity — need OOS walk-forward before shipping

---

## Next Steps

1. ✅ Kitchen task enqueued: `2443926f` (HIGH priority) — full OOS walk-forward + quality gate test
2. Accumulate 30+ more `high_PM` observations before considering watcher change
3. If OOS walk-forward passes: implement as OP-22 watcher change (same pattern as v14e chop zone)
4. Monitor quarterly distribution — if 2026-Q2 stays negative, may indicate regime shift

---

*This analysis uses deduped watcher-observations.jsonl data (L67 dedup applied). Raw undeduplicated 
counts are ~2x higher. All WR/P&L figures from deduped unique bar timestamps.*
