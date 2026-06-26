# Level Quality Ratification Report

**Date:** 2026-06-15  
**PAUL Plan:** trustworthy-levels milestone  
**Source of truth:** `markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md`  
**Status:** ALL PHASES COMPLETE — see verdicts per study below

---

## The Mission (recap)

Make key-level quality **measurable then improvable**. Five phases:

0. Benchmark harness + ledger
1. Null model + parity checks
2. Star-rating and wick-rejection studies
3. Source pruning + pattern detectors + VIX regime
4. Vision-divergence report + near-miss trace spec
5. Level-set shadow A/B harness

---

## Headline Number

| Metric | Value |
|--------|-------|
| Days benchmarked | 219 |
| Baseline respect-lift vs DM-null | **-0.6pp** |
| Verdict | **Levels produce NO conditional reaction edge vs distance-matched null** |

The **distance-matched null (DM-null)** places random levels at the same distances from the open as real levels. A +0pp lift means the auto-generated levels are no better than random at getting price to react. The reaction edge is NOT present in the current generator.

---

## Phase 1 — Benchmark Results

### Respect-Lift by Source (vs DM-Null)

| Source | N levels | DM-lift | Verdict |
|--------|----------|---------|---------|
| multi_day | — | n/a (null cannot tag multi_day) | INCONCLUSIVE |
| intraday (session H/L) | 281 | **-3.1pp** | KILL |
| round ($1.00 nearest) | 494 | **+2.1pp** | KEEP |
| swept (liquidity upgrade) | — | n/a | INCONCLUSIVE |

**Overall DM-lift: -0.6pp.** No source crosses the +3pp "SEPARATES" threshold except round (+2.1pp is below threshold but positive).

---

## Phase 2 — Star Rating and Wick Rejection

### B4 — Star Rating vs Respect (DOES_NOT_SEPARATE)

| Stars | N levels | Touch rate | Respect rate |
|-------|----------|-----------|--------------|
| 1★ | 114 | 34.2% | **28.2%** |
| 2★ | 683 | 26.1% | **27.0%** |
| 3★ | 2,386 | 61.4% | **24.8%** |

Spread: 28.2% - 24.8% = **3.4pp** — below the 5pp threshold. Stars inversely correlate with respect (more stars = lower respect). Root cause: the star formula rewards touch count, which is higher for frequently-tested levels that tend to break more than hold.

**Verdict: DOES_NOT_SEPARATE.** The star formula does not add conditional edge. Known fix: rebuild scoring to use DM-lift as the target, not touch count.

### C2 — Wick Rejection vs Close-Based (FAIL)

| Filter | N events | Next-bar respect |
|--------|---------|-----------------|
| Close-based (close < level) | 939 | 97.6% |
| Wick-only (high > level, close >= level) | 723 | 91.6% |
| Gap | — | **-6.0pp** |

The production close-based filter is 6pp better than wick-only. **Verdict: keep close-based filter, do not add wick-only entries.** (Note: absolute rates are high because the measurement is first-touch-only from a confirmed close below level, not all touches.)

---

## Phase 3 — Source Pruning, Patterns, VIX Regime

### B1/B2/B3 — Source Pruning Verdicts (Analytical)

| Source | DM-lift | Anchor regression | Verdict |
|--------|---------|-----------------|---------|
| intraday | -3.1pp | SAFE (no anchor used intraday) | **KILL** |
| round | +2.1pp | SAFE | **KEEP** |
| multi_day | n/a | RISK (3 winners use multi_day) | **INCONCLUSIVE** |
| swept | n/a | Unknown | **INCONCLUSIVE** |

**KILL candidate: `intraday` H/L.** However, see Phase 5 shadow A/B — the trading backtest contradicts this recommendation.

### L75 — False-Break Bear Trap Detector (TOO BROAD)

- Events: 1,230 across 211/219 days (96.3% of days)
- Fires on 3/3 anchor LOSERS and 3/3 anchor WINNERS
- Root cause: implementation scans ALL bars; spec says "open bar only"
- **Verdict: DRAFT — needs bar_i=0 restriction before production use**

### L59 — Close-Ceiling Distribution Detector (SIGNAL PRESENT)

