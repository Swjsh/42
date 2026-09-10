# Clean single-trigger ATTRIBUTION study -- does `trendline_rejection` carry its own weight?

Script: [`attribution_study_2026_09_10.py`](attribution_study_2026_09_10.py), raw output
[`attribution_study_2026_09_10.json`](attribution_study_2026_09_10.json) (this session's run).
Prior context: [`RESULTS-2026-09-10-trade-outcome-ab.md`](RESULTS-2026-09-10-trade-outcome-ab.md)
caveat (a) -- that file's n=45 population cannot say whether `trendline_rejection` was
load-bearing or a passenger on a multi-trigger fill. This file closes that gap.

## VERDICT (one line)

**Underpowered -- cannot distinguish.**

SOLE's as-traded point estimate sits almost exactly on breakeven (PF 1.042, `p(PF<=1)=0.471`
-- a coin flip under resampling), its sign is NOT stable across the two independently-built
real-fills pipelines that should agree (+$1.91/tr this study's 4-arm cut vs -$2.17/tr the
validated `trendline_tier_rail.py` 2-arm cut -- fully reconciled below, not a mystery), and
its entire as-traded result is one session's trade (2026-08-20: dropping it flips SOLE from
+$84 net to -$429 net). n=44/19 days is short of the work order's own n>=15 floor only in the
sense that 19 days is not enough to survive a single-day removal test. This is not a "SOLE
is secretly fine" result and not a "SOLE is secretly toxic" result -- it is a result that
cannot support either claim yet.

## The decomposition (frozen before running, not re-cut afterward)

Population: `analysis/trades-enriched.jsonl`, `attribution=="engine"`, arm in
`go_live_gate.ACTIVE_ARMS` = `{safe-2, bold-2, safe-3, risky-1}` (**verified live this
session**: `go_live_gate.ACTIVE_ARMS` printed `['safe-3', 'safe-2', 'risky-1', 'bold-2']`).
296 engine rows total in that scope.

| Bucket | Definition | N | Days | Date range |
|---|---|---|---|---|
| **SOLE** | `triggers == ["trendline_rejection"]` exactly | 44 | 19 | 2026-07-02 -> 2026-09-08 |
| **CO_FIRING** | `trendline_rejection` present, `len(triggers)>1` | 1 | 1 | 2026-07-27 only |
| **NONE** (baseline) | `trendline_rejection` absent | 251 | 40 | 2026-06-26 -> 2026-09-03 |
| ALL_TL (SOLE ∪ CO_FIRING) | any presence of the trigger | 45 | 19 | 2026-07-02 -> 2026-09-08 |
| BOOK_AS_TRADED | every engine row, all 4 arms | 296 | 43 | 2026-06-26 -> 2026-09-08 |

**CO_FIRING is n=1** -- the trigger almost never co-fires with anything else in this real-fill
population (the one exception: 2026-07-27, bold-2, `confluence+level_rejection`, -$355). This
is itself a finding: the premise that `trendline_rejection` "can carry alongside
`confluence`/`level_reclaim`/etc." (per the prior A/B study's caveat) is true in principle
(`filters.py`'s bypass shape permits it) but essentially never happens on real fills -- 44 of
45 real trendline_rejection fills are SOLE. ALL_TL's -$271 headline from the prior study is
therefore **entirely a SOLE+one-outlier story, not a mixed-trigger story**: SOLE alone nets
+$84; the single CO_FIRING trade alone nets -$355; 84 + (-355) = -271, which reproduces the
prior study's total_pnl to the cent (cross-check, not re-derivation -- same source file, same
session).

## Per-bucket table -- N, ex-best-day PF CI-lower, per-trade P&L

`statistical_criterion()` REUSED VERBATIM from `setup/scripts/go_live_gate.py` (L251), never
reimplemented. Criterion: CI-lower(2.5%) > 1.0 on ALL THREE of as-traded / ex-best-day /
cost-adjusted to PASS. **No bucket below passes** -- consistent with the book's known state
(no arm has cleared the go-live gate yet); the comparison that matters here is *relative*,
not against the 1.0 bar.

