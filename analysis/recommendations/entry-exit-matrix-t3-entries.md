# T3 — Entry-matrix (SWARM A): passive limit-below vs pay-up, priced honestly

250 ribbon_ride signals, qty 10. **Does entering at a LIMIT below the signal premium beat paying up NET of the winners it misses?** Frictionless (market = signal bar open; only the limit-below offset is tested — a real spread would tax market MORE, so this is conservative-for-passive). Limit fills = bar low ≤ L−$0.01 within patience (5-min bars). **Exploratory — nothing ships (STOP A).**

`exp incl misses` is the adjudicator (miss = $0). `forgone/miss` = mean P&L of the winners a limit skipped. A passive entry wins ONLY if `net vs market` > 0.

## HEADLINE — passive entry is CONDITIONAL (entry offset = stop headroom)

| exit | best honest (cancel) limit net vs market | verdict |
|---|--:|---|
| `control(-20/+150/sell80/fixed)` | +9 | ✅ passive WINS (best limit-5%/pat5/cancel @ 0.5) |
| `ride(none/+150/sell66/trail15)` | -3 | ❌ pay-up better (best limit-5%/pat10/cancel @ 0.5) |
| `scalp(-35/+50/sell80/trail15)` | +65 | ✅ passive WINS (best limit-20%/pat10/cancel @ 0.5) |

