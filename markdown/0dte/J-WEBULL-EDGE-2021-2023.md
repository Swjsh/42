# J's Real Webull Options Edge — 2021-2023 Ground Truth

> Mined from `docs/WeBull History/{2021,2022,2023}/Webull_Orders_Records_Options.csv`.
> Parser: [`backtest/autoresearch/webull_history_miner.py`](../../backtest/autoresearch/webull_history_miner.py).
> Setup analyzer: [`backtest/autoresearch/webull_winner_setups.py`](../../backtest/autoresearch/webull_winner_setups.py).
> Trade ledger + stats: [`analysis/webull-j-trades/`](../../analysis/webull-j-trades/).
> Generated 2026-06-19. **This is real fills — the richest ground truth Gamma has.**

---

## TL;DR — what actually worked for J

1. **J has a real, small, positive edge — and destroys it by sizing up.** Trading
   **1-2 contracts he is net +$4,576 (50.8% WR, +$7.9/trade)**. Every dollar of his
   net loss comes from larger / scaled-in positions: **3-5 contracts -$13,975
   (18.6% WR), 6-10 contracts -$3,486, scaled-in entries -$327/trade**. He sizes
   up into his *worst* trades. **This is empirical proof of Rule 6 + "no sizing up
   after losses."**
2. **Time-of-day is a genuine edge axis.** The midday window is his money: **13:00 ET
   = 72.7% WR / +$69/trade**, 11:00 = +$29, 12:00 = +$19, 14:30 = +$4. The dead
   zones bleed: 11:30 (-$55), 12:30 (-$87), 13:30 (-$76), 15:30 (-$103). The 09:30-10:30
   open is a coin-flip at best (51%/-$31 → 45%/-$11).
3. **Calls > puts.** Bull bias -$6/trade (near breakeven), bear bias -$33/trade. J's
   long-call timing held up; his put timing was where he bled.
4. **He cuts winners and lets losers run** (the classic leak). Avg win **$121** vs
   avg loss **-$144**; winners held a median **15.3 min**, losers **18.5 min**.
5. **The winning setups are trend-continuation + reversal-off-extreme**, not breakout
   chasing — and **every winner was on the correct side of session VWAP** for its
   direction.

> **Honest headline:** on the SPX/SPY family across 2021-2023 J was **net -$12,885**
> over 667 round-trips (46.9% WR, -$19/trade expectancy, profit factor 0.75). The
> *edge* is real but lived entirely in his small, well-timed, trend-aligned trades;
> the *account* went negative because of oversized, mistimed, counter-trend puts.
> These winners are excellent NEW anchors for the diversified book — far richer
> than the 3 bearish source-of-truth trades.

---

## Data scope + quality

| Item | Value |
|---|---|
| Raw rows (3 files) | 4,818 |
| **Exact-duplicate rows dropped** | **1,890** — the "2023" export actually contains 1,574 rows of *2022* data; files overlap heavily. Dedup is mandatory (lesson C7). |
| Filled fills after dedup | 2,414 |
| Round-trips reconstructed (all underliers) | 1,221 |
| Underliers in raw data | 114 (TSLA 345, QQQ 184, AMD 90, …) |
| **SPX/SPY family round-trips** (primary subject) | **668** (667 closed) |
| Date range | 2021-06-09 → 2023-10-03 |
| 0DTE fraction (family fills) | **86%** — confirms J's 0DTE directional style |

**Scope decision:** Project Gamma trades SPY 0DTE; SPX (SPXW), XSP and SPY are the
same underlying price action (SPX ≈ 10× SPY). The **SPX/SPY family** is the primary
analysis subject. All 114 underliers are still parsed; the non-family universe is
summarised in `j_style_stats.json → non_family_summary` so nothing is hidden.

**Reconstruction method:** FIFO match of Buy→Sell fills per option symbol. Handles
partial fills, scaling in (weighted entry price across lots) and scaling out
(one round-trip per sell fill). Leftover 0DTE buys with no sell = expired worthless
(full premium loss); leftover longer-dated buys = `unclosed` (P&L 0, excluded from
expectancy). 10 anomalies (sell-without-open / overflow) logged, not counted as trades.

---

## Step 2 — style analytics (SPX/SPY family, closed trades)

### Overall

| Metric | Value |
|---|---|
| Round-trips | 667 |
| Win rate | 46.9% |
| Total P&L | **-$12,885** |
| Avg win / avg loss | +$121 / -$144 |
| Expectancy / trade | -$19 |
| Profit factor | 0.75 |

### By year

| Year | n | WR | P&L | Exp/trade |
|---|---|---|---|---|
| 2021 | 20 | 45.0% | -$268 | -$13 |
| 2022 | 555 | 45.8% | -$9,657 | -$17 |
| 2023 | 92 | 54.4% | -$2,960 | -$32 |

