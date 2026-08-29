# Go-Live Gate -- RED

_generated 2026-08-29T11:42:21 ET by `setup/scripts/go_live_gate.py`. Reporting instrument only -- arms nothing. Live-money arming stays J's decision (OP-0 #1)._

| Criterion | Verdict |
|---|---|
| 1. Statistical (per-arm CI-lower>1.0, as-traded + ex-best-day + cost-adjusted) | FAIL |
| 2. Operational (guardrail tests pinned+green) | FAIL |
| 3. Reconciliation (ledger vs live broker equity, all 5 arms) | PASS |
| 4. Behavioural (rule breaks / manual overrides in trailing window) | PASS |
| 5. Prod-shadow (dedicated shadow arm net of costs) | FAIL (NOT_WIRED) |

## Statistical -- per arm

| Arm | n_days | as-traded CI_lo | ex-best-day CI_lo | cost-adj CI_lo | Verdict |
|---|---|---|---|---|---|
| safe-3 | 26 | 0.356 | 0.259 | 0.353 | FAIL |
| safe-2 | 29 | 0.292 | 0.209 | 0.289 | FAIL |
| risky-1 | 26 | 0.412 | 0.285 | 0.407 | FAIL |
| bold-2 | 19 | 0.358 | 0.282 | 0.354 | FAIL |

## Reconciliation -- per arm

| Arm | Window | Broker P&L | Ledger P&L | Est. fees | Diff (fee-adj) | Verdict |
|---|---|---|---|---|---|---|
| safe-3 | 2026-08-03..2026-08-28 | $852.70 | $863.00 | $10.75 | $0.45 | PASS |
| safe-2 | 2026-08-03..2026-08-28 | $563.04 | $577.00 | $13.11 | $-0.85 | PASS |
| risky-1 | 2026-08-03..2026-08-28 | $1,495.12 | $1,520.00 | $25.85 | $0.97 | PASS |
| bold-2 | 2026-08-03..2026-08-28 | $749.47 | $764.00 | $15.04 | $0.51 | PASS |

## Operational guardrails

| Guard | Verdict |
|---|---|
| eod_flatten_coverage_all_5_arms | PASS |
| eod_flatten_read_failure_fails_open | PASS |
| never_average_down_no_stacked_entry | PASS |
| killswitch_threshold_parity_rule5 | PASS |
| orphan_position_adoption | PASS |
| dead_mans_switch_open_position_on_process_death | FAIL |

## Prod-shadow

No SPY-strategy production-shadow arm identified. The task brief's "C1's shadow arm" reference does not resolve to any artifact found in this repo this session -- reported as a gap, not guessed at. Existing shadow-labeled ledgers found (feature-level, not a go-live shadow track record): analysis/recommendations/catastrophe-cap-shadow-ledger.jsonl, analysis/recommendations/day-throttle-shadow-ledger.jsonl, analysis/recommendations/stop-mode-shadow-ledger.jsonl, analysis/recommendations/vix-floor-shadow-ledger.jsonl

Full machine payload: `analysis/go-live-gate.json`. Runbook: `markdown/planning/LIVE-FLIP-RUNBOOK.md`.
