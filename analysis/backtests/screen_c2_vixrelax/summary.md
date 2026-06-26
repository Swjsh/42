# Backtest Summary — screen_c2_vixrelax

**Window:** 2026-05-08 to 2026-06-16
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** [8]
**Run at:** 2026-06-21T11:08:35

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 27 |
| Bars evaluated | 1,797 |
| High-score bars (≥7/10) | 1062 |
| **Trades fired** | **39** |
| Winners | 17 (44%) |
| Losers | 22 |
| Total P&L (3 contracts each) | **$7088** |
| Avg P&L / trade | $182 |
| Avg winner | $718 |
| Avg loser | $-232 |
| Avg return on premium | 8.2% |
| Avg hold | 29 min |
| Max drawdown (sequential) | $-1423 |
| Win/loss ratio | 3.09x |
| Expectancy per trade | $182 |

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
| MORNING | 16 |
| MIDDAY | 12 |
| AFTERNOON | 1 |
| POWER_HOUR | 7 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 22 |
| TP1_THEN_RUNNER_RIBBON | 7 |
| EXIT_ALL_TIME_STOP | 3 |
| EXIT_ALL_RIBBON_FLIP_BACK | 3 |
| TP1_THEN_RUNNER_BE_STOP | 3 |
| TP1_THEN_RUNNER_TIME | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 39 | PASS |
| Win rate | ≥ 45% | 44% | FAIL |
| Avg W/L ratio | ≥ 1.5x | 3.09x | PASS |
| Expectancy / trade | > 0 | $182 | PASS |

## Caveats

- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.