> 2023 had the best WR (54%) but worst expectancy (-$32) — a few large losing puts
> (June 2023 cluster) dominated. Win rate ≠ profitability; sizing of the losers did it.

### Call vs put (directional bias)

| Bias | n | WR | P&L | Exp/trade |
|---|---|---|---|---|
| **bull (calls)** | 344 | 46.8% | **-$2,070** | **-$6** |
| bear (puts) | 323 | 47.1% | -$10,815 | -$33 |

> Near-identical WR, **5× worse expectancy on puts.** J's call timing is close to
> breakeven; his bleed is concentrated in puts.

### 0DTE vs longer-dated

| Bucket | n | WR | P&L | Exp/trade |
|---|---|---|---|---|
| 0DTE | 584 | 48.6% | -$11,076 | -$19 |
| longer-dated | 83 | 34.9% | -$1,809 | -$22 |

> 0DTE is where he lives (88% of trades) and has the better WR. Longer-dated swing
> attempts had a poor 35% hit rate.

### Entry time-of-day — WR by 30-min bucket (the edge axis)

| Bucket (ET) | n | WR | Exp/trade |
|---|---|---|---|
| 09:30 | 164 | 51.2% | -$31 |
| 10:00 | 134 | 47.8% | -$27 |
| 10:30 | 83 | 44.6% | -$11 |
| **11:00** | 63 | **52.4%** | **+$29** |
| 11:30 | 49 | 28.6% | -$55 |
| **12:00** | 36 | 47.2% | **+$19** |
| 12:30 | 11 | 27.3% | -$87 |
| **13:00** | 22 | **72.7%** | **+$69** |
| 13:30 | 34 | 35.3% | -$76 |
| 14:00 | 30 | 43.3% | -$13 |
| **14:30** | 29 | 58.6% | +$4 |
| 15:00 | 6 | 16.7% | -$39 |
| 15:30 | 5 | 20.0% | -$103 |

> **The 13:00 ET lunch-reversal hour is J's standout** (small n=22 but 72.7%). The
> profitable windows (11:00, 12:00, 13:00, 14:30) are all *midday*; the open and the
> late-afternoon are where he loses. Note: production engine's 09:35 entry gate fires
> J straight into his *weakest* time band — see recommendations.

### Hold duration — winners vs losers

| | mean | median | n |
|---|---|---|---|
| winners | 47.8 min | 15.3 min | 313 |
| losers | 50.3 min | 18.5 min | 354 |

> Classic asymmetry: winners cut fast (median 15 min), losers held longer (18.5 min)
> hoping for reversal. Combined with avg-win < avg-loss, this is the textbook
> "cut winners / let losers run" leak.

### Day-of-week

| Day | n | WR | Exp/trade |
|---|---|---|---|
| Mon | 113 | 42.5% | -$28 |
| Tue | 147 | 52.4% | -$15 |
| Wed | 139 | 39.6% | -$37 |
| Thu | 135 | 50.4% | -$10 |
| Fri | 133 | 48.9% | -$8 |

> Tue/Thu/Fri ~breakeven-ish; **Wednesday is his worst day** (39.6% WR).

### Scaling / sizing behaviour — **the single biggest leak**

| Size | n | WR | Exp/trade | Total P&L |
|---|---|---|---|---|
| **1-2 contracts** | 579 | **50.8%** | **+$7.9** | **+$4,576** |
| 3-5 contracts | 70 | 18.6% | -$199.65 | **-$13,975** |
| 6-10 contracts | 18 | 33.3% | -$193.67 | -$3,486 |

| Entry style | n | Exp/trade |
|---|---|---|
| single-fill entry | 621 | +$3.5 |
| **scaled-in (multi-fill)** | 46 | **-$327.3** |

> **This is the whole story.** J trading 1-2 lots is *profitable* (+$4,576). The
> entire account loss is the 88 trades sized 3+ (-$17,461 combined). When he sizes
> up — almost always scaling into a position that's already moving against him — his
> WR collapses to ~19-33%. This is conviction/revenge sizing on losers, and it is
> exactly what **Rule 6 (per-trade cap), the "no sizing up after losses" veto, and
> the kill-switch** exist to prevent. **Gamma's discipline directly addresses J's
> documented largest leak.**

---

## Top 10 winners (SPX/SPY family, full detail)

