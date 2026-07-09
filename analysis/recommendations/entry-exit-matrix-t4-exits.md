# T4 — Exit-matrix v2 (wider + P5-gated), full OPRA ribbon_ride

2016 exit-shape cells replayed on **250 signals** (qty 10) through the LIVE exit_manager. Frictionless, 5-min OPRA (touch stops), premium-only replay, ribbon_ride only. Ranked by per-trade EXPECTANCY (OP-32). **Exploratory — nothing ships (STOP A).** edge_capture is relative-to-control at qty 10.

> ⚠️ **READ THE DOWNSIDE, NOT JUST THE EXPECTANCY.** The winners are 'no-stop ride' shapes: they beat control on expectancy AND on the real-fill anchor, but their maxDD (≈ −$5,000 at qty 10) EXCEEDS a $2K account — on a real account the −30%/−50% daily kill switch + per-trade cap would fire long before that, so the absolute qty-10 numbers OVERSTATE what a live arm realizes. The TRUSTWORTHY signals here are **relative-to-control** and the **real-fill anchor**; the absolute $/trade is optimistic (frictionless + no account-risk limits). This is a STOP-A judgment call: how much tail to accept for winner-capture, at what qty, under the kill switch.

**CONTROL (shipped -20/+150/sell80/fixed):** exp **$22.91** · WR 15% · OOS+ True · WF n/a · qpf 0.667 · drop-top-3 $0.68 · maxDD $-3982.0 · worst-decile $-264.8 · P5-survivor False

## Top 25 by expectancy (drop-top-3 + DOWNSIDE + P5 gate)

Downside columns are load-bearing: a 'no-stop ride' buys winner-capture with tail risk. `maxDD`/`worst-dec` (mean of the worst 10% of trades) are how much you pay for it.

| # | shape | exp | WR | OOS+ | WF | qpf | drop-3 | maxDD | worst-dec | P5 | vs ctl |
|--:|---|--:|--:|:--:|--:|--:|--:|--:|--:|:--:|--:|
| 1 | `stopnone/tp+150/sell66/trail15/tgtnone/t15:40` | $92.57 | 38% | Y | 3.622 | 1.0 | $65.46 | $-5034.6 | $-989.64 | · | +70 |
| 2 | `stopnone/tp+150/sell66/trail15/tgt2.5x/t15:40` | $90.33 | 38% | Y | 3.892 | 1.0 | $63.19 | $-4814.8 | $-989.64 | · | +67 |
| 3 | `stopnone/tp+150/sell80/trail15/tgtnone/t15:40` | $81.96 | 38% | Y | 4.288 | 1.0 | $54.97 | $-5153.8 | $-989.64 | · | +59 |
| 4 | `stopnone/tp+150/sell66/fixed/tgt2.5x/t15:40` | $81.32 | 38% | Y | 4.055 | 0.833 | $47.16 | $-5587.0 | $-989.64 | · | +58 |
| 5 | `stopnone/tp+150/sell80/trail15/tgt2.5x/t15:40` | $80.84 | 38% | Y | 4.486 | 1.0 | $53.83 | $-5043.9 | $-989.64 | · | +58 |
| 6 | `stopnone/tp+150/sell66/trail15/tgtnone/t15:00` | $80.67 | 37% | Y | 1.489 | 1.0 | $53.42 | $-4686.1 | $-910.42 | · | +58 |
| 7 | `stopnone/tp+150/sell66/trail15/tgt2.5x/t15:00` | $80.38 | 37% | Y | 1.492 | 1.0 | $53.12 | $-4466.3 | $-910.42 | · | +57 |
| 8 | `stopnone/tp+150/sell66/trail22/tgt2.5x/t15:40` | $79.09 | 38% | Y | 4.488 | 1.0 | $53.25 | $-4924.84 | $-989.64 | · | +56 |
| 9 | `stopnone/tp+150/sell80/fixed/tgt2.5x/t15:40` | $76.34 | 38% | Y | 4.631 | 1.0 | $45.81 | $-5430.0 | $-989.64 | · | +53 |
| 10 | `stopnone/tp+150/sell66/trail22/tgtnone/t15:40` | $76.28 | 38% | Y | 4.438 | 1.0 | $50.41 | $-5279.88 | $-989.64 | · | +53 |
| 11 | `stopnone/tp+150/sell80/trail22/tgt2.5x/t15:40` | $75.22 | 38% | Y | 4.908 | 1.0 | $48.86 | $-5098.92 | $-989.64 | · | +52 |
| 12 | `stopnone/tp+150/sell80/trail22/tgtnone/t15:40` | $73.82 | 38% | Y | 4.887 | 1.0 | $47.44 | $-5276.44 | $-989.64 | · | +51 |
| 13 | `stopnone/tp+150/sell66/fixed/tgt2.5x/t15:00` | $72.7 | 37% | Y | 1.519 | 1.0 | $38.97 | $-5238.5 | $-910.42 | · | +50 |
| 14 | `stopnone/tp+150/sell80/trail15/tgtnone/t15:00` | $71.83 | 37% | Y | 1.496 | 1.0 | $44.71 | $-4805.3 | $-910.42 | · | +49 |
| 15 | `stopnone/tp+150/sell80/trail15/tgt2.5x/t15:00` | $71.69 | 37% | Y | 1.498 | 1.0 | $44.57 | $-4695.4 | $-910.42 | · | +49 |
| 16 | `stopnone/tp+150/sell100/fixed/tgt2.5x/t15:40` | $71.36 | 38% | Y | 5.445 | 1.0 | $44.47 | $-5273.0 | $-989.64 | · | +48 |
| 17 | `stopnone/tp+150/sell100/fixed/tgtnone/t15:40` | $71.36 | 38% | Y | 5.445 | 1.0 | $44.47 | $-5273.0 | $-989.64 | · | +48 |
| 18 | `stopnone/tp+150/sell100/trail15/tgt2.5x/t15:40` | $71.36 | 38% | Y | 5.445 | 1.0 | $44.47 | $-5273.0 | $-989.64 | · | +48 |
| 19 | `stopnone/tp+150/sell100/trail15/tgtnone/t15:40` | $71.36 | 38% | Y | 5.445 | 1.0 | $44.47 | $-5273.0 | $-989.64 | · | +48 |
| 20 | `stopnone/tp+150/sell100/trail22/tgt2.5x/t15:40` | $71.36 | 38% | Y | 5.445 | 1.0 | $44.47 | $-5273.0 | $-989.64 | · | +48 |
| 21 | `stopnone/tp+150/sell100/trail22/tgtnone/t15:40` | $71.36 | 38% | Y | 5.445 | 1.0 | $44.47 | $-5273.0 | $-989.64 | · | +48 |
| 22 | `stopnone/tp+150/sell66/trail22/tgt2.5x/t15:00` | $71.32 | 37% | Y | 1.487 | 1.0 | $45.39 | $-4576.34 | $-910.42 | · | +48 |
| 23 | `stopnone/tp+150/sell80/fixed/tgt2.5x/t15:00` | $67.85 | 37% | Y | 1.513 | 1.0 | $37.7 | $-5081.5 | $-910.42 | · | +45 |
| 24 | `stopnone/tp+150/sell80/trail22/tgt2.5x/t15:00` | $67.16 | 37% | Y | 1.496 | 1.0 | $40.7 | $-4750.42 | $-910.42 | · | +44 |
| 25 | `stopnone/tp+150/sell66/trail22/tgtnone/t15:00` | $66.86 | 37% | Y | 1.473 | 1.0 | $40.88 | $-4931.38 | $-910.42 | · | +44 |

