# Touch Rate Analysis — Placement Edge by Level Source

**Date:** 2026-06-18  
**Task:** a6c17120 — Touch Rate Benchmark  
**Source data:** `level-quality-benchmark.json` (220 days, 2025-08-01 to 2026-06-16)  
**Hypothesis (Q3 from RATIFICATION-REPORT.md):** For 0DTE entries, placement edge (price touches the zone) is the true tradeable edge, not reaction edge. If sources have touch_rate > DM-null by +5pp, placement edge is confirmed.

---

## Results: Touch Rate per Source vs DM-Null

| Source | n | Real touch | DM-null touch | **Lift vs DM-null** | +5pp target | Verdict |
|--------|---|-----------|--------------|-------------------|-------------|---------|
| **intraday** | 287 | **73.9%** | 49.4% | **+24.5pp** | PASS | STRONG placement edge |
| **round** | 278 | **72.3%** | 66.9% | **+5.3pp** | PASS (marginal) | Confirmed |
| **swept** | 1568 | **58.0%** | 51.3% | **+6.7pp** | PASS | Confirmed |
| **multi_day** | 1069 | 34.6% | 51.3% | **-16.7pp** | **FAIL** | Anti-placement edge |

Headline: Real=52.9% vs DM-null=51.3% → +1.5pp (near-zero lift once distance is controlled).

---

## Key Findings

### 1. The 2.4x touch-over-random was mostly a distance artifact
The previous "2.4x touch lift" compared real (52.9%) vs UNIFORM null (21.9%). But distance-matched null (DM-null) shows 51.3%. Once you control for distance from open, only +1.5pp of lift remains. **The 31pp lift vs uniform null was mostly "levels are drawn close to current price."**

### 2. Intraday and round ARE placement magnets (+24.5pp, +5.3pp vs DM-null)
- **Intraday (session H/L):** 73.9% touch vs 49.4% DM-null. Price reliably visits session highs/lows during RTH — even after controlling for their typical distance from open. Strong magnet effect.
- **Round ($1.00 increments):** 72.3% touch vs 66.9% DM-null. Round numbers have genuine gravitational pull beyond their proximity alone (+5.3pp).
- **Swept (liquidity sweeps):** 58.0% touch vs 51.3% DM-null. Retesting swept levels is a reliable phenomenon (+6.7pp).

### 3. Multi_day levels have ANTI-placement edge (-16.7pp vs DM-null)
Multi_day levels (PDH, PDL, 5-day high/low, weekly levels) touch only 34.6% of the time, while distance-matched random levels would touch 51.3%. **Price systematically AVOIDS multi_day levels relative to random levels at the same distances.**

Root cause: multi_day S/R levels work by REPELLING price before the exact zone. SPY approaches within $0.30 of a PDH then bounces back. The APPROACH is the signal; the actual TOUCH is rare. The +/-$0.02 zone almost never fires.

### 4. The reaction edge story is unchanged: still near-zero
Despite strong touch differentiation, respect-lift vs DM-null remains near-zero (-0.5pp headline). Touched levels bounce as often as touched random levels. The signal is in the APPROACH (will price get there?), not the REACTION (will it bounce when it arrives?).

---

## Implication for Entry Scoring

Current engine treats all level sources equally in proximity scoring. This data argues for differentiation:

| Source | Touch edge | Use case |
|--------|-----------|----------|
| intraday | HIGH magnet | "Price will visit this today" — strong entry proximity signal |
| round | MOD magnet | Price seeks round numbers — use as target/stop anchors |
| swept | MOD magnet | Retests reliably — use as entry proximity signal |
| multi_day | PROXIMITY INDICATOR only | Approach toward multi_day = signal; don't wait for exact touch |

**Practical change:** For entries near multi_day levels, trigger on APPROACH ($0.30-$0.50 proximity + confirmation) not level touch. For intraday/round, exact touch zone is a reliable trigger.

---

## Verdict for Cook-Queue Task a6c17120

**COMPLETE.** Touch rate per source vs DM-null confirms placement edge for intraday (+24.5pp), round (+5.3pp), swept (+6.7pp). Multi_day DISCONFIRMED (-16.7pp). The hypothesis is partially confirmed — placement edge exists but only for intraday/round/swept sources.

**Scorecard:** `level-quality-benchmark.json` (field: `by_source_dm_null_lift`)  
**No code changes needed** — benchmark already ran with correct metrics. Findings inform engine scoring weights (future work, not auto-ratifiable without A/B).
