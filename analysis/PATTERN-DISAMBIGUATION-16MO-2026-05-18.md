# Pattern Disambiguation — 16-mo backtest findings (2026-05-18)

Run: `python backtest/autoresearch/pattern_backtest.py --range 2025-01-02 2026-05-15 --csv backtest/data/spy_5m_2025-01-01_2026-05-15.csv`

## TL;DR

1. **Disambiguator works**: today's 12:30 conflict resolved correctly — bullish failed_breakdown_wick won (next bar WIN), bearish double_top rejected. WR 35.7% -> 42.9% on the single day.
2. **Conflicts are RARE**: 48 in 16 months (~1 every 7 trading days). Disambiguator's narrow purpose: a tie-breaker.
3. **The MUCH bigger lever is a CONTRA-TREND FILTER**: every detector scores +2.5pp to +15.5pp better when its bias is contrary to the prevailing trend.

## Headline numbers (16-mo range 2025-01-02 -> 2026-05-15)

- 342 days scanned
- 3,196 raw pattern hits
- 2,376 graded outcomes (WIN+LOSS)
- Overall RAW WR: 49.6%
- Overall DISAMBIGUATED WR: 49.5% (effectively flat; conflicts are too rare to move headline)
- Conflicts found: 50 (1.5% of all hits)
- Conflict resolution WR: 47.9% (when 2 detectors fire opposite, regime-resolved pick is barely a coin flip)

## Regime breakdown (the gold)

| Detector | Aligned WR | Contrary WR | Delta | Sample sizes |
|---|---:|---:|---:|---|
| `double_bottom` | 49.5% | **54.3%** | **+4.8pp** | aligned n=307, contrary n=752 |
| `double_top` | 43.6% | **48.0%** | **+4.4pp** | aligned n=250, contrary n=544 |
| `failed_breakdown_wick` | 36.8% | **52.3%** | **+15.5pp** | aligned n=19, contrary n=176 |
| `momentum_acceleration` | 44.9% | **47.4%** | **+2.5pp** | aligned n=107, contrary n=97 |
| `rejection_at_level_bearish` | 35.0% | **46.2%** | **+11.2pp** | aligned n=20, contrary n=104 |

**Reading: every detector lifts when contrary to the 20-bar trend. The biggest jumps (failed_breakdown_wick +15.5pp, rejection_at_level +11.2pp) are precisely the reversal-at-level patterns — they ARE the "wick against the trend" archetype.**

## Confidence band (already documented)

| Conf band | n | WR |
|---|---:|---:|
| `<0.60` | 271 | 47.6% |
| `0.60-0.70` | 1043 | 51.0% |
| `0.70-0.80` | 833 | 48.5% |
| `0.80+` | 229 | 49.3% |

Sweet spot is 0.60-0.70; high-confidence (0.80+) actually under-performs. Confidence formula calibration is queued.

## What ships next

1. **`contra_trend_filter` primitive** — boolean helper: "is this hit contrary to its 20-bar regime?". Heartbeat would consume this as a confidence boost.
2. **Nightly gym reps** — `Gamma_PatternGymOvernight` task fires nightly, replays the prior day's bars, produces a scorecard, appends to growing `analysis/pattern-gym-history.jsonl`.
3. **Prior-day context bars** — `_load_bars_for_date` extended to load N prior trading days so SMA50 (richer regime signal) can replace SMA20 when called from real heartbeat (currently has full history).
