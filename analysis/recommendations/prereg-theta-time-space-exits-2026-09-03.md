# THETA-NOT-GIVEBACK: time/underlying-space exit pre-registration (2026-09-03)

> Pre-registered BEFORE any cell is computed. Covers queue item
> `THETA-NOT-GIVEBACK: 0DTE HOLD-TIME IS THE EXIT LEAK` (filed 2026-07-28,
> `automation/overnight/queue.md:190`). Two mechanism families, run ONE AT A
> TIME, G4 runner-cohort veto mandatory on both. Per OP-16 eval-first gate,
> C6 no-look-ahead, and playbook §4.5 window-scheme discipline.

## Overlap check (done before writing this file)

Grepped `analysis/recommendations/` for `underlying_stall`, `stall`,
`hold_time`/`hold-time`, `entry_hour`, `time_stop`/`time-stop`, `theta`. No
existing prereg tests either mechanism this item calls for:

- `prereg-time-stop-broker-sweep-2026-09-01.json` / measured result
  `time-stop-band-2026-09-01.{json,md}` — a **different thing**, confirmed by
  reading it: it moves the wall-clock `time_stop_et` from 15:40 to 15:20
  **for every trade uniformly**, motivated by Alpaca's 15:30 ET
  broker-liquidation-sweep policy (exercise/ITM risk), not by theta decay or
  underlying stall. It is already `SHIP`-verdicted and frozen for the
  2026-09-29 close. No overlap; not duplicated here.
- `prereg-hour-gate-12xx-2026-09-02.json` — blocks NEW ENTRIES in the 12:xx
  hour (an entry-side gate). Not an exit/hold-time mechanism. No overlap.
- `prereg-hold-posture-2026-07-14.json` / `hold-posture-ab.{json,md}` —
  closest prior art, but tests the OPPOSITE shape (`MIN_HOLD_30`: a **minimum**
  hold floor before any exit can fire; `TRAIL_ONLY_60`: defer TP1). Both were
  KILLed (MIN_HOLD_30 clean kill, TRAIL_ONLY_60 kill vs the shuffle null on
  the frozen bar). Different population too (250-signal `signal-set.json`
  cache, not the live `exit_manager_walk` real-fills/full-history population
  used here). Not the underlying-stall or hour-conditioned max-hold-cap
  mechanism this item calls for — no overlap, cited as prior art only.
- `prereg-pretp1-be-floor-isolated-2026-08-02.json`, `exit-armpct-ab-2026-07-28`,
  `exit-armscope-tp1-ab-2026-07-28` — all PREMIUM-space floors/trails. This is
  exactly the class the queue item says is structurally the wrong instrument
  for a theta problem (see Mechanism below). No overlap; they are the
  falsified prior iterations this item explicitly supersedes.

Verdict: **no duplicate. Proceeding to file this prereg.**

## Mechanism (the reframe, unchanged from the queue item)

Bold 741C: entered 11:28 ET @ SPY 741.33 / premium 1.38; peaked 12:57 ET @
SPY 742.56 / premium 2.16 (+56%); exited 15:55 ET @ SPY 741.09 / premium
0.795 (-42%). SPY finished 0.24 pts from entry (flat); at 15:30 ET SPY was
741.81, *above* entry, with the premium already destroyed. The loss is theta
on a 4.5-hour 0DTE hold, not a giveback of an underlying move. Every
premium-space trail/BE mechanism tested to date (`exit-armscope-tp1-ab`,
`exit-armpct-ab`, `be-floor-ab`, arm_pct 0.05/0.20/0.30/0.40) is a NULL on the
runner cohort (G4 fails at every tested point) because a premium pullback on
0DTE is frequently theta bleed, not a live-thesis reversal — a premium-space
rule cannot tell the two apart. This item pre-registers the untested
TIME/UNDERLYING-space class instead.

## `time_stop_et` — verified, quoted, and why it does not already solve this

```
automation/state/params.json:44:              "time_stop_et": "15:40",
automation/state/aggressive/params.json:38:    "time_stop_et": "15:40",
```

Both accounts carry an identical **wall-clock backstop** — a single fixed
clock time, unconditional on when the position was entered. It does not
condition on entry hour, so an 11:28 entry (4h12m of runway to 15:40) and a
14:30 entry (1h10m of runway) are given the same nominal decay budget by this
knob even though their actual theta exposure differs by ~3.5x. It is not a
decay budget. (Open item, not resolved by this document: today's Bold 741C
exit fired at 15:55 via `structure_stop`, after `time_stop_et=15:40` should
have already closed the position — that discrepancy is a separate mechanical
audit, out of scope for a document-only prereg, and is flagged here so it
is not lost.)

