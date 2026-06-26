# Backtest Summary — screen_c4_spreadoff

**Window:** 2026-05-08 to 2026-06-16
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** [6]
**Run at:** 2026-06-21T11:08:44

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 27 |
| Bars evaluated | 1,789 |
| High-score bars (≥7/10) | 731 |
| **Trades fired** | **39** |
| Winners | 17 (44%) |
| Losers | 22 |
| Total P&L (3 contracts each) | **$14176** |
| Avg P&L / trade | $363 |
| Avg winner | $1091 |
| Avg loser | $-198 |
| Avg return on premium | 11.6% |
| Avg hold | 36 min |
| Max drawdown (sequential) | $-2003 |
| Win/loss ratio | 5.50x |
| Expectancy per trade | $363 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 38 |
| HIGH | 1 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 3 |
| MORNING | 14 |
| MIDDAY | 12 |
| AFTERNOON | 4 |
| POWER_HOUR | 6 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 22 |
| TP1_THEN_RUNNER_RIBBON | 6 |
| TP1_THEN_RUNNER_TIME | 3 |
| EXIT_ALL_RIBBON_FLIP_BACK | 3 |
| TP1_THEN_RUNNER_BE_STOP | 3 |
| EXIT_ALL_TIME_STOP | 2 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 39 | PASS |
| Win rate | ≥ 45% | 44% | FAIL |
| Avg W/L ratio | ≥ 1.5x | 5.50x | PASS |
| Expectancy / trade | > 0 | $363 | PASS |

## Caveats

- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.