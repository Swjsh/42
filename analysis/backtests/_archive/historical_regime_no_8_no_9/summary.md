# Backtest Summary — historical_regime_no_8_no_9

**Window:** 2026-03-15 to 2026-05-07
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** [8, 9]
**Run at:** 2026-05-07T01:45:05

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 37 |
| Bars evaluated | 2,453 |
| High-score bars (≥7/10) | 2352 |
| **Trades fired** | **38** |
| Winners | 19 (50%) |
| Losers | 19 |
| Total P&L (3 contracts each) | **$821** |
| Avg P&L / trade | $22 |
| Avg winner | $142 |
| Avg loser | $-98 |
| Avg return on premium | 2.6% |
| Avg hold | 37 min |
| Max drawdown (sequential) | $-755 |
| Win/loss ratio | 1.44x |
| Expectancy per trade | $22 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 14 |
| HIGH | 24 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 9 |
| MORNING | 8 |
| MIDDAY | 14 |
| AFTERNOON | 5 |
| POWER_HOUR | 2 |

## By exit reason

| Reason | Count |
|---|---|
| TP1_THEN_RUNNER_BE_STOP | 16 |
| EXIT_ALL_LEVEL_STOP | 15 |
| EXIT_ALL_PREMIUM_STOP | 3 |
| TP1_THEN_RUNNER_TARGET | 2 |
| EXIT_ALL_RIBBON_FLIP_BACK | 1 |
| TP1_THEN_RUNNER_TIME | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 38 | PASS |
| Win rate | ≥ 45% | 50% | PASS |
| Avg W/L ratio | ≥ 1.5x | 1.44x | FAIL |
| Expectancy / trade | > 0 | $22 | PASS |

## Caveats

- **Pricing is approximate.** Black-Scholes with `IV = VIX/100`. Real ATM 0DTE IV is typically 0.5-1.5x VIX depending on regime. Real fills include bid-ask spread (we use mid). Expect ±10-15% P&L noise vs a real-fill replay.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.