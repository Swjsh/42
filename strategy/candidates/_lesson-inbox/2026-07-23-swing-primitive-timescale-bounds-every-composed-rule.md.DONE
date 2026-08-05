# Lesson candidate: a shared primitive's timescale silently bounds EVERY rule composed on it

> Queued by conductor (AFTERHOURS) 2026-07-23 ~16:50 ET, from ENGULFING-AT-STRUCTURE-TRIGGER
> (`automation/overnight/queue.md`). lesson-author picks up at next wake fire.

## Symptom

Built `engulfing_at_swing_shelf` (`backtest/lib/patterns/registry.py`, commit `31c5089e`) to
close the vocabulary gap J named live on two mirror-symmetric days (2026-07-21 bullish,
2026-07-23 bearish -- an engulfing candle reacting at a fresh 2-touch intraday double-top/
bottom shelf). The C27 frequency prescreen (`backtest/tools/pattern_prescreen.py`) came back
CLEAN: TESTABLE full-history (28.9% days fired, 0.42 fires/day) AND stable in the recent-90d
window (no drift flag) -- a genuinely good-looking result on the aggregate metric. Ran the
targeted sanity-anchor check the queue item itself demanded (does the shipped predicate fire
on the EXACT two bars J called live?) anyway, per OP-33 / `/fable-too-good` discipline ("a
clean-looking result gets suspicion scaled to how good it looks, not less scrutiny"). **It
failed both anchors** -- neither 07-21 11:05 nor 07-23 10:40 fires under the shipped rule.

## Root cause

`engulfing_at_swing_shelf` composes over `ctx.structure.labeled_swings` (via the existing
`flat_side` predicate) -- the SAME shared swing-pivot primitive that
`double_top_bottom_at_level`, `monotone_swings`, `triangle_ascending/descending`, and
`rectangle_range_break` all already depend on (`backtest/lib/patterns/predicates.py`, wrapping
`crypto/lib/market_structure.py`'s HH/HL/LH/LL labeler). That labeler's pivot-confirmation
timescale is tuned for genuine trend-structure reversals, not tight/fast intraday
double-tops-or-bottoms that resolve within 2-3 five-minute bars and a few cents of price.
Direct evidence: at 07-21 11:05, the real touch cluster (10:40 L745.77 / 11:00 L745.83 /
11:05 L745.85, ~$0.08 apart, 5 min apart -- named separately in the same day's
RSI-EXTENSION-BLOCK-ELITE-BULL item) never registers as 2+ DISTINCT swing-low pivots; the
labeler only emits the 10:40 touch, then reads 11:00/11:05 as continuation (higher lows), not
new reversal points, so `flat_side` sees only ONE pivot and returns `None`. Same shape at
07-23 10:40 (740.505/740.585, 8c/5min apart -- last confirmed swing high by then is a stale
09:40 print). **The C27 prescreen's clean aggregate number never surfaces this** -- it measures
"does this rule fire selectively across history," which is a genuinely different question from
"does this rule fire on the SPECIFIC mechanism it was built to capture." A rule can be
frequency-clean and still be capturing a DIFFERENT (adjacent, coincidentally similarly-shaped)
population than the one that motivated building it.

## Fix

No code fix this fire -- `engulfing_at_swing_shelf` ships as-is (it's a real, tested, stable
grammar addition on its own terms, just not proof of THIS mechanism). The refined next step
(documented in the queue item, not yet built): a genuinely NEW primitive -- a rolling-K-bar
local-extreme-CLUSTER check (last K closes/highs/lows within $X of each other, no formal
swing-confirmation lag) -- structurally different from the pivot-labeling family, needed to
ever catch tight/fast double-tops-or-bottoms. That primitive must be re-run through the SAME
2-anchor falsification check BEFORE any frozen pre-reg grid or real-fills replay is built on
top of it (doing the expensive replay on an unverified primitive would repeat this exact
mistake one layer deeper).

## Encoded in

Not yet graduated to code (this is a methodology lesson about validation ORDER, not a data
bug a guard test can catch mechanically -- lesson-author's call on whether a generic reminder
in `PATTERN-GRAMMAR.md` sec 2/3 ("prescreen-clean is necessary, not sufficient -- always
falsify against the named live exhibit before composing further") suffices, or whether this
belongs in the C27 class (LESSONS-LEARNED.md) as a new sub-lesson under a swing-detection-
family root theme.

## L## (optional)

None suggested -- lesson-author greps current max and assigns next (last seen: L249 in
CLAUDE.md's OP-25 index as of this fire).
