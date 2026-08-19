# Two "independent" features from the same event are not independent — a quality score counted them twice

**Date:** 2026-08-18 (weekly-options lane)
**Class:** C14-adjacent (dead knob), but the ROOT CAUSE is different — the knob was not dead by
neglect, it was wired to a **self-double-counting input**.

## Symptom

Two things looked unrelated:

1. `MIN_ZONE_CONFLUENCE` / the confluence score measured nothing about outcome (Spearman
   rho = -0.054, p = 0.226 over 513 positions; high-vs-low Mann-Whitney p = 0.627). Read at
   first as "a dead knob."
2. The `structure_hh_hl_lh_ll` zone family produced **zero** attributed signals across 9
   symbols and both timeframes. Looked like dead code.

They are the same defect.

## Root cause, one sentence

`_structure_zones` emits the price of a swing that was BROKEN, and a broken swing price *is* a
swing price — so 100% of its zones duplicate a `swing_high_low` zone price, which (a) loses
every attribution tie-break to the earlier-emitted family, and (b) hands every broken level a
free +1 on a confluence score that counts *distinct families* overlapping a band.

## Evidence

- Structure zones price-identical to a swing zone: QQQ **15/15**, GLD **10/10**, NVDA **17/17**
  (100% in every case).
- Emission order: `swing_high_low` at index 0, `structure_hh_hl_lh_ll` at index 32-39, so
  `min(touched, key=|price - close|)` keeps swing on every exact tie.
- Direct measurement on QQQ: a structure zone scored **confluence = 2** where only **1 distinct
  price** existed in the band.

## Why this is worse than an ordinary dead knob

The spurious +1 is **not randomly distributed**. It attaches precisely to levels that have been
BROKEN — plausibly the *lower*-quality levels, since a broken level is a level that failed. So
the "quality" score was adding a point for a possibly-negative property, on a specific
non-random subset. A dead knob is noise; this was structured, directional corruption that
happened to average out to approximately nothing.

It also means the per-family stratification in any analysis using these labels **conflates the
two families** — "swing_high_low, n=102" silently contains the structure population.

## The rule to encode

**Before a score aggregates multiple features, verify they are actually independent —
specifically, that two features derived from the SAME underlying event are not counted twice.**

1. Any confluence / agreement / vote score must dedupe by the underlying OBSERVATION (here: the
   price level), not by the label of the producer that emitted it.
2. When two producers can emit the same value, that is a design decision requiring an explicit
   answer: are they the same thing (dedupe), or genuinely different (emit distinguishably)?
3. **A component that never wins attribution is a symptom worth chasing** — here it pointed
   straight at the duplication that was corrupting a different metric entirely.

## Suggested guard

- A test asserting no two zone families emit the same price within tolerance without an explicit
  flip-role distinction.
- A `_confluence_count` unit test pinning that N producers reporting ONE price yields
  confluence 1, not N.

**Evidence:** `analysis/deep-research/WEEKLY-EXPIRY-EXPERIMENT-2026-08-18.md` (defect section),
`weekly/lib/zones.py::_structure_zones`, `weekly/lib/trigger.py::_confluence_count`.
