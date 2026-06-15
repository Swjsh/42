# Backtest Summary — diag_v14_validate_only

**Window:** 2026-02-14 to 2026-05-07
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-05-09T01:02:00

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 57 |
| Bars evaluated | 3,991 |
| High-score bars (≥7/10) | 1500 |
| **Trades fired** | **59** |
| Winners | 14 (24%) |
| Losers | 45 |
| Total P&L (3 contracts each) | **$-57** |
| Avg P&L / trade | $-1 |
| Avg winner | $107 |
| Avg loser | $-35 |
| Avg return on premium | -0.4% |
| Avg hold | 14 min |
| Max drawdown (sequential) | $-576 |
| Win/loss ratio | 3.10x |
| Expectancy per trade | $-1 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 23 |
| HIGH | 36 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 7 |
| MORNING | 13 |
| MIDDAY | 31 |
| AFTERNOON | 3 |
| POWER_HOUR | 5 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 45 |
| TP1_THEN_RUNNER_BE_STOP | 13 |
| TP1_THEN_RUNNER_TIME | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 59 | PASS |
| Win rate | ≥ 45% | 24% | FAIL |
| Avg W/L ratio | ≥ 1.5x | 3.10x | PASS |
| Expectancy / trade | > 0 | $-1 | FAIL |

## Caveats

- **Pricing is approximate.** Black-Scholes with `IV = VIX/100`. Real ATM 0DTE IV is typically 0.5-1.5x VIX depending on regime. Real fills include bid-ask spread (we use mid). Expect ±10-15% P&L noise vs a real-fill replay.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.