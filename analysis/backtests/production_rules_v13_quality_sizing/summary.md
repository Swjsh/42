# Backtest Summary — production_rules_v13_quality_sizing

**Window:** 2026-03-15 to 2026-05-07
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-05-08T00:06:51

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 38 |
| Bars evaluated | 2,541 |
| High-score bars (≥7/10) | 831 |
| **Trades fired** | **56** |
| Winners | 27 (48%) |
| Losers | 29 |
| Total P&L (3 contracts each) | **$3021** |
| Avg P&L / trade | $54 |
| Avg winner | $215 |
| Avg loser | $-96 |
| Avg return on premium | 6.6% |
| Avg hold | 32 min |
| Max drawdown (sequential) | $-616 |
| Win/loss ratio | 2.24x |
| Expectancy per trade | $54 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 20 |
| HIGH | 36 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 7 |
| MORNING | 12 |
| MIDDAY | 29 |
| AFTERNOON | 3 |
| POWER_HOUR | 5 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 18 |
| TP1_THEN_RUNNER_BE_STOP | 15 |
| EXIT_ALL_LEVEL_STOP | 10 |
| TP1_THEN_RUNNER_TIME | 8 |
| TP1_THEN_RUNNER_RIBBON | 4 |
| EXIT_ALL_RIBBON_FLIP_BACK | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 56 | PASS |
| Win rate | ≥ 45% | 48% | PASS |
| Avg W/L ratio | ≥ 1.5x | 2.24x | PASS |
| Expectancy / trade | > 0 | $54 | PASS |

## Caveats

- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.