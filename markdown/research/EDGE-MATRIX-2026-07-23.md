# EDGE MATRIX — 2026-07-23 — the giant table

> **Run:** 6 pre-registered level-interaction families × frozen grids = **98 cells**, all run once over the
> frozen day inventory (386 covered days 2025-01-02→2026-07-22; 381 OPRA real-fill days; 285 tuning / 96 held-out
> by date, held-out = 2026-02-25→2026-07-17). Real OPRA fills only, zero BS-synthetic in gate math, live
> RIBBON_RIDE exit shape + structure stop on every cell (entry-side tuning ONLY). All inputs:
> `analysis/edge-matrix/` (preregs, results, episodes, day inventory, parity oracle).
> **Verification survivors list (from the verification pass): `[]` — EMPTY.**

## VERDICT LINE

**🚨 NO SHIP-CANDIDATES. 0 of 98 cells clears the ship bar after matrix-wide BH-FDR.** All 82 cells of the
five RTH families have **negative tuning expectancy** (best: −$5.08/trade). The only positive cells live in the
premarket family, on a structurally tiny tuning population (24 premarket-covered tuning days), and its single
4/4-gate cell was **REFUTED** by the verification pass (survivors = []). 19 cells are BH-significant — **every
one in the LOSING direction.** This is a clean, pre-registered null across the entire level-interaction entry
vocabulary under the live exit shape.

---

## TV PARITY ORACLE — certifies / caveats this table

Full report: [`analysis/edge-matrix/tv-parity-oracle-2026-07-23.md`](../../analysis/edge-matrix/tv-parity-oracle-2026-07-23.md)

