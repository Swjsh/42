# Backtest Summary — screen_baseline_recent

**Window:** 2026-05-08 to 2026-06-16
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-06-21T11:07:51

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 27 |
| Bars evaluated | 1,799 |
| High-score bars (≥7/10) | 648 |
| **Trades fired** | **35** |
| Winners | 14 (40%) |
| Losers | 21 |
| Total P&L (3 contracts each) | **$5024** |
| Avg P&L / trade | $144 |
| Avg winner | $694 |
| Avg loser | $-223 |
| Avg return on premium | 8.0% |
| Avg hold | 29 min |
| Max drawdown (sequential) | $-1588 |
| Win/loss ratio | 3.11x |
| Expectancy per trade | $144 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 34 |
| HIGH | 1 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 3 |
| MORNING | 13 |
| MIDDAY | 12 |
| AFTERNOON | 2 |
| POWER_HOUR | 5 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 21 |
| TP1_THEN_RUNNER_RIBBON | 5 |
| EXIT_ALL_RIBBON_FLIP_BACK | 3 |
| TP1_THEN_RUNNER_BE_STOP | 3 |
| EXIT_ALL_TIME_STOP | 2 |
| TP1_THEN_RUNNER_TIME | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 35 | PASS |
| Win rate | ≥ 45% | 40% | FAIL |
| Avg W/L ratio | ≥ 1.5x | 3.11x | PASS |
| Expectancy / trade | > 0 | $144 | PASS |

## Caveats

- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.