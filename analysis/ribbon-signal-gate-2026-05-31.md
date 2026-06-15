# RIBBON SIGNAL GATE — momentum + duration thresholds

Base: 312 trades, +3.7/trade total +1140/c

## Ribbon momentum gate (require spread widening ≥ threshold)
| momentum threshold | n kept | WR | per-trade /c | total /c |
|---|---|---|---|---|
| rmom >= -20 | 268 | 0.32 | +7.0 | +1880 |
| rmom >= -10 | 225 | 0.33 | +8.8 | +1984 |
| rmom >= -5 | 198 | 0.34 | +9.3 | +1836 |
| rmom >= +0 | 167 | 0.35 | +10.3 | +1728 |
| rmom >= +5 | 122 | 0.36 | +12.6 | +1542 |
| rmom >= +10 | 77 | 0.43 | +20.2 | +1555 |
| rmom >= +15 | 53 | 0.43 | +17.5 | +929 |

## Ribbon duration gate (require fresh ribbon, bars ≤ threshold)
| max duration | n kept | WR | per-trade /c | total /c |
|---|---|---|---|---|
| rdur ≤10 bars | 125 | 0.28 | +2.8 | +355 |
| rdur ≤15 bars | 173 | 0.32 | +7.0 | +1208 |
| rdur ≤20 bars | 197 | 0.34 | +7.4 | +1461 |
| rdur ≤25 bars | 216 | 0.33 | +6.7 | +1444 |
| rdur ≤30 bars | 236 | 0.34 | +6.8 | +1598 |
| rdur no limit | 312 | 0.30 | +3.7 | +1140 |

## COMBINED: momentum ≥ threshold AND duration ≤ threshold
| combo | n | WR | per-trade /c | total /c | pct signals kept |
|---|---|---|---|---|---|
| rmom≥-5 AND rdur≤15 | 122 | 0.35 | +11.4 | +1393 | 39% |
| rmom≥-5 AND rdur≤20 | 139 | 0.37 | +12.7 | +1762 | 45% |
| rmom≥-5 AND rdur≤25 | 151 | 0.36 | +11.4 | +1715 | 48% |
| rmom≥+0 AND rdur≤15 | 109 | 0.37 | +12.0 | +1310 | 35% |
| rmom≥+0 AND rdur≤20 | 122 | 0.38 | +13.1 | +1594 | 39% |
| rmom≥+0 AND rdur≤25 | 132 | 0.37 | +12.0 | +1585 | 42% |
| rmom≥+5 AND rdur≤15 | 87 | 0.40 | +17.2 | +1493 | 28% |
| rmom≥+5 AND rdur≤20 | 97 | 0.39 | +16.8 | +1627 | 31% |
| rmom≥+5 AND rdur≤25 | 102 | 0.38 | +15.5 | +1585 | 33% |
| rmom≥+10 AND rdur≤15 | 61 | 0.46 | +24.7 | +1508 | 20% |
| rmom≥+10 AND rdur≤20 | 68 | 0.44 | +23.6 | +1603 | 22% |
| rmom≥+10 AND rdur≤25 | 69 | 0.43 | +23.0 | +1585 | 22% |

## BEST COMBINED GATE: **rmom≥10 AND rdur≤15 — +24.7/trade**
This is the visual 'conviction check' a human does before entering:
- Ribbon spread is widening (trend accelerating, not topping)
- Ribbon is relatively fresh (not a stale 2-hour trend near exhaustion)
Combined: the setup has momentum AND hasn't been running too long.