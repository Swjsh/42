# Backtest Summary — production_rules_v4_with_candlesticks

**Window:** 2026-03-15 to 2026-05-07
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-05-07T17:59:16

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 37 |
| Bars evaluated | 2,599 |
| High-score bars (≥7/10) | 712 |
| **Trades fired** | **17** |
| Winners | 8 (47%) |
| Losers | 9 |
| Total P&L (3 contracts each) | **$135** |
| Avg P&L / trade | $8 |
| Avg winner | $124 |
| Avg loser | $-95 |
| Avg return on premium | 0.2% |
| Avg hold | 39 min |
| Max drawdown (sequential) | $-302 |
| Win/loss ratio | 1.30x |
| Expectancy per trade | $8 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 6 |
| HIGH | 11 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 2 |
| MORNING | 3 |
| MIDDAY | 6 |
| AFTERNOON | 4 |
| POWER_HOUR | 2 |

## By exit reason

| Reason | Count |
|---|---|
| TP1_THEN_RUNNER_BE_STOP | 6 |
| EXIT_ALL_LEVEL_STOP | 6 |
| EXIT_ALL_PREMIUM_STOP | 3 |
| TP1_THEN_RUNNER_TIME | 1 |
| TP1_THEN_RUNNER_TARGET | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 17 | FAIL |
| Win rate | ≥ 45% | 47% | PASS |
| Avg W/L ratio | ≥ 1.5x | 1.30x | FAIL |
| Expectancy / trade | > 0 | $8 | PASS |

## Caveats

- **Pricing is approximate.** Black-Scholes with `IV = VIX/100`. Real ATM 0DTE IV is typically 0.5-1.5x VIX depending on regime. Real fills include bid-ask spread (we use mid). Expect ±10-15% P&L noise vs a real-fill replay.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.