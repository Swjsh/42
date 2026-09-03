# PRE-REGISTRATION — FLEET GATE INHERITANCE, 2026-09-03

**Status: FROZEN before any forward data accrues.** Commit timestamp of this file is the
freeze proof. `setup/scripts/fleet_gate_leak_shadow.py` (the ledger/summary builder) and
`setup/install-fleet-gate-leak-shadow.ps1` (the scheduled task) are committed alongside
this file. `IN_SAMPLE_CUTOFF = "2026-09-03"` — this build's own date — means every row
dated on or before this freeze is IN-SAMPLE (backfilled, already seen, descriptive only);
the forward window this decision rule is judged on opens `2026-09-04`, the first date
this instrument could not already explain.

Queue item: `FLEET-GATE-LEAK-SHADOW` (MED, filed 2026-09-03 14:51 ET,
`automation/overnight/queue.md`), which itself closes out `FLEET-STRATEGIES-BYPASS-SAFE-
GATES` (status:done, decided 14:51 ET 2026-09-03, 20-agent fleet review). That review's
own decision text is the source of this prereg's bar and decision rule; nothing below is
invented independent of it.

---

## 1. What is being judged

Whether **safe-role fleet arms (safe-3, safe-1)** — the two `accounts.json` roster
entries in the `safe x *` cell family — should be routed through
`fleet_executor._perception_for_arm` (the dormant safe/bold role router that already
exists in the codebase but is never reached on the live signal shape, per
`veto-scope-safe-3.md` and `fleet-gates-code-binding-table.md`) instead of the current
`_plan_from_strategies` path, which reads `sig["strategies"]` — a signal that defaults to
SAFE's own (bear, bull) block but silently substitutes BOLD's block whenever SAFE is
gated (`action` starts with `SKIP_`) and BOLD's own perception separately passes.

Routing through `_perception_for_arm` would make safe-role arms subject to EVERY
safe-only `params.json` `GATE_KEYS` cohort flag (`structure_veto_enabled`,
`block_bull_1100_1200`, `block_elite_bull*`, etc.) that `_plan_from_strategies` currently
lets them bypass on a minority of ticks. This is a **trading-path change**
(`build_shared_signal.py` / `fleet_executor.py`), gated by the 2026-09-29 config-freeze
window — **frozen for real until 2026-10-30**, matching the closed queue item's own
stated date. `risky-1`/`risky-3` (the `risky x *` cell family) are explicitly OUT of
scope for this decision — their nominal role is BOLD's looser gate set, and the fleet
review found their mirror-direction bleed-through (bold gated, safe entered) is a
separate, unresolved question this prereg does not adjudicate.

## 2. Why a forward shadow, not a ship/kill call on the backfilled data already in hand

The in-sample population (2026-08-06 through 2026-09-03, `analysis/recommendations/
fleet-gate-leak-ledger.jsonl`, `in_sample: true` rows) already shows safe-3's bypass
cohort is **not distinguishable from zero**: `SKIP_STRUCTURE_VETO` n_real=3 (CI
[-384, +433]), `SKIP_BULL_1100_1200` n_real=8 (CI [-25, +306]) — both bootstrap CIs
straddle zero by a wide margin, and n is far below any bar that would let a CI resolve
one way or the other. The fleet review's own consequence-lens finding was explicit: "no
go-live instrument assumes safe-3 runs safe's gates; a 09-29 inheritance change would not
cost any scored day." There is no defensible way to read a ship/kill signal out of 3-8
real trades per gate — the only clean path is accruing forward evidence nobody has
cherry-picked, exactly the same two DO-NOTs the sibling `tp1-r50-forward-shadow` prereg
already established for this repo (do not re-open the in-sample read as if it were fresh;
do not act on a population this thin).

## 3. Population and measurement (frozen)