## Populations

**Primary — engine-attributed real fills, core arms, 2026-07-08..2026-09-02**
(source: `analysis/go-live-gate.json`, `generated_et: 2026-09-03T03:49:47`,
`n_engine_trades` fields):

| Arm | n_engine_trades | n_trading_days |
|---|---|---|
| Book-wide (all 4 core arms, correlated rollup) | 278 | 41 |
| safe-2 | 90 | 31 |
| safe-3 | 63 | 27 |
| bold-2 | 42 | — |
| risky-1 | 83 | — |

**Secondary / disclosed — 386-day P1 replay**
(`analysis/recommendations/engine-fullhist-replay-2026-07-23.json`): Safe-account,
`ribbon_ride`-family-only, ~18-month OPRA-covered window, frozen n=190
trades (the same population `be-floor-ab-2026-07-29` and
`exit-armpct-ab-2026-07-28` reused as CONTROL). Scope-disclosed: this
population does NOT cover Bold, does not cover non-ribbon setups
(`bollinger_squeeze`, `vwap_continuation`, `vwap_reclaim_failed_break`,
`vix_regime_dayside`, `double_bottom_base_quiet`, `gap_and_go`), per
`engine-fullhist-replay-2026-07-23.json`'s own SCOPE DISCLOSURE. Reported
alongside the primary population, never pooled with it, never substituted
for it.

**Window scheme (playbook §4.5, fixed here, before any cell runs):** the
expected changed-trade fraction for BOTH families is unknown ahead of the
first run — an underlying-stall exit and an hour-conditioned hold cap only
touch the subset of trades that (a) are still open at bar N / at the cap
minute AND (b) would otherwise have kept riding. That is very plausibly
under the 33% floor §4.5 sets for calendar windows to stay valid. Per §4.5's
own rule, this prereg defaults to **EQUAL-CHANGED-TRADE-COUNT buckets**
(`backtest/lib/canonical_battery.py::equal_count_buckets`, `n_buckets=4`)
for the sub-window stability gate on both families. If the measured
changed-trade fraction on the primary population turns out to be >= 33% at
run time, calendar windows may be substituted — but that decision is made
and recorded in the RESULT file, not retroactively re-chosen here.

## Evaluation method and the primary metric (why sign/rank, not dollars)

Exits are re-derived via `backtest/lib/exit_manager_walk.walk_exit_manager`
at 1-minute resolution driving the real `plan_exit_actions` decision core
(never `simulate_trade_real` — 2026-07-09 sim-parity scar), same convention
as every cited exit study in this repo (`be-floor-ab-2026-07-29`,
`exit-armpct-ab-2026-07-28`, `prereg-hold-posture-2026-07-14`).

**The walker's dollar-magnitude fidelity is NOT yet trustworthy per-arm.**
`analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md`:

- Pooled full population (n=223, default slippage): sign_agreement 88.34%,
  aggregate_ratio 0.6896, verdict **PASS** — but the report itself states
  "the pooled PASS is arithmetic cancellation, not per-arm fidelity."
- Per-arm breakdown (n=223 across 4 arms): **safe-2** n=72,
  sign_agreement 95.83%, aggregate_ratio 0.9634 → **PASS**. **bold-2** n=39,
  sign_agreement 92.31%, aggregate_ratio 6.4361 → **FAIL**. **risky-1** n=63,
  sign_agreement 80.95%, aggregate_ratio 1.7195 → **FAIL**. **safe-3** n=49,
  sign_agreement 83.67%, aggregate_ratio -0.1241 → **FAIL** (replay even
  flips sign vs actual: actual +$750, replay -$93.10).

Given that, this study's **PRIMARY metric is sign/rank-based**, not dollar
totals:

1. Fraction of runner-cohort-eligible trades whose exit is IMPROVED
   (later/higher-realized exit under the treatment cell vs CONTROL) —
   sign-only, per trade.
2. Median per-trade delta (rank statistic, not sum), reported with an
   interquartile spread.

Dollar totals (aggregate P&L delta, per-arm $ impact) are computed and
reported for every cell but are **DISCLOSURE ONLY** until the walker clears
the per-arm criterion (`|aggregate_ratio-1|<=0.40 AND median_abs_error<=$40`)
for that specific arm. Concretely: safe-2 dollar figures may inform a ship
decision; bold-2/risky-1/safe-3 dollar figures may not — only their sign/rank
figures count toward gating until each arm's walker fidelity is independently
re-verified.

## G4 — runner-cohort veto (quoted verbatim, mandatory, unchanged)

