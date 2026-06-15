# Backtest Summary — production_rules_v1

**Window:** 2026-03-15 to 2026-05-07
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-05-07T01:44:26

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 37 |
| Bars evaluated | 2,610 |
| High-score bars (≥7/10) | 860 |
| **Trades fired** | **13** |
| Winners | 8 (62%) |
| Losers | 5 |
| Total P&L (3 contracts each) | **$102** |
| Avg P&L / trade | $8 |
| Avg winner | $85 |
| Avg loser | $-116 |
| Avg return on premium | -1.7% |
| Avg hold | 47 min |
| Max drawdown (sequential) | $-243 |
| Win/loss ratio | 0.74x |
| Expectancy per trade | $8 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 7 |
| HIGH | 6 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 2 |
| MORNING | 2 |
| MIDDAY | 5 |
| AFTERNOON | 3 |
| POWER_HOUR | 1 |

## By exit reason

| Reason | Count |
|---|---|
| TP1_THEN_RUNNER_BE_STOP | 7 |
| EXIT_ALL_PREMIUM_STOP | 3 |
| EXIT_ALL_LEVEL_STOP | 2 |
| TP1_THEN_RUNNER_TIME | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 13 | FAIL |
| Win rate | ≥ 45% | 62% | PASS |
| Avg W/L ratio | ≥ 1.5x | 0.74x | FAIL |
| Expectancy / trade | > 0 | $8 | PASS |

## Caveats

- **Pricing is approximate.** Black-Scholes with `IV = VIX/100`. Real ATM 0DTE IV is typically 0.5-1.5x VIX depending on regime. Real fills include bid-ask spread (we use mid). Expect ±10-15% P&L noise vs a real-fill replay.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.