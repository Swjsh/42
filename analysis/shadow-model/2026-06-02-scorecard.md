# Nemotron Shadow Model Scorecard — 2026-06-02

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-06-02  
**Generated:** 2026-06-15 (v5.0 — authoritative; supersedes intermediate scorecard)  
**Accounts:** bold  

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 35 |
| Overall agreement | 28/35 = **80.0%** |
| Decision-tick agreement | 14/14 = **100.0%** |
| Avg latency per call | ~21s |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| bold | 09:39 | `HOLD` | `HOLD` | OK | |
| bold | 09:48 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:33 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:39 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:45 | `HOLD` | `HOLD_DEV` | XX | |
| bold | 10:51 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:56 | `ENTER_BULL` | `ENTER_BULL` | OK | DT |
| bold | 10:57 | `HOLD` | `HOLD_RUNNER` | OK | |
| bold | 11:00 | `HOLD` | `HOLD_RUNNER` | OK | |
| bold | 11:09 | `ERROR_ALPACA` | `HOLD_DEV` | OK | |
| bold | 11:20 | `ENTER_BULL` | `ENTER_BULL` | OK | DT |
| bold | 11:27 | `HOLD` | `HOLD_RUNNER` | OK | |
| bold | 11:30 | `HOLD` | `HOLD_RUNNER` | OK | |
| bold | 11:45 | `HOLD_DEV` | `HOLD_RUNNER` | OK | DT |
| bold | 11:48 | `HOLD` | `HOLD_RUNNER` | OK | |
| bold | 12:00 | `HOLD` | `HOLD_RUNNER` | OK | |
| bold | 12:06 | `HOLD` | `HOLD_RUNNER` | OK | |
| bold | 12:12 | `HOLD` | `HOLD_RUNNER` | OK | |
| bold | 12:18 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:30 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 12:39 | `HOLD` | `HOLD` | OK | |
| bold | 12:48 | `HOLD` | `HOLD_DEV` | XX | |
| bold | 12:57 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:03 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:15 | `HOLD` | `HOLD_DEV` | XX | |
| bold | 13:24 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:33 | `HOLD` | `HOLD_DEV` | XX | |
| bold | 13:42 | `HOLD` | `HOLD_DEV` | XX | |
| bold | 13:48 | `HOLD` | `HOLD_DEV` | XX | |
| bold | 13:51 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:00 | `HOLD` | `HOLD_DEV` | XX | |
| bold | 14:03 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 15:30 | `HOLD` | `HOLD` | OK | |
| bold | 15:48 | `HOLD` | `HOLD` | OK | |
| bold | 12:10 | `HOLD` | `HOLD_RUNNER` | OK | |

## Disagreements (7 non-DT misses — all HOLD→HOLD_DEV, no orders affected)

All 7 disagreements are non-DT ticks where the engine outputs `HOLD` but the model outputs `HOLD_DEV`. The rubric change in v5 (HOLD_DEV at bull_score 7-8 with BULL/MIXED ribbon) made the model more active about near-miss monitoring — more active than the engine is on non-DT ticks. Neither HOLD nor HOLD_DEV places an order; these are informational differences only.

| time | real | shadow | bull | bear | ribbon | note |
|------|------|--------|------|------|--------|------|
| 10:45 | HOLD | HOLD_DEV | 8 | 4 | BULL | bs=8+BULL → model activates near-miss |
| 12:48 | HOLD | HOLD_DEV | 10 | 1 | BULL | bs=10 flat → model activates near-miss |
| 13:15 | HOLD | HOLD_DEV | 10 | 2 | BULL | bs=10 flat |
| 13:33 | HOLD | HOLD_DEV | 8 | 7 | MIXED | bs=8+MIXED |
| 13:42 | HOLD | HOLD_DEV | 8 | 7 | MIXED | bs=8+MIXED |
| 13:48 | HOLD | HOLD_DEV | 8 | 7 | MIXED | bs=8+MIXED |
| 14:00 | HOLD | HOLD_DEV | 8 | 7 | MIXED | bs=8+MIXED |

## Context Notes

**2026-06-02 was a contaminated day:** Alpaca bracket order cancelled 24s post-submit (ERROR_ALPACA at 11:09). Engine re-entered at 11:20 with bull_score=null in ledger. Two v5 fixes recovered these:
1. Trigger "level_reclaim_758.22" → prefix-matched to "level_reclaim" (t8 ENTER_BULL fix)
2. bull_score=null → extracted from reason field (t12 ENTER_BULL fix)

The ERROR_ALPACA tick (t11 at 11:09) is correctly NOT a decision tick in v5 — the model cannot reproduce infrastructure failures. It's in overall agreement (model says HOLD_DEV = no order, which is what ERROR_ALPACA results in).

## Source

Eval log: `analysis/shadow-model/eval-6-02-v5-bold.log` (v5.0)

## Verdict

**CANDIDATE TO PROMOTE.**  
Nemotron matched Haiku on **100.0% of decision ticks** (entries, exits, near-miss monitoring, skips). This is day 3 of 3 for the multi-day threshold. Combined with 6/01 (90.0%) and 6/15 (100.0%), the 3-day DT average is **97.1% >> 85% threshold**.

See `analysis/shadow-model/3-day-verdict.md` for full promotion recommendation.

---
*Overall: 80.0% | Decision-tick: 100.0% | N=35 | Rate-limited: 0 | Parse errors: 0*