| Date | Symbol | Bias | Qty | Entry→Exit ET | Hold | Premium | P&L |
|---|---|---|---|---|---|---|---|
| 2023-06-01 | SPXW 4200 C | bull | 1 | 10:31→10:47 | 16m | $2.25→$7.50 | **+$525** |
| 2022-03-14 | SPXW 4195 P | bear | 1 | 11:20→11:43 | 23m | $4.90→$9.90 | +$500 |
| 2022-05-02 | SPXW 4200 C | bull | 1 | 10:25→10:31 | 6m | $4.10→$8.70 | +$460 |
| 2023-06-02 | SPXW 4280 C | bull | 1 | 10:10→11:02 | 52m | $2.00→$6.50 | +$450 |
| 2022-06-06 | SPXW 4115 P | bear | 1 | 11:11→11:18 | 7m | $2.55→$7.00 | +$445 |
| 2022-07-22 | SPXW 3940 P | bear | 1 | 13:18→13:35 | 17m | $3.20→$7.20 | +$400 |
| 2023-05-30 | SPXW 4200 P | bear | 1 | 10:57→11:21 | 24m | $3.50→$7.40 | +$390 |
| 2022-07-27 | SPXW 4030 C | bull | 2 | 14:21→14:35 | 14m | $2.35→$4.30 | +$390 |
| 2022-05-12 | SPXW 3810 P | bear | 1 | 11:16→11:54 | 38m | $4.20→$8.10 | +$390 |
| 2022-07-22 | SPXW 3950 P | bear | 1 | 11:23→11:37 | 15m | $2.30→$6.00 | +$370 |

> **Every single top winner was 1-2 contracts.** All 0DTE except the 5/12 swing put.
> Premium roughly doubled→tripled — these are clean directional reads held minutes,
> not hours.

### 📌 ANCHOR SET REGISTRATION (canonical pointer — future ground-truth)

**These 10 small-lot winners are hereby REGISTERED as J's NEW candidate anchor set**
for validating the regime-aware diversified book (`backtest/lib/engine/regime_book.py`)
on J's *real* edge. They are a balanced **5 bull / 5 bear** set spanning 2022-2023 and
cover BOTH winning archetypes (trend-continuation/pullback-resumption ≈ RIDE_THE_RIBBON,
and reversal-off-extreme ≈ BEARISH_REJECTION) — richer and more balanced than the 3
bearish source-of-truth trades currently in `j_edge_tracker` (CLAUDE.md OP-16).

**Status: NOT yet wired into `j_edge_tracker` — by design.** These are **SPX 2021-23**
fills (a different instrument scale and a different volatility era than the SPY-now
engine, cf. lesson C22). They become the validation anchor set **once real ★★★ levels
bank** on the live SPY engine and the regime book has REGIME_ACTIVE slots to test —
they are *future* ground-truth, recorded here so the path is explicit. Do not treat
them as immutable engine targets the way the OP-16 SPY trades are; validate any derived
rule on the full IS population first (C24 — anchor winners can be one-off exceptions).

Provenance for re-loading: rows above + `analysis/webull-j-trades/j_roundtrips.csv`
(filter to the listed dates/symbols); archetype/VWAP overlay in
`analysis/webull-j-trades/winner_setups.json`. See L168 for the sizing-discipline
finding mined from the same ledger.

## Top 10 losers (SPX/SPY family, full detail)

| Date | Symbol | Bias | Qty | Entry→Exit ET | Hold | Premium | P&L |
|---|---|---|---|---|---|---|---|
| 2022-05-12 | SPXW 3750 P | bear | 6 | 09:50→11:09 | 79m | $3.30→$1.00 | **-$1,380** |
| 2023-06-13 | SPXW 4355 P | bear | 5 | 11:59→12:27 | 28m | $3.60→$1.60 | -$1,000 |
| 2022-07-29 | SPXW 4060 P | bear | 6 | 11:12→12:45 | 93m | $1.95→$0.30 | -$990 |
| 2023-06-16 | SPXW 4460 C | bull | 5 | 10:01→10:47 | 46m | $2.67→$0.95 | -$860 |
| 2023-06-05 | SPXW 4270 P | bear | 3 | 10:15→10:52 | 37m | $4.27→$1.47 | -$839 |
| 2022-06-08 | SPXW 4090 P | bear | 8 | 13:33→13:47 | 15m | $1.88→$0.85 | -$820 |
| 2022-05-11 | SPXW 3880 P | bear | 4 | 09:36→09:47 | 12m | $3.34→$1.60 | -$695 |
| 2022-06-14 | SPXW 3810 C | bull | 1 | 10:00→10:15 | 15m | $9.80→$3.10 | -$670 |
| 2022-06-14 | SPXW 3700 P | bear | 3 | 09:49→10:00 | 11m | $4.10→$1.90 | -$660 |
| 2023-06-08 | SPXW 4250 P | bear | 3 | 09:55→10:06 | 11m | $3.60→$1.50 | -$630 |

