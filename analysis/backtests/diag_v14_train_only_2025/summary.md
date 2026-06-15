# Backtest Summary — diag_v14_train_only_2025

**Window:** 2025-01-01 to 2025-12-31
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-05-09T01:03:53

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 249 |
| Bars evaluated | 17,483 |
| High-score bars (≥7/10) | 5261 |
| **Trades fired** | **142** |
| Winners | 18 (13%) |
| Losers | 124 |
| Total P&L (3 contracts each) | **$-285** |
| Avg P&L / trade | $-2 |
| Avg winner | $189 |
| Avg loser | $-30 |
| Avg return on premium | -0.7% |
| Avg hold | 12 min |
| Max drawdown (sequential) | $-1630 |
| Win/loss ratio | 6.36x |
| Expectancy per trade | $-2 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 15 |
| MID | 109 |
| HIGH | 18 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 8 |
| MORNING | 39 |
| MIDDAY | 63 |
| AFTERNOON | 14 |
| POWER_HOUR | 18 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 124 |
| TP1_THEN_RUNNER_BE_STOP | 10 |
| TP1_THEN_RUNNER_TARGET | 4 |
| TP1_THEN_RUNNER_TIME | 3 |
| EXIT_ALL_RIBBON_FLIP_BACK | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 142 | PASS |
| Win rate | ≥ 45% | 13% | FAIL |
| Avg W/L ratio | ≥ 1.5x | 6.36x | PASS |
| Expectancy / trade | > 0 | $-2 | FAIL |

## Caveats

- **Pricing is approximate.** Black-Scholes with `IV = VIX/100`. Real ATM 0DTE IV is typically 0.5-1.5x VIX depending on regime. Real fills include bid-ask spread (we use mid). Expect ±10-15% P&L noise vs a real-fill replay.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.