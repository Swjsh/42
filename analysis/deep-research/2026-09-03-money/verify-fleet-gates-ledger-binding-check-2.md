# VERIFY (skeptic pass #2) — G2 LEDGER TRUTH TABLE (fleet-gates-ledger-binding-check)

Stamp: 2026-09-03, ~14:20-14:45 ET (market hours), read-only. Verifies
`analysis/deep-research/2026-09-03-money/fleet-gates-ledger-binding-check.md` /
`.json` and its script `backtest/tools/fleetgates_ledger-binding-check.py`.
Re-derivation scripts (new, read-only, <5s each): `backtest/tools/fleetgates_realfill_correction.py`,
`backtest/tools/fleetgates_dropbest3_realtrades.py`.

## Verdict up front

**REFUTED — the report's novel/headline claim, not its narrower echo of `veto-scope-safe-3.md`.**

The original script computed "did the fleet arm enter" by reading `action` off
`automation/state/fleet/<arm>/decisions.jsonl` alone. It never cross-checked
`automation/state/fills-ledger.jsonl` (real broker fills). That ledger logs the
SAME persisting decision (identical `reason`/`qty`/`strike` string) on every
~1-minute tick while a signal condition holds, independent of whether an order
already filled or a downstream constraint (day-trade cap, duplicate-suppression,
already-in-position, session cutoff) blocks execution. Re-running the join
against `fills-ledger.jsonl` (match window 0-300s after `core_tick_id`, dedup by
`order_id`) shows the report's "entries" are **1.2x-4.7x inflated by repeated
decision-log rows that never became a real trade**, and the inflation is
**concentrated almost entirely in Table B (the mirror direction)** — exactly the
side the report's headline claim depends on.

Once corrected to real distinct buy fills:

| | Table A share (real) | Table B share (real) | report's raw-share ratio B/A | corrected ratio B/A |
|---|---|---|---|---|
| safe-3 | 8.3% (11/133, unchanged) | **4.8%** (9/188, was 8.0%) | 0.96 | **0.58** |
| risky-1 | 10.5% (14/133, was 11.3%) | **8.5%** (16/188, was 21.8%) | 1.93 | **0.81** |
| risky-3 | 5.3% (7/133, was 6.0%) | **3.2%** (6/188, was 14.9%) | 2.48 | **0.61** |

**The report's central "New finding not in the prior doc" — sourcing is
asymmetric, ~2x worse when bold is the gated side — REVERSES on real-trade
data**: every arm leaks *less*, not more, in the mirror direction once phantom
decision-log rows are removed. This is robust to a top-3-contributing-date drop
(see Robustness section) and to widening the match window to 600s (checked,
counts unchanged — the phantom ticks have no matching fill at any horizon that
day, not a timing-window artifact).

The report's single loudest, most-quoted line — **"`SKIP_CONF_LVL_REC_AFTERNOON`
... NON-BINDING for risky-1 (53% bleed-through)"** — is the worst-affected claim
and does not survive:

| arm | report's raw share (n=45-46) | real-trade share | verdict |
|---|---|---|---|
| safe-3 | 15.6% (7/45) | **8.7%** (4/46) | mostly binding, not the headline number either way |
| risky-1 | **53.3%** (24/45) | **6.5%** (3/46) | report's "non-binding" call is REFUTED — 93.5% held |
| risky-3 | 40.0% (18/45, of logged) | **0.0%** (0/46) | report's number is entirely phantom — gate fully held |

Of the report's own 4 quoted "concrete `core_tick_id`s" for this exact claim,
**3 of 4 have no matching real fill** for the arm(s) cited (checked directly
against `fills-ledger.jsonl`, 300s window):

- `2026-08-12T14:16:02.973209` (safe-3+risky-1) — **real** for both (safe-3 buy
  `2026-08-12T14:17:07.640914` $0.56 x3; risky-1 buy
  `2026-08-12T14:17:09.876975` $0.56 x2). This one holds up.
