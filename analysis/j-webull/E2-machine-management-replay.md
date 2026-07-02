# E2 — "J's entries + machine management" counterfactual replay (2026-07-01)

> ## ⚠ BS-SYNTHETIC OPTION PRICING — RANKING-ONLY EVIDENCE PER C1
> Every dollar figure below comes from a smile-less, spread-less, slippage-less
> Black-Scholes path model (`backtest/lib/pricing.py` conventions: IV = VIX/100,
> r = 4%, expiry 16:00 ET). These numbers rank hypotheses; they are NEVER a
> promotion gate and NEVER a forecast of live P&L. Anything promotable must be
> re-expressed as a detector on 2025-26 SPY and validated on OPRA real fills.

## Question

Was J's 2021-23 edge in his ENTRIES (destroyed by his management), or was there
no salvageable edge at all? E1/E3 already showed the raw 3-feature fingerprint
does not port to 2025-26 OPRA — this is the remaining question.

## Verdict: **MANAGEMENT_WAS_THE_LEAK** (top rung, on the BS-sim's ranking-only terms)

All three machine variants are materially positive vs J-actual AND above
breakeven in absolute terms, and the **opposite-direction null control loses
money** — so the sign is carried by J's directional read (his 59.2% hit rate),
not by the exit ladder mechanically harvesting volatility.

## Method

- Population: 567 closed SPX/SPY-family episodes (`trades-normalized.csv`).
- His EXACT entry moment + direction; entry priced at the close of the last
  COMPLETED SPY 5m bar before his entry tick (C6-causal, same convention as the
  context join). SPX/SPXW spot = 10×SPY, XSP = 1×SPY.
- Everything after entry replaced by v15-style mechanical exits, evaluated on
  5m bar closes: **TP1 +30% sells 0.8** (Safe `tp1_qty_fraction`), **runner
  targets 2.5× entry premium with breakeven stop after TP1**, **−50%
  catastrophe cap**, **15:50 ET time stop** (close of the 15:45 bar).
  Fractional-contract accounting; qty **hard-capped at his FIRST fill size**
  (no adds ever). No chandelier, no chart-stop — this isolates the
  premium-mechanical management layer only.
- Script: `analysis/j-webull/scripts/e2_e5_replay.py` (self-checks rebuild
  against the published parse: 567 episodes, −$12,885 to the dollar).
  Full numbers: `E2-machine-management-replay.json`.

### Data sources (disclosed)

- SPY 5m: existing cache `cache/spy_5m_2021-06-01_2023-10-31.csv` (Alpaca IEX,
  raw). **Verified span: 2021-06-01 09:30 → 2023-10-31 15:55 ET, 47,488 RTH
  bars** — covers the full family population (2021-06-09 → 2023-10-03), so no
  historical backfill fetch was needed for SPY.
- VIX: **NO 2021-23 VIX existed in the repo** — fetched daily ^VIX via
  yfinance → `cache/vix_daily_2021-06-01_2023-10-31.csv` (592 rows,
  2021-06-01..2023-10-05). IV = the entry day's **OPEN** (known at any RTH
  entry — causal), held constant intraday. Daily granularity, not 5m.

### Drops (counted, per C7)