- **Scope:** every `core_tick_id` since `2026-08-06` where `account=safe`'s own `action`
  starts with `SKIP_` (a gate refused safe) AND `account=bold`'s `verdict` is
  `ENTER_BULL`/`ENTER_BEAR` (bold's perception separately passed) — the **bypass
  cohort** — restricted to **arm = safe-3** and **arm = safe-1** (safe-1 retired
  2026-07-11, entirely before `core_tick_id` existed 2026-08-03; it is tracked for
  completeness and is expected to contribute zero forward rows, never silently dropped
  from the roster).
- **"Real fill"** = a CLOSED FIFO round trip (`automation/state/fleet/fills_fifo.
  mine_real_arm_fills`) whose `entry_ts_et` falls inside `[core_tick_id, core_tick_id +
  300s]` and whose option side (C/P) matches the bypassing direction (BULL→C, BEAR→P).
  **NEVER** a `decisions.jsonl` action-row count — that definition was proven inflated
  1.2x-4.7x by a re-logged, still-open decision persisting across ticks
  (`verify-fleet-gates-ledger-binding-check-2.md`). One real fill can be claimed by AT
  MOST one qualifying tick (`fleet_gate_leak_shadow.assign_real_fills`'s single-claim,
  no-look-ahead dedup — see that module's own docstring for the full mechanism and the
  worked example of why the claim pool spans every gate + the control cohort together,
  not one gate in isolation).
- **300s entry window**, stated and justified in `fleet_gate_leak_shadow.py`'s own
  docstring: the fleet_rest arms' ~3-min shared-signal read cadence
  (`fill_latency.py`) plus ~0.1-0.2s broker fill latency
  (`fleet_live.py`'s `ENTRY_CLAIM_TTL_SEC` comment) gives 300s a ~1.7x margin; this exact
  window was independently checked at 600s with no count change by this session's own
  skeptic pass.
- **Per-trade P&L:** the FIFO round trip's own `real_pnl` (buy notional vs sell
  notional, summed across every partial-exit leg) — never a re-simulation.
- **No look-ahead, no cherry-picking:** `IN_SAMPLE_CUTOFF = "2026-09-03"`. The forward
  window is `>= 2026-09-04`. Nothing before the freeze date is ever counted toward the
  bar or the decision rule below, by construction.

## 4. Forward bar (frozen — NOT softened at read time)

Both conditions required, evaluated **per decision-focus arm** (safe-3, safe-1
independently — safe-1 is expected to never reach it, disclosed not hidden):

- **>= 20 forward trading sessions elapsed** (`n_forward_sessions_elapsed >= 20`,
  counted from ALL distinct `core-decisions.jsonl` session dates on/after
  `2026-09-04` — a calendar/liveness clock, not gated on the arm having fired that day), AND
- **>= 20 real bypass entries on that arm** (`n_forward_real_bypass_entries >= 20` —
  the evidence-volume floor; a low-fire-rate cell needs its own adequate-power floor,
  the same lesson `GATE-DESIGN-FIXED-CALENDAR-WINDOWS-STARVE-LOW-FIRE-RATE-KNOBS`
  generalized for the sibling `tp1-r50-forward-shadow` prereg).

Below the bar the instrument's status is `ACCRUING` and produces NO ship/kill signal.
`fleet-gate-leak-summary.json`'s own `forward_bar` block names the remaining distance
every night.

## 5. Decision rule (frozen — the bar cannot be softened after data starts arriving)

Once the bar in §4 is met for a decision-focus arm (safe-3 or safe-1 independently),
that arm becomes a **route-candidate** for `_perception_for_arm` ONLY if BOTH hold on
its accrued forward bypass-cohort ledger:

1. **`session_clustered_ci.ci_upper_97.5 < 0`** — the ENTIRE day-clustered percentile
   bootstrap CI (2000 resamples, resampling trading DAYS with replacement, matching
   `go_live_gate.bootstrap_pf_ci`'s methodology so within-day trade correlation is
   respected) over the bypass cohort's per-trade `real_pnl` mean lies strictly below
   zero — i.e. the bypass cohort's real-fill P&L is negative with the CI excluding zero,
   the exact phrase the closed `FLEET-STRATEGIES-BYPASS-SAFE-GATES` decision used.
2. **None of the four already-named winning days (2026-08-06, 2026-08-13, 2026-08-27,
   2026-08-28) loses more than 10% of that day's TOTAL arm P&L** (bypass + control +
   every other source that day, from the arm's own broker fills) **to removing its
   bypass-cohort trades.** This guards against a change that is "CI-negative on
   average" yet would have gutted one of the four days this project has already
   pointed to as evidence of a working edge — a fix that costs one of the four named
   wins more than a dime on the dollar is not a clean win even with a negative CI.

**Any single failure = the forward evidence does not support routing this arm through
`_perception_for_arm`, full stop.** Reaching the bar is permission to READ the verdict,
never to ship regardless of the read, and this decision rule is not re-opened after the
fact. If the rule is NOT satisfied when the bar is met, the arm's designation text in
`prod-shadow-designation.json` (and anywhere else describing safe-3 as running under
safe's gate set) **stays corrected as already fixed by the closed
`FLEET-STRATEGIES-BYPASS-SAFE-GATES` decision** — the config itself is left as-is, no
trading-path change ships, and this prereg's outcome is logged as a closed, evidence-
based non-action rather than left silently open.

## 6. Falsifier

This shadow's own hypothesis — "safe-role fleet arms should inherit safe's cohort
gates" — is FALSIFIED (not merely "not yet supported") if, once the bar is met, the
bypass cohort's forward CI is not entirely negative (condition 1 fails) OR the 10%
day-loss guard trips on any of the four named days (condition 2 fails). Either failure
is a stated, frozen NO, not grounds to loosen the bar, extend the window, or re-slice
the population until a passing cut is found.

## 7. No free parameters

Every threshold in §4-§6 is copied verbatim from the closed `FLEET-STRATEGIES-BYPASS-
SAFE-GATES` decision text (20-session/20-entry bar per arm, CI-excluding-zero-negative
rule) plus one addition stated explicitly and justified here (the 10%-day-loss guard on
the four named days, added because the closed decision's own consequence-lens section
flagged day-level P&L concentration as the thing worth re-checking before any change
touches those specific days). Nothing in this file was tuned against the in-sample
ledger already in hand — the in-sample numbers quoted in §2 are reported as motivation
for building a forward clock, never as inputs to the bar or the rule.

## 8. Build step (structured, for machine reference)

```json
{
  "build_step": {
    "id": "FLEET-GATE-LEAK-SHADOW",
    "queue_source": "automation/overnight/queue.md",
    "closes_decision": "FLEET-STRATEGIES-BYPASS-SAFE-GATES",
    "frozen_date": "2026-09-03",
    "in_sample_cutoff": "2026-09-03",
    "forward_start_date": "2026-09-04",
    "backfill": "2026-08-06 through in_sample_cutoff -- descriptive only, not judged",
    "decision_focus_arms": ["safe-3", "safe-1"],
    "out_of_scope_arms": ["risky-1", "risky-3"],
    "entry_window_sec": 300,
    "bar": {
      "min_forward_sessions": 20,
      "min_real_bypass_entries": 20
    },
    "decision_rule": {
      "session_clustered_ci_upper_lt_zero": true,
      "no_named_day_loses_more_than_10pct_of_its_pnl": true,
      "all_required": true,
      "softenable": false
    },
    "named_winning_days": ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"],
    "route_target_on_pass": "fleet_executor._perception_for_arm",
    "route_change_type": "trading_path",
    "route_change_earliest_date": "2026-10-30",
    "artifacts": {
      "ledger": "analysis/recommendations/fleet-gate-leak-ledger.jsonl",
      "summary": "analysis/recommendations/fleet-gate-leak-summary.json",
      "builder": "setup/scripts/fleet_gate_leak_shadow.py",
      "scheduled_task": "Gamma_FleetGateLeakShadow",
      "install_script": "setup/install-fleet-gate-leak-shadow.ps1"
    },
    "do_not": [
      "act on the in-sample (on/before 2026-09-03) ledger as if it were a forward verdict",
      "route risky-1/risky-3 through this same rule -- out of scope, unresolved separately",
      "soften the bar or the decision rule in sections 4-5 after forward data starts arriving",
      "ship the route change before 2026-10-30 regardless of what the forward read shows"
    ]
  }
}
```

## 9. What this instrument is not

Descriptive and shadow-only. It never calls `fleet_executor._perception_for_arm`, never
edits `accounts.json`/`strategies.py`/`build_shared_signal.py`, and never places an
order. A positive read here is the PERMISSION for a separate, later 2026-10-30
ratification decision to cite this ledger as its forward evidence base — never itself
sufficient to ship the change, exactly the two-step contract every sibling shadow clock
in this repo (`tp1_r50_forward_shadow.py`, `stop_mode_shadow_ledger.py`,
`day_throttle_shadow.py`) already uses.

## 10. Revert

Whole instrument, one shot: `Unregister-ScheduledTask -TaskName
Gamma_FleetGateLeakShadow -Confirm:$false` + delete `setup/scripts/
fleet_gate_leak_shadow.py` + `setup/install-fleet-gate-leak-shadow.ps1` + this file.
Nothing on the trading path depends on this instrument — it is an analysis-only leaf,
exactly like `Gamma_LadderRungShadow`.