| Layer | Verdict | Meaning for this table |
|---|---|---|
| **Bar data** (SPY cache vs TV, same bar) | ✅ PARITY_OK (worst $0.04) | The 5m bars every detector read match what J's chart prints. **The table's price triggers are certified.** |
| **EMA math** at matched series scope | ✅ ~OK (≤$0.38 residual) | `lib/ribbon.py` arithmetic is sound. |
| **Engine ribbon vs J's chart render** | 🚨 **CRITICAL** (up to $6.40 at open) | J's TV chart computes EMAs over **extended-hours** bars; engine/backtest ribbon is **RTH-only**. Backtest↔live-engine parity is intact (same lib, same scope, self-consistent) — but ribbon-gated entries (bear family's BEAR-stack gate) and ribbon-flip exits in this matrix reflect the **ENGINE's** ribbon, which can disagree with the ribbon J *sees* for ~90 min after any overnight gap. |

**Net:** this is an **engine-truth table**, certified at the bar level. Any read of the form "the chart J was
looking at would have shown…" is caveated on gap-day mornings until the RTH-vs-ETH ribbon doctrine question
(oracle follow-up #1) is decided. No cell's dollars change either way — exits were walked on the engine ribbon,
which is exactly what production would have done.

---

## How to read the table

- **Cell (plain chart language)** — uniquely identifies the cell; machine `cell_id`s are 1:1 in each family's results JSON.
- **n** = tuning-side real OPRA fills. **Exp** = mean $/trade (3-lot ATM, live Safe sizing). **Day-WR** = fraction of tuning days with ≥1 fill that finished green.
- **Ex-top3** = tuning total P&L minus the 3 best trades (concentration check). **Held-out** = total $ on the frozen 96 held-out days, touched once.
- **p_raw conventions differ by family (pre-registered):** `bear-level-rejection`, `bull-reclaim-quality`, `sr-flip-retest` report a **two-sided** one-sample t vs zero (small p = significantly *non-zero* — here that means significantly **negative**); `break-retest`, `range-pingpong`, `premarket-level` report a **one-sided** sign-flip permutation p = P(perm ≥ observed) (small p = positive edge; p→1 = deeply negative).
- **q** = Benjamini-Hochberg-adjusted p across the **entire 98-cell matrix** (mandatory multiplicity correction; single ranking over all families). Cells overlap heavily within and across families (same days, nested episode sets), so p's are positively dependent — BH remains a reasonable (conservative-ish) control under that structure, disclosed rather than modeled.
- **Direction check (do not misread):** every q ≤ 0.05 cell in this table has *negative* expectancy — BH-significant **losses**. As a coherence check, converting all 98 cells to a one-sided *positive-edge* p and re-running BH yields **zero** cells at q ≤ 0.05. There is no multiplicity-surviving positive edge anywhere in this matrix.
- **Verification** — `SURVIVED` / `REFUTED` / `not-tested`. Only cells clearing 4/4 pre-registered gates advanced to the verification pass; the survivors list returned **empty**, so the sole 4/4 cell is REFUTED and every other cell never reached the bar.
- **Gates** (pre-registered, per cell): G1 tuning total > 0 · G2 day-majority > 50% · G3 survives ex-top-1 · G4 held-out total > 0.

---

## THE MATRIX — 98 cells (grouped by family, best expectancy first within family)

| Family | Cell (plain chart language) | n | Exp $/tr | Day-WR | Ex-top3 $ | Held-out $ | p_raw | q (BH-98) | Gates | Verification |
|---|---|---|---|---|---|---|---|---|---|---|
| premarket-level | go with break of PM high/low, ±$0.20 zone, next-bar confirm; direction per approach side | 2 | +521.25 | 100% | +0 | -243 | 1 | 1 | 3/4 | not-tested |
| premarket-level | go with break of PM high/low, ±$0.35 zone, next-bar confirm; direction per approach side | 2 | +521.25 | 100% | +0 | -1092 | 1 | 1 | 3/4 | not-tested |
| premarket-level | fade first RTH touch PM high/low, ±$0.35 zone, next-bar confirm; direction per approach side | 12 | +172.65 | 55% | +77 | +566 | 0.0526 | 0.156 | 4/4 | **REFUTED** |
| premarket-level | go with break of PM high/low, ±$0.20 zone, no confirm; direction per approach side | 7 | +140.96 | 71% | -47 | -370 | 0.1425 | 0.325 | 3/4 | not-tested |
| premarket-level | go with break of PM high/low, ±$0.35 zone, no confirm; direction per approach side | 7 | +140.96 | 71% | -47 | -1527 | 0.1425 | 0.325 | 3/4 | not-tested |
| premarket-level | fade first RTH touch PM high/low, ±$0.20 zone, next-bar confirm; direction per approach side | 12 | +114.89 | 46% | -617 | -686 | 0.1714 | 0.382 | 2/4 | not-tested |
| premarket-level | fade first RTH touch PM high/low, ±$0.20 zone, no confirm; direction per approach side | 18 | +58.14 | 50% | -604 | -1434 | 0.2006 | 0.437 | 2/4 | not-tested |
| premarket-level | fade first RTH touch PM high/low, ±$0.35 zone, no confirm; direction per approach side | 20 | +46.58 | 50% | -718 | -862 | 0.2209 | 0.471 | 2/4 | not-tested |
| premarket-level | go with break of PM flip level, ±$0.20 zone, no confirm; direction per approach side | 1 | +7.87 | 100% | +0 | -424 | 1 | 1 | 2/4 | not-tested |
| premarket-level | go with break of PM flip level, ±$0.35 zone, no confirm; direction per approach side | 1 | +7.87 | 100% | +0 | -245 | 1 | 1 | 2/4 | not-tested |
| premarket-level | fade first RTH touch PM flip level, ±$0.20 zone, no confirm; direction per approach side | 0 | +0.00 | — | +0 | -1899 | 1 | 1 | 0/4 | not-tested |
| premarket-level | fade first RTH touch PM flip level, ±$0.20 zone, next-bar confirm; direction per approach side | 0 | +0.00 | — | +0 | -1081 | 1 | 1 | 0/4 | not-tested |
| premarket-level | go with break of PM flip level, ±$0.20 zone, next-bar confirm; direction per approach side | 0 | +0.00 | — | +0 | +610 | 1 | 1 | 1/4 | not-tested |
| premarket-level | fade first RTH touch PM flip level, ±$0.35 zone, no confirm; direction per approach side | 0 | +0.00 | — | +0 | -896 | 1 | 1 | 0/4 | not-tested |
| premarket-level | fade first RTH touch PM flip level, ±$0.35 zone, next-bar confirm; direction per approach side | 0 | +0.00 | — | +0 | -170 | 1 | 1 | 0/4 | not-tested |
| premarket-level | go with break of PM flip level, ±$0.35 zone, next-bar confirm; direction per approach side | 0 | +0.00 | — | +0 | +761 | 1 | 1 | 1/4 | not-tested |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 10c, retest ±35c zone, next bar closes on flip side | 388 | -5.08 | 37% | -4128 | +2191 | 0.592 | 1 | 1/4 | not-tested |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 20c, retest ±35c zone, next bar closes on flip side | 377 | -6.14 | 36% | -4470 | +876 | 0.5322 | 0.948 | 1/4 | not-tested |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 10c, retest ±35c zone, retest bar closes on flip side | 477 | -6.50 | 38% | -5323 | +1140 | 0.4264 | 0.774 | 1/4 | not-tested |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 10c, retest ±15c zone, retest bar closes on flip side | 500 | -7.78 | 35% | -6128 | +250 | 0.2989 | 0.587 | 1/4 | not-tested |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 20c, retest ±35c zone, retest bar closes on flip side | 458 | -8.79 | 38% | -6246 | +1227 | 0.2993 | 0.587 | 1/4 | not-tested |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 20c, retest ±15c zone, retest bar closes on flip side | 481 | -9.29 | 34% | -6705 | -311 | 0.2272 | 0.474 | 0/4 | not-tested |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 10c, retest ±15c zone, next bar closes on flip side | 401 | -15.32 | 32% | -7927 | +1824 | 0.0697 | 0.19 | 1/4 | not-tested |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 20c, retest ±15c zone, next bar closes on flip side | 395 | -15.38 | 30% | -7982 | +1012 | 0.0834 | 0.221 | 1/4 | not-tested |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 10c, retest ±15c zone, next bar closes on flip side | 378 | -18.37 | 32% | -9052 | -646 | 0.0639 | 0.179 | 0/4 | not-tested |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 20c, retest ±15c zone, next bar closes on flip side | 378 | -21.32 | 30% | -10093 | -714 | 0.0281 | 0.0984 | 0/4 | not-tested |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 10c, retest ±35c zone, next bar closes on flip side | 387 | -25.53 | 31% | -11694 | -1020 | 0.0089 | 0.0459 | 0/4 | not-tested |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 10c, retest ±35c zone, retest bar closes on flip side | 476 | -25.96 | 31% | -14290 | -162 | 0.0013 | 0.0116 | 0/4 | not-tested |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 20c, retest ±35c zone, retest bar closes on flip side | 461 | -26.62 | 31% | -14205 | -133 | 0.0012 | 0.0116 | 0/4 | not-tested |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 20c, retest ±35c zone, next bar closes on flip side | 375 | -27.43 | 29% | -12167 | -859 | 0.0057 | 0.038 | 0/4 | not-tested |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 20c, retest ±15c zone, retest bar closes on flip side | 490 | -30.69 | 27% | -16978 | +64 | ~0 | ~0 | 1/4 | not-tested |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 10c, retest ±15c zone, retest bar closes on flip side | 500 | -32.68 | 26% | -18214 | -417 | ~0 | ~0 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; RSI<68 req; no reset req; ≤$3.50 off session low | 551 | -7.16 | 40% | -6377 | -1950 | 0.3439 | 0.636 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; no RSI cap; no reset req; ≤$3.50 off session low | 575 | -7.43 | 40% | -6707 | -2433 | 0.3223 | 0.607 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; RSI<68 req; RSI-reset≤55 in last hr req; ≤$3.50 off session low | 548 | -7.65 | 39% | -6624 | -1950 | 0.3121 | 0.6 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; no RSI cap; RSI-reset≤55 in last hr req; ≤$3.50 off session low | 564 | -8.81 | 40% | -7400 | -2415 | 0.2402 | 0.49 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; no RSI cap; no reset req; any extension | 762 | -10.39 | 40% | -10348 | -4465 | 0.1355 | 0.324 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; RSI<68 req; no reset req; ≤$3.50 off session low | 786 | -11.28 | 38% | -11299 | -4112 | 0.0477 | 0.146 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; no RSI cap; RSI-reset≤55 in last hr req; any extension | 737 | -11.39 | 40% | -10828 | -4559 | 0.102 | 0.25 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; no RSI cap; no reset req; ≤$3.50 off session low | 810 | -11.58 | 38% | -11814 | -4421 | 0.0422 | 0.133 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; RSI<68 req; no reset req; any extension | 728 | -11.75 | 38% | -10990 | -4847 | 0.0906 | 0.228 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; RSI<68 req; RSI-reset≤55 in last hr req; ≤$3.50 off session low | 780 | -11.96 | 37% | -11762 | -4112 | 0.0353 | 0.119 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; no RSI cap; no reset req; any extension | 1048 | -12.45 | 37% | -15484 | -5387 | 0.0187 | 0.0788 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; RSI<68 req; RSI-reset≤55 in last hr req; any extension | 714 | -13.26 | 38% | -11899 | -5119 | 0.0565 | 0.163 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; no RSI cap; RSI-reset≤55 in last hr req; ≤$3.50 off session low | 798 | -13.27 | 38% | -13022 | -4812 | 0.0193 | 0.0788 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; no RSI cap; RSI-reset≤55 in last hr req; any extension | 1013 | -13.64 | 36% | -16246 | -5749 | 0.0104 | 0.051 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; RSI<68 req; no reset req; any extension | 1015 | -13.83 | 36% | -16466 | -5799 | 0.0087 | 0.0459 | 0/4 | not-tested |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; RSI<68 req; RSI-reset≤55 in last hr req; any extension | 992 | -15.01 | 35% | -17325 | -5992 | 0.0044 | 0.0332 | 0/4 | not-tested |
| range-pingpong | Fade edge of 0.80-3.50 range, 3+ touches/side, ±$0.20 zone, wait 1 bar inside range; both directions | 942 | -8.05 | 38% | -10468 | -8096 | 0.8862 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 0.80-3.50 range, 2+ touches/side, ±$0.20 zone, wait 1 bar inside range; both directions | 947 | -9.25 | 38% | -11641 | -9079 | 0.921 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 1.20-3.50 range, 3+ touches/side, ±$0.20 zone, wait 1 bar inside range; both directions | 432 | -9.54 | 36% | -6570 | -6495 | 0.8074 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 0.80-3.50 range, 3+ touches/side, ±$0.20 zone, enter at tag-bar close; both directions | 1179 | -9.97 | 38% | -14394 | -9263 | 0.9639 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 0.80-3.50 range, 3+ touches/side, ±$0.10 zone, enter at tag-bar close; both directions | 1055 | -10.73 | 37% | -13998 | -6726 | 0.9561 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 0.80-3.50 range, 3+ touches/side, ±$0.10 zone, wait 1 bar inside range; both directions | 840 | -11.20 | 39% | -12286 | -6882 | 0.9367 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 1.20-3.50 range, 2+ touches/side, ±$0.20 zone, wait 1 bar inside range; both directions | 433 | -12.01 | 35% | -7651 | -7284 | 0.8614 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 0.80-3.50 range, 2+ touches/side, ±$0.20 zone, enter at tag-bar close; both directions | 1185 | -12.03 | 37% | -16898 | -8244 | 0.9825 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 0.80-3.50 range, 2+ touches/side, ±$0.10 zone, wait 1 bar inside range; both directions | 842 | -12.19 | 39% | -13142 | -7168 | 0.953 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 1.20-3.50 range, 3+ touches/side, ±$0.20 zone, enter at tag-bar close; both directions | 542 | -12.41 | 37% | -9160 | -3807 | 0.9117 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 0.80-3.50 range, 2+ touches/side, ±$0.10 zone, enter at tag-bar close; both directions | 1057 | -12.87 | 36% | -16286 | -5922 | 0.9825 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 1.20-3.50 range, 3+ touches/side, ±$0.10 zone, enter at tag-bar close; both directions | 476 | -13.78 | 39% | -8992 | -2534 | 0.9176 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 1.20-3.50 range, 2+ touches/side, ±$0.20 zone, enter at tag-bar close; both directions | 545 | -14.96 | 37% | -10588 | -3748 | 0.9471 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 1.20-3.50 range, 2+ touches/side, ±$0.10 zone, enter at tag-bar close; both directions | 475 | -16.45 | 39% | -10247 | -1984 | 0.947 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 1.20-3.50 range, 3+ touches/side, ±$0.10 zone, wait 1 bar inside range; both directions | 374 | -18.34 | 36% | -9310 | -4386 | 0.9357 | 1 | 0/4 | not-tested |
| range-pingpong | Fade edge of 1.20-3.50 range, 2+ touches/side, ±$0.10 zone, wait 1 bar inside range; both directions | 373 | -20.78 | 35% | -10200 | -4667 | 0.9588 | 1 | 0/4 | not-tested |
| break-retest | Break level by 30c, retest ±25c zone within 60min, wait for close beyond level; both directions | 1109 | -10.37 | 42% | -14599 | -9501 | 0.945 | 1 | 0/4 | not-tested |
| break-retest | Break level by 30c, retest ±25c zone within 60min, enter on the touch; both directions | 1247 | -10.91 | 42% | -16702 | -8496 | 0.9668 | 1 | 0/4 | not-tested |
| break-retest | Break level by 30c, retest ±10c zone within 60min, enter on the touch; both directions | 1206 | -11.28 | 39% | -16702 | -11726 | 0.9743 | 1 | 0/4 | not-tested |
| break-retest | Break level by 30c, retest ±25c zone within 30min, enter on the touch; both directions | 1194 | -11.39 | 41% | -16703 | -8267 | 0.9693 | 1 | 0/4 | not-tested |
| break-retest | Break level by 30c, retest ±25c zone within 30min, wait for close beyond level; both directions | 1063 | -11.57 | 41% | -15402 | -8710 | 0.9571 | 1 | 0/4 | not-tested |
| break-retest | Break level by 30c, retest ±10c zone within 60min, wait for close beyond level; both directions | 1021 | -13.21 | 39% | -16586 | -11816 | 0.9712 | 1 | 0/4 | not-tested |
| break-retest | Break level by 15c, retest ±25c zone within 60min, wait for close beyond level; both directions | 1491 | -13.75 | 44% | -23597 | -12255 | 0.9944 | 1 | 0/4 | not-tested |
| break-retest | Break level by 15c, retest ±10c zone within 60min, wait for close beyond level; both directions | 1360 | -13.91 | 42% | -22020 | -14309 | 0.9951 | 1 | 0/4 | not-tested |
| break-retest | Break level by 15c, retest ±10c zone within 60min, enter on the touch; both directions | 1558 | -14.28 | 42% | -25344 | -13088 | 0.9975 | 1 | 0/4 | not-tested |
| break-retest | Break level by 15c, retest ±25c zone within 60min, enter on the touch; both directions | 1615 | -14.43 | 43% | -26407 | -10804 | 0.9982 | 1 | 0/4 | not-tested |
| break-retest | Break level by 15c, retest ±25c zone within 30min, wait for close beyond level; both directions | 1476 | -15.21 | 44% | -25552 | -10286 | 0.9981 | 1 | 0/4 | not-tested |
| break-retest | Break level by 15c, retest ±25c zone within 30min, enter on the touch; both directions | 1596 | -15.38 | 42% | -27651 | -10226 | 0.9992 | 1 | 0/4 | not-tested |
| break-retest | Break level by 30c, retest ±10c zone within 30min, enter on the touch; both directions | 1122 | -16.70 | 36% | -21836 | -11868 | 0.997 | 1 | 0/4 | not-tested |
| break-retest | Break level by 15c, retest ±10c zone within 30min, enter on the touch; both directions | 1503 | -17.35 | 41% | -29174 | -12025 | 0.9998 | 1 | 0/4 | not-tested |
| break-retest | Break level by 15c, retest ±10c zone within 30min, wait for close beyond level; both directions | 1329 | -17.63 | 42% | -26532 | -12069 | 0.9995 | 1 | 0/4 | not-tested |
| break-retest | Break level by 30c, retest ±10c zone within 30min, wait for close beyond level; both directions | 956 | -19.04 | 36% | -21301 | -11681 | 0.9973 | 1 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; any touch; touch alone, no confirm | 1079 | -8.87 | 34% | -12150 | -7191 | 0.08855 | 0.228 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; any touch; touch alone, no confirm | 857 | -16.27 | 34% | -16518 | -5571 | 0.01521 | 0.071 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 2nd+ touch; touch alone, no confirm | 529 | -17.68 | 33% | -11894 | -2315 | 0.03758 | 0.123 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; any touch; red candle at the level | 767 | -18.71 | 31% | -16779 | -5484 | 0.0089 | 0.0459 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; any touch; red candle at the level | 639 | -19.41 | 34% | -14836 | -6407 | 0.02575 | 0.0935 | 0/4 | not-tested |
| bear-level-rejection | **[LIVE BASELINE]** Put on rejection; penny-exact; any touch; close back below the level (= `detect_level_rejection`) | 508 | -24.88 | 32% | -15265 | -3425 | 0.02015 | 0.079 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 3rd+ touch; touch alone, no confirm | 319 | -25.04 | 29% | -10256 | -2170 | 0.02396 | 0.0903 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 2nd+ touch; touch alone, no confirm | 463 | -27.84 | 33% | -15149 | -2295 | 0.00606 | 0.038 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; any touch; close back below the level | 462 | -28.17 | 32% | -15639 | -5236 | 0.01922 | 0.0788 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 3rd+ touch; touch alone, no confirm | 359 | -30.64 | 26% | -13192 | +780 | 0.00106 | 0.0116 | 1/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 2nd+ touch; red candle at the level | 450 | -35.56 | 28% | -18357 | -2199 | 0.00031 | 0.00555 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 3rd+ touch; red candle at the level | 268 | -37.07 | 27% | -11961 | -2648 | 0.0025 | 0.0204 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 2nd+ touch; red candle at the level | 401 | -37.10 | 30% | -17231 | -2455 | 0.0011 | 0.0116 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 2nd+ touch; close back below the level | 411 | -38.64 | 31% | -18238 | -2705 | 0.00043 | 0.00602 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 3rd+ touch; close back below the level | 239 | -41.02 | 29% | -11999 | -2048 | 0.00621 | 0.038 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 3rd+ touch; red candle at the level | 293 | -41.71 | 26% | -14218 | +597 | 7e-05 | 0.00171 | 1/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 3rd+ touch; close back below the level | 266 | -45.27 | 23% | -14187 | -681 | 0.00034 | 0.00555 | 0/4 | not-tested |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 2nd+ touch; close back below the level | 369 | -52.79 | 29% | -21748 | -762 | 2e-05 | 0.000653 | 0/4 | not-tested |

Results provenance: `bear-level-rejection-results-2026-07-23.json` · `bull-level-reclaim-quality-results-2026-07-23.json` ·
`break-retest-continuation-results.json` · `range-pingpong-results.json` · `sr-flip-retest-results-2026-07-23.json` ·
`premarket-level-interaction-episodes.json` (cells embedded in header) — all under `analysis/edge-matrix/`.

---

## RANKED VERDICT — FOCUS-DOCTRINE realism lens (day-consistency > total P&L; one-good-trade cadence)

Ranking families by the lens in FOCUS-DOCTRINE §3 (day-consistency first, per-trade expectancy at ~1-trade/day
cadence second, +30%-class capture third):

1. **premarket-level-interaction (PM high/low arm)** — the ONLY family with positive-expectancy cells and the only
   one whose cadence naturally fits one-good-trade (≤1 episode per level per day, first-touch only). But the
   evidence is **structurally unmeasurable today**: only 24 of 285 tuning days have ≥6 premarket bars (feed seam
   disclosed pre-run in the prereg; full 04:00-premarket coverage starts 2026-03-16 and sits ENTIRELY inside the
   held-out window). Best cell n=12, below the n≥15 floor, q=0.156, and the verifier refuted it. **Verdict: not an
   edge claim — a data-backfill claim.**
2. **sr-flip-retest, BULL side** — every tuning cell negative (−$5 to −$15/trade) yet **all 7 gate-4-passing BULL
   cells are held-out positive** (held-out = the most recent 5 months). Day-WR ≤38% everywhere → fails the
   day-consistency lens outright. The tuning-negative/held-out-positive split is a regime signature (recent bull
   tape), not entry edge (C22 pattern). J's praised 07-17 "13:50 break and then retest" produced **zero signals**
   in any BEAR cell's anchor window — the mechanical vocabulary does not even capture the anchor trade.
3. **bull-level-reclaim-quality** — J's 07-21 quality conditioning (RSI cap / reset / extension cap) moves
   expectancy in the RIGHT direction (raw −$12.45 → best-conditioned −$7.16, day-WR 37%→40%) but **never crosses
   zero**. The conditioning thesis is directionally validated as a LOSS-REDUCER, refuted as an entry-maker. The
   live block on raw bull reclaim stays justified.
4. **range-pingpong** — all 16 cells negative (best −$8.05/trade), day-WR ≤39%, held-out all negative. "Things
   ping-pong between levels" does not survive as a mechanical zone-fade under the live exit shape.
5. **break-retest-continuation** — all 16 cells negative; carries the highest day-WRs of the RTH families (up to
   44%) but the worst totals (−$11.5K to −$26K). Wider break margin (30c) loses less than 15c — decisiveness
   filters noise but not enough.
6. **bear-level-rejection (refinement grid)** — the harshest result: **the live baseline detector cell itself is
   −$24.88/trade over 508 isolated fills**, and J's "repeated rejection ⇒ put" nth-touch thesis makes it
   monotonically WORSE (3rd+ touch: −$30 to −$45/trade; the more a level is tested, the more likely it breaks —
   consistent with L142/C25). 11 of 18 cells are BH-significant losers. **Scope honesty:** this isolates the
   detector + ribbon-BEAR + entry-window; production stacks VIX/volume/HTF/tier blocks on top (and
   `block_level_rejection=true` already blocks the bare LEVEL tier live) — this refutes the DETECTOR as a
   standalone entry, not the live ELITE confluence path.

**Cross-family structural finding (the real takeaway):** 82/82 RTH cells negative, day-WR 23–45%, under ONE
frozen execution stack (ATM 3-lot, next-bar VWAP entry, RIBBON_RIDE + structure stop, 15:40/15:50 time stop).
The matrix cannot distinguish "these entries have no edge" from "this exit/friction stack eats whatever edge the
entries have" — exits were frozen by design (entry-side tuning only). The next discriminating experiment is
exit-side/friction, not a seventh entry grid.

---

## SHIP-CANDIDATES

**NONE.** No cell passes 4/4 pre-registered gates AND matrix-wide BH-FDR AND verification. The single 4/4-gate
cell (`pmli-pm_hl-b35-reject-next_bar`, n=12) fails the evidence floor (n<15), fails BH (q=0.156), and was
refuted by the verification pass (survivors list empty). Per the pre-registered honest-null commitments in all
six preregs: **the null is the result.** No extra-signal lane is proposed from this run.

## ACCRETE (promising but insufficient-n — feed the standing rerun loop, do not wire)

| Item | What accrues | Becomes decidable when |
|---|---|---|
| **premarket PM-high/low family** (fade + go-with arms) | Every new trading day now carries full 04:00 premarket bars (SIP appends since 2026-03-16) → the live-forward segment grows ~20 days/month | n≥15 fills per cell on POST-2026-07-17 forward days alone; re-verify then. A 2025 premarket backfill (vendor data) would unlock the whole tuning window at once — that is a data purchase decision, not a research one |
| **sr-flip-retest BULL, wide-zone cells** (±35c, next-bar confirm) | Forward days accrue held-out-style evidence untouched by tuning | Only if forward segment shows day-WR >50% — the current 37% day-WR means regime, not edge; treat as a watch item, not a candidate |
| **bull-reclaim conditioning as a VETO layer** | The dist-cap/RSI-cap knobs reliably cut losses (~$4-5/trade) on an already-blocked family | Only relevant if bull reclaim is ever re-armed at n≥20 under SS-B per OP-16's standing re-eval — then test conditioning as block-filter refinement, not entry |

## DEAD (nothing here — recorded so nobody re-digs)

- **bear-level-rejection entry refinements** — zone-band widening, nth-touch escalation, confirmation relaxation:
  ALL negative; nth-touch INVERTS the thesis. 11/18 cells BH-significant losers.
- **range-pingpong zone-fade** — 16/16 negative, both spacings, both touch floors, both bands, both confirms.
- **break-retest-continuation** — 16/16 negative in both directions; J's anchor instance not reproduced by the vocabulary.
- **sr-flip-retest BEAR side** — 6/8 BEAR cells BH-significant losers (−$18 to −$33/trade).
- **premarket PM-FLIP-level arm** — LevelMemory rarely forms on sparse premarket bars: 0-1 tuning signals in 8/8
  cells. Structurally starved, not evidenced. (Distinct from the pm_hl arm above.)
- Combined with the 2026-07-20 premarket-touch-credit KILL: premarket **touch counts** on RTH levels add nothing
  (killed) and premarket **flip levels** are unformable on current data — only the PM high/low location question
  remains open, and only pending data.

---

## Standing rerun — "infinite backtesting" loop

Stub + full protocol notes: [`backtest/tools/edge_matrix_rerun.py`](../../backtest/tools/edge_matrix_rerun.py).
One command (after-hours only): `python backtest/tools/edge_matrix_rerun.py --refresh` — rebuilds the day
inventory forward, appends new-day episodes per family (frozen grids, frozen gates, original tuning/held-out
split untouched; new days accrue to a FORWARD segment), recomputes matrix-wide BH including forward evidence,
and appends a dated delta section to this file. Grid/gate changes require a NEW dated prereg — the rerun tool
must never tune.

## Disclosures (committed in the preregs, honored here)

- Real OPRA fills only; no BS-synthetic anywhere in gate math; all skip reasons disclosed per cell in results files.
- ~60.6K tuning fills across 98 cells overlap heavily (nested knobs, shared days) — cells are not independent bets;
  BH is applied to the reported p's as the pre-registered multiplicity control.
- p_raw conventions differ by family (two-sided t vs one-sided permutation) per each frozen prereg; the
  direction-of-effect column (Exp) must be read alongside p. A unified positive-edge BH pass finds zero q≤0.05 cells.
- bear-level-rejection prereg carries 2 pre-run amendments (TRUE-ET frame fix; offset-less-source fallback) — data
  plumbing only, frozen before results were read.
- sr-flip-retest runner deviated from its prereg in DISCLOSURE SHAPE only (no synthetic pricing at all vs
  "flagged+excluded"); gates/axes/population untouched; noted in its results file.
- premarket family: tuning-vs-held-out feed confound (premarket coverage era) disclosed and measured BEFORE any
  cell ran; day inventory dedupe/frame rules in `day-inventory-2026-07-23-summary.md`.
