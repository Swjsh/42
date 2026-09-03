# Verify G3 (bypass-cohort-pnl) — CONSEQUENCE lens

Stamp: 2026-09-03T14:44 ET (market open, `et_clock.py` confirmed). Read-only skeptic pass on
`analysis/deep-research/2026-09-03-money/fleet-gates-bypass-cohort-pnl.md` /
`.json` and its builder `backtest/tools/fleetgates_bypass-cohort-pnl.py`. Independent
re-derivation script (imports the original module, does not re-implement its logic):
`backtest/tools/fleetgates_verify_bypass_cohort_pnl_consequence.py`, output
`analysis/deep-research/2026-09-03-money/verify-fleet-gates-bypass-cohort-pnl-2.json`.

**Lens assigned: CONSEQUENCE** — does this finding change what the go-live gate measures, or
what a 2026-09-29 kill-type change would do? Remove the top-3 dollar contributors from every
headline cut and recompute; state whether the conclusion survives.

## Verdict

**NOT REFUTED. Core dollar totals independently reproduced exactly.** The CONSEQUENCE lens
does not overturn the finding's SUPPORTED verdict — if anything it reinforces the finding's own
"fragile, concentration-driven, not a ratification" framing, sometimes more strongly than the
original report states. Two real, non-fatal issues found (below): one factual overstatement in
the Method section's disclosure claim, and one place where the finding's headline language is
more confident about candidate (b)'s robustness than a natural alternative stress test supports
(a gap the finding's own `proposed_change` field had already partly hedged).

## What was independently reproduced

Re-ran the join (`build_core_index` → `join_arm` → cohort classification) via direct import of
the original script — no logic re-implemented, only new aggregation on top. All five headline
dollar totals matched **exactly**:

| Cut | Report claim | My re-derivation |
|---|---:|---:|
| safe-3 cohort A (bypass) | +$752 (n=13) | +$752 (n=13) |
| Population cohort A (bypass, 4 arms) | +$33 (n=38) | +$33 (n=38) |
| Population cohort B (control) | -$1,325 (n=60) | -$1,325 (n=60) |
| Candidate (a) removed set | +$752 (n=13) | +$752 (n=13) |
| Candidate (b) removed set | +$1,323 (n=29 matched) | +$1,323 (n=29 matched) |
| safe-3 September cohort A | +$802 (n=4) | +$802 (n=4) |

## Top-3-contributor removal (the assigned stress test)

Sorted each headline cohort by realized P&L, removed the 3 largest-dollar trades (not by day —
by individual trade, a stricter cut than the report's own "drop single best day" methodology),
recomputed.

| Cut | Full | Top-3 removed (identity) | After removing top-3 | Verdict |
|---|---:|---|---:|---|
| **safe-3 cohort A** | +$752 (n=13) | 09-03 +507, 09-03 +433, 08-27 +303 | **-$491 (n=10), WR 10%, PF 0.30** | Flips negative — **worse** than the report's own "-$188 drop-today" number, because 08-27's winner isn't "today" and the report's day-level cut left it in. |
| **Population cohort A** | +$33 (n=38) | 09-03 safe-3 +507, 09-03 safe-3 +433, 08-27 risky-1 +353 | **-$1,260 (n=35), WR 14.3%, PF 0.54** | "Breakeven" does not survive — clear net loser once its 3 biggest winners (74% of gross win $) are pulled. |
| **Population cohort B (control)** | -$1,325 (n=60) | 08-05 risky-3 -664, 08-07 safe-3 -488, 08-14 risky-1 -468 (largest **losers**) | **+$295 (n=57), WR 22.8%, PF 1.07** | Flips positive. The "control also loses money" read is itself concentration-driven, not just cohort A's. Symmetric fragility — reinforces, doesn't contradict, the report's own "not distinguishably better or worse" line. |
| **Candidate (a) removed set** | +$752 (n=13) | same as safe-3 cohort A | **-$491 (n=10)** | Same numbers as row 1 (safe-1 contributes 0, as the report notes). |
| **Candidate (b) removed set** | +$1,323 (n=29) | 08-06 risky-3 mirror-case +830, 09-03 safe-3 +507, 09-03 safe-3 +433 | **-$447 (n=26), WR 15.4%, PF 0.73** (and **-$743, n=25** if the untouched 08-06 leftover trade, +$296, is also pulled) | **Does not survive.** This directly contradicts the finding's headline framing that candidate (b) is *"the ONLY cut in the whole analysis that stays net positive... the one cut... that survives"* a stress test. |

## The one substantive finding: candidate (b)'s "survives" claim is test-specific, not general

The original report's stress test for candidate (b) is **drop-the-single-best-day** (2026-08-06,
$1,126), leaving +$197 — and that specific number is correct; I reproduced it exactly
(`drop_best_day_total_pnl: 197.0, drop_best_day_n: 27` in the source JSON). But an equally valid,
arguably more natural reading of "remove the top-3 contributors" (three specific *trades*, which
happen to span **two different days** — one 08-06 trade and two 09-03 trades) flips it to
**-$447**. The day-level cut passes only because 08-06's second contributor (+$296, a risky-1
mirror-case trade) is small enough that dropping the whole day still nets +$197; a trade-level
cut that also removes today's two safe-3 winners fails.

