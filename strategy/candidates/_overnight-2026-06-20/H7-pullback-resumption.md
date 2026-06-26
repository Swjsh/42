# H7 — Pullback-Resumption Entry (don't chase fresh extremes)

**Rank:** 7 of 8 · **Score:** 5.5 · **Seam:** J winner archetype / entry-timing · **Status:** PROPOSAL (test, do not ship)

---

## The setup / signal

A **"wait-for-the-retrace"** entry-timing modifier on trend-continuation setups: instead of entering on the breakout/extension bar, require a **shallow pullback into the trend** (1-3 bars retracing toward but holding above VWAP / the prior swing / the ribbon) followed by a resumption bar in the trend direction. Penalize (raise the bar for, or suppress) entries that fire on a **fresh session extreme** with no prior pullback.

## The insight (why it should have edge)

From `J-WEBULL-EDGE` step-3:

> "**He is not a breakout chaser.** Only **2 of 9** entered on a fresh session extreme; most entered on **pullbacks/midrange continuation or reversals** — i.e. waiting for a retrace before joining."

7 of J's 9 top winners were *not* fresh-extreme chases — they were pullback-resumption or midrange-continuation entries. The mechanism: entering on the extension bar buys the worst price (max premium, max adverse-excursion risk if it's the exhaustion top), while entering on the shallow pullback buys a better fill with a tighter, structurally-defined stop and the trend still intact. This is also the *correct generalization* of the 5/01 anchor lesson (`mistakes.md`): J's leg-2 entry at the 13:36 **retest** would have been +194% on a third of the capital vs the +72% anticipation entry — the retrace entry is mathematically superior even when both win.

## EXACT backtest to validate

1. **Feature:** `bars_since_extreme` + `pullback_depth` (retrace % off the local extreme) + `vwap_held_on_pullback` (bool). Look-ahead-free.
2. **Grid:** entry-timing arms — {breakout-bar (baseline), require-pullback (1-3 bars), require-pullback-holding-VWAP} x max-pullback-depth {0.3R,0.5R} x strike/stop poles.
3. **Anchor (OP-16) — load-bearing:** 5/01 is the *literal* case study — the engine should prefer the 13:36 retest leg over the 13:09 anticipation leg. Verify the require-pullback arm **keeps** 4/29//5/01//5/04 (all had retrace structure) and ideally improves the 5/01 entry price. `edge_capture` must hold or rise.
4. **Real-fills:** the win shows up as *better fills* (lower entry premium, tighter stop) → real-fills per-trade expectancy should **rise** even if WR is similar. This is the key metric — report entry-premium delta.
5. **Guards:** L171 truncation (a better entry price changes the truncation math — re-run the cross-check), L172 null-MAX, L167 (this is a timing modifier, not a clock gate — but confirm it doesn't just re-introduce a folklore time bias).
6. **Scorecard:** `analysis/recommendations/h7-pullback-resumption.json` with entry-premium and adverse-excursion deltas vs breakout-bar baseline.

## Kill criteria (reject if ANY)

- Require-pullback arm **misses** more winners than it improves (some trends never pull back — the breakout *is* the entry; measure missed-trade win rate).
- `edge_capture < baseline` (dropped an anchor by waiting for a pullback that didn't come).
- Real-fills per-trade expectancy not improved vs baseline (the better-fill thesis didn't materialize on SPY-now → C22 non-transfer).
- Truncation/null fail.

## Expected edge_capture x feasibility

**edge_capture MED** (better fills on existing winners + fewer exhaustion-top chases; mostly raises the *quality* of trades already taken rather than adding new edge). **feasibility MED** (timing feature, moderate look-ahead care). Ranked #7 because the benefit is incremental (fill quality) and there's a real risk of missing fast trends that don't retrace — a known tension. Worth testing because it operationalizes the 5/01 anchor lesson into a mechanical rule.

## Disclosure (OP-20)

Disclose the trade-off explicitly: require-pullback trades fewer setups but at better prices — net P&L depends on how often SPY-now trends run without retracing. The missed-trade win rate is the load-bearing disclosure.
