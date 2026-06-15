# Backtest Summary — missed_week_safe

**Window:** 2026-05-19 to 2026-05-29
**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON
**Filters disabled:** none (full production rules)
**Run at:** 2026-05-31T10:00:58

## Top-line numbers

| Metric | Value |
|---|---|
| Trading days in window | 8 |
| Bars evaluated | 538 |
| High-score bars (≥7/10) | 104 |
| **Trades fired** | **8** |
| Winners | 2 (25%) |
| Losers | 6 |
| Total P&L (3 contracts each) | **$-557** |
| Avg P&L / trade | $-70 |
| Avg winner | $122 |
| Avg loser | $-134 |
| Avg return on premium | -11.3% |
| Avg hold | 13 min |
| Max drawdown (sequential) | $-802 |
| Win/loss ratio | 0.92x |
| Expectancy per trade | $-70 |

## By IV regime

| Regime | Trades |
|---|---|
| LOW | 0 |
| MID | 8 |
| HIGH | 0 |

## By time-of-day bucket

| Bucket | Trades |
|---|---|
| OPEN_DRIVE | 2 |
| MORNING | 3 |
| MIDDAY | 3 |
| AFTERNOON | 0 |
| POWER_HOUR | 0 |

## By exit reason

| Reason | Count |
|---|---|
| EXIT_ALL_PREMIUM_STOP | 3 |
| EXIT_ALL_RIBBON_FLIP_BACK | 2 |
| EXIT_ALL_LEVEL_STOP | 2 |
| TP1_THEN_RUNNER_RIBBON | 1 |

## Live deployment threshold check

| Threshold | Required | Actual | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 8 | FAIL |
| Win rate | ≥ 45% | 25% | FAIL |
| Avg W/L ratio | ≥ 1.5x | 0.92x | FAIL |
| Expectancy / trade | > 0 | $-70 | FAIL |

## Caveats

- **Pricing is real OPRA option bars** from Alpaca historical (cached at `backtest/data/options/`). Entry uses bar VWAP (intra-bar volume-weighted average); stops/targets/exits use bar high/low/close. No bid-ask spread modeled — we use the bar's price quotes directly. Expect ±5-10% noise vs an actual broker fill.
- **Levels are auto-detected** from premarket clusters + prior day H/L + 5-day swing + round numbers. Real playbook trades sometimes target levels J drew based on judgment beyond rolling-high rules — those won't be detected here.
- **No multi-day trendlines.** Confluence trigger is approximated as 'rejected level matches a multi-day swing within $0.30'. The chart-anatomy `multi_day_trendline` requires swing-point + line-fitting which isn't implemented.
- **First-trigger-wins.** Engine takes the first trade that passes filters each day. J's discretion (waiting for the 'best' setup) isn't modeled.
- **Filters disabled (if any) are listed at the top** — interpret stats accordingly.