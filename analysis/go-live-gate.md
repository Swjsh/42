# Go-Live Gate -- RED

_generated 2026-09-01T20:50:20 ET by `setup/scripts/go_live_gate.py`. Reporting instrument only -- arms nothing. Live-money arming stays J's decision (OP-0 #1)._

| Criterion | Verdict |
|---|---|
| 1. Statistical (per-arm CI-lower>1.0, as-traded + ex-best-day + cost-adjusted) | FAIL |
| 2. Operational (guardrail tests pinned+green) | PASS |
| 3. Reconciliation (ledger vs live broker equity, all 5 arms) | PASS |
| 4. Behavioural (rule breaks / manual overrides in trailing window) | PASS |
| 5. Prod-shadow (dedicated shadow arm net of costs) | FAIL (INSUFFICIENT_DAYS) |

## Statistical -- per arm

| Arm | n_days | as-traded CI_lo | ex-best-day CI_lo | cost-adj CI_lo | Verdict |
|---|---|---|---|---|---|
| safe-3 | 26 | 0.356 | 0.259 | 0.353 | FAIL |
| safe-2 | 30 | 0.333 | 0.253 | 0.329 | FAIL |
| risky-1 | 26 | 0.412 | 0.285 | 0.407 | FAIL |
| bold-2 | 20 | 0.347 | 0.272 | 0.343 | FAIL |

## Reconciliation -- per arm

| Arm | Window | Broker P&L | Ledger P&L | Est. fees | Diff (fee-adj) | Verdict |
|---|---|---|---|---|---|---|
| safe-3 | 2026-08-03..2026-08-31 | $852.70 | $863.00 | $10.75 | $0.45 | PASS |
| safe-2 | 2026-08-03..2026-08-31 | $562.85 | $577.00 | $13.11 | $-1.04 | PASS |
| risky-1 | 2026-08-03..2026-08-31 | $1,495.12 | $1,520.00 | $25.85 | $0.97 | PASS |
| bold-2 | 2026-08-03..2026-08-31 | $749.47 | $764.00 | $15.04 | $0.51 | PASS |

## Operational guardrails

| Guard | Verdict |
|---|---|
| eod_flatten_coverage_all_5_arms | PASS |
| eod_flatten_read_failure_fails_open | PASS |
| never_average_down_no_stacked_entry | PASS |
| killswitch_threshold_parity_rule5 | PASS |
| orphan_position_adoption | PASS |
| dead_mans_switch_open_position_on_process_death | PASS |

## Prod-shadow

**arm=safe-3 window=2026-09-01..2026-09-29 days_scored=0/20 current CI_lo=None status=INSUFFICIENT_DAYS**

Extended clock (disclosure only, never the pass bar) through 2026-10-30: 0/40 days scored, as-traded CI_lo=None.

0/20 scored trading days for arm 'safe-3' in 2026-09-01..2026-09-29. Not yet scorable -- reported as INSUFFICIENT_DAYS, never PASS or FAIL, on a window that hasn't reached its own registered day-count bar.

## Frozen-config-window disclosure (since 2026-08-31)

_disclosure only -- pass criterion unchanged (criterion 1 stays full-history)_

| Arm | n_days | as-traded CI_lo |
|---|---|---|
| safe-3 | -- | INSUFFICIENT |
| safe-2 | 1 | None |
| risky-1 | -- | INSUFFICIENT |
| bold-2 | 1 | None |

## Effective evidence disclosure

| Arm | Days on current config (>=09-01) | Days post-ladder (>=08-11) | Best-2-days share of gross winners |
|---|---|---|---|
| safe-3 | 0 | 9 | 0.405 |
| safe-2 | 1 | 14 | 0.38 |
| risky-1 | 0 | 9 | 0.463 |
| bold-2 | 1 | 12 | 0.354 |

Book rollup ex-best-day P(PF<=1) = 0.573

## Plan reachability disclosure

_zero-variance best case -- constant $/day over remaining trading days that would push CI-lower(2.5%) above 1.0, as of 2026-09-01_

| Arm | Config-freeze close (09-29) | Tight-ladder clock close (10-30) |
|---|---|---|
| safe-3 | $136.58/day | $59.42/day |
| safe-2 | $166.33/day | $65.91/day |
| risky-1 | $115.39/day | $52.45/day |
| bold-2 | $137.64/day | $57.18/day |

Full machine payload: `analysis/go-live-gate.json`. Runbook: `markdown/planning/LIVE-FLIP-RUNBOOK.md`.
