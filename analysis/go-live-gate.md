# Go-Live Gate -- RED

_generated 2026-09-03T03:35:04 ET by `setup/scripts/go_live_gate.py`. Reporting instrument only -- arms nothing. Live-money arming stays J's decision (OP-0 #1)._

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
| safe-3 | 27 | 0.335 | 0.243 | 0.333 | FAIL |
| safe-2 | 31 | 0.324 | 0.245 | 0.321 | FAIL |
| risky-1 | 27 | 0.371 | 0.261 | 0.366 | FAIL |
| bold-2 | 21 | 0.346 | 0.27 | 0.342 | FAIL |

## Reconciliation -- per arm

| Arm | Window | Broker P&L | Ledger P&L | Est. fees | Diff (fee-adj) | Verdict |
|---|---|---|---|---|---|---|
| safe-3 | 2026-08-03..2026-09-01 | $852.70 | $863.00 | $10.75 | $0.45 | PASS |
| safe-2 | 2026-08-03..2026-09-01 | $780.30 | $795.00 | $13.69 | $-1.01 | PASS |
| risky-1 | 2026-08-03..2026-09-01 | $1,495.12 | $1,520.00 | $25.85 | $0.97 | PASS |
| bold-2 | 2026-08-03..2026-09-01 | $609.02 | $624.00 | $15.50 | $0.52 | PASS |

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

**arm=safe-3 window=2026-09-01..2026-10-30 days_scored=1/20 current CI_lo=None status=INSUFFICIENT_DAYS**

Extended clock (disclosure only, never the pass bar) through 2026-10-30: 1/40 days scored, as-traded CI_lo=None.

1/20 scored trading days for arm 'safe-3' in 2026-09-01..2026-10-30. Not yet scorable -- reported as INSUFFICIENT_DAYS, never PASS or FAIL, on a window that hasn't reached its own registered day-count bar.

## Frozen-config-window disclosure (since 2026-08-31)

_disclosure only -- pass criterion unchanged (criterion 1 stays full-history)_

| Arm | n_days | as-traded CI_lo |
|---|---|---|
| safe-3 | 1 | None |
| safe-2 | 2 | 0.0 |
| risky-1 | 1 | None |
| bold-2 | 2 | 0.0 |

## Effective evidence disclosure

| Arm | Days on current config (>=09-01) | Days post-ladder (>=08-11) | Best-2-days share of gross winners |
|---|---|---|---|
| safe-3 | 1 | 10 | 0.405 |
| safe-2 | 2 | 15 | 0.38 |
| risky-1 | 1 | 10 | 0.463 |
| bold-2 | 2 | 13 | 0.354 |

Book rollup ex-best-day P(PF<=1) = 0.634

## Plan reachability disclosure

_zero-variance best case -- constant $/day over remaining trading days that would push CI-lower(2.5%) above 1.0, as of 2026-09-03_

| Arm | Config-freeze close (09-29) | Tight-ladder clock close (10-30) |
|---|---|---|
| safe-3 | $171.08/day | $67.43/day |
| safe-2 | $193.35/day | $77.11/day |
| risky-1 | $162.87/day | $66.79/day |
| bold-2 | $152.24/day | $63.95/day |

## Trailing 20-trading-day view (DISCLOSURE ONLY -- not a bar)

_same three-view bootstrap as criterion 1 (as-traded / ex-best-day / cost-adjusted, PF CI-lower 2.5%), scored per arm over only its most recent 20 trading days. The pass criterion stays the aggregate, full-history statistical_criterion in criteria.statistical -- this view never substitutes for it._

| Arm | Window | n_days | as-traded CI_lo | ex-best-day CI_lo | cost-adj CI_lo | Verdict |
|---|---|---|---|---|---|---|
| safe-3 | 2026-07-15..2026-09-02 | 20/20 | 0.377 | 0.279 | 0.375 | FAIL |
| safe-2 | 2026-08-04..2026-09-02 | 20/20 | 0.406 | 0.301 | 0.403 | FAIL |
| risky-1 | 2026-07-15..2026-09-02 | 20/20 | 0.434 | 0.312 | 0.429 | FAIL |
| bold-2 | 2026-07-02..2026-09-02 | 20/20 | 0.35 | 0.274 | 0.346 | FAIL |

## REGIME COVERAGE (disclosure only)

_never gates the overall verdict -- answers whether the evidence window has actually seen a stressed market_

| Window | n_days | VIX daily-max min/max | days VIX>20 | SPY cum. return | worst day | days down >1% |
|---|---|---|---|---|---|---|
| lifetime | 6 | 14.82/16.8 | 0 | -0.097% | {'date': '2026-09-01', 'ret_pct': -0.8} | 0 |
| frozen (since 2026-09-01) | 2 | 16.21/16.8 | 0 | -0.264% | {'date': '2026-09-01', 'ret_pct': -0.8} | 0 |

**calm-only window -- a GREEN here is untested in stress**

Full machine payload: `analysis/go-live-gate.json`. Runbook: `markdown/planning/LIVE-FLIP-RUNBOOK.md`.
