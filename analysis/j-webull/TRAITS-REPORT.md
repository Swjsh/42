# J's Trading Traits — Fresh Re-Derivation (2026-07-01)

> Population: **567 closed SPX/SPY-family position episodes** (flat→flat), 222 distinct days,
> 2021-06-09 → 2023-10-03. Net **−$12,885**, WR 41.4%, expectancy −$22.7/trade, PF 0.74.
> P&L = actual WeBull fills. Contrast baseline: `markdown/0dte/J-WEBULL-EDGE-2021-2023.md`
> (Opus, 2026-06-19). Reconciliation: same parse (2,414 fills, 10 anomalies, −$12,885 total);
> unit of analysis changed from per-sell-fill trips (667) to position episodes (567).

---

## The five strongest evidence-backed findings

### 1. ⛔ REVISED — "J is profitable at 1-2 lots" is an accounting artifact. He is *least unprofitable* there.

At the **episode** level (size = max open contracts):

| Size | n | WR | Exp/trade | Total | Exp/contract |
|---|---|---|---|---|---|
| 1-2 | 455 | 42.9% | −$9.7 | **−$4,420** | −$7.1 |
| 3-5 | 93 | 36.6% | −$54.9 | −$5,110 | −$17.9 |
| 6-10 | 19 | 31.6% | −$176.6 | −$3,355 | −$28.7 |

The prior "+$4,576 at 1-2 contracts" replicates EXACTLY when one round-trip per *sell fill*
is used with size = sell qty (578 trips, +$4,576, 50.9% WR — matched to the dollar). That
method banks profitable partial exits of BIG positions into the "1-2" band: small clips out
of 3+ lot episodes contributed **+$8,996**, flipping the band's sign. No XSP contamination
(0 of 112 size-3+ episodes are XSP).

