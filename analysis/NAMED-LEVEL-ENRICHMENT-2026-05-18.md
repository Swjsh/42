# Named-Level Enrichment in pattern_backtest — 16-mo findings

> Date: 2026-05-18 evening (Option D ratification)
> Run: `python backtest/autoresearch/pattern_backtest.py --range 2025-01-02 2026-05-15`
> Per OP-25 engine-benefit autonomy.

## TL;DR

`failed_breakdown_wick` + named-level proximity is the **highest-conviction signal** in the engine, with **+10-14pp WR lift**. Other detectors are either flat or slightly hurt by level proximity (the level acts as resistance against the pattern's bias).

## Methodology

For each historical day, `_derive_named_levels()` synthesizes the production-relevant levels from prior-day RTH OHLC:
- **PDH** — prior-day RTH high (★★ Active)
- **PDL** — prior-day RTH low (★★ Active)
- **PDC** — prior-day RTH close (★ Reference)
- **PDO** — target-day RTH open (★ Reference)

For each detector hit, `_nearest_named_level()` finds the closest level within $0.50 of the hit's `key_price`. Hits are tagged `near_named_level=True` if any level within range.

WR breakdown computed per detector × near_named/no_named bucket.

## Per-detector findings (16-mo, 357 days, 5,989 graded hits)

| Detector | near_named WR | no_named WR | Δ pp | Interpretation |
|---|---:|---:|---:|---|
| **`failed_breakdown_wick`** | **59.5%** (n=74) | 49.1% (n=224) | **+10.4pp** | Sweep-and-reclaim of a NAMED level is the strongest signal |
| **`failed_breakdown_wick_contra`** | **62.2%** (n=45) | 48.3% (n=176) | **+13.9pp** | Combined with contra-trend filter, hits 62% WR |
| `double_bottom` | 54.2% (n=517) | 54.0% (n=1129) | +0.2pp | Bar-shape pattern; level proximity neutral |
| `double_bottom_contra` | 56.2% (n=96) | 56.8% (n=407) | -0.6pp | Already strong via contra; level adds nothing |
| `double_top` | 45.0% (n=369) | 47.9% (n=856) | -2.9pp | Slight drag — level may be supporting the bullish reversal |
| `rejection_at_level_bearish` | 41.9% (n=43) | 49.4% (n=162) | -7.5pp | Interesting — when bearish rejection is AT a named level it underperforms |
| `momentum_acceleration` | 46.3% (n=95) | 48.9% (n=237) | -2.6pp | Bar-shape; level neutral |
| `head_and_shoulders_top` | 50.0% (n=88) | 55.4% (n=195) | -5.4pp | Top pattern fading the level |

## The big signal

**`failed_breakdown_wick_contra` + near_named_level**:
- 45 graded hits across 16 months (~3 per month)
- 62.2% WR (28W / 17L)
- This IS the production-grade alert criterion the `numeric_pulse` already filters on (conf ≥ 0.65 + contra-trend + level-proximate).
- Now formally validated as the highest-edge signal we have.

## What ships from this finding

1. **`_derive_named_levels()` + `_nearest_named_level()`** primitives in `pattern_backtest.py` — synthesizes PDH/PDL/PDC/PDO from CSV bars per day.
2. **Each hit dict now includes** `nearest_named_level` (full info) + `near_named_level` (bool) fields.
3. **Aggregate output** now includes `named_level_breakdown` keyed by `{detector}::{near_named|no_named}` with WR + n per bucket.
4. **No changes to live doctrine** — this is observation/enrichment only. The `numeric_pulse` already alerts on the production criterion (level-proximate + contra + conf ≥ 0.65).

## Implications

- **Pattern detectors should NOT be uniformly level-gated.** Only `failed_breakdown_wick` benefits.
- **The "BULLISH_RECLAIM_RIDE_THE_RIBBON" archetype** maps cleanly to `failed_breakdown_wick` + level proximity + contra-trend. This is the doctrine archetype Bold blocked on 5/18 morning despite 4 separate BULL 10-11/11 setups firing — exactly the foot-gun the fast-path executor + numeric-alert pipeline now addresses.
- **fast_path_executor's filter pipeline already** requires `level_proximate` for high-conviction alerts. The 16-mo data confirms this gate is the right one for the failed_breakdown_wick pattern class. The next-cycle work: extend the alert pipeline to also gate on contra-trend + named-level for the OTHER detector classes where appropriate (or NOT, for detectors where named-level hurts WR).

## Production-deployment notes

- Per Rule 9, no live-trading doctrine change in this cycle. fast_path_executor's existing filters already exploit this finding.
- For LLM heartbeat (Step 0a, ratified this cycle): when reading `numeric-alert.jsonl`, the alert's `level_name` field IS the named-level proximity — the LLM heartbeat now sees this context.
