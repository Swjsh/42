# Regime Early-Classifier + Stand-Down Feasibility — 2026-08-02

**Written 2026-08-02, overnight.** Follow-up to the weekend's regime-library work
(`REGIME-PARTICIPATION-2026-08-02.md`): THE FINDING (measured 2026-08-01, commit `df0348d9`,
regime library over the engine's full-history replay — $4,808.75 / 191 trades) showed
**gap-go = 60.5% of ALL P&L on ~22% of days** and survives drop-best, while **pin-day and
gap-fade are net-losing archetypes**. The engine currently trades every archetype identically.
This document asks the PARTICIPATION question that follow-up left open: should it stand down
on the reliably-losing archetypes, and/or lean into gap-go?

**The catch, stated up front because it is the whole ballgame:** `day-archetypes.json` labels
every day from its FULL session OHLC — hindsight. Its own README says so: *"POST-HOC... may
slice studies and stamp yesterday, never feed a live entry decision for the same day."* To gate
live participation you must know the archetype EARLY. This document builds that early
classifier first, evaluates it brutally honestly, and only THEN asks whether stand-down helps.

---

## Verdict first

- **NOT LIVE-EXECUTABLE with the current early-classifier methodology.** The early classifier
  shows real, above-baseline signal, but not enough of it, and it fails in exactly the wrong
  place: it cannot reliably tell a **gap-go** morning (the book's single best archetype) from a
  **gap-fade** morning (a net loser) at 09:45–11:00 ET, because both are defined by the same
  early precursor — a significant gap that has not yet resolved — and diverge only on
  information (does it fill before the close) that does not exist yet at any of the cutoffs
  tested.
- **Root cause in one sentence:** gap-go and gap-fade share an identical early signature, so a
  classifier tuned to catch gap-fade/pin-day losers necessarily also flags a large share of
  gap-go's genuine winners, and because gap-go alone carries 60.5% of the book's total P&L
  while gap-fade/pin-day combined are a comparatively small loss, the collateral damage
  overwhelms the benefit — **confirmed empirically**, not just argued: the pre-registered arm
  study fails every gate at both frozen cutoffs (recent-window delta negative, runner-cohort —
  the book's actual profit engine — loses 27–47% of its dollars).
- **The confusion matrix is genuinely weak across the board, not just on the archetypes that
  matter operationally.** The full 8-way classifier scores 16.6–20.9% accuracy, *worse* than
  simply always guessing the majority class (39.1%) — several archetypes (trend-up/down,
  V-reversal, inverted-V) are DEFINED by where the close lands relative to the full day's
  eventual range, which is not knowable early by construction, not by a fixable modeling gap.
- **Waiting longer does not rescue it.** An exploratory sweep out to 11:00 ET (forgoing 1.5
  hours of the trading session) only lifts standdown precision from 26.8% to 29.6% and
  gap-go cannibalization from 64.8% down to a floor around 25–27% — a genuine plateau, not a
  "just wait 15 more minutes" problem. This is evidence the limitation is informational (the
  feature set cannot resolve gap-go vs gap-fade that early), not a tuning shortfall.
- **Both pre-registered arms fail every gate.** ARM_1 (10:00 ET cutoff, primary): recent-25-day
  delta **-$632.95**, runner-cohort keeps only **72.6%** of CONTROL's runner dollars (removed
  $3,934.70 of real runner profit). ARM_1B (09:45 ET, secondary): recent-25-day delta
  **-$967.50**, runner-cohort keeps only **52.6%**. Neither the day-majority gate nor the
  worst-single-dodge gate passes either arm. BH-FDR: neither arm's removed-trade sample is
  even statistically distinguishable from a mean of zero (p=0.50 and p=0.86) — there isn't
  robust evidence the skipped trades were net losers in the first place.
- **No arming plan follows.** Per the frozen prereg's ship rule, nothing ships when no arm
  clears every gate. This is filed as a real, dated null result, exactly as the task brief
  anticipated it might be.
- **2024 stratum:** considered, not extended. Reasoned as a feature-identifiability problem
  (more training days cannot manufacture information about whether a gap will fill), not a
  sample-size problem — detail in §5.

---

## 1. The feasibility check (do this first, honestly)

### 1a. Method

`backtest/lib/regime_early_features.py` computes the SAME shape-feature vocabulary
`build_day_archetypes.py` uses (gap%, range%, body%, close_loc, open_loc) but restricted to
bars closed by a wall-clock cutoff — 09:45 ET (first 3 bars) and 10:00 ET (first 6 bars) were
the pre-registered pair (the task brief's own stated window); 10:15/10:30/11:00 were added
**post-hoc as an exploratory, non-gating sweep** to characterize the accuracy/lateness
tradeoff (§1d). Context features add prior-day archetype, day-of-week, VIX at the open, and
5-day/20-day VIX moving averages computed from strictly-prior days.

**No-lookahead is a construction property, not a runtime check:** `early_features()` takes a
bars frame as given and has no concept of "cutoff" or "the rest of the day" — it cannot read a
bar it was never handed. `backtest/tests/test_regime_early_classifier_guards.py` proves this
end to end (corrupt every bar after the cutoff — reverse it, blow the values out 50x, append
garbage rows — and the feature read on the correctly-truncated prefix is byte-identical).
**RED-proofed live this session:** the boundary comparison (`<` vs `<=`) was flipped, 3 tests
failed exactly as predicted (including the corrupt-the-tail lookahead proof itself), reverted,
confirmed green again.

`backtest/tools/build_regime_early_classifier.py` trains two `DecisionTreeClassifier`s
(`class_weight="balanced"`, `max_depth=4`, `min_samples_leaf=10`; sklearn pip-installed into
`backtest/.venv` this session, free/local/OSS): an 8-WAY classifier (the literal ask) and a
DIRECT BINARY classifier for `archetype in {pin-day, gap-fade}` (the operationally relevant
question). Both are evaluated via **expanding-window walk-forward** (`sklearn.TimeSeriesSplit`,
5 folds over the chronologically-sorted 392-day population) — a day's own outcome NEVER
contributes to the model that predicts it, which catches ACROSS-day lookahead (fitting one set
of thresholds on the whole population including the days being scored) in addition to the
SAME-day lookahead the feature module already forecloses structurally. Cost: the first ~17% of
the population (the walk-forward "seed" window, ending 2025-04-13) is training-only and never
scored — a smaller, honestly disclosed test population (n=325 tested days), not a padded one.

### 1b. The 8-way confusion matrix (09:45 ET cutoff, out-of-fold, n=325)

| True \ Pred | V-rev | gap-fade | gap-go | inv-V | pin-day | range-chop | trend-dn | trend-up | support |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| V-reversal | 3 | 2 | 0 | 1 | 2 | 0 | 2 | 0 | 10 |
| gap-fade | 4 | **16** | 10 | 3 | 1 | 0 | 5 | 5 | 44 |
| gap-go | 5 | 18 | **22** | 12 | 6 | 0 | 7 | 1 | 71 |
| inverted-V | 0 | 0 | 1 | 1 | 3 | 0 | 2 | 1 | 8 |
| pin-day | 3 | 1 | 1 | 0 | **7** | 1 | 4 | 1 | 18 |
| range-chop | 20 | 10 | 4 | 6 | 32 | **6** | 41 | 25 | 144 |
| trend-down | 1 | 1 | 0 | 0 | 3 | 0 | **3** | 2 | 10 |
| trend-up | 1 | 1 | 0 | 0 | 3 | 0 | 5 | **10** | 20 |

Diagonal = correct. **Accuracy 20.9%, balanced accuracy 29.1%** (random-chance floor for 8
classes is 12.5%, so genuinely better than random, but the *majority-class baseline* — always
guess range-chop — scores **39.1%**, beating this balanced tree on raw accuracy). Read
range-chop's row: only 6 of 144 true range-chop days (4.2%) are correctly identified — the
tree confuses it most with pin-day (32) and trend-down (41) and trend-up (25). This is expected:
range-chop is the *residual* class in the original taxonomy (defined by the absence of every
other mechanism), which is close to impossible to positively identify from a quiet-looking
open, since a quiet open can resolve into almost anything. 10:00 ET cutoff is not materially
better (16.6% accuracy) — full matrix in `analysis/regime-library/early-classifier-2026-08-02.json`.
**Underpowered classes (n<15 in the test set, CLAUDE.md OP-11 convention): V-reversal (10),
inverted-V (8), trend-down (10)** — their individual cells should not be over-read.

### 1c. The binary question that actually matters: can we spot pin-day/gap-fade to skip?

| Cutoff | Precision | Recall | F1 | Base rate | N flagged "skip" (of 325) |
|---|---:|---:|---:|---:|---:|
| 09:45 ET | 26.8% | 71.0% | 0.389 | 19.1% | 164 (50.5% of all days!) |
| 10:00 ET | 26.9% | 46.8% | 0.341 | 19.1% | 108 (33.2%) |

Baselines on the *same* out-of-fold test set: persistence ("skip if yesterday was pin-day/
gap-fade") scores **14.3%** precision, majority-vote scores **16.9%** — both *worse* than the
19.1% base rate, meaning pin-day/gap-fade show **no positive day-to-day persistence** (a real,
if secondary, finding). The trained classifier does beat both naive baselines by a real margin
(~1.6–1.9x), so this is not zero signal. But 26.8% precision means **roughly 3 of every 4
"skip" calls are wrong**, and the 09:45 cutoff would flag literally half of all trading days as
"stand down" — nowhere near the surgical, high-confidence gate a live capital-affecting
decision needs.

### 1d. The gap-go cannibalization number (the load-bearing one)

Computed directly from the classifier's own out-of-fold predictions, before any P&L was
touched — **this number, not the raw precision figure, is what actually killed this lane:**

| Cutoff | True gap-go days in test | Wrongly flagged "skip" | % of gap-go cannibalized |
|---|---:|---:|---:|
| 09:45 ET | 71 | 46 | **64.8%** |
| 10:00 ET | 71 | 24 | **33.8%** |
| 10:15 ET *(exploratory)* | 71 | 19 | 26.8% |
| 10:30 ET *(exploratory)* | 71 | 18 | 25.4% |
| 11:00 ET *(exploratory)* | 71 | 19 | 26.8% |

The 10:15–11:00 rows are **exploratory, not pre-registered, not gating anything** — added
post-hoc because the sweep is nearly free (~0.5s/cutoff) and directly answers "would waiting
longer fix it." It doesn't, not really: cannibalization plateaus around a quarter of gap-go's
occurrences even after giving up 1.5 hours of the trading session, and standdown precision
tops out at 29.6% (11:00 ET) — still far short of "useful." Feature importances at every
cutoff are dominated by `gap_pct` and early range/body — the model has essentially one lever
(how big is the gap, has it started to fill), and that lever cannot distinguish "will fill
later today" from "won't," which is precisely the gap-go/gap-fade discriminator.

---

## 2. The arm study (pre-registered, run after the classifier verdict was already on record)

**Pre-registration:** `analysis/recommendations/prereg-regime-standdown-2026-08-02.json`,
frozen 2026-08-02 02:16:24 ET, **committed (`60e1dcc8`) before
`backtest/tools/regime_standdown_study.py` existed on disk** — git-provable freeze order, per
the task brief's hard requirement. The prereg states H0 (standdown doesn't help, or
cannibalizes gap-go faster than it saves) as the **favored prior explicitly**, before running
anything — this study exists to attach a dollar figure and a full gate record to that prior,
not because the outcome looked ambiguous.

**Why run it at all if the prior was already negative?** Because a precision number is an
argument; a gate-by-gate dollar figure against the exact same real-fills, real-exit-walked
trade log THE FINDING itself came from is evidence. The gates (especially G4, the runner-
cohort zero-tolerance floor) are built to catch exactly the failure mode the classifier
evidence predicted — running it turns "this classifier looks weak" into a falsifiable,
measured claim.

### 2a. Method — zero new simulation

Reuses `analysis/recommendations/engine-fullhist-replay-2026-07-23.json` verbatim (191 real
OPRA trades, real `exit_manager_walk` exit derivation, 2025-01-06..2026-07-21 — the exact
trade log THE FINDING's $4,808.75/191 was measured from). `regime_standdown_study.py` performs
**pure post-hoc filtering** against the already-committed, already-frozen classifier's
out-of-fold predictions — no re-simulation, no new entry/exit logic, zero risk of a second,
drifted replay pipeline (a documented past failure mode in this exact lane — see the sibling
VIX-gate prereg's provenance section on the disqualified 2026-05-19 sweep family).

**Scope:** 161 of 191 trades are in-scope (30 trades / 21 dates excluded — the walk-forward
seed window has no honest out-of-fold prediction and is dropped from both arms identically,
never defaulted either way). **Runner-cohort** = `exit_reason.startswith("runner_stop")`,
exact-matched to reproduce the task brief's own cited anchor (n=35, +$15,774.05 over the full
191-trade population, confirmed by direct computation before the prereg was written; 32 of
those 35 trades fall in-scope). **Recent-25-day window** = last 25 distinct session dates in
the in-scope population — the doctrine-anchored convention (`recency_check.py`, also used by
the same-night sibling VIX-gate prereg), disclosed explicitly since a second, ad hoc "last 25
dates with a trade" convention also exists elsewhere in this codebase.

### 2b. Results — both arms, every gate, no cherry-picking

| Gate | ARM_1 (10:00 ET, primary) | ARM_1B (09:45 ET, secondary) |
|---|:---:|:---:|
| G1 recent-window positive (**PRIMARY**) | **FAIL** (Δ = -$632.95) | **FAIL** (Δ = -$967.50) |
| G2 day-majority (recent) | **FAIL** (4 improved / 6 worsened) | **FAIL** (4 improved / 4 worsened) |
| G3 survives worst-single-dodge (recent) | **FAIL** (-$1,211.95) | **FAIL** (-$1,546.50) |
| G4 runner-cohort no-regression (**zero tolerance**) | **FAIL** — kept 72.6% of control $ (22/32 trades) | **FAIL** — kept 52.6% of control $ (16/32 trades) |
| G5 meaningful participation change | pass (52 trades removed) | pass (82 trades removed) |
| **SHIPS (all gates)** | **NO** | **NO** |

| Metric | ARM_1 (10:00) | ARM_1B (09:45) |
|---|---:|---:|
| Control total P&L (in-scope) | $+5,376.30 (161 trades) | $+5,376.30 (161 trades) |
| Kept (post-standdown) total P&L | $+5,397.00 (109 trades) | $+2,778.20 (79 trades) |
| Removed total P&L | -$20.70 (52 trades) | +$2,598.10 (82 trades) |
| Full-population delta | +$20.70 | **-$2,598.10** |
| Removed-trade one-sided p (mean<0) | 0.495 (not significant) | 0.865 (not significant) |

**Removed trades by TRUE (hindsight) archetype:**

| Archetype | ARM_1 (10:00): n / $ removed | ARM_1B (09:45): n / $ removed |
|---|---|---|
| gap-fade (the intended target) | 13 / **-$733.90** | 17 / **+$557.05** (!) |
| pin-day (the other intended target) | 1 / -$51.00 | 3 / -$189.00 |
| gap-go (collateral damage) | 13 / **+$163.85** | 24 / **+$2,218.70** |
| range-chop (collateral damage) | 22 / +$683.55 | 31 / -$469.85 |
| trend-up (collateral damage) | 0 | 1 / **+$752.00** — the SAME single 2026-06-11 outlier trade that carries trend-up's entire full-population total per THE FINDING's own drop-best analysis |
| V-reversal (collateral damage) | 3 / -$83.20 | 6 / -$270.80 |

ARM_1 (10:00) is the *closer* of the two calls — full-population delta is a wash (+$20.70) and
gap-fade was correctly caught as a real loser (-$733.90) — but it still fails G1, G2, G3, and
most importantly **G4 outright**: it removes $3,934.70 of real runner-cohort profit while only
correctly avoiding a comparatively small gap-fade loss, and the recent-25-day window — the
PRIMARY gate, per J's dynamic-market doctrine — is unambiguously negative. ARM_1B (09:45) is
worse on every axis, including catching the *exact* single outlier trade that makes trend-up
look positive in aggregate, and even manages to remove gap-fade trades that were net WINNERS
in that arm's specific cut (+$557.05) — a reminder that "predicted gap-fade" and "was actually
a losing trade" are two different things even within the correctly-labeled cohort.

**BH-FDR** (advisory, alpha=0.10, across both arms' removed-trade one-sample tests): zero
survivors. Neither arm's removed-trade sample is statistically distinguishable from a mean of
zero — there is not even robust evidence, independent of the gate battery, that the skipped
trades were net losers as a population.

Full cell-by-cell detail (drop-best-day, day-sums, exact trade lists):
`analysis/recommendations/regime-standdown-2026-08-02.{json,md}`.

---

## 3. Honest power accounting

| Archetype | Early-identifiable? | Why |
|---|---|---|
| gap-go | **No, not separably from gap-fade.** Same early precursor (unresolved gap); diverges only on same-day-future information. | Mechanism, not power. |
| gap-fade | **No, not separably from gap-go**, for the identical reason, symmetric. | Mechanism, not power. |
| pin-day | Weak positive signal (early low range/body is a real, if noisy, precursor) but severely underpowered in this population (only 1–3 true pin-day trades ever get correctly caught in either arm). | n=18 in test set, near the OP-11 underpowered floor. |
| trend-up / trend-down / V-reversal / inverted-V | **No.** Defined by where the close lands relative to the FULL day's eventual range — not knowable at any early cutoff by construction. | Definitional, not a data problem. |
| range-chop | **No.** Residual/default class (absence of every other mechanism); a quiet open is consistent with almost any eventual outcome. | Definitional. |

This table is the honest generalization of §1: the ONE archetype pairing that is even
theoretically plausible to separate early (gap mechanism days, since the gap itself is known
instantly at the open) turns out to be the one pairing that matters most and fails hardest,
because the two gap archetypes are mirror images of each other until the information that
would separate them (fill or no fill) arrives — which, by definition of "early," it hasn't.

---

## 4. What would it actually take (not attempted, flagged for a future session)

Not a recommendation to build any of these — descriptive only, per the task's "if infeasible,
say so" framing, this is the honest answer to "is there ANY way to make this work":

1. **A genuinely different early signal for gap resolution** — options-market positioning
   (put/call skew, 0DTE gamma exposure at the open), overnight futures order-flow shape, or a
   volume/velocity read on the first few bars (a gap that fills on heavy volume vs light volume
   may resolve differently) — none of these are in the current SPY-5m-bars-plus-VIX feature
   set, and none were available/scoped for this session.
2. **Accept a much later cutoff AND redesign the rule as intraday-conditional** rather than
   whole-day: the tested design decides "skip today" once, at one early cutoff, for the WHOLE
   session. A design that instead asks "given everything through bar N, does the gap look like
   it's filling right now" continuously through the morning is a different, more complex rule
   than what this session tested (whole-day stand-down decided once, early) — genuinely
   untested here, flagged as the most promising untried direction, not attempted tonight.
3. **A 2024 stratum extension does not help** (§5) — this is an information ceiling, not a
   sample-size one.

---

## 5. 2024 stratum — considered, not extended

`analysis/deep-research/OPRA-BACKFILL-2026-07-31.md` clears 239 usable 2024 trading days.
Tagging them into the archetype library would be cheap (`build_day_archetypes.py` is
deterministic pure-Python) — but there is no 2024 `engine_fullhist_replay`-equivalent trade log
to test a standdown filter against, and building one is a separate, non-trivial infra task
(already flagged as out-of-lane in the sibling VIX-gate prereg for the identical reason). More
fundamentally: doubling the training population sharpens the tree's OTHER splits marginally
but cannot manufacture same-day-future information the feature set structurally lacks. Full
reasoning frozen in the prereg's `2024_stratum_decision` block before this study ran.

---

## 6. Guards, provenance, commits

- `backtest/tests/test_regime_early_classifier_guards.py` — 9 tests, no-lookahead proofs
  (RED-proofed live: boundary op flipped, 3 tests failed exactly as predicted including the
  corrupt-the-tail leak proof, reverted, confirmed green), arithmetic parity against
  `build_day_archetypes.day_features()`, walk-forward leakage assertion on the real builder.
- `backtest/tests/test_regime_standdown_study.py` — 14 tests, arm-study bookkeeping (BH-FDR
  correctness, runner-cohort exact-prefix matching, kept+removed=control invariant, gate
  boolean correctness on hand-checked fixtures).
- All 88 regime-lane tests green together (`test_regime_early_classifier_guards.py` +
  `test_regime_standdown_study.py` + `test_regime_library_guards.py` +
  `test_regime_participation_replay.py` + `test_regime_participation_study.py`).
- Commits: `76857479` (classifier infra + honest evaluation, feasibility verdict already
  visible) → `60e1dcc8` (prereg frozen, predates the runner script) → `70e7d1fa` (runner +
  arm-study results, both arms NULL) → this document.
- Nothing armed. Nothing in `DO NOT TOUCH` (heartbeat_core.py, fleet_*, filters.py,
  params.json sizing keys) was read or modified. No live/paper order path touched.

---

_Sources: `analysis/regime-library/day-archetypes.json` (WS6) ·
`analysis/regime-library/early-classifier-2026-08-02.json` ·
`analysis/recommendations/engine-fullhist-replay-2026-07-23.json` ·
`analysis/recommendations/prereg-regime-standdown-2026-08-02.json` ·
`analysis/recommendations/regime-standdown-2026-08-02.{json,md}` ·
`analysis/deep-research/REGIME-PARTICIPATION-2026-08-02.md` (THE FINDING) ·
`analysis/deep-research/OPRA-BACKFILL-2026-07-31.md`._