- Events: 247 across 133/219 days (60.7% of days)
- Fires on 2/3 anchor LOSER days
- Definition: N≥3 consecutive bars with high above level but close below = distribution zone
- **Verdict: DRAFT — add as conviction SIGNAL (not blocker). Pair with other bears signals.**

### VIX-Character Regime Study (SEPARATES, WF MIXED)

| Regime | N levels | DM-lift | WF ratio |
|--------|----------|---------|---------|
| low_spike (VIX<15, falling) | 195 | **+5.6pp** | 9.0 (suspicious) |
| low_trending | 75 | +4.6pp | n/a |
| mid_spike | 1,419 | +1.8pp | 0.022 |
| mid_trending (VIX 15-25, rising) | 1,229 | **-4.1pp** | 0.181 |
| high_spike | 37 | +2.1pp | n/a |
| high_trending | 228 | -1.3pp | -0.029 |

Max regime spread: **9.7pp** (threshold: 3pp) → **SEPARATES**.

WF ratios are mixed — `low_spike` WF=9.0 is suspicious (small N=195, dominated by specific periods). `mid_spike` WF=0.022 (collapsed OOS). These instabilities prevent AUTO_RATIFY.

**Verdict: DRAFT — regime multiplier has real signal (9.7pp spread) but WF ratio instability requires longer OOS window. Revisit after 2026-09 with 6+ months of VIX character data.**

---

## Phase 4 — Live-Path Robustness

### D1/D2 — Vision-vs-Heartbeat Divergence (INSUFFICIENT_DATA)

- Vision observer fired only 3 times (2026-05-19 only)
- N=3 vs minimum 20 required (OP-11)
- 1 paired tick, 1 D1 event, 0 D2 events

**Verdict: FRAMEWORK COMPLETE, DATA INSUFFICIENT.** All D1/D2/multi-hour-context logic is implemented and ready. Rerun when vision-observations.jsonl reaches N≥20 across ≥5 trading days.

**Activation cost: $0/day incremental** (vision observer already uses Haiku; more consistent wiring needed in heartbeat tick loop).

### D3 — Auto-Decision-Trace DRAFT (READY FOR RATIFICATION)

Proposed `near_miss_trace` structured field:
- Trigger: bear≥8 OR bull≥9 with no ENTER action
- Key fields: `primary_blocker`, `secondary_blockers`, `confidence_tier`, `is_first_near_miss_today`
- Logging target: existing decisions.jsonl row (no new file)
- LLM calls: **ZERO** (pure dict computation from existing filter_state)
- Incremental cost: **$0/day**

Near-miss frequency (current data): ~8/day safe + aggressive combined.

**Verdict: READY FOR RATIFICATION.** Spec is complete. Requires J sign-off before heartbeat.md edit (Rule 9).

---

## Phase 5 — Level-Set Shadow A/B

### Shadow A/B: Intraday H/L Prune (AUTO_RATIFY=False)

Candidate: `exclude_intraday_hl=True` in `_detect_from_history()`

| Metric | Baseline | Candidate | Delta |
|--------|----------|-----------|-------|
| Anchor edge_capture | $664 | $664 | 0 |
| IS n_trades | 32 | 36 | +4 (more trades) |
| IS WR | 18.8% | 16.7% | **-2.1pp** |
| OOS n_trades | 16 | 15 | -1 |
| OOS WR | 37.5% | 40.0% | +2.5pp |
| WF ratio | — | -0.3 | negative (OOS worse on IS metric) |

OP-11 gates:
- dominates: FALSE (candidate wins wl_ratio + max_drawdown but loses WR + expectancy)
- thresholds_4_of_4: FALSE (2/4 — n>=20 PASS, WR<45% FAIL, wl_ratio>=1.5 PASS, expectancy>0 FAIL)
- sub_window_stable: FALSE (WF=-0.3)
- evidence_n >= 20: TRUE (n=51)
- anchor_no_regression: TRUE

**AUTO_RATIFY: FALSE.**

### Critical Tension — Benchmark vs Trading Backtest

| Study | Finding |
|-------|---------|
| Benchmark (DM-null) | Intraday H/L: DM-lift=-3.1pp → KILL |
| Trading backtest (Shadow A/B) | Removing intraday H/L → +4 more trades, -2.1pp WR → KEEP |