**What survives:** the sizing *gradient* is real and monotonic — per-contract expectancy
degrades 4× from 1-2 lots to 6-10 lots, so bigger size means *worse* trades, not just more
exposure. **What changes:** J had **no positive edge at any size**. Bootstrap on the 1-2 lot
episodes: P(sum>0)=0.11, CI90 [−$10,265, +$1,413] — statistically indistinguishable from
breakeven, definitively not +$4,576. Hard 1-2 lot sizing is damage control, not an edge.
"J entry + machine exits" (EXPERIMENTS.md #1) is now the live question: entry timing alone
never got to prove itself under disciplined management.

### 2. ⛔ NEW — The killer behavior is intra-position averaging-down, not next-trade revenge.

- **Scaled-in episodes: n=67, −$138.5/trade, −$9,281 total** vs single-fill n=500, −$7.2/trade.
- **94% of scale-ins (63/67) averaged DOWN** — added at a lower premium than the first fill,
  i.e. bought more of a position already moving against him: 31.7% WR, −$8,628.
- Trade-level "revenge" is WEAK in his data: after a loss, the next entry is actually *fine*
  (n=194, −$4.6/trade — better than baseline); sized-up-≥1.5× share after loss = 25% vs 19%
  after win; P(size 3+) after loss 19.1% vs after win 17.3%. Fast re-entry ≤5min after a loss
  (n=60) ≈ −$5.9/trade — mildly worse than patient >15min (−$2.7), not catastrophic.
- Tilt DOES show at the **day** level: the day after a red day averages **−$90** (n=128 days)
  vs −$14 after a green day (n=93).

**Doctrine mapping: Rule 4 (no adds without a new trigger) is THE load-bearing guard** —
it alone addresses −$9,281 of the −$12,885 net loss. Post-loss size vetoes are secondary.

### 3. ✅ NEW — J's directional read is genuinely good (59%); the loss is manufactured after entry.

Joining SPY spot at entry and exit (n=542 with context):

- **Direction hit rate 59.2%** — SPY moved his way between entry and exit far more often than chance.
- When direction RIGHT: option WR 62.9%, +$55.7/trade. When WRONG: 9.5% WR, −$138.5/trade.
- He converts a 59% directional read into a 41% option WR and −$23/trade: the gap is theta,
  spread, deep-OTM strikes (52% of entries are >1% OTM), and exit management — J's own data
  confirms C3 (SPY-price edge ≠ option edge).
- Hold-time gradient: <10m −$3.5/trade → 1-2h **−$112.4/trade** (direction hit rate stays
  ~60% across buckets — the decay is the instrument, not the read).
- Exit discipline: median loser cut at −42.7%, but **39% of losers were held past −50%**
  (130 episodes, −$30,381 gross). Capping those at −50% premium saves ≥ **$6,176** (bound:
  no option-path data; OPRA replay needed for the true number). 40% of winners were cut
  below +30%.

### 4. ✅ CONFIRMED + SHARPENED — VWAP/trend alignment and prior-day levels are his real entry fingerprint.

- VWAP-aligned (call above / put below): −$17.2/trade (n=373, WR 44.5%) vs counter-trend
  −$37.4 (n=169, WR 33.7%). Ribbon-aligned similar (+9pp WR). **Both-aligned** −$11.3 vs
  **neither** −$23.1 vs mixed −$45.8.
- **The single positive-expectancy context in his whole book: entry within 0.1% of a
  prior-day level (PDH/PDL/PDC): n=94, 46.8% WR, +$3.7/trade, PF 1.05** — degrading
  monotonically with distance (0.1–0.3%: −$21.9; >0.3%: −$33.2). At-level AND 1-2 lots:
  n=77, 49.4% WR, **+$1,634 total** — the best cohort in the dataset. (Bull at-level +$875
  strong; bear at-level −$524 — direction-asymmetric, cf. C25/C26.)
- The put bleed (bear −$39.6/trade vs bull −$7.0) is really an *alignment* bleed:
  bear+counter-VWAP = **−$68.1/trade, PF 0.37 (n=84)** — buying puts against an uptrend.
  Bull+aligned ≈ breakeven (−$5.4, PF 0.93). Direction per se is not the discriminator.
- His fades lose: population "fade" entries (bear in top quartile of session range / bull in
  bottom) = 33% WR, −$37.1/trade (n=97). The prior pass's "reversal-off-extreme is a winning
  archetype" came from 2 anchor winners — the archetype's population is a LOSER (C24 vindicated).

### 5. ✅ CONFIRMED — Midday is his window; the open and 13:30+ chop bleed. (And Wednesday is real.)

Episode-level time-of-day reproduces the prior claim almost bucket-for-bucket:

- Positive: **11:00 (n=51, +$29.9)**, **12:00 (n=30, +$26.1)**, **13:00 (n=19, 73.7% WR, +$74.5)**.
- Negative: 09:30 (n=139, −$35.9), 11:30 (n=43, −$63.0), 13:30 (n=30, −$96.5), 15:00+ (n=11, −$68).
- 24% of his volume (09:30 bucket) sits in his worst half-hour; the live engine's 09:35 entry
  gate fires exactly there. Small n's per bucket — treat as a strong prior for the
  time-weighting A/B (EXPERIMENTS.md #4), not a rule.
- Day-of-week: Monday −$32.2 and Wednesday −$41.3/trade vs Thu/Fri ≈ −$10; Wednesday worst-WR
  claim confirmed (34.1%).

---

## Other traits (fresh numbers)

- **Instrument profile:** 85% 0DTE; median 1 contract; median entry premium $2.00; 52% of
  entries >1% OTM (0DTE lotto zone). Deep-OTM isn't obviously worse per trade (−$17.9) than
  0.1–0.5% OTM (−$33.7) — but WR mechanics differ (cheap low-WR vs pricier mid-WR).
- **Premium-at-risk bands:** ≤$250: −$9.3/trade (n=246) · $250-750: −$16.5 (n=278) ·
  $750-1500: **−$125.5 (n=40)** · >$1500: −$328 (n=3). Risk-dollars gradient matches the
  contracts gradient.
- **No edge decay story:** 2022 (n=478) −$20.2/trade vs 2023 (n=71) −$41.7/trade — 2023 had
  better WR but bigger losers (sizing), consistent with the prior pass.
- **Concentration:** worst 5 days = 54% of the net loss (−$1,600 … −$1,145); best day +$1,065.
  Green days only 41.9% of 222.
- **First-of-day is not special** (−$25.7 vs −$20.8 later); the "stop after 2 daily losses"
  counterfactual saves only $2,246 (63 blocked trades) — day-level kill switches help less
  than position-level guards in his data.
- **Cap-at-2-lots counterfactual** (linear scale-down of oversized episodes): −$12,885 →
  −$8,833. Sizing discipline alone recovers ~$4k but does NOT make the book positive —
  exits must change too (see #3).

## Confirm / Revise scorecard vs the 2026-06-19 Opus pass

| Prior claim | Verdict | Fresh evidence |
|---|---|---|
| 1-2 lots = +$4,576 profitable; 3+ = −$17,461 (C31) | **REVISED** | Artifact of per-sell banding. Episodes: 1-2 = −$4,420 (breakeven-ish at best), 3+ = −$8,465. Gradient + doctrine implication (Rule 6) survive; "small-J was profitable" does not. |
| Scaled-in −$327/trade (C31) | **CONFIRMED (softer)** | −$138.5/episode × 67 = −$9,281; 94% are averaging-down. Rule 4 is the big guard. |
| Revenge/conviction sizing after losses | **REFUTED at trade level; CONFIRMED at day level** | Post-loss next trades are fine (−$4.6); red→next-day −$90/day avg. |
| Calls ≈ breakeven, puts bleed 5× | **CONFIRMED, mechanism sharpened** | bear−counter-VWAP (−$68/trade) carries the bleed; aligned bears −$31; aligned bulls −$5. |
| Midday edge (11:00/12:00/13:00), open + late bleed | **CONFIRMED** | Same buckets positive at episode level; 13:00 = 73.7% WR (n=19). |
| Winners cut / losers run | **CONFIRMED, quantified** | 39% of losers past −50% (−$30,381 gross); 40% of winners cut <+30%; −50% cap saves ≥$6,176. |
| "Reversal-off-extreme" = winning archetype (from top-10 winners) | **REFUTED for the population** | Fade cohort n=97: 33% WR, −$37/trade. C24 in action. |
| VWAP alignment near-universal in winners | **CONFIRMED as a contrast, NOT as positive edge** | Aligned −$17 vs counter −$37; even aligned is net negative on the full population (the j-daily-pattern +$26/trade figure was winner-date-biased, as its own caveat admitted). |
| WR 46.9% / net −$12,885 / 0DTE-dominant | **CONFIRMED** (WR is 41.4% at episode level; money identical) | Same parse, same dollars. |
| OP-16 anchors (2026 SPY trades) | **OUT OF SCOPE of this dataset** | 2026 trades are not in the 2021-23 WeBull export; nothing here contradicts them, but the at-level/alignment fingerprint is consistent with the 4/29–5/04 winners' structure. |

## Doctrine follow-ups proposed (not applied — Rule 9 / after-hours ratification)

1. **Amend C31's row** in LESSONS-LEARNED to the episode-level numbers (draft filed in
   `backtest/_lesson-inbox/`): the sizing gradient stands; the "+$4,576 profitable small-J"
   framing is wrong and currently feeds OP-16-adjacent reasoning.
2. The at-level entry fingerprint (+$3.7/trade at ≤0.1% from PDH/PDL/PDC) independently
   re-validates the LEVEL_REJECT family direction (range-scalp memory) from J's own history.
3. Entry-time weighting and the −50% catastrophe cap already in v15.3 get fresh empirical
   backing from #5 and #3; specs to test them properly are in `EXPERIMENTS.md`.
