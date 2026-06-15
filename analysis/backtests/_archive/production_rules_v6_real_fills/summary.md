# Backtest Summary — production_rules_v6_real_fills

**Window:** 2026-03-15 to 2026-05-07
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-05-07T18:56:08

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 37 |
| Bars evaluated | 2,670 |
| High-score bars (≥7/10) | 736 |
| **Trades fired** | **13** |
| Winners | 9 (69%) |
| Losers | 4 |
| Total P&L (3 contracts each) | **$891** |
| Avg P&L / trade | $69 |
| Avg winner | $134 |
| Avg loser | $-78 |
| Avg return on premium | 24.8% |
| Avg hold | 17 min |
| Max drawdown (sequential) | $-124 |
| Win/loss ratio | 1.72x |
| Expectancy per trade | $69 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 7 |
| HIGH | 6 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 2 |
| MORNING | 2 |
| MIDDAY | 5 |
| AFTERNOON | 3 |
| POWER_HOUR | 1 |

## By exit reason

| Reason | Count |
|---|---|
| TP1_THEN_RUNNER_BE_STOP | 7 |
| EXIT_ALL_LEVEL_STOP | 4 |
| TP1_THEN_RUNNER_TARGET | 2 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 13 | FAIL |
| Win rate | ≥ 45% | 69% | PASS |
| Avg W/L ratio | ≥ 1.5x | 1.72x | PASS |
| Expectancy / trade | > 0 | $69 | PASS |

## Caveats

- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.