From `analysis/recommendations/exit-armpct-ab-2026-07-28.json`'s frozen
gate definitions (the codebase's canonical G4 wording, reused unmodified by
every subsequent exit study in this lineage):

> "G4 RUNNER-COHORT VETO on the 35 RUNNER_TRAIL winners (+$15,774.05) --
> ANY degradation of that cohort's aggregate FAILS the cell outright,
> regardless of G1. Not negotiable (unchanged from iteration 1, which this
> gate killed)."

Applied here unmodified: for every cell in both families, the 35-trade
RUNNER_TRAIL cohort's realized P&L (as re-derived on the same 190-trade
Safe/ribbon_ride population) must not degrade. Any degradation is an
outright cell FAIL, independent of every other gate, including the
sign/rank primary metric above. This is the instrument that already killed
every premium-space mechanism tested to date — an underlying-stall or
hour-conditioned hold cap must clear it on its own merits, not be exempted
because it is a different mechanism class.

## Family A — UNDERLYING-STALL exit

**Claim under test:** if the underlying (SPY) has not made a new favorable
extreme (higher high for a call position, lower low for a put position)
within N five-minute bars of entry, exiting at that bar while premium is
still intact outperforms holding to the next scheduled exit-manager stage,
on the runner-cohort-eligible population, without degrading the runner
cohort itself (G4).

**Cells (frozen):** N ∈ {6, 9, 12} five-minute bars since entry (30/45/60
minutes). No sweep beyond these three points.

- CONTROL: live exit shape as-is (no stall check).
- SA1: N=6. SA2: N=9. SA3: N=12.

**Falsification:** the family is falsified (no cell ships) if, at every N,
either (a) the runner cohort degrades (G4 fails), or (b) the sign/rank
primary metric shows the stall-exit cohort is not majority-improved
(fraction improved <= 0.5, or the median delta is not distinguishable from
zero against a shuffle null), or (c) Family A's own discriminator check
(below) shows the effect is carried by the fixed exit time, not the stall
signal.

**Discriminator null (item 5) — isolating signal from clock:** for every
stall-exit trade at cell N, a matched counterfactual is also computed:
"exit at the SAME bar (entry+N) regardless of whether the underlying
stalled." If the stall-conditioned cells and the always-exit-at-N
counterfactual produce statistically indistinguishable results (same sign
fraction, same median delta within the shuffle-null band), the effect is
attributable to the fixed hold-time clock, not the stall discriminator, and
Family A is reported as NOT CARRYING INDEPENDENT SIGNAL beyond a plain
time-based cap — in which case only Family B (which is explicitly a
time-based cap) is eligible to proceed, and Family A is a clean KILL.

## Family B — hold-time cap conditioned on entry hour

**Claim under test:** capping maximum hold time for entries BEFORE 12:30 ET
(which otherwise carry the most decay runway ahead of 15:40) outperforms the
uniform, entry-hour-blind `time_stop_et=15:40` wall clock, on the same
population, without degrading the runner cohort (G4).

**Cells (frozen):** max hold ∈ {90, 120, 150} minutes, applied ONLY to
trades whose `entry_hour_et < 12:30`. Trades entered at/after 12:30 ET are
UNCHANGED in every cell (they already sit inside a <=3h10m window to 15:40
and are not the population this family targets). No sweep beyond these
three points.

- CONTROL: live exit shape as-is (`time_stop_et=15:40` uniform, no
  hour-conditioning).
- HB1: 90min cap, entries <12:30 only. HB2: 120min cap. HB3: 150min cap.

**Falsification:** the family is falsified (no cell ships) if, at every cap,
either (a) the runner cohort degrades (G4 fails), or (b) the sign/rank
primary metric shows the capped cohort is not majority-improved, or (c) the
early-entry subpopulation (`entry_hour_et<12:30`) is too small at the
primary-population scale to clear a meaningful n (report power explicitly;
do not conclude on n<15 changed trades per cell).

## Sequencing and pooled correction

Family A runs first (it is the more specific, theta-discriminating
mechanism named first in the queue item and is a prerequisite for correctly
interpreting Family B — if Family A shows time-not-signal per its own
discriminator, that directly informs whether Family B's cap should be a flat
number or itself needs a stall gate). Family B runs second, using the same
frozen population and harness. **BH-FDR correction is applied POOLED across
all 6 cells opened by both families together** (SA1-3, HB1-3), not
per-family — consistent with this repo's stated convention ("~191
cumulative exit cells this week, 0 ships" in the queue item itself refers to
pooled correction across the whole trailing-lock axis).

## Forward shadow requirement

