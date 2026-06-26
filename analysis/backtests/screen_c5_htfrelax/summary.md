# Backtest Summary — screen_c5_htfrelax

**Window:** 2026-05-08 to 2026-06-16
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** [11]
**Run at:** 2026-06-21T11:08:48

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 27 |
| Bars evaluated | 1,798 |
| High-score bars (≥7/10) | 637 |
| **Trades fired** | **43** |
| Winners | 14 (33%) |
| Losers | 29 |
| Total P&L (3 contracts each) | **$2169** |
| Avg P&L / trade | $50 |
| Avg winner | $715 |
| Avg loser | $-270 |
| Avg return on premium | 5.8% |
| Avg hold | 30 min |
| Max drawdown (sequential) | $-4153 |
| Win/loss ratio | 2.64x |
| Expectancy per trade | $50 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 1 |
| MID | 41 |
| HIGH | 1 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 5 |
| MORNING | 14 |
| MIDDAY | 16 |
| AFTERNOON | 3 |
| POWER_HOUR | 5 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 29 |
| TP1_THEN_RUNNER_RIBBON | 5 |
| TP1_THEN_RUNNER_BE_STOP | 3 |
| TP1_THEN_RUNNER_TIME | 2 |
| EXIT_ALL_TIME_STOP | 2 |
| EXIT_ALL_RIBBON_FLIP_BACK | 2 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 43 | PASS |
| Win rate | ≥ 45% | 33% | FAIL |
| Avg W/L ratio | ≥ 1.5x | 2.64x | PASS |
| Expectancy / trade | > 0 | $50 | PASS |

## Caveats

- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.