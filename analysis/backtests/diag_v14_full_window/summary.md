# Backtest Summary — diag_v14_full_window

**Window:** 2025-01-01 to 2026-05-07
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-05-09T01:04:32

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 336 |
| Bars evaluated | 23,448 |
| High-score bars (≥7/10) | 7488 |
| **Trades fired** | **230** |
| Winners | 40 (17%) |
| Losers | 190 |
| Total P&L (3 contracts each) | **$-377** |
| Avg P&L / trade | $-2 |
| Avg winner | $142 |
| Avg loser | $-32 |
| Avg return on premium | -0.5% |
| Avg hold | 14 min |
| Max drawdown (sequential) | $-2081 |
| Win/loss ratio | 4.45x |
| Expectancy per trade | $-2 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 22 |
| MID | 153 |
| HIGH | 55 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 15 |
| MORNING | 69 |
| MIDDAY | 103 |
| AFTERNOON | 18 |
| POWER_HOUR | 25 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 190 |
| TP1_THEN_RUNNER_BE_STOP | 30 |
| TP1_THEN_RUNNER_TARGET | 4 |
| TP1_THEN_RUNNER_TIME | 4 |
| EXIT_ALL_RIBBON_FLIP_BACK | 1 |
| TP1_THEN_RUNNER_RIBBON | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 230 | PASS |
| Win rate | ≥ 45% | 17% | FAIL |
| Avg W/L ratio | ≥ 1.5x | 4.45x | PASS |
| Expectancy / trade | > 0 | $-2 | FAIL |

## Caveats

- **Pricing is approximate.** Black-Scholes with `IV = VIX/100`. Real ATM 0DTE IV is typically 0.5-1.5x VIX depending on regime. Real fills include bid-ask spread (we use mid). Expect ±10-15% P&L noise vs a real-fill replay.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.