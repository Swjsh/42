# Nemotron Shadow Model Scorecard — 2026-05-18

**Model:** `nvidia/nemotron-3-super-120b-a12b:free`  
**Evaluation date:** 2026-05-18  
**Generated:** 2026-06-16T00:51:52Z  
**Accounts:** bold

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total ticks replayed | 22 |
| Overall agreement | 16/22 = **72.7%** |
| Decision-tick agreement | 7/8 = **87.5%** |
| Avg latency per call | 11764ms |
| Rate-limited (429) | 0 |
| Parse errors | 0 |
| Other errors | 0 |

## Tick-by-Tick Results

| Acct | time | real_action | shadow_action | agree | DT |
|------|------|-------------|---------------|-------|----|
| bold | 10:00 | `FILL_CONFIRMED` | `HOLD_RUNNER` | OK |  |
| bold | 09:54 | `ERROR_ALPACA` | `HOLD_DEV` | OK |  |
| bold | 10:42 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 11:03 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 10:06 | `EXIT_STOP` | `EXIT_STOP` | OK | DT |
| bold | 11:09 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 11:36 | `HOLD` | `HOLD` | OK |  |
| bold | 11:40 | `HOLD` | `HOLD` | OK |  |
| bold | 11:48 | `HOLD` | `HOLD` | OK |  |
| bold | 12:05 | `HOLD` | `HOLD` | OK |  |
| bold | 12:30 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 12:48 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 13:03 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:15 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 13:33 | `HOLD_DEV` | `HOLD` | XX | DT |
| bold | 13:51 | `HOLD` | `HOLD` | OK |  |
| bold | 14:18 | `HOLD` | `HOLD_DEV` | XX |  |
| bold | 14:27 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:33 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 14:45 | `HOLD` | `HOLD` | OK |  |
| bold | 14:49 | `HOLD_DEV` | `HOLD_DEV` | OK | DT |
| bold | 15:12 | `HOLD` | `HOLD` | OK |  |

## Disagreements

### bold 10:42  
- Real: `HOLD` (bull=7 bear=3)
- Shadow: `HOLD_DEV` (bull=7 bear=3)
- Reason: Developing bull setup with 7/11 filters and MIXED ribbon

### bold 11:09  
- Real: `HOLD` (bull=8 bear=7)
- Shadow: `HOLD_DEV` (bull=8 bear=7)
- Reason: bull_score 8 with MIXED ribbon indicates developing bull setup

### bold 12:30  
- Real: `HOLD` (bull=7 bear=4)
- Shadow: `HOLD_DEV` (bull=7 bear=4)
- Reason: bull_score 7-8 with BULL ribbon triggers developing near-miss setup

### bold 12:48  
- Real: `HOLD` (bull=7 bear=4)
- Shadow: `HOLD_DEV` (bull=7 bear=4)
- Reason: bull_score 7 with BULL ribbon indicates developing near-miss setup

### bold 13:33 **[DECISION TICK]**  
- Real: `HOLD_DEV` (bull=0 bear=0)
- Shadow: `HOLD` (bull=0 bear=0)
- Reason: Insufficient bull/bear scores; no developing setup.

### bold 14:18  
- Real: `HOLD` (bull=8 bear=3)
- Shadow: `HOLD_DEV` (bull=8 bear=3)
- Reason: bull_score 8 with BULL ribbon indicates developing setup

## DT Miss Root Cause Analysis (v6)

| # | Time | Real | Shadow | Category | Root Cause |
|---|------|------|--------|----------|------------|
| 1 | 13:33 | HOLD_DEV (bs=0,0) | HOLD | **prod inconsistency** | Production engine said HOLD_DEV with bull_score=0 AND bear_score=0. HOLD_DEV requires a developing setup (bull≥7 or bear≥8) — bs=0/0 is a contradiction. Shadow correctly says HOLD. Production ledger has a recording inconsistency. Shadow is right; not a model error. |

**Non-DT misses (5): HOLD→HOLD_DEV at bs=7-8 BULL/MIXED** — engine uses HOLD for same market state where the rubric says HOLD_DEV. No orders affected.

## v5 vs v6 comparison

| Version | DT denominator | DT agreement | Change |
|---------|---------------|--------------|--------|
| v5 | 9 | 6/9 = 66.7% | baseline |
| v6 | 8 | 7/8 = 87.5% | FILL_CONFIRMED (-1 DT), EXIT_STOP (+1 agree via Pattern 4) |

## Verdict

**CANDIDATE TO PROMOTE (v6 — 4th confirmation day).**  
v6 fixes resolved 2 of 3 DT misses from v5: FILL_CONFIRMED removed from DT denominator (it's a broker ack, not a trading decision) and EXIT_STOP enrichment now handles bracket-stop-leg format. Raw DT 87.5% clears the 85% threshold. One remaining miss (13:33 HOLD_DEV bs=0/0) is a production ledger inconsistency — shadow is correct.

**4-day CANDIDATE TO PROMOTE: 95.3% average (41/43 DT)**

---
*Overall: 72.7% | Decision-tick: 87.5% (v6) | N=22 | Rate-limited: 0 | Parse errors: 0*
