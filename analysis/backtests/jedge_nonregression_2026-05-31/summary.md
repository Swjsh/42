# Backtest Summary — jedge_nonregression_2026-05-31

**Window:** 2026-04-27 to 2026-05-07
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-05-31T10:04:23

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 9 |
| Bars evaluated | 603 |
| High-score bars (≥7/10) | 186 |
| **Trades fired** | **7** |
| Winners | 2 (29%) |
| Losers | 5 |
| Total P&L (3 contracts each) | **$-215** |
| Avg P&L / trade | $-31 |
| Avg winner | $404 |
| Avg loser | $-204 |
| Avg return on premium | -2.8% |
| Avg hold | 40 min |
| Max drawdown (sequential) | $-952 |
| Win/loss ratio | 1.97x |
| Expectancy per trade | $-31 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 7 |
| HIGH | 0 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 2 |
| MORNING | 2 |
| MIDDAY | 3 |
| AFTERNOON | 0 |
| POWER_HOUR | 0 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 5 |
| EXIT_ALL_RIBBON_FLIP_BACK | 1 |
| TP1_THEN_RUNNER_RIBBON | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 7 | FAIL |
| Win rate | ≥ 45% | 29% | FAIL |
| Avg W/L ratio | ≥ 1.5x | 1.97x | PASS |
| Expectancy / trade | > 0 | $-31 | FAIL |

## Caveats

- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.