No cell from either family ships to a live account gate on backtest/replay
evidence alone. Per `markdown/research/BACKTESTING-PLAYBOOK.md` §4.9
(non-ribbon/new-mechanism forward-clock standard) and this project's
standing shadow-ledger pattern (`analysis/recommendations/*-shadow-ledger.jsonl`):
any cell that clears G4 + the sign/rank primary bar on the historical
population is written to a shadow ledger and must additionally clear
**>= 20 forward trading sessions** shadow-scored (sign/rank primary metric,
same gates) before it is eligible for the 2026-10-30 shape-change menu. This
mirrors `prereg-hour-gate-12xx-2026-09-02.json`'s own explicit routing: a
mechanism that changes WHICH exits fire is a shape change, forbidden inside
the current config freeze (through 2026-09-29) regardless of how good the
historical numbers look.

## `build_step`

```yaml
build_step:
  new_file: backtest/tools/theta_stall_hold_ab_2026-09-0X.py
  reuses_verbatim:
    - backtest/lib/exit_manager_walk.walk_exit_manager
    - automation/state/fleet/exit_manager.py#plan_exit_actions (decision core, unmodified)
    - population loader pattern from be_floor_ab_2026_07_29.py / exit_armpct_ab_2026_07_28.py
      (frozen 190-trade engine-fullhist-replay-2026-07-23.json population, entry+1 convention)
    - primary-population loader: analysis/go-live-gate.json-consistent engine-attributed
      real-fills pull (fills-ledger.jsonl, attribution=='engine', core arms only)
    - G4 runner-cohort constant (n=35, +$15,774.05 anchor) reused, not recomputed, unless the
      primary population's own runner cohort is freshly derived and disclosed as a DIFFERENT
      anchor (must not silently conflate the two, per the pretp1-be-floor-isolated precedent)
  new_surface:
    - Family A: a per-tick actuator-side "stall check" filter, same pattern as
      prereg-hold-posture-2026-07-14's hold_gate ("a thin per-tick actuator-side filter on
      which of the decision core's OWN actions get executed" -- exit_manager.py itself is
      NOT modified)
    - Family B: an hour-conditioned max-hold actuator-side filter, same pattern
  guard_tests:
    - backtest/tests/test_theta_stall_hold_ab.py: RED-proof the stall discriminator against
      the always-exit-at-N counterfactual (item 5); pin no-look-ahead (stall check uses only
      bars up to and including the current tick, C6); pin G4 anchor reuse is byte-identical
      to the cited source unless explicitly and visibly recomputed
  outputs:
    - analysis/recommendations/theta-stall-hold-ab-2026-09-0X.json
    - analysis/recommendations/theta-stall-hold-ab-2026-09-0X.md
  writes_only_to: analysis/recommendations/
  never_touches: [exit_manager.py, strategies.py, params.json, aggressive/params.json,
                   heartbeat_core.py, any live-order path, any scheduled-task registration]
  cost: "$0 -- local OPRA cache + fills-ledger.jsonl, no network, pure Python"
```

## Kill-type classification (item 8)

**Exit tightening is NOT automatically a kill-type (risk) reduction.** An
earlier exit that forfeits winners still riding a live thesis is a SHAPE
change to the profit engine, not a safety change — it trades upside for an
unproven theta-avoidance benefit. Per the standing distinction in this repo
(kill-type = catastrophe-cap / risk-cap changes that only ever reduce tail
loss without touching the winner distribution; shape-type = anything that
changes which trades are taken or how winners are harvested), **both
families are classified SHAPE-TYPE, routed to the 2026-10-30 shape-change
menu**, same as `prereg-hour-gate-12xx-2026-09-02.json`. Neither family ships
mid-freeze even on a clean historical result — only measurement + forward
shadow accrual proceed now.

## Unverified / explicitly flagged

- The 15:40 vs 15:55 exit-timing discrepancy on today's Bold 741C trade
  (time_stop_et should have fired before structure_stop did) is quoted from
  the queue item and re-confirmed against params.json here, but the
  mechanical root cause is NOT investigated in this document-only pass —
  flagged, not resolved.
- `n_engine_trades` for bold-2 (42) and risky-1 (83) trading-day counts were
  not individually re-extracted (only safe-2/safe-3 day counts are shown
  above); if a per-arm day-level power check is needed before running Family
  B's early-entry subpopulation, re-pull those fields from
  `analysis/go-live-gate.json` directly rather than assuming.
- The exact expected changed-trade fraction for either family is UNVERIFIED
  ahead of the first run (stated as "likely under 33%" reasoning above, not
  measured) — the equal-count-bucket default is the safe choice per §4.5,
  to be confirmed or overridden by the measured fraction at run time.