| Reason | n |
|---|---|
| No context join (`ctx_ok=False`, pre-09:35 entries / missing IEX bars) | 25 |
| No path bars after entry (entered at/after 15:45 bar close) | 3 |
| Unpriceable at his strike (BS entry premium < $0.05 — deep-OTM the smile-less model can't price) | 102 (variant a only) |
| No VIX / no entry bar | 0 |

## Results

| | n | Machine total | Exp/tr | WR | MaxDD | Total drop-top3 | P(sum>0) boot | J-actual same pop (exp/tr, WR) | Δ vs J |
|---|---|---|---|---|---|---|---|---|---|
| **(a) his strike** + machine exits + first-fill cap | 437 | **+$8,184** | +$18.7 | 63.8% | $1,329 | +$6,506 | 0.999 | −$11,169 (−$25.6, 41.9%) | **+$19,353** |
| **(b) ATM strike** + machine exits + first-fill cap | 539 | **+$109,112** | +$202.4 | 67.0% | $5,488 | +$97,484 | 1.000 | −$12,818 (−$23.8, 41.0%) | **+$121,930** |
| **(c) = (b), best cell** (at-level ≤0.1% & VWAP-aligned & morning 10:00-11:00) | 29 | **+$12,062** | +$415.9 | 79.3% | $868 | +$7,154 | 1.000 | +$2,613 (+$90.1, 65.5%) | +$9,449 |
| **NULL: (b) with OPPOSITE direction** | 539 | **−$27,557** | −$51.1 | 49.7% | $39,820 | −$37,566 | 0.085 | — | — |

Exit-reason mix (b): runner_breakeven 203 · catastrophe_stop 179 · runner_target 128 ·
time stops 29. Null control: catastrophe_stop 261 (the ladder correctly bleeds
out wrong-way entries).

### The null control is the load-bearing check

- Direction-attributable spread: (b) − (null) = **$136,669 over 539 trades ≈
  $253.6/trade** of J-direction alpha as expressed through machine exits.
- Convexity/realized-vol baseline (average of both directions) = **+$75.7/tr**
  — this part is a frictionless-BS artifact (long-gamma + 2022 realized vol vs
  VIX-implied, zero spread) and would be substantially eaten by real 0DTE
  spreads. It inflates ALL absolute dollar figures above.
- Even so: the null is **negative** (P(sum>0)=0.085) while J's direction is
  strongly positive — the ranking conclusion (his entries carried signal his
  management destroyed) does not depend on the artifact.

### BS calibration honesty check (why variant (a) is the noisy one)

Median BS-entry-premium / J's-actual-entry-premium at his strikes = **0.222**;
**69.8%** of episodes are BS-priced below HALF his actual cost (smile-less
BS+VIX massively underprices his deep-OTM lottos; only 1.3% overpriced 2×).
Percent-based exits on a mispriced entry premium make (a) path-noisy, and the
102 unpriceable drops select AGAINST his deepest-OTM entries. (b)/ATM is the
better-behaved model, at the cost of answering a slightly different question
("his moments, sane strikes").

## What this licenses (and what it does not)

1. **Licensed (ranking):** J's 2021-23 entry moments contained genuine
   directional signal; mechanical v15-style management + no-adds flips his book
   from −$11K/−$13K to positive in-era on every variant tested, and the best-cell
   cohort (c) is the strongest per-trade. Keep mining his entry CONTEXTS
   (E1-style detectors, midday/at-level families for the P1 swarm); the prize
   is real, the leak was management + deep-OTM strikes + adds.
2. **Licensed (ranking):** strike normalization to ATM is worth far more than
   exit mechanics alone ((b) ≫ (a)) — J's own data re-confirms C3 and the
   engine's per-tier strike selection: the deep-OTM leak was the second-biggest
   destroyer after management.
3. **NOT licensed:** any absolute P&L expectation, any live/paper arming, any
   params change. (a)'s +$18.7/tr would be thinner after real spreads; (b)'s
   +$202/tr contains the +$76/tr frictionless-vol artifact. (c) is n=29 with
   top-3 winners = 41% of its total (C4 concentration).
4. E1/E3 remain true: the fingerprint as a 3-feature screen did NOT port to
   2025-26 OPRA. E2 refines the conclusion — the signal existed in-era, so the
   failure to port is about regime/expression, not about there never having
   been anything to port. Next expression attempts must validate on OPRA real
   fills (C1) before anything ships.

## Caveats (complete list)

- BS-synthetic, ranking-only (C1): no vol smile, no bid-ask spread, no
  slippage, no fills — absolute dollars inflated (see null decomposition).
- IV = daily ^VIX OPEN via yfinance (disclosed new fetch), constant intraday;
  actual 0DTE IV runs 0.5-1.5× VIX and moves intraday.
- 5m bar-close granularity: stops/TPs fire at bar closes (gap-through gets the
  bar price, intrabar touches are missed both ways).
- Entry priced up to 5 min BEFORE his actual tick (last completed bar) — on
  momentum entries this is a small favorable bias to all variants.
- Non-0DTE episodes (15% of book) are force-flattened same-day at 15:50 (the
  machine's rule, not their real expiry); SPX AM/PM settlement ignored.
- r fixed at 4% across an era where rates ran 0→5.5% (0DTE negligible).
- 130 episodes dropped/absent across variants — counted above; (a)'s drops are
  adversely selective (deepest OTM).
