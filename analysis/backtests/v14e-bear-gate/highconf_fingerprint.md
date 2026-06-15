# V14E BEAR_HIGH_CONF Sub-Tier Fingerprint Analysis
> Generated: 2026-05-21 03:59 ET
> Source: 33 bear+high-confidence v14_enhanced_watcher observations

## Summary

**N=33  WR=84.8%  P&L=$+1,173**

The BEAR_HIGH_CONF sub-tier requires `direction=short AND confidence=high` in the
v14_enhanced_watcher. High confidence = `has_confluence AND n_triggers >= 3`.

## VIX Regime — Is the edge regime-independent?

| VIX Regime | N | WR% | P&L |
|---|---:|---:|---:|
| VIX_ELEVATED (20-25) | 7 | 57.1% | $+10 |
| VIX_HIGH (ge25) | 2 | 50.0% | $-118 |
| VIX_MODERATE (15-20) | 24 | 95.8% | $+1,281 |

## Time-of-Day Distribution (30-min buckets)

| Time ET | N | WR% | P&L |
|---|---:|---:|---:|
| 09:30 | 3 | 100.0% | $+90 |
| 10:00 | 1 | 100.0% | $+60 |
| 10:30 | 3 | 66.7% | $-18 |
| 11:00 | 13 | 69.2% | $+269 |
| 11:30 | 6 | 100.0% | $+234 |
| 12:00 | 4 | 100.0% | $+110 |
| 13:00 | 3 | 100.0% | $+429 |

## Outcome Distribution

| Outcome | Count |
|---|---:|
| tp1_then_be_stop | 25 |
| stopped | 5 |
| runner_hit | 3 |

## Top Trigger Combinations (what makes high confidence?)

| Trigger combo | Count |
|---|---:|
| `[]` | 33 |

## Individual Trigger Frequency

| Trigger | Count |
|---|---:|

## Date Concentration

Unique dates with observations: **15**
Unknown (timestamp parse fail): 0

Top-5 dates by observation count:

| Date | N |
|---|---:|
| 2026-05-04 | 8 |
| 2026-05-15 | 6 |
| 2026-04-23 | 3 |
| 2026-04-28 | 3 |
| 2026-04-20 | 2 |

## Implications for V14E Promotion Path

- If WR ≥ 80% holds across ≥2 VIX regimes → regime-independent edge confirmed
- If time-of-day shows strong concentration → gate by entry window
- If trigger combos cluster around 2-3 patterns → the 'high confidence' gate
  is already capturing a real structural signal, not randomness
- Promotion gate proposal: BEAR_HIGH_CONF watch-only → N_target=50 obs, WR≥75%
  This is faster than the full BEAR_ONLY path (N_target=100, WR≥55%)
  because the 84.8% WR with n=33 already provides strong signal