# Lesson inbox — 2026-07-31: a gate A/B's headline delta was 86% position-sequencing pre-emption, not the gate's own block-set

**Source fire:** filter-5 (ribbon MA-stack) fate lane, 2026-07-31 evening.
**Artifacts:** `analysis/recommendations/prereg-filter5-ribbon-2026-07-31.json` (frozen 17:34 ET, before any run) ·
`analysis/recommendations/filter5-ribbon-2026-07-31.json` / `.md` ·
runner `backtest/tools/filter5_ribbon_fate_2026_07_31.py`.

## Symptom

Deleting FILTER 5 (the ribbon MA-stack entry veto: strict fast>pivot>slow on the 13/20/48 EMA
ribbon at the trigger bar, `backtest/lib/filters.py:1174` bull / `:1463` bear) produced a
**+$738.60** full-history delta over 2025-01-02..2026-07-31 on real OPRA fills walked through
the REAL `exit_manager.plan_exit_actions`. Read naively, that is "the lagging ribbon gate is
costing us $739 — delete it."

That reading is wrong, and the harness only caught it because the pre-reg required the delta to
be DECOMPOSED into added-vs-dropped before being attributed.

## What was actually happening

The arm changed the book two ways:

| component | n | total |
|---|--:|--:|
| **ADDED** — trades filter 5 was genuinely blocking | 21 | **+$103.60** (+$4.93/trade, WR 52.4%, **ex-best −$437.00**) |
| **DROPPED** — CONTROL trades that simply vanish | 8 | −$635.00 (so removing them *adds* +$635.00) |

`+103.60 − (−635.00) = +738.60`. **86% of the headline came from the DROPPED side.**

Those 8 dropped trades were not blocked by anything. They disappeared because an unlocked
earlier entry consumed the one-position-at-a-time slot / escalation lock, so the engine never
reached them. Proof: **6 of 6** distinct dropped days also carry an added trade the same day.
Whether that pre-emption helps or hurts is a coin-flip on the day's ordering — it is not a
property of the gate under test.

The gate's own block-set — the only cohort that IS evidence about the gate — is worth
**~$0/trade and turns NEGATIVE once the single best trade is dropped**.

## Generalizable pattern

**In any engine that holds at most one position at a time (or carries an escalation lock, a
per-setup re-entry lock, or a daily trade cap), loosening ANY entry gate reshuffles the entire
downstream trade sequence.** The resulting A/B delta is the sum of two mechanically different
things:

1. **the admitted cohort** — the trades the gate was blocking. This is the evidence.
2. **the pre-empted cohort** — pre-existing trades that vanish because slot occupancy moved.
   This is sequencing luck and carries no information about the gate.

Reporting only the aggregate delta silently attributes (2) to (1). A gate can look worth
hundreds of dollars while its actual block-set is worthless — or the reverse.

**Rule: for any gate/filter/veto A/B in a slot-constrained engine, report `added_total` and
`dropped_total` SEPARATELY and gate the ship decision on the ADDED cohort's own expectancy.
Cross-check how many dropped days also gained a trade — a high ratio is the pre-emption
signature.**

## Second finding from the same run (worth its own line)

The added cohort's exit mix vs the control book's:

| exit reason | added cohort | control book |
|---|--:|--:|
| ribbon_flip_back | **16 (76.2%)** | 19 (9.9%) |
| premium_stop | 0 (0.0%) | 93 (48.7%) |

Entries admitted against a non-stacked ribbon are closed by the **ribbon-flip EXIT** almost
immediately. The entry veto and the exit rule read the SAME lagging indicator, so filter 5 is
largely **redundant** with `ribbon_flip_back` rather than independently costly — removing the
entry veto alone mostly manufactures round-trips. Any future attempt to loosen ribbon-based
ENTRY gating must move the ribbon-based EXIT in the same change, or it will null the same way.

## Suggested guard

Add the added/dropped decomposition to the shared scorecard helper any future gate A/B uses, so
the split is structurally impossible to omit (this fire's `attribution_block()` in
`backtest/tools/filter5_ribbon_fate_2026_07_31.py` is a working reference implementation).

**Related clusters:** C4 (disclose concentration — ex-best flipped this cohort negative),
C14 (a measured knob whose apparent effect came from somewhere else entirely),
C15 (gates interact multiplicatively — trace session cascades),
C28 (ribbon is a lagging indicator; L243's "the fix was itself too lagging" shape).
