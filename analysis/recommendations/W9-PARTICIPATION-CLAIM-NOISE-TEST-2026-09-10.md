# W9 — Participation-decline claim: adversarial noise test

**Fired:** 2026-09-10 23:19:25 Thursday EDT (`python setup/scripts/et_clock.py`). Goal:
`automation/state/goals/GOAL-WHY-THIS-WEEK-2026-09-10.md` item W9. Measurement only —
no trading-path file touched (`setup/hooks/doctrine.py` `FROZEN_TRADING_PATH` checked;
this file is not on it).

## Claim under test
> "Participation is down 34%: 4.30 waves/day in August (the engine's best month, +$3,564)
> vs 2.83 waves/day in the frozen window (2026-09-01 onward). A right-tail engine starved
> of at-bats cannot express its edge." — labelled PROVISIONAL, n=6 frozen-window days.

## VERDICT: **NOT DISTINGUISHABLE FROM NOISE.** Strike the point estimate as established;
**W5 RANK 1 / W7 must be re-justified without treating "-34% participation" as a fact.**

---

## Method
- Source: `analysis/trades-enriched.jsonl` filtered to `attribution == "engine"` (419 rows).
  `journal/trades.csv` NOT used (goal's hard constraint — it spans the pre-engine era).
- Wave-dedup rule (stated per task instructions): group same-`date` legs into 10-minute
  buckets on `entry_ts_et`; one bucket = one market event = one wave, regardless of how many
  arms/legs fired on it. This collapses 419 legs → **168 waves**.
- Trading-day calendar: NYSE schedule via `pandas_market_calendars` (`backtest/.venv`), not
  "days with a fill" — this is the artifact check the task asked for, see below.

## 1. Waves/day across the full engine era
Engine era = 2026-06-26 → 2026-09-10 = **53 NYSE trading days**, 168 waves.

- Full-era waves/day, correct denominator (all 53 trading days): **3.170/day**
- Full-era waves/day, denominator = only the 47 days that had ≥1 fill: 3.574/day
- These two already diverge by ~13% — using "days with fills" as the denominator
  systematically **inflates** the reported rate, and it inflates MORE for windows with more
  zero-fill days.

## 2. THE ARTIFACT CHECK (confirmed real, but it cuts the WRONG way to save the claim)
Zero-fill trading days in the era: `2026-07-10, 2026-07-14, 2026-07-24, 2026-08-31,
2026-09-04, 2026-09-09` (6 total, confirmed by direct enumeration against the NYSE calendar).

- August: 21 NYSE trading days, only **1** had zero fills (08-31).
- Frozen window (09-01 → 09-10): 7 NYSE trading days, **2** had zero fills (09-04, 09-09).
- The original "n=6 frozen days" figure could not be exactly reproduced from any denominator
  I could construct (calendar days-with-fills = 5, calendar all-days = 7, 09-02→09-10 = 6 but
  gives 2.33 not 2.83). **The provisional number is not reproducible from the underlying
  ledger with a stated, consistent rule — that alone is grounds to not treat it as
  established.**
- Directionally: dropping the two frozen zero-fill days from the denominator (as a
  fills-only-day rule would) makes frozen's rate **look better** (16 waves / 5 fill-days =
  3.20/day), not worse. So the "zero-fill days silently excluded" failure mode the task asked
  me to check for does **not** explain away the decline — if anything, correcting for it
  (using the full 7-day calendar) makes the reported gap on the frozen side **larger**, not an
  artifact that inflates the decline. The artifact is real (the two windows were being
  measured with inconsistent, unstated denominator rules) but it is not what kills this claim.

## 3. Proper interval on the Aug-vs-frozen difference
Using the full trading-day calendar (August n=21, Frozen n=7):

- August: 83 waves / 21 days = **3.952 waves/day**
- Frozen: 16 waves / 7 days = **2.286 waves/day**
- Point estimate of decline: 1.667 waves/day (42% relative, not quite the claimed 34%/4.30
  because the original Aug figure (4.30) was itself computed off the wrong, fills-only
  denominator)
- **Bootstrap (20,000 resamples, day-level, iid resampling within each window): 95% CI on
  (Aug − Frozen) = [−0.190, +3.476].** The interval **includes zero**. At the 95% level this
  difference is **not statistically distinguishable from noise**, driven entirely by n=7 on
  the frozen side (exactly the "wide interval" the task predicted for small n).

## 4. Is a decline this size unremarkable given the engine's own history?
- **Monthly waves/day, whole era:** Jun 3.333 (n=3, too short to weight) · **Jul 2.682**
  (n=22) · **Aug 3.952** (n=21) · Sep-partial 2.286 (n=7).
  **July was already nearly as low as the frozen window (2.68 vs 2.29) with nothing broken
  and no participation narrative ever raised about it.** August, not July, is the outlier
  month on the high side — using August as the baseline instead of the whole-era mean is
  itself a form of cherry-picking the best comparison point.