| Bucket | N (days) | Net P&L | Mean $/trade | WR | as-traded CI-lower | ex-best-day CI-lower (dropped day) | cost-adj CI-lower |
|---|---|---|---|---|---|---|---|
| **SOLE** | 44 (19) | +$84.00 | **+$1.91** | 34.1% | 0.304 | 0.194 (2026-08-20) | 0.300 |
| **CO_FIRING** | 1 (1) | -$355.00 | -$355.00 | 0.0% | n/a (n<2 days) | n/a | n/a |
| **NONE** (4-arm baseline) | 251 (40) | +$2,182.00 | +$8.69 | 27.1% | 0.351 | 0.245 (2026-08-04) | 0.347 |
| ALL_TL | 45 (19) | -$271.00 | -$6.02 | 33.3% | 0.257 | 0.167 (2026-08-20) | 0.254 |
| BOOK_AS_TRADED | 296 (43) | +$1,911.00 | +$6.46 | -- | 0.414 | 0.318 (2026-08-04) | -- |

**CO_FIRING (n=1) is reported and labelled UNDERPOWERED per the work order's own rule --
never dropped, never treated as decisive.** One trade cannot characterize a "co-firing"
population; the -$355 number is a fact about that one trade, not a rate.

## Confound: SOLE never fires on safe-3/risky-1 -- the NONE baseline above is not apples-to-apples

SOLE/ALL_TL's per-arm split is `{bold-2: $8, safe-2: $76}` -- **zero** rows from safe-3 or
risky-1 (same disclosure the prior A/B study made for the 45-row population). The 4-arm NONE
baseline above (+$8.69/tr) is therefore inflated relative to SOLE by two arms
(risky-1 +$1,259, safe-3 +$1,233) that structurally cannot produce a trendline_rejection SOLE
entry at all. A same-arm (safe-2+bold-2 only) comparison is the fair one:

| Same-arm (safe-2+bold-2 only) cut | Source | N | Days | Mean $/trade |
|---|---|---|---|---|
| SOLE | this study (trades-enriched.jsonl) | 44 | 19 | +$1.91 |
| SOLE | `trendline_tier_rail.py` (independent pipeline, fresh dry-run this session) | 41 | 20 | -$2.17 |
| rest-of-book, same 2 arms, all days | this study (trades-enriched.jsonl) | 97 | 32 | -$3.20 |
| rest-of-book, same 2 arms, all days | `trendline_tier_rail.py` | 104 | 32 | -$4.73 |
| rest-of-book, same 2 arms, SOLE's own 20 sessions only | `trendline_tier_rail.py` | 53 | 16 | -$2.94 |

On **every** same-arm cut, in **both** independently-built pipelines, the rest-of-book baseline
is more negative than SOLE. That is directionally consistent with the 2026-09-08 STATUS.md
read ("trendline-only rail HOLDING... rest-of-book worse"). But SOLE's own sign flips between
the two pipelines (+$1.91 vs -$2.17) on what should be the identical population -- see
reconciliation below for exactly why, and note that a $4/trade swing on n=41-44 is well inside
the noise band these CIs already show (as-traded CI spans roughly [0.30, 3.5]x PF).

## Block counterfactuals (NAIVE -- explicitly stated, not modeled as replaced)

**Assumption stated up front:** every counterfactual below assumes a blocked entry simply does
not happen and nothing fills that capital/PDT slot. If the engine would plausibly have taken a
different trade in that slot, this model does not capture it -- no replacement trade is
evidenced or simulated anywhere in this study.

| Scenario | N remaining | Net P&L | Mean $/trade | as-traded CI-lower | ex-best-day CI-lower (dropped day) |
|---|---|---|---|---|---|
| Book as-traded (no block) | 296 (43d) | +$1,911.00 | +$6.46 | 0.414 | 0.318 (08-04) |
| Block SOLE only | 252 (40d) | **+$1,827.00** | +$7.25 | 0.340 | 0.236 (08-04) |
| Block ALL trendline-carrying (SOLE+CO_FIRING) | 251 (40d) | **+$2,182.00** | +$8.69 | 0.351 | 0.245 (08-04) |

**Blocking SOLE alone makes the book's real dollar P&L WORSE, not better** (+$1,911 ->
+$1,827, a $84 loss -- exactly SOLE's own net contribution, since SOLE is marginally net
positive as-traded over this window). Blocking everything trendline-carrying (SOLE + the one
CO_FIRING outlier) makes the book better (+$1,911 -> +$2,182, a $271 gain) -- but that gain is
**entirely attributable to the single CO_FIRING trade** (-$355), not to SOLE. Both scenarios
also drop 3 trading days from the book (days where SOLE was the ONLY engine activity),
which independently widens the bootstrap CI and pulls ci_lower down in both block scenarios
relative to the unblocked book -- a real effect of losing sample days, not evidence the
remaining book got riskier.

