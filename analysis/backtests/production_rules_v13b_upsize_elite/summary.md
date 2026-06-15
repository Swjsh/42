# Backtest Summary — production_rules_v13b_upsize_elite

**Window:** 2026-03-15 to 2026-05-07
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-05-08T00:09:23

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 38 |
| Bars evaluated | 2,512 |
| High-score bars (≥7/10) | 818 |
| **Trades fired** | **63** |
| Winners | 31 (49%) |
| Losers | 32 |
| Total P&L (3 contracts each) | **$4375** |
| Avg P&L / trade | $69 |
| Avg winner | $236 |
| Avg loser | $-91 |
| Avg return on premium | 7.0% |
| Avg hold | 37 min |
| Max drawdown (sequential) | $-416 |
| Win/loss ratio | 2.57x |
| Expectancy per trade | $69 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 25 |
| HIGH | 38 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 7 |
| MORNING | 13 |
| MIDDAY | 34 |
| AFTERNOON | 3 |
| POWER_HOUR | 6 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 19 |
| TP1_THEN_RUNNER_BE_STOP | 15 |
| EXIT_ALL_LEVEL_STOP | 12 |
| TP1_THEN_RUNNER_TIME | 9 |
| TP1_THEN_RUNNER_RIBBON | 7 |
| EXIT_ALL_RIBBON_FLIP_BACK | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 63 | PASS |
| Win rate | ≥ 45% | 49% | PASS |
| Avg W/L ratio | ≥ 1.5x | 2.57x | PASS |
| Expectancy / trade | > 0 | $69 | PASS |

## Caveats

- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.