This is not a contradiction of anything the report states as fact — the number it quotes ($197
after dropping 08-06) is right. But the *headline/verdict-field* language ("the ONLY cut... the
one cut in this whole analysis that stays positive") reads more confidently than the underlying
robustness actually is; the report's own `proposed_change` field already partially catches this
("also not a robust base" for candidate b), so this sharpens an existing hedge rather than
exposing a new one. **A reader relying on the headline/verdict fields alone (not the full
`proposed_change` prose) would over-credit candidate (b) as "the safer of the two candidates."**
It is not more robust than candidate (a) under a trade-level cut — both flip negative.

## Independent factual check: the "0 unmatched trades" claim is false (narrow, non-headline scope)

Method section item 4 of the `.md` states: *"After the real-placement fix, **0 unmatched trades
remain** in any cohort for any arm."* Re-checking the source JSON's own `join_stats` and per-arm
`cohort_C_other.n_unmatched` fields:

- `risky-1`: `n_entry_decisions=90`, `n_joined_to_pain_ledger=89` — 1 short.
- `risky-3`: `n_entry_decisions=96`, `n_joined_to_pain_ledger=95` — 1 short.
- Both gaps land in `cohort_C_other` (risky-1 `n_unmatched=1` of 13; risky-3 `n_unmatched=1` of
  5) — both trades dated **2026-08-26** (`SPY260826C00766000` / `SPY260826C00768000`,
  `decision_ts_et` 14:57:06, identical timestamp — likely a shared tick / correlated event, not
  independently checked further here). Cohorts A and B (the two cohorts every headline dollar
  figure in this report is built from) genuinely do have 0 unmatched — the false part of the
  claim is specifically the word "any cohort," not the headline numbers.

**Consequence**: candidate (b)'s "29 trades" removed-set count is short by these same 2 trades
— the true kill-type removal set for candidate (b) is **31 trades**, 2 of which have **unknown**
$ impact (not $0 — unknown, no pain-ledger row and no fills-ledger reconstruction match). The
reported $1,323 is the sum over 29 *matched* trades only; this is disclosed in the raw JSON
(`n_unmatched: 2` sits right next to `total_pnl: 1323.0`) but not called out in the `.md` prose
for candidate (b) specifically, and directly contradicts the Method section's blanket claim.
Does not change candidate (a) or the safe-3/population A/B headline numbers.

## Go-live gate: does this finding change what it measures?

**No — confirmed by direct grep: zero references to `core_tick_id`, `cohort`, `bypass`, or
`A_BYPASS` anywhere in `setup/scripts/go_live_gate.py`.** `statistical_criterion()` (the function
behind both criterion 1 and criterion 5/PROD-SHADOW) operates on **all** `attribution=="engine"`
round trips for the arm, aggregated to **day-level** bootstrap PF CI (as-traded, ex-single-best-
day, cost-adjusted) — it has no concept of which trades were safe-gated/bold-passed. This G3
report is a diagnostic overlay on top of the gate's evidence base, not an input to it. Running
`go_live_gate.py` fresh this session (2026-09-03T14:43 ET):

- **Criterion 5 (PROD-SHADOW, the safe-3-designated criterion)**: `FAIL status=INSUFFICIENT_DAYS`
  — `days_scored=2/20`, `current_CI_lo=0.0`. Today's two bypass wins (+$940) are *inside* this
  2-day window and still leave it nowhere near scorable, let alone passing.
- **Trailing 20-trading-day view (disclosure only, not a pass bar)**: safe-3 `as_traded
  CI_lo=0.51` — **FAIL**, over `2026-07-17..2026-09-03`, i.e. even with today's $940 folded in
  across the full 20-day disclosure window, safe-3 is well under the CI-lower>1.0 bar.
- The gate's own day-level `ex_best_day` check is architecturally identical to the report's
  "drop-best-day" methodology (same function, `statistical_criterion`, used for both) — meaning
  the gate would face the **same blind spot** this note surfaces for candidate (b): a
  multi-day trade-level concentration (two winners split across two different days) is invisible
  to a single-best-day dropout test. This is a real, mechanism-level implication of the
  CONSEQUENCE lens, not a numbers quibble: **any future safe-3 PASS should be read against
  `best2_share_of_gross_winners` (already tracked in the gate's EFFECTIVE EVIDENCE block,
  currently 0.342 for safe-3) rather than assumed clean just because ex-best-day survives.**

## Consequence for a 2026-09-29 kill-type change

- **Candidate (a)** (safe-3/safe-1 inherit safe's own gates): the top-3-trade cut makes the case
  for this kill **stronger**, not weaker, than the original report's framing. Excluding just
  today's 2 trades (the report's own stress test) leaves -$188; excluding the 3 largest-dollar
  trades (which also removes 08-27's +$303, a trade with no special "lucky/recent" status) leaves
  **-$491 over 10 trades, WR 10%, PF 0.30** — a much more decisively negative "what would have
  been removed" number. A 09-29 prereg citing this evidence has a stronger case available to it
  than the original report's headline conveys.
- **Candidate (b)** (mirror-direction, all arms): does **not** clear the same bar under a
  trade-level cut (**-$447**, or **-$743** dropping the 08-06 leftover too) despite clearing the
  original report's day-level cut (+$197). Any 09-29 prereg citing candidate (b) as "the more
  robust cut" needs to cite the day-level number with this caveat attached, not as an
  unqualified robustness claim.
- Neither candidate changes: both were already correctly described by the original report as not
  clearing this repo's pre-registration bar (n≥20, OOS split) — nothing here promotes either
  candidate to shippable. The CONSEQUENCE lens sharpens *which* candidate has the stronger
  descriptive case (a, once top-3 trades are stripped) without changing that verdict.

## What would flip this note's own read

A single subsequent trading day with 2-3 large bypass-cohort losses on safe-3 or risky-1 would
simultaneously: (a) reproduce the report's own "today-dominated, could flip any day" caveat, and
(b) make candidate (a)'s -$491 ex-top-3 number look conservative rather than definitive. This
note's top-3-removal cut is itself just another single stress test on an n=13/29/38 sample —
not a substitute for the pre-registered OOS validation both the original report and this note
agree is still missing.

## Files

- Original finding: `analysis/deep-research/2026-09-03-money/fleet-gates-bypass-cohort-pnl.md` /
  `.json`.
- This verification script (scratch, re-runnable, imports the original module):
  `backtest/tools/fleetgates_verify_bypass_cohort_pnl_consequence.py`.
- This verification's raw output: `analysis/deep-research/2026-09-03-money/verify-fleet-gates-bypass-cohort-pnl-2.json`.
- Go-live gate run quoted above: `setup/scripts/go_live_gate.py`, executed fresh this session,
  read-only, no state written.