### Drop-best-arm on both (a result living in one arm is not a result)

The single largest-net-pnl arm in every post-block scope is **risky-1**. Removing it entirely
(on top of the block) collapses both scenarios toward the same weak, non-clearing state:

| Scenario | N (days) | Net P&L | Mean $/trade | as-traded CI-lower | ex-best-day CI-lower |
|---|---|---|---|---|---|
| Block SOLE, drop risky-1 | 165 (40d) | +$568.00 | +$3.44 | 0.285 | 0.181 |
| Block ALL_TL, drop risky-1 | 164 (40d) | +$923.00 | +$5.63 | 0.299 | 0.191 |

Neither survives losing its best-contributing arm either -- the book's marginal edge (such as
it is, and it does not clear 1.0 anywhere in this study) is not concentrated in a way that
SOLE or ALL_TL removal fixes; it is concentrated in risky-1's contribution, a completely
orthogonal axis to the trendline decomposition this study was asked to test.

## Reconciliation with the 2026-09-08 STATUS.md number (n=41, -$2.17/tr)

STATUS.md quote (LOSS-MECHANISMS-READ-2026-09-08): *"Trendline-only rail HOLDING (n=41,
-2.17/tr; rest-of-book -4.73/tr, WR 25 pct)."*

**Fresh dry-run of `setup/scripts/trendline_tier_rail.py` this session** (read-only,
`--dry-run`, writes nothing) reproduces that number exactly, unchanged since 2026-09-08 (no
new trendline-only fills in the interim):

```
[trendline-tier-rail] HOLDING :: TRENDLINE-only cohort: n=41 over 20 sessions, $-89 net
($-2.17/trade, WR 31.7%); DROP-BEST-DAY $-16.72/trade. Rest of book: $-4.73/trade
(drop-best $-16.66/trade), WR 25.0%. Holding -- not negative on a drop-best-day basis.
```

This study's SOLE bucket, restricted to the same 2 arms (safe-2+bold-2 -- SOLE has zero
safe-3/risky-1 rows so this restriction does not change SOLE's N), is **n=44, +$84 net,
+$1.91/tr -- does NOT match n=41/-$89/-$2.17/tr exactly.**

**Scope difference (identified, not hand-waved):** the two pipelines measure the SAME
strict `triggers==["trendline_rejection"]` shape but from DIFFERENT sources --
`trendline_tier_rail.py` sources `automation/state/core-decisions.jsonl` (action=="PLACED")
joined to `fills-ledger.jsonl` via `exit_shape_parity_study.reconstruct_positions`
(position-level, flat-to-flat). This study sources `analysis/trades-enriched.jsonl`
(a separately-built FIFO-trip round-trip ledger). A row-by-row diff (this session, both
lists sorted by date/arm/symbol) found the **exact** residual:

- **5 rows present in this study's SOLE bucket, absent from the rail's cohort** (net +$173):
  `2026-07-02 bold-2 SPY260702P00740000 +$290`, `2026-07-17 bold-2 SPY260717P00743000 +$191`,
  `2026-08-13 bold-2 SPY260813P00776000 -$200`, and TWO `2026-08-14 safe-2
  SPY260814P00776000` rows (`-$18`, `-$90`) where the rail shows no safe-2 activity that day
  at all (only bold-2 `-$160`, which both pipelines agree on).
- **2 rows present in the rail's cohort, absent from this study's SOLE bucket** (net $0):
  `2026-09-04 safe-2 SPY260904P00772000 $0` and `2026-09-04 bold-2 SPY260904P00770000 $0`.