The pattern: a limit-below fills CHEAPER → the SAME stop sits offset% further from the signal (free headroom) → but you MISS the winners the bar never dipped to. That trade pays off ONLY with a stop to protect AND a reachable target: the **scalp (−35/+50)** wins big, the **control (−20/+150)** wins only with a premium floor, the **no-stop ride** LOSES (no stop = headroom protects nothing). A premium floor amplifies passive everywhere. 'convert' policies add a second edge — entering one bar later dodges the signal-bar premium spike (defect #2) — but that is DELAY, not the limit; the **cancel** rows are the clean passive-fill test. Joint entry×exit optimum needs the combined grid (T6).

## Exit held fixed: `control(-20/+150/sell80/fixed)`

### premium floor $0.0  (eligible n=250, market exp $22.91)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $22.91 | +0 | $22.91 | $0.0 |
| `limit-5%/pat10/convert` | 100% | $12.25 | -11 | $12.25 | $0.0 |
| `limit-5%/pat5/cancel` | 88% | $10.11 | -13 | $11.44 | $305.17 |
| `limit-5%/pat10/cancel` | 93% | $8.81 | -14 | $9.45 | $319.12 |
| `limit-10%/pat5/cancel` | 84% | $8.24 | -15 | $9.86 | $341.46 |
| `limit-20%/pat10/cancel` | 81% | $4.99 | -18 | $6.15 | $456.09 |
| `limit-10%/pat3/cancel` | 78% | $4.69 | -18 | $6.05 | $251.36 |

### premium floor $0.2  (eligible n=188, market exp $29.14)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $29.14 | +0 | $29.14 | $0.0 |
| `limit-10%/pat5/cancel` | 84% | $14.28 | -15 | $16.99 | $421.57 |
| `limit-5%/pat5/cancel` | 89% | $13.86 | -15 | $15.6 | $386.67 |
| `limit-5%/pat10/convert` | 100% | $13.13 | -16 | $13.13 | $0.0 |
| `limit-5%/pat10/cancel` | 94% | $12.25 | -17 | $13.02 | $437.18 |
| `limit-20%/pat10/cancel` | 81% | $10.22 | -19 | $12.64 | $562.81 |
| `limit-10%/pat3/cancel` | 77% | $9.38 | -20 | $12.16 | $296.77 |

### premium floor $0.3  (eligible n=157, market exp $36.62)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $36.62 | +0 | $36.62 | $0.0 |
| `limit-5%/pat10/convert` | 100% | $24.05 | -13 | $24.05 | $0.0 |
| `limit-5%/pat5/cancel` | 90% | $22.52 | -14 | $25.08 | $444.81 |
| `limit-5%/pat10/cancel` | 96% | $20.91 | -16 | $21.88 | $536.57 |
| `limit-10%/pat5/cancel` | 85% | $16.39 | -20 | $19.35 | $487.58 |
| `limit-5%/pat5/convert` | 100% | $13.9 | -23 | $13.9 | $0.0 |
| `limit-10%/pat5/convert` | 100% | $13.15 | -23 | $13.15 | $0.0 |

### premium floor $0.5  (eligible n=102, market exp $34.68)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $34.68 | +0 | $34.68 | $0.0 |
| `limit-5%/pat10/convert` ✅ | 100% | $44.71 | +10 | $44.71 | $0.0 |
| `limit-5%/pat5/cancel` ✅ | 90% | $43.44 | +9 | $48.16 | $425.4 |
| `limit-5%/pat5/convert` ✅ | 100% | $39.27 | +5 | $39.27 | $0.0 |
| `limit-5%/pat10/cancel` ✅ | 95% | $36.73 | +2 | $38.63 | $546.8 |
| `limit-10%/pat5/convert` | 100% | $9.6 | -25 | $9.6 | $0.0 |
| `limit-20%/pat10/cancel` | 82% | $7.42 | -27 | $9.01 | $866.39 |

## Exit held fixed: `ride(none/+150/sell66/trail15)`

### premium floor $0.0  (eligible n=250, market exp $92.57)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $92.57 | +0 | $92.57 | $0.0 |
| `limit-25%/pat1/convert` | 100% | $84.9 | -8 | $84.9 | $0.0 |
| `limit-5%/pat10/cancel` | 93% | $78.67 | -14 | $84.41 | $293.32 |
| `limit-20%/pat1/convert` | 100% | $77.05 | -16 | $77.05 | $0.0 |
| `limit-5%/pat5/cancel` | 88% | $75.11 | -17 | $84.97 | $355.06 |
| `limit-15%/pat1/convert` | 100% | $71.41 | -21 | $71.41 | $0.0 |
| `limit-5%/pat10/convert` | 100% | $70.1 | -22 | $70.1 | $0.0 |

### premium floor $0.2  (eligible n=188, market exp $126.64)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $126.64 | +0 | $126.64 | $0.0 |
| `limit-25%/pat1/convert` | 100% | $120.54 | -6 | $120.54 | $0.0 |
| `limit-5%/pat10/cancel` | 94% | $111.67 | -15 | $118.61 | $396.05 |
| `limit-20%/pat1/convert` | 100% | $110.2 | -16 | $110.2 | $0.0 |
| `limit-5%/pat5/cancel` | 89% | $106.44 | -20 | $119.82 | $453.07 |
| `limit-15%/pat1/convert` | 100% | $103.47 | -23 | $103.47 | $0.0 |
| `limit-10%/pat1/convert` | 100% | $98.08 | -29 | $98.08 | $0.0 |

### premium floor $0.3  (eligible n=157, market exp $149.36)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $149.36 | +0 | $149.36 | $0.0 |
| `limit-25%/pat1/convert` | 100% | $145.38 | -4 | $145.38 | $0.0 |
| `limit-5%/pat10/cancel` | 96% | $141.49 | -8 | $148.09 | $385.27 |
| `limit-5%/pat5/cancel` | 90% | $133.9 | -15 | $149.1 | $504.68 |
| `limit-20%/pat1/convert` | 100% | $132.87 | -16 | $132.87 | $0.0 |
| `limit-15%/pat1/convert` | 100% | $124.84 | -25 | $124.84 | $0.0 |
| `limit-5%/pat10/convert` | 100% | $118.31 | -31 | $118.31 | $0.0 |

### premium floor $0.5  (eligible n=102, market exp $162.39)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $162.39 | +0 | $162.39 | $0.0 |
| `limit-25%/pat1/convert` ✅ | 100% | $170.19 | +8 | $170.19 | $0.0 |
| `limit-5%/pat10/cancel` | 95% | $159.32 | -3 | $167.53 | $318.22 |
| `limit-20%/pat1/convert` | 100% | $154.83 | -8 | $154.83 | $0.0 |
| `limit-5%/pat5/cancel` | 90% | $152.45 | -10 | $169.02 | $526.41 |
| `limit-15%/pat1/convert` | 100% | $145.01 | -17 | $145.01 | $0.0 |
| `limit-10%/pat1/convert` | 100% | $130.26 | -32 | $130.26 | $0.0 |

## Exit held fixed: `scalp(-35/+50/sell80/trail15)`

### premium floor $0.0  (eligible n=250, market exp $13.19)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $13.19 | +0 | $13.19 | $0.0 |
| `limit-25%/pat5/convert` ✅ | 100% | $55.08 | +42 | $55.08 | $0.0 |
| `limit-20%/pat5/convert` ✅ | 100% | $41.4 | +28 | $41.4 | $0.0 |
| `limit-20%/pat10/cancel` ✅ | 81% | $38.57 | +25 | $47.5 | $236.42 |
| `limit-25%/pat3/convert` ✅ | 100% | $35.33 | +22 | $35.33 | $0.0 |
| `limit-25%/pat5/cancel` ✅ | 62% | $35.19 | +22 | $56.76 | $184.72 |
| `limit-25%/pat10/cancel` ✅ | 74% | $32.68 | +19 | $43.92 | $237.65 |

### premium floor $0.2  (eligible n=188, market exp $19.95)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $19.95 | +0 | $19.95 | $0.0 |
| `limit-25%/pat5/convert` ✅ | 100% | $72.72 | +53 | $72.72 | $0.0 |
| `limit-20%/pat5/convert` ✅ | 100% | $56.34 | +36 | $56.34 | $0.0 |
| `limit-20%/pat10/cancel` ✅ | 81% | $54.29 | +34 | $67.15 | $291.96 |
| `limit-25%/pat5/cancel` ✅ | 61% | $47.48 | +28 | $78.31 | $225.56 |
| `limit-25%/pat3/convert` ✅ | 100% | $45.44 | +25 | $45.44 | $0.0 |
| `limit-25%/pat10/cancel` ✅ | 73% | $45.1 | +25 | $61.89 | $285.12 |

### premium floor $0.3  (eligible n=157, market exp $27.82)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $27.82 | +0 | $27.82 | $0.0 |
| `limit-25%/pat5/convert` ✅ | 100% | $86.73 | +59 | $86.73 | $0.0 |
| `limit-20%/pat5/convert` ✅ | 100% | $66.67 | +39 | $66.67 | $0.0 |
| `limit-20%/pat10/cancel` ✅ | 81% | $64.67 | +37 | $79.95 | $331.3 |
| `limit-25%/pat5/cancel` ✅ | 60% | $57.85 | +30 | $96.62 | $251.76 |
| `limit-25%/pat3/convert` ✅ | 100% | $56.74 | +29 | $56.74 | $0.0 |
| `limit-25%/pat10/cancel` ✅ | 73% | $55.14 | +27 | $75.93 | $317.22 |

### premium floor $0.5  (eligible n=102, market exp $20.81)

| policy | fill% | exp incl misses | net vs mkt | filled-only exp | forgone/miss |
|---|--:|--:|--:|--:|--:|
| `market(pay-up ctl)` | 100% | $20.81 | +0 | $20.81 | $0.0 |
| `limit-25%/pat5/convert` ✅ | 100% | $110.45 | +90 | $110.45 | $0.0 |
| `limit-25%/pat3/convert` ✅ | 100% | $92.55 | +72 | $92.55 | $0.0 |
| `limit-20%/pat10/cancel` ✅ | 82% | $85.76 | +65 | $104.14 | $416.55 |
| `limit-20%/pat5/convert` ✅ | 100% | $81.96 | +61 | $81.96 | $0.0 |
| `limit-25%/pat5/cancel` ✅ | 62% | $77.23 | +56 | $125.04 | $311.97 |
| `limit-20%/pat3/convert` ✅ | 100% | $75.32 | +55 | $75.32 | $0.0 |

---
**READ:** if `filled-only exp` >> market but `exp incl misses` ≤ market, the limit gets BETTER fills but misses too many winners (defect: the passive entry's miss cost eats its headroom edge). If `net vs market` > 0 at a reachable fill%, J's hypothesis holds for that exit×floor. Finalists → T5 confirmatory OOS + anchor (post-STOP-A).

_Source: `backtest/tools/t3_entry_matrix.py`. No entry-path change ships from this file._
