# A 2-symbol sample manufactured a clean mechanism that 9 symbols destroyed

**Date:** 2026-08-18 (weekly-options lane night run)
**Class:** C4 (disclose concentration / small-N) in a NEW costume — not concentration in
*trades*, but concentration in *symbols* while characterizing what a signal IS.

## Symptom

After the weekly lane's v1 signal failed its null gate, the diagnosis ranked "the trigger
detects VOLATILITY, not DIRECTION" as the leading explanation. Tested on the two pilot symbols
(GLD + QQQ), the result looked decisive and mechanistically clean:

- absolute forward-move lift vs baseline: **+24.4% / +17.9% / +24.0%** at 1/3/5 days
- direction hit rate: **48.5% / 49.3% / 48.8%** (pure coin flip)

That is a textbook "volatility detector wearing a directional costume." It was written up as
the finding, with a follow-on implication (the signal needs a NON-directional structure —
straddles — which the lane does not currently support and would have to be built).

## What it actually was

Re-run on **9 symbols** (GLD, QQQ, IWM, XOM, CVX, SPY, NVDA, AAPL, TSLA), the effect vanished:

- pooled abs-move lift: **+5.2% / −2.4% / −0.9%**
- symbols with p<0.05 on magnitude: **1–2 of 9** (roughly what chance predicts)
- symbols with p<0.05 on direction: **0 of 9**
- per-symbol at 3d: GLD **+33.5%**, then IWM −4.9%, SPY −6.6%, TSLA −19.9%, NVDA −27.6%, and
  QQQ/XOM/CVX/AAPL all within ±2.3% of baseline

**The entire "mechanism" was GLD — one idiosyncratic name — dominating a two-symbol mean.**
(GLD's own effect survives Bonferroni across the nine, 0.0012 × 9 = 0.011, so it is plausibly
real *for GLD*. One name is not a property of a trigger.)

## Root cause, one sentence

When characterizing what a signal *is* (as opposed to whether it *pays*), a 2-symbol sample has
no power to separate a property of the TRIGGER from a property of one UNDERLYING, and averaging
two symbols lets a single idiosyncratic name carry the whole result.

## Why this class is more dangerous than a normal small-N error

A small-N *performance* number is obviously suspect and gets discounted automatically. A
small-N *mechanistic characterization* does the opposite: it produces a plausible causal story
("it detects volatility, not direction") that then becomes the premise for the NEXT build. Here
it would have sent the following session building straddle machinery to express an edge that
does not exist. The wrong conclusion was more expensive than the wrong number would have been.

## The rule to encode

**Before characterizing what a signal IS, widen the symbol sample and report the per-symbol
spread, not just the pooled mean.** Specifically:

1. Any claim of the form "this signal detects X" requires ≥5 symbols, and must report how many
   of them individually clear significance — not only the pooled statistic.
2. If the effect is carried by fewer than half the symbols, it is a property of those names,
   and must be stated that way ("GLD shows X") rather than as a property of the method.
3. Pooled means across a handful of symbols are reported WITH the per-symbol table beside them,
   never alone.

## Suggested guard

Extend whatever character/attribution analysis the research tools do with an assertion that
refuses to emit a pooled "the signal detects X" verdict when `n_symbols < 5`, or when the
fraction of individually-significant symbols is below a stated floor — mirroring how
`research_guards.py` already refuses other under-powered claims.

**Evidence:** `analysis/deep-research/WEEKLY-EXPIRY-EXPERIMENT-2026-08-18.md` (final
characterization section), `analysis/weekly-lane/signal-character-test.json`,
`backtest/tools/weekly_signal_character_test.py`. Commits `cac7f500`, `9a50ba5e`.