`44 - 5(extra) = 39` matched; `39 + 2(rail-only) = 41` = the rail's N exactly.
`$84 - $173(extra) - $0(missing) = -$89` = the rail's net exactly. **The residual is fully
accounted for to the cent** -- this is a real join/reconstruction disagreement between the two
pipelines (most visibly the double-counted 08-14 safe-2 rows, suggestive of the FIFO-trip
splitter producing two round trips from what the rail's flat-to-flat reconstruction treats as
one continuous position), not a population-definition disagreement and not an error in either
number taken alone. Root-causing WHY the two pipelines disagree on those specific 5-7 rows was
not pursued further (out of this study's scope; flagged as a residual pipeline-parity gap).

**The two independent measurements of "the same thing" disagree on SIGN** (+$1.91/tr vs
-$2.17/tr) by an amount smaller than either pipeline's own bootstrap CI half-width. That
instability is itself the strongest piece of evidence for this study's verdict: SOLE is not
resolved either direction yet.

## OP-20 disclosure

- **N per bucket:** SOLE 44/19d, CO_FIRING 1/1d (**UNDERPOWERED, reported not dropped**), NONE
  251/40d, ALL_TL 45/19d, BOOK 296/43d. All below the work order's implicit adequacy bar in
  the sense that NONE of them survive drop-best-day; only CO_FIRING is below the explicit
  n=15 floor.
- **IS vs OOS:** 100% in-sample / real-fills-to-date (2026-06-26 through 2026-09-08). No
  forward/OOS window exists for this decomposition; it was not attempted.
- **Null/baseline:** the NONE bucket (entries without `trendline_rejection`) is the
  within-study baseline; `trendline_tier_rail.py`'s independently-built rest-of-book is the
  cross-pipeline baseline. Both agree in direction (rest-of-book worse than SOLE, same-arm
  basis) though not in exact magnitude.
- **Metric definition:** `statistical_criterion()` = percentile bootstrap (n_boot=20000,
  seed=42) profit-factor CI over trading DAYS, as-traded / ex-best-day / A1-cost-adjusted
  (fees + 2c/contract exit slippage), pass requires CI-lower(2.5%) > 1.0 on all three.
  Per-trade P&L = net pnl_dollars / N, option premium P&L only (never SPY-price P&L, L74/C3).
- **Known confounds:**
  1. SOLE/ALL_TL structurally never appear on safe-3/risky-1 -- any 4-arm NONE/BOOK
     comparison is confounded by arm composition unless restricted to safe-2/bold-2 (done
     above).
  2. Two independently-built real-fills pipelines disagree by 5-7 rows / $173 on the
     identical population definition -- reconciled to the cent above but not root-caused at
     the row level.
  3. SOLE's as-traded result is carried almost entirely by ONE session (2026-08-20); the
     rail's own cohort independently flags the same day as its top day. This is the same
     "does not survive its own best day" characterization already on record in
     `trendline_tier_rail.py`'s module docstring (2026-08-21 build note) -- this study
     corroborates it on a materially different (4-arm, trades-enriched-sourced) population.
  4. CO_FIRING n=1 cannot support any rate claim about co-firing entries; it is reported as a
     fact about one trade, nothing more.
  5. Block counterfactuals are naive (no replacement-trade model) -- stated in the
     counterfactual section above, not repeated as a footnote.
  6. `bootstrap_pf_ci` returns `None` on <2 days (CO_FIRING's as-traded and cost-adjusted
     views) -- reported as `n/a`, never silently coerced to a number.

## `/fable-too-good` consideration

This result is **not** extraordinary in either direction -- it landed on "underpowered,
sign-unstable," which is the least dramatic of the four allowed verdicts, not a clean win or
a clean kill. Per the precedent already on record in this same directory
(`RESULTS-2026-09-10-trade-outcome-ab.md`: *"the result is not extraordinary... so the
suspicion protocol does not apply here"*), the formal `/fable-too-good` artifact hunt was not
invoked as a separate step. The equivalent diligence WAS performed inline and is fully
reproducible from this file: (a) the $271/$173/$89 reconciliation residuals were traced to
specific, named rows rather than accepted as an unexplained gap; (b) the two real-fills
pipelines were cross-checked against each other rather than trusting either alone; (c) the
single best day driving SOLE's sign was identified and quoted, matching an independently
pre-existing disclosure in `trendline_tier_rail.py`'s own docstring rather than being a new
surprise this session invented.

## Boundaries honoured

No edits to `backtest/lib/filters.py`, `setup/scripts/heartbeat_core.py`,
`automation/state/params*.json`, or `FROZEN_TRADING_PATH`. No `GAMMA_FREEZE_OVERRIDE`. No
orders, no scheduled tasks, no params changes. `trendline_tier_rail.py` was run with
`--dry-run` only (confirmed: writes nothing to `automation/state/trendline-tier-rail.json`
when `dry_run=True`, verified by reading the function body before running it). Ran as ONE
single-threaded process; no concurrent workers; `analysis/trades-enriched.jsonl` was read
AS-IS off disk, not refreshed, to avoid any write during the market-hours-adjacent window.
Nothing committed.
