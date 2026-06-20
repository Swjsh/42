# Backtest Summary — missed_week_safe

**Window:** 2026-05-19 to 2026-05-29
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-06-15T19:39:51

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 8 |
| Bars evaluated | 553 |
| High-score bars (≥7/10) | 107 |
| **Trades fired** | **3** |
| Winners | 0 (0%) |
| Losers | 3 |
| Total P&L (3 contracts each) | **$-110** |
| Avg P&L / trade | $-37 |
| Avg winner | $0 |
| Avg loser | $-37 |
| Avg return on premium | -8.0% |
| Avg hold | 10 min |
| Max drawdown (sequential) | $-110 |
| Win/loss ratio | 0.00x |
| Expectancy per trade | $-37 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 3 |
| HIGH | 0 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 0 |
| MORNING | 2 |
| MIDDAY | 1 |
| AFTERNOON | 0 |
| POWER_HOUR | 0 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 3 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 3 | FAIL |
| Win rate | ≥ 45% | 0% | FAIL |
| Avg W/L ratio | ≥ 1.5x | 0.00x | FAIL |
| Expectancy / trade | > 0 | $-37 | FAIL |

## Caveats

- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.