> **9 of 10 losers were 3+ contracts; 8 of 10 were puts; most entered 09:30-10:30
> or in the 11:30-13:30 dead zone.** The mirror image of the winners: oversized,
> mistimed, mostly bearish. (The lone 1-lot loser, 6/14 deep-ITM $9.80 call, is a
> high-premium ITM punt — different failure mode.)

---

## Step 3 — setup archetypes behind the top winners

SPY 5m bars (Alpaca IEX) pulled for each winner date; features computed
look-ahead-free at J's entry bar (`winner_setups.json`). SPX/SPY ≈ 10:1, so SPY
price action reconstructs the SPXW setup.

| Date | Bias | Archetype | Prior-30m | New extreme? | VWAP side |
|---|---|---|---|---|---|
| 2023-06-01 | bull | bullish pullback resumption | +0.19% | no | above |
| 2022-03-14 | bear | reversal off session high | -0.09% | no | above (fade) |
| 2022-05-02 | bull | momentum breakout continuation | +0.45% | **yes** | above |
| 2023-06-02 | bull | trend continuation (midrange) | -0.04% | no | above |
| 2022-06-06 | bear | bearish pullback resumption | -0.41% | no | below |
| 2022-07-22 | bear | momentum breakout continuation | -0.43% | **yes** | below |
| 2023-05-30 | bear | trend continuation (midrange) | -0.10% | no | below |
| 2022-07-27 | bull | trend continuation (midrange) | +0.13% | no | above |
| 2022-05-12 | bear | reversal off session high | +0.67% | no | above (fade) |

**Archetype tally:** trend-continuation 3 · reversal-off-extreme 2 · momentum-breakout 2 ·
pullback-resumption 2.

**What characterises a J winner:**
- **VWAP alignment is near-universal.** In the 7 trend/continuation/breakout winners,
  the entry was on the correct side of session VWAP for the direction. The 2 reversal
  winners (3/14, 5/12) deliberately faded price that had pushed *above* VWAP into a
  session high — catching the top.
- **He is not a breakout chaser.** Only 2 of 9 entered on a fresh session extreme;
  most entered on pullbacks/midrange continuation or reversals — i.e. waiting for
  a retrace before joining, or fading exhaustion.
- **Two distinct, repeatable plays:** (1) *trend-continuation / pullback resumption*
  with VWAP (the calls + the trending puts), and (2) *reversal off a session
  high/low* (the fade puts). Both are already in spirit in the Gamma playbook
  (RIDE_THE_RIBBON ≈ #1; BEARISH_REJECTION ≈ #2).

> Caveat: n=9, hand-coarse archetypes from 5m bars only (no VIX/level overlay). These
> are directional characterisations, not a validated detector. Treat as anchor
> context, then validate any derived rule on the full IS population (lesson C24 —
> anchor winners can be one-off exceptions; verify the population WR before expanding).

---

## How this feeds the engine (recommendations, not ratified)

1. **New anchor set.** The 10 winners above (all 1-2 lot, clean directional reads)
   are far richer than the 3 bearish source-of-truth trades for validating the
   diversified book on J's *real* edge — a balanced 5 bull / 5 bear set spanning
   2022-2023, both trend-continuation and reversal archetypes.
2. **Sizing discipline is empirically J's #1 edge-killer.** His 1-2 lot book is
   +$4,576; everything 3+ is -$17,461. This is the strongest possible evidence for
   keeping Rule 6, the post-loss size veto, and the kill-switch *tight*. Consider a
   backtest knob that hard-caps adds after an adverse excursion.
3. **Time-of-day weighting is worth a controlled test.** The 13:00 / 11:00 / 14:30
   windows carry positive expectancy; 11:30-13:30-ex-13:00 and the late-afternoon
   bleed. The production 09:35 entry gate fires into his *weakest* band — a
   midday-weighted or open-avoidance variant deserves an A/B (OOS + real-fills +
   anchor-no-regression, per OP-16/OP-11). Small-n per bucket — treat as hypothesis.
4. **Calls held up better than puts for J.** Aligns with the current scope-lock
   debate (BEARISH_REJECTION is the proven edge for the *engine*, but J's *manual*
   put timing bled). The discriminator is timing + VWAP alignment, not direction
   per se.

---

## Reproduce

```bash
cd backtest
python -m autoresearch.webull_history_miner --write   # ledger + style stats
python _build_winner_cache.py                          # SPY bar cache for winners
python -m autoresearch.webull_winner_setups            # setup archetypes
python -m pytest tests/test_webull_history_miner.py -q # 22 unit tests
```

Outputs land in `analysis/webull-j-trades/`:
`j_roundtrips.csv` · `j_roundtrips.json` · `j_style_stats.json` ·
`winner_candles.json` · `winner_setups.json`.
