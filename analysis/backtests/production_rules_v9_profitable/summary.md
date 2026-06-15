# Backtest Summary — production_rules_v9_profitable

**Window:** 2026-03-15 to 2026-05-07
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-05-07T22:26:49

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 38 |
| Bars evaluated | 2,683 |
| High-score bars (≥7/10) | 942 |
| **Trades fired** | **26** |
| Winners | 16 (62%) |
| Losers | 10 |
| Total P&L (3 contracts each) | **$1332** |
| Avg P&L / trade | $51 |
| Avg winner | $231 |
| Avg loser | $-237 |
| Avg return on premium | 7.6% |
| Avg hold | 54 min |
| Max drawdown (sequential) | $-733 |
| Win/loss ratio | 0.98x |
| Expectancy per trade | $51 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 10 |
| HIGH | 16 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 2 |
| MORNING | 4 |
| MIDDAY | 9 |
| AFTERNOON | 8 |
| POWER_HOUR | 3 |

## By exit reason

| Reason | Count |
|---|---|
| TP1_THEN_RUNNER_RIBBON | 9 |
| EXIT_ALL_PREMIUM_STOP | 8 |
| TP1_THEN_RUNNER_TIME | 6 |
| EXIT_ALL_TIME_STOP | 1 |
| TP1_THEN_RUNNER_BE_STOP | 1 |
| EXIT_ALL_LEVEL_STOP | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 26 | PASS |
| Win rate | ≥ 45% | 62% | PASS |
| Avg W/L ratio | ≥ 1.5x | 0.98x | FAIL |
| Expectancy / trade | > 0 | $51 | PASS |

## Caveats

- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.