These are NOT contradictory. They measure different things:
- **Benchmark** measures: does price REACT to these levels (bounce away from them)?
- **Trading backtest** measures: does being NEAR these levels help the engine pick better entries?

The intraday session H/L have low reaction edge (price doesn't bounce from them reliably). But the engine uses proximity to intraday H/L as an additional filter that improves entry quality. Removing them makes the engine enter more freely (less filtering) with worse per-trade WR.

**Verdict: HOLD — do not prune intraday source without further investigation.** The analytical KILL verdict is overridden by the trading backtest result. Further work needed: identify which specific trades change when intraday levels are removed (are those trades better or worse in isolation?).

---

## Known-Broken Section

Issues found during this audit that are blocked or unresolved:

1. **DM-null cannot tag multi_day/swept sources** — random levels get tagged as `intraday` or `round` because `multi_day`/`swept` identification requires matching against real level sets. DM-lift is UNKNOWN for these sources. Fix: separate DM-null generation per source type.

2. **Star formula inversely correlated with respect** — stars should predict respect, but 3★ levels respect LESS than 1★. Fix: rebuild star scoring using DM-lift as target, not touch count.

3. **L75 implementation too broad** — scans all bars, not just open bar (bar_i=0). Fires on 96.3% of days (effectively always-on). Fix: restrict to bar_i=0 + ★★★ Carry level only.

4. **Vision observer has 4 observations total** — systematic gaps in coverage mean D1/D2 analysis framework exists but has no data. Fix: wire `chart_vision_observer` to fire every heartbeat tick and persist to `vision-observations.jsonl`.

5. **VIX WF ratios unstable** — `low_spike` WF=9.0 (suspicious), `mid_spike` WF=0.022 (collapsed OOS). Both extreme. Fix: longer IS/OOS window (6+ months data).

6. **Trading backtest WR below 45% threshold** — with V15_J_EDGE_OVERRIDES and real-fills, both baseline and candidate IS WR < 45% (18.8%/16.7%). This is the Config 1 (strike_offset_bear=0, min_triggers_bear=1) which maximizes coverage at the cost of WR. Production uses stricter filters. The level quality A/B runs at "fire everything" to measure level quality signal, not trading quality signal.

---

## Summary Table — All Studies

| Study | Status | Verdict | Action |
|-------|--------|---------|--------|
| B1 — intraday source | COMPLETE | HOLD (shadow A/B contradicts KILL) | Deeper trade-level analysis |
| B2 — round source | COMPLETE | KEEP | No action needed |
| B3 — multi_day source | COMPLETE | INCONCLUSIVE | Block on DM-null tag limitation |
| B4 — star vs respect | COMPLETE | DOES_NOT_SEPARATE | Rebuild star formula |
| B7 — swept source | COMPLETE | INCONCLUSIVE | Same DM-null limitation |
| C2 — wick rejection | COMPLETE | FAIL — close-based better | No action (production already correct) |
| L75 — false-break | COMPLETE | CANNOT_RATIFY as entry blocker — blocks 2/3 anchor winners | Demote to logging-only signal |
| L59 — close ceiling | DRAFT | Signal present, 60.7% days | Add as conviction signal |
| VIX regime | DRAFT | SEPARATES (9.7pp) but WF mixed | Revisit 2026-09 |
| D1/D2 vision | DRAFT | INSUFFICIENT_DATA | Wire vision observer |
| D3 near-miss trace | DRAFT | READY FOR RATIFICATION | J sign-off needed |
| Shadow A/B (intraday) | COMPLETE | AUTO_RATIFY=FALSE | HOLD |

---

## Phase 3 Addendum — L75 v2 Final Verdict (2026-06-17)

**`pattern_detectors_v2_study.py` results (bar_i=0 only restriction):**

| Metric | v1 (all bars) | v2 (bar_i=0 only) |
|--------|---------------|-------------------|
| Total events | 1,230 | 109 |
| Days w/ event | 211 (96.3%) | 60 (27.4%) |
| Anchor losers covered | 3/3 | 2/3 |
| Would block J entry on loser days | — | 1/3 (5/05 09:35) |
| Would block J entry on WINNER days | — | **2/3 (5/01 +$470, 5/04 +$730)** |

**v2 conclusion: CANNOT_RATIFY as entry blocker.**
- Frequency OK (27.4% < 30%) ✓
- Covers 2/3 loser days ✓  
- BUT blocks 2/3 winner days: 5/01 (+$470) and 5/04 (+$730) ✗
- Net anchor impact: saves -$260 (5/05) – costs $1,200 (5/01+5/04) = **-$940 net**

**Root cause:** The false-break at bar_i=0 fires on BOTH winners AND losers. On 5/01 and 5/04 (anchor winners), the open bar dipped below key levels (721.00, 719.90) then recovered — identical L75 pattern. J correctly took bearish setups 5 minutes later (09:35) and profited. L75 would have blocked those entries during the 30-min suspend. The pattern does NOT discriminate good days from bad.

**Disposition:** Demote L75 from ENTRY_BLOCKER to LOGGING_ONLY. Log L75 events to decisions.jsonl as `open_bar_false_break: true` for post-trade analysis. Do NOT use as an entry filter. A second discriminating feature would be required before re-testing as a blocker (e.g., next-bar close direction, VIX spike at 09:30, or specific level tier).

---

## Open Questions (from handoff)

**Q2 — Is "respect once touched" the right target for 0DTE?**

The benchmark shows -0.6pp overall DM-lift — levels are not reliably better than random at generating bounces. But the engine fires profitable trades near these levels. This suggests:

> The **placement edge** (price reaching these zones) may be the real, tradeable edge. The strategy leans into "price will reach this zone" (the entry trigger proximity), not "price will bounce here" (the reaction measurement).

If this framing is correct, the improvement direction is NOT "find levels with higher reaction edge" but "find levels that price reliably tests during 0DTE hours." The benchmark metric (respect-lift vs DM-null) may be the wrong primary metric entirely.

**Recommendation for J:** consider running the benchmark with TOUCH RATE (not respect rate) as the primary metric. If certain sources have higher touch rates than DM-null, that IS the placement edge we want.

**Q5 — Time-of-day stratification:**

4/29 and 5/04 J winner trades were 09:35-10:30 ET (morning). The benchmark does not yet stratify by hour. Hypothesis: morning levels (established pre-session) have higher touch + respect rate than midday levels (established intraday). Worth measuring.

---

## What Moved

| Before this PAUL plan | After |
|-----------------------|-------|
| No systematic level quality measurement | 219-day benchmark with DM-null baseline |
| No null model | Distance-matched null (DM-null) = 25.68% baseline |
| No per-source lift numbers | All 4 sources measured; intraday=-3.1pp, round=+2.1pp |
| Star formula assumed predictive | Proven NOT to separate (inversely correlated) |
| Wick vs close filter = unknown | Close-based 6pp better than wick-only |
| L75/L59 patterns = text-only doc | Both implemented as detectors; L75 too broad as written |
| VIX regime = unknown | 9.7pp spread found; low_spike best, mid_trending worst |
| Intraday source = unclear | Kill verdict from benchmark; Hold verdict from shadow A/B |
| Shadow A/B level harness = non-existent | Complete harness in level_shadow_ab.py; flag in levels.py |
| Near-miss trace = free-text | Structured spec ready for ratification |

---

## Next Steps (for J weekend review)

1. **Ratify D3 (near_miss_trace)**: Low risk, $0 cost, $0 LLM calls. Add `near_miss_trace` field to decisions.jsonl on near-miss ticks. Enables machine-readable near-miss clustering.

2. **Wire vision observer**: Run `chart_vision_observer` on every heartbeat tick. Goal: N≥20 obs across ≥5 days. Then re-run `vision_divergence_report.py` to get real D1/D2 signal.

3. **Consider touch-rate as primary metric**: Reframe "level quality" as "will price reach this zone?" rather than "will price bounce from it?" Matches 0DTE entry paradigm.

4. **Intraday source deeper audit**: Before pruning, identify the specific trades that change when intraday H/L is removed. Do those trades go up or down in quality? This resolves the benchmark-vs-trading tension.

5. **L75 production implementation**: Restrict to `bar_i=0` (first RTH bar only) + ★★★ Carry levels. Then re-run the detector study to see if it separates losers from winners cleanly.
