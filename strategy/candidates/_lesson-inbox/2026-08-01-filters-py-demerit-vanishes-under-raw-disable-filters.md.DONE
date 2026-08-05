# LESSON CANDIDATE: a demerit counter gated on `if N in blockers` silently vanishes when a study disables filter N upstream instead of letting it fire-then-get-waived

**Date:** 2026-08-01 (WS4, PAIRED-RIBBON-AB-2026-08-01 study — prereg frozen 12:43 ET,
committed `e5e323f2`; runner `4814e6bb`; verdict NULL `96ae89bb`; STATUS graveyard entry
`e9f73811`).

**Symptom:** WS4's primary mechanism (plain `disable_filters=[5]`, deleting the ribbon
MA-stack veto outright for level-anchored setups) tripped `filters.py`'s HARD INVARIANT on
a trendline-only ADDED entry (2026-05-19 14:20, internal tag "P737") — a trendline-only
setup should never be reachable through this study's level-anchored-only bypass path.
Diagnosing WHY, before applying the pre-registered fallback, surfaced a real (verdict-
unaffecting) mechanism gap: `filters.py:1653-1664` only increments
`trendline_chop_demerit` inside `if 5 in blockers: blockers.remove(5); ...` (and
identically for filters 8/9). A raw `disable_filters=[5]` call prevents filter 5 from ever
entering `blockers` in the first place — so for a trendline-only setup, that whole `if 5 in
blockers` branch is FALSE, `trendline_chop_demerit` silently stays 0, and the setup is
scored as if it passed filter 5 cleanly, carrying NONE of the demerit bookkeeping
production's real bypass path would have charged it.

**Root cause:** the demerit counter and the bypass mechanism are coupled through the SAME
state check (`5 in blockers`), but "delete filter 5 from evaluation entirely" and "filter 5
fired, then got waived by the trendline-only bypass" are NOT equivalent code paths even
though both end with "filter 5 didn't block this trade." A raw `disable_filters=[N]` knob
— the standard, obvious way a backtest/study harness simulates "what if filter N didn't
block this" — silently diverges from production's real waiver semantics whenever a
downstream side effect (a demerit, a counter, a flag read elsewhere) is conditioned on the
SAME "filter N was present in blockers" test that the raw knob also short-circuits.

**Why it matters / generalizable pattern:** sibling to L248 (a disclosed harness-baseline
knob that omits a gate unconditional in production is not the production number) but
inverted — there a study's baseline OMITTED a gate production always applies; here a
study's raw bypass knob OMITTED a side effect (a demerit) production's real bypass DOES
apply. Same family, opposite direction: **any knob that "turns off" a check must be
checked for side effects gated on the SAME state the knob short-circuits, not just the
check's own pass/fail outcome.** Worth a defensive sweep anywhere `filters.py` or a similar
scored-blockers module threads demerits/counters through a condition also reachable via a
raw disable/override flag.

**Caught how — and why WS4's verdict stands untouched:** the invariant trip forced the
pre-registered fallback (`run_arm_scoped`, a wrapper that runs production's real
`evaluate_bearish_setup`/`evaluate_bullish_setup` FIRST — trendline-only demerit intact —
and only re-evaluates with `disable_filters=[5]` when the result's blockers are EXACTLY
`{5}` and the setup is level-anchored). The SAME trade then reappeared under that
production-semantics-first wrapper, proving the admitter was a sequencing KNOCK-ON (an
earlier level-anchored unlock changes the day's position-slot state, making a
production-path entry reachable that CONTROL had pre-empted) — not a gate-semantics leak.
Disclosed explicitly in the study's own output JSON (`"prereg_deviation"` field, citing
`filters.py:1654-1657` by name) and in `analysis/recommendations/paired-ribbon-2026-08-01.md`
as "a crack in the 07-31 ARM_A==ARM_B narrative, verdict unaffected." WS4's NULL verdict
does not depend on this finding either way.

**Fix / suggested guard (not yet built):** a `vary-and-assert` guard (C14 doctrine) —
construct one trendline-only setup that fires filter 5 under production evaluation, then
assert `trendline_chop_demerit` (or its nearest downstream visible effect) is IDENTICAL
whether reached via production's real bypass path or via `disable_filters=[5]` on the same
bar. Would have caught this before a live study needed to trip a hard invariant to surface
it. No urgency to build ahead of the next study that needs `disable_filters` on a
demerit-bearing filter — flagging the pattern is the immediate value.

**Encoded in:** not yet — first occurrence, low-severity (didn't change any verdict).
File/line citations: `backtest/lib/filters.py:1653-1664` (the `trendline_chop_demerit`
block); discovered via `backtest/tools/paired_ribbon_ab_2026_08_01.py:16-30` (AS-BUILT NOTE
docstring) and its output JSON; human-readable disclosure in
`analysis/recommendations/paired-ribbon-2026-08-01.md`. **Related:** C14 (dead/translated-
but-unapplied knobs), L248 (inverse case, harness baseline omitting a production-unconditional
gate).