- **Rolling 10-trading-day waves/day across the whole era:** min 2.10, max 5.10, mean 3.25,
  sd 0.96. **Rolling 20-day:** min 2.30, max 4.25, mean 3.39, sd 0.60. The era routinely
  swings by a factor of ~2x with no known cause — a 3.95→2.29 move sits inside that native
  range, not outside it.
- **Direct base-rate test on a matched window size:** of 48 rolling 6-trading-day windows
  spanning the whole era, **11 (22.9%) have a waves/day rate at or below the frozen window's
  2.286** — i.e. a window this quiet happens roughly **1 in 4-5 times**, not as a rare event.
  Symmetrically, 16 of 48 (33.3%) match or beat August's 3.95 rate. Both tails of this "swing"
  are common; the claim treats one ordinary tail as anomalous.

## 5. Enter-verdicts vs fills (partial — data does not cover the full era)
`automation/state/fill-funnel-*.json` per-day funnel snapshots exist only sparsely before
2026-08-24 (`07-01, 07-22, 08-06` sampled dates only) and densely from `08-24` onward. **A
full-era enters-vs-fills decomposition is not possible with what's on disk** — flagging this
rather than silently building the comparison on a truncated population.

Using the only clean comparable stretch (08-25→08-31 "August tail" vs 09-01→09-10 "frozen",
both daily-covered):
- `core:safe` ENTER/day: 13.6 (Aug tail) → 9.6 (frozen) — **down**
- `core:bold` ENTER/day: 10.4 (Aug tail) → 13.1 (frozen) — **up**
- Combined filled/day: 2.0 (Aug tail) → 2.6 (frozen) — **up**

This is not a consistent signal in either direction across the two core accounts, on a
5-vs-7-day sample. It does **not** support a clean "enters are flat, only fills declined"
refusal story, nor a clean "enters declined too" market-conditions story. **Underpowered —
say so, don't force a read.**

---

## Decomposition (per task item 4) — conclusion
Given the CI includes zero and the historical base-rate test shows this magnitude of swing
recurs ~1-in-4 windows, there is **no established decline to decompose**. Attempting to
attribute "why" a statistically-unconfirmed effect happened (fewer signals vs more refusals
vs an arm going quiet vs measurement artifact) would be reasoning from noise. The one
artifact genuinely found — inconsistent day-count denominators between the two windows being
compared — is recorded above (§2) as a real methodology defect in how the original number was
built, independent of whether the underlying decline is real.

## Consequence for the rest of the goal
- **Strike** "-34% participation, Aug 4.30 → frozen 2.83 waves/day" as an established number.
  Replace with, if cited at all: *"waves/day may have declined from ~3.95 (Aug) to ~2.29
  (frozen 09-01→09-10); the 95% CI on that difference includes zero and a swing this size
  recurs in roughly 1 of every 4-5 six-day windows across the engine's history (e.g. July's
  whole-month rate, 2.68, was nearly as low) — UNCONFIRMED, likely ordinary variance."**
- **W5 RANK 1 / W7 (the NOT_FLAT counterfactual)** should be re-justified on its own
  procedural merits — measuring what the one-position cap costs is a reasonable thing to
  measure regardless of whether participation actually declined — but it must **not** carry
  forward "the participation decline is real and needs explaining" as a premise. If W7 is run,
  its write-up should cite this file rather than the original provisional claim.
- This does **not** reopen W4 (variance verdict on the week's P&L) — W4 was independently
  derived from realised daily P&L, not from waves/day, and stands unaffected.

## Reproducibility
Script: temp scratchpad `w9_waves_analysis.py` (not committed — inputs are the tracked
ledger; rerun by re-deriving from the method described above). Run via
`backtest/.venv/Scripts/python.exe` (for `pandas_market_calendars`). Raw output quoted:

```
engine rows: 419
waves (10-min bucket dedup): 168
NYSE trading days in era 2026-06-26..2026-09-10: 53
trading days with ZERO waves: 6
August: sum waves = 83, n_days(calendar)=21, waves/day = 3.952
Frozen: sum waves = 16, n_days(calendar)=7, waves/day = 2.286
Bootstrap 95% CI on (Aug-Frozen): [-0.190, 3.476]
Monthly: 2026-06 3.333 | 2026-07 2.682 | 2026-08 3.952 | 2026-09 2.286
Rolling 6-day windows <= frozen rate: 11/48 (22.9%)
```
