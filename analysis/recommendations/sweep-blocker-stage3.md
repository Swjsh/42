# BEARISH_SWEEP_BLOCKER — Stage-3 Aggregate Sharpe Report

_Generated: 2026-05-21T03:30:17_
_Window: 2025-01-01 ->2026-05-07 (16 months)_

## Verdict

**Recommendation: REJECT**

- Sharpe improved: FAIL (Δ-0.049)
- P&L not regressed: FAIL (Δ$-650)
- J-edge preserved: FAIL (edge_capture Δ+0)

## Aggregate Metrics

| Metric | Baseline | With Gate | Delta |
|---|---:|---:|---:|
| Trades | 360 | 358 | -2 |
| Total P&L | $+6022 | $+5372 | $-650 |
| Win Rate | 22.2% | 22.4% | +0.1pp |
| Sharpe | 0.663 | 0.614 | -0.049 |
| Max Drawdown | $-7252 | $-7252 | $+0 |
| Trades/Day | 1.071 | 1.065 | -0.006 |

## Blocked Trades Analysis

**3 trades blocked by sweep_blocker**  (aggregate P&L of blocked trades: $+1622)

| Date | Time | Dir | Level | P&L blocked | Triggers |
|---|---|---|---|---:|---|
| 2025-03-11 | 13:05 | P | 554.0 | $+0 | level_rejection |
| 2025-12-10 | 15:20 | P | 685.0 | $-528 | level_reclaim, ribbon_flip |
| 2025-12-10 | 15:50 | P | 684.5572250120026 | $+2150 | level_reclaim, confluence |

## J Source-of-Truth Day Check

| Date | Category | Baseline | With Gate | Delta |
|---|---|---:|---:|---:|
| 2026-04-29 | WINNER | $+0 | $+0 | $+0 |
| 2026-05-01 | WINNER | $-360 | $-360 | $+0 |
| 2026-05-04 | WINNER | $+220 | $+220 | $+0 |
| 2026-05-05 | LOSER | $+0 | $+0 | $+0 |
| 2026-05-06 | LOSER | $-175 | $-175 | $+0 |
| 2026-05-07 | LOSER | $-157 | $-157 | $+0 |

---

_Stage-3 script: `backtest/autoresearch/sweep_blocker_stage3.py`_
_Candidate: `strategy/candidates/2026-05-16-bearish-sweep-blocker.md`_
_Primitive: `crypto/lib/sweep.py` + `backtest/lib/filters.py` `_detect_sweep_at_level()`_