**drop-3** = expectancy after removing the 3 biggest winners (ground rule 8: carried by outliers?). **maxDD** = worst chronological equity drawdown (qty 10, frictionless). Every top shape is **P5=·** (not a survivor) → the T5 confirmatory pass + P5 gate + anchor MUST clear it before it can arm anything.

## Per-band leaders (best exp shape within each entry-premium band)

| band | best shape (by band exp) | band exp | control band exp |
|---|---|--:|--:|
| <0.20 | `stop-25/tp+150/sell66/trail15/tgtnone/t15:00` | $10.14 | $4.02 |
| 0.20-0.50 | `stopnone/tp+150/sell66/trail15/tgtnone/t15:40` | $84.24 | $22.58 |
| 0.50-1.00 | `stopnone/tp+150/sell66/trail15/tgt2.5x/t15:40` | $192.52 | $49.33 |
| >1.00 | `stopnone/tp+150/sell66/fixed/tgt2.5x/t15:40` | $118.82 | $-0.5 |

## Per-direction leaders

- **bear** (n=191): best `stopnone/tp+150/sell66/trail15/tgtnone/t15:40` exp $68.57 (control $1.07)
- **bull** (n=59): best `stopnone/tp+150/sell66/trail15/tgtnone/t15:40` exp $170.26 (control $93.63)

## Anchor — top-5 finalists on the 17 REAL fleet signals (mandated kill-check)

Replayed on 79 real fleet positions. Control anchor total: **$-757.1**. A finalist materially worse than control here = KILL (ground rule / T4).

| finalist | anchor total | no-regression vs control |
|---|--:|:--:|
| `stopnone/tp+150/sell66/trail15/tgtnone/t15:40` | $1490.95 | Y |
| `stopnone/tp+150/sell66/trail15/tgt2.5x/t15:40` | $1490.95 | Y |
| `stopnone/tp+150/sell80/trail15/tgtnone/t15:40` | $1573.85 | Y |
| `stopnone/tp+150/sell66/fixed/tgt2.5x/t15:40` | $1053.4 | Y |
| `stopnone/tp+150/sell80/trail15/tgt2.5x/t15:40` | $1573.85 | Y |

---
_Source: `backtest/tools/t4_exit_matrix.py`. Finalists still owe a pre-registered OOS pass at T5 (post-STOP-A) + the P5 gate. No shape ships from this file._
