---
name: fable-too-good
description: The extraordinary-result protocol — when a backtest/metric/fix looks GREAT, hunt the artifact before celebrating. Invoke on any result that beats expectations (huge expectancy, perfect parity, sudden green, "found the edge"), before reporting it to J, arming anything, or building on it. Trigger phrases; "too good to be true", "sanity check this result", "is this real". The gap this patches: smaller models scale confidence WITH result quality; Fable scales SUSPICION with it — extraordinary results are usually bugs, leaks, or accounting illusions, and this codebase has produced all three.
---

# FABLE-TOO-GOOD — surprise is evidence of error

> Prior: in this project's history, results that looked extraordinary were an accounting artifact (+$4,576 "profitable small-lot" → actually −$4,420), a look-ahead/staleness leak (E6's +21.8pp train separation → inverted on holdout), a harness bug (exit A/Bs modeled WITHOUT the chandelier production trades with), or multiple-comparisons noise (55,595 of 57,600 grid cells "train-positive"). The one result that survived every hunt (bollinger) became MORE trusted because the hunts were run and documented. Suspicion is how good results earn belief.

## The hunt (run ALL that apply, report which you ran)

**H1 — The leak hunt (information from the future or from the answer):** does any input see the outcome bar, the same-session future, or the label? Check: bar boundaries (completed bars only, entry NEXT bar), joins by timestamp (a naive SPY↔VIX join gave winter look-ahead via offset mismatch), features computed over windows that include the trade, train/test contamination (was the holdout touched during ANY prior iteration? burned = burned), selection applied before the split.

**H2 — The accounting audit:** what is ONE observation? Recount at a different unit (per-episode vs per-fill; per-day vs per-trade) — does the sign survive? Who's in the denominator (winner-date-biased samples)? Pooled cells: does the headline survive full-axis intersection (the "+$3.7/tr at-level" pooled all times; the 3-axis midday cell was −$29.9)?

**H3 — The multiplicity check:** how many variants/cells/features were tried before this winner? If >~5, the winner must survive BH-FDR across ALL of them and a never-touched holdout. "It got better as I iterated" is the signature of fitting noise.

**H4 — The harness parity check:** does the measuring tool do what production does? Run ONE case through both and diff (strike selection, exit shape incl. trails, fill model, session frame). A harness that drops one key silently invalidates every verdict it produced.

**H5 — The baseline/null sanity:** random-entry null with the same exits; opposite-direction null on the same entries; and the dumb-baseline ("just buy every bar") — your edge must beat all three by more than noise. If the exit ladder alone is profitable on random entries, you found convexity, not signal.

**H6 — The perfect-number smell:** exact 100%s, byte-identical parities, zero-error runs on first try — verify the check actually RAN and can FAIL (run it once with a deliberately broken input; if it still passes, your check is vacuous — the G14 guard "passed" for weeks while re-implementing the bug it guarded).

**H7 — The scale check:** does the result imply something absurd at scale ($202/trade on 539 trades = +$109K on a $2K account → the number is a frictionless-convexity artifact; useful for RANKING, meaningless as dollars)? State what the number can and cannot claim.

## Verdict language (mandatory)
- Survived all applicable hunts → "REAL, pending fresh-data confirm" + list the hunts run.
- Failed any hunt → name the artifact class (leak / accounting / multiplicity / harness / null-dominated / vacuous-check) and REPORT THE KILL — a named artifact prevents the same illusion twice.
- Couldn't run a needed hunt → the result is UNVERIFIED; say so; do not build on it.

## Tells you're failing this skill
☐ You feel excited and are reaching for the report button. ☐ The result improved with each variant you tried. ☐ You haven't asked what one observation is. ☐ Your parity/verification check has never been seen failing. ☐ You're annotating caveats in fine print instead of the headline.