- `2026-08-13T15:11:02.929340` (risky-1) — **no real fill**. risky-1's only
  buys that day were 09:52:10, 11:42:37, 14:37:11 — nothing near 15:11-15:13.
  Confirmed by checking `automation/state/fleet/risky-1/decisions.jsonl`: the
  identical `ENTER_BULL` decision repeats at 15:11/15:12/15:13 with no order
  ever landing in the fills ledger.
- `2026-08-26T14:56:02.621899` — safe-3 leg is real (buy `14:57:07.359823`
  $1.50 x3), but **risky-3's leg has no real fill**. `automation/state/fills-
  ledger.jsonl` has **zero risky-3 rows on 2026-08-26 at all**.
- `2026-08-26T15:51:02.640393` (safe-3) — **no real fill**. safe-3's only buy
  that whole day was the 14:57:07 one already counted above; the entire
  14:56-15:10 and 15:51-15:53 decision-log streak on 2026-08-26 (17 rows total
  across the three arms combined) produced **zero fleet trades** — checked
  directly: `automation/state/fills-ledger.jsonl` has zero risky-1 rows on
  2026-08-26 and zero risky-3 rows on 2026-08-26; safe-3 has exactly the one
  pair already counted.

## What survives

- The narrower claim this report shares with `veto-scope-safe-3.md` —
  `SKIP_STRUCTURE_VETO` and `SKIP_BULL_1100_1200` (Table A, the two gates
  actually mapped to `params.json` GATE_KEYS) are **mostly binding, with a real
  but small minority leak** — **survives essentially unchanged** on real-trade
  data: raw vs. real counts are identical or off by at most 1 (`SKIP_STRUCTURE_
  VETO`: 3/3, 5/5, 1/1 across safe-3/risky-1/risky-3; `SKIP_BULL_1100_1200`:
  8/8, 8/8, 7/6). These two gates show almost no decision-log-repeat inflation
  because the qualifying ticks are sparser and more isolated in time than the
  Table B afternoon-gate streaks. The `2026-09-03T11:21:02.576928` tick both
  documents already quote is a genuine real fill (verified: safe-3 buy
  `11:22:07.262113` $0.74 x5, matches `veto-scope-safe-3.md`'s own trace).
- `SKIP_MIN_PREMIUM_FLOOR` and `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` (Table B)
  also show raw≈real (4/4, 4/4, 2/2 and 0/0, 9/8, 4/3 respectively) — these two
  are genuinely close to what the report reported.
- The report's own methodology section, the reproduced aggregate n-counts
  (n=133 Table A, n=187-188 Table B — a 1-tick drift from live ticks accruing
  between the original run and this verification, both windows are live during
  market hours), and its symmetric-gate checks (`SKIP_LATE_ENTRY`,
  `SKIP_STALE_TRIGGER` both-accounts-together, `SKIP_MIN_PREMIUM_FLOOR` never
  symmetric) were independently re-run byte-for-byte against
  `fleetgates_ledger-binding-check.py` and reproduce exactly (see Reproduction
  section) — the underlying data pull and the *original* per-gate/per-arm
  decision-log counts are not disputed, only their interpretation as "the arm
  entered/traded."

## Robustness: does the refutation survive dropping top-3 contributors?

Per the CONSEQUENCE-lens instruction, re-ran the real-trade aggregate with the
top-3 contributing calendar dates removed from each arm x table cell
(`fleetgates_dropbest3_realtrades.py`):

| arm | Table A real share (full) | Table A (drop top-3 dates) | Table B real share (full) | Table B (drop top-3 dates) |
|---|---|---|---|---|
| safe-3 | 8.3% | 5.5% | 4.7% | 3.3% |
| risky-1 | 10.5% | 7.4% | 8.4% | 4.2% |
| risky-3 | 5.3% | 2.0% | 3.2% | 1.3% |

Table B stays lower than Table A for every arm after the drop — **the
asymmetry-reversal is not a top-3-date artifact.** (n gets thin after dropping
3 of ~12-17 distinct dates, so treat these as directional, not precise.)

## Consequence lens — does this change what the go-live gate measures, or a 09-29 kill-type change?

- **Go-live gate criterion 5 (safe-3's PROD-SHADOW designation):** No change,
  either from the original finding or from this correction. Read
  `setup/scripts/go_live_gate.py:766` (`prod_shadow_criterion`) — it scores
  safe-3 via `statistical_criterion()` on realized rows net of costs, sourced
  from the arm's actual fills/reconciliation data, not from
  `decisions.jsonl` action counts. Whatever the true leak rate is (8% as this
  note finds, or the report's overstated 8-22%), criterion 5 was never
  computing from the inflated numerator to begin with — it already reflects
  whatever safe-3 actually traded. **This finding — right or wrong — does not
  change what the go-live gate measures.**
- **09-29 kill-type-reduction consequence — this is where the correction
  matters.** The report's `proposed_change` says a future kill-type package
  should give "the leaking arms (chiefly risky-1)... an explicit mirror of
  that gate" for `block_conf_lvl_rec_afternoon`, based on a claimed 53%
  real-money bleed-through. The corrected number is 6.5% (risky-1) / 0.0%
  (risky-3) — i.e. the gate is **already ~93-100% binding in practice** for
  this specific cohort-mismatch subset. Acting on the original 53% framing
  would over-prioritize patching a gate that isn't materially leaking money,
  and the report's `caveats` field never flags this risk (it discusses
  under-powered gates and risky-3's retirement, but not decision-log vs.
  real-fill conflation at all). If a 09-29 package uses this report's Table B
  numbers to decide which gate needs an explicit fleet-arm mirror, it would be
  acting on a number that is off by 4x-8x for the specific line item it calls
  "the strongest single finding here."
- **Dollar effect:** the report explicitly scoped a P&L read as out-of-scope
  ("Does not score whether the leak is P&L-positive or -negative... separate
  expectancy question"), so there is no dollar figure in the original finding
  to recompute. What this note adds instead is the **trade-count** correction
  a dollar estimate would need to start from: of the 26 raw Table A+B "entries"
  the report attributes to safe-3, 20 are real trades (11+9); of risky-1's 56
  raw entries, 30 are real (14+16); of risky-3's 36 raw entries, 13 are real
  (7+6). A dollar-effect estimate built on the report's raw counts would
  overstate exposure by roughly the same 1.3x-2.8x per-arm factor found above.

## Reproduction — original script re-run, byte-level check

Re-ran `backtest/tools/fleetgates_ledger-binding-check.py` fresh this session
(market is live, so absolute tick counts drift by a handful between runs —
8006→8002 total ticks, 133→133 / 187→187 aggregate Table A/B n unchanged
within the ~10-minute gap). All per-gate n-counts and per-arm entry counts
quoted in the report's tables were reproduced exactly from the JSON
(`analysis/deep-research/2026-09-03-money/fleet-gates-ledger-binding-check.json`)
before any real-fill correction was applied — the dispute here is entirely
about the "entered" definition, not the underlying data pull.

## What this does NOT resolve

Does not re-verify the `_plan_from_strategies` code trace (already flagged as
INFERENCE by the original report, unchanged here) or the four gate-name-to-
params.json-key mappings (taken as given from the session's established
context, consistent with `heartbeat_core.py` GATE_KEYS naming). Does not
extend the real-fill correction to every underpowered (n<10) gate row — the
n<10 rows were already flagged UNDERPOWERED by the original report and are not
load-bearing for either verdict. Match window fixed at 300s (spot-checked at
600s for the four disputed example ticks with no change) — a systematically
different execution-latency profile on some arm/day combination could in
principle shift a marginal case from "real" to "phantom" or vice versa, but
the disputed claims here are decided by same-day zero-fill counts (a risky-1
or risky-3 arm with literally 0 buy rows on a given date), which is
window-independent.

## Recomputed numbers (structured)

See accompanying JSON:
`analysis/deep-research/2026-09-03-money/verify-fleet-gates-ledger-binding-check-2.json`
