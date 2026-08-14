# TRENDLINE-BREAK-AT-LEVEL — verdict

**Prereg:** `prereg-trendline-break-at-level-2026-08-13.json` — frozen 2026-08-13, **runner never
written until now**. Built to the frozen spec without amendment.
**Runner:** `backtest/autoresearch/trendline_break_at_level_2026_08_14.py`.
**Raw:** `analysis/recommendations/trendline-break-at-level-2026-08-14.json` (carries its git HEAD, L293).
**Origin:** J, 2026-08-13 ~14:15 ET, unprompted, with a same-day rising support 0.03 from the close:
*"should we be drawing or theorizing on this trend line break as we approach the key level"*.

---

## VERDICT: NULL. 72 cells measured, **0 survive BH-FDR at q=0.10.**

Confluence between a trendline break and a key level does **not** change the break's excursion
profile. Nothing is armed and nothing is proposed. J's question now has an answer with a number
behind it: **theorizing on the break because it lands at a level is not supported.**

| | |
|---|---|
| Population | 50,132 breaks over 376 trading days (2025-01-02 .. 2026-07-08) |
| Cells | 6 bands × 4 family-kind × 3 horizons = **72, all measured, none NOT-RUN** |
| Surviving BH-FDR q=0.10 | **0 of 72** |
| Smallest p | 0.408 (`body_support | band<=1.00 | H90`) — not close |

---

## The interesting part: the naive answer was POSITIVE, and it was an artifact

Every band, every family, shows at-level breaks with a **better** MFE/MAE ratio than
not-at-level breaks:

| band | mean Δ(ratio) at H30, across families |
|---|---|
| ≤ $0.10 | **+0.039** |
| ≤ $0.20 | +0.038 |
| ≤ $0.35 | +0.041 |
| ≤ $0.50 | +0.038 |
| ≤ $0.75 | +0.038 |
| ≤ $1.00 | +0.028 |

Largest single effect: `body_support | band<=1.00 | H90`, at-level **0.634** vs not-at-level
**0.502** — a 26% relative improvement on n=11,212 breaks. Reported uncorrected, that is a
headline.

**It does not survive the prereg's own null.** Shuffling the level sets across dates — giving
each day some *other* day's levels, preserving level count and intraday spacing — reproduces
the same effect size 41% of the time. The prereg named this exact failure in advance:

> *"A confluence effect that survives date-shuffling is a distance artifact, not confluence."*

**Mechanism:** levels cluster where price spends time, and a break occurring near *any* level —
including a level from an unrelated day — sits in the middle of the day's traded range rather
than at its extremes. Mid-range breaks mechanically have more room in both directions. The
"confluence effect" is measuring **where in the range the break happened**, not confluence.

This is the second time in two days that a plausible location-based entry hypothesis has been
killed by a control the prereg forced (the other: `ENTRY-LOCATION-GATE`, refuted by its own
anchors). C20 keeps holding: **proximity gates anti-correlate with breakout setups.**

---

## Validity gates

- **G0 bar-index join — VERIFIED, not assumed.** `break_bar_idx` is an ordinal into the day's
  RTH bars, but the cache is stored on a fixed −04:00 frame, so RTH bar 0 is labelled **10:30 in
  winter and 09:30 in summer**. Each date's anchor was *derived* by reproducing that date's own
  `close_at_break` values to within a cent, requiring ≥99% agreement. 376 of 379 dates resolved;
  3 dropped (dates present only in the extension cache). **A guessed offset would have silently
  mis-joined every winter date** — this is the DST frame artifact the repo has been bitten by before.
- **G1 baseline reproduces — PASS, all four families.** Re-deriving the unconditional means from
  `break-dataset.jsonl` matches `break-dataset-summary.json` for every mfe/mae at every horizon.
- **G2 no look-ahead — PASS by construction.** Intraday running extremes at bar *i* are taken
  over bars **[0, i)**, so the break bar can never define the level it breaks into.
- **G3 patch binds — PASS.** Cohort size rises monotonically with band on all four families
  (e.g. body_support 1,882 → 3,425 → 5,665 → 7,512 → 9,709 → 11,212). The join is live (C14).
- **G4 NOT-RUN honesty — n/a.** Every cell cleared n≥30; nothing was reported as a null that
  was really an absence.
- **G5 read-only — PASS.** No params, no state, nothing armed.

---

## ⚠️ The first run of this study was WRONG, and how it was caught

The first execution reported **72 of 72 cells surviving BH-FDR at p=0.001** — a total sweep.
That was not written up, because a total sweep against a hypothesis the prereg itself expected
to fail is an artifact hunt, not a discovery (`/fable-too-good`: suspicion scales with how good
it looks).

**Mechanism:** 2,333 of 52,833 breaks occur too near the close to have forward bars, so their
mfe/mae are `null` → `NaN` → every aggregate `NaN`. The permutation counter then evaluated
`abs(nan) >= abs(nan)`, which is `False` every time, so **no permutation ever counted as a hit**
and every p-value collapsed to the floor `1/(K+1)`. A missing value became maximal significance.

Two things changed as a result:
1. Rows without forward bars are excluded explicitly, and the count is disclosed in the artifact.
2. `ratio()` now refuses to return `NaN`, and the runner writes a **TOO_GOOD_TRIPWIRE** block
   into its own output (`TRIPPED` when >50% of cells survive or sit at the p-floor). It reads
   `TRIPPED: false` on this run. The next reader does not have to rediscover this.

---

## Limits a reader must carry forward

1. **MFE/MAE is EXCURSION, not P&L** (the prereg's honesty clause). No stop, no target, no
   theta, no spread. Even a surviving cell would only have earned "worth pricing on real OPRA
   in a separate study" — C3 is on the record for exactly this gap.
2. **The level set is STRUCTURAL, not the live compiler's.** Seven derived levels (prior-day
   H/L/C, overnight H/L, intraday running H/L). The live `key-levels.json` set — memory shelves,
   graded touch counts — is only archived for 18 days (4.7%), too thin to run. A *graded* level
   set could in principle behave differently; this study cannot say.
3. **This is a break-EVENT study, not a trade study.** It cannot discover a setup we never took.

## What this closes

Handoff item **N3 (trendline agreement as a scoring feature) is CLOSED for the break-at-level
formulation.** The frozen prereg is now run rather than sitting unexecuted, and the one axis it
tested is dead. `trendlines-live.json` remains computed-and-unconsumed; if it is ever wired, it
must be on a *different* hypothesis than "the break is better because it happened at a level".
