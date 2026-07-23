# EDGE MATRIX — FULL-HISTORY — 2026-07-23 — synthesis + comparison vs the prior run

> **Run:** Same 6 pre-registered level-interaction families × frozen grids = **98 cells**, re-executed over the
> `*-fullhist` result files (`analysis/edge-matrix/*-fullhist*.json` / `*_fullhist*.json`). Population per family's
> own metadata: **386 covered days (2025-01-02→2026-07-22), 386 OPRA real-fill days (100% of covered days),
> 289 tuning / 97 held-out by date** (premarket family computes its own heldout window; disclosed below).
> Same frozen exit shape (RIBBON_RIDE + structure stop, 3-lot ATM, next-bar VWAP entry, 15:40/15:50 time stop) as
> the prior run — entry-side tuning only, nothing re-tuned. **Verification survivors: `[]` — EMPTY**, and, unlike
> the prior run, **zero cells even reach the 4/4-gate eligibility bar this time** (was 1/98) — see FLIPS below.

---

## ⛔ CORRECTION TO THE RUN PREMISE — read this before the table

The brief for this synthesis characterized the prior report (`EDGE-MATRIX-2026-07-23.md`, commit `4273a446`) as a
**"44-day" run** and asked what changed with **"9x the data."** That framing does not survive contact with the
files. Checked directly against both runs' own embedded metadata:

| | Prior run (`EDGE-MATRIX-2026-07-23.md`) | This run (`*-fullhist`) | Delta |
|---|---|---|---|
| OPRA real-fill days | **381** (2025-01-02 → 2026-07-17) | **386** (2025-01-02 → 2026-07-22) | **+5 days (+1.3%)** |
| Tuning days | 285 | 289 | +4 |
| Held-out days | 96 | 97 | +1 |
| Bear-family baseline cell, n | 508 fills | 518 fills | +10 fills (+2%) |

The prior run was **already a full-history run** — it already spanned essentially all of 2025 and 2026 YTD. The
"9x"/"44-day" language traces to one phrase in the fullhist premarket prereg's `run_kind` field: `"FULL-HISTORY
RE-RUN of the v1 (44-day-era) grid over the complete 386-day OPRA inventory"` — a **vintage label for how the
grid was originally designed**, months before 2026-07-22, back when the OPRA cache was thin. It is not a
description of what last night's committed report ran on. Whoever staged this task read the vintage label, not
the report. Per OP-33 (verify, don't claim): **the actual day-count delta between the two reports is 5 trading
days, not a 9x expansion.** This is disclosed up front so nothing downstream is read as "we found 9x more edge
evidence" — we did not; we found five more trading days' worth.

**What DID materially change, and why:** the **premarket-level-interaction family alone** gained a real, large,
non-trivial evidence expansion — but from a **bug fix, not new trading days**: `n_days_covered_tuning` for that
family went **24 → 80** (3.3x), sourced from `analysis/edge-matrix/premarket-level-interaction-episodes.json`
(old) vs `premarket_level_interaction-episodes-fullhist.json` (full). The fullhist premarket prereg's
`loading_seam_amendment` fixed the ET timestamp frame used to detect premarket bars (`wall-v1 → et-v2`,
`lib/et_frame.py`) for both the SPY and OPRA loaders. Under the old (buggy) frame, 268 of 386 days were excluded
for having <6 premarket bars; under the corrected frame, only 212 are. **56 previously-invisible tuning days'
premarket bars were recovered by a timestamp-parsing fix**, not by five additional trading days. This is the real
story behind every premarket-family number that moved. The other five families' populations are within 1-2% of
the prior run and their conclusions should be read as **confirmations at higher statistical confidence**, not
new evidence.

---

## VERDICT LINE

**🚨 STILL NO SHIP-CANDIDATES — and the null got MORE certain, not less.** 0/98 cells clear the ship bar.
**23 cells are now BH-significant matrix-wide (was 19) — every one still in the LOSING direction.** The
positive-edge coherence check (BH re-run on one-sided positive-edge p-values) again returns **zero** survivors,
identical to the prior run. **0/98 cells now reach 4/4 pre-registered gates (was 1/98)** — the sole
gate-4 cell from the prior run (`premarket-level`, fade PM high/low ±$0.35, next-bar confirm, then n=12) fell to
**2/4 gates** once its true tuning population (n=40, up from n=12) was measured under the corrected premarket
frame. **The one cell that looked like a candidate wasn't one — it was a small-sample artifact, and the
fullhist rerun caught it before it could ship.** That is this run's single most important finding.

---

## THE MATRIX — 98 cells, full-history, regime-split (all cells × all families)

- **n** = tuning-side real OPRA fills. **Exp** = mean $/trade (3-lot ATM, live Safe sizing). **Day-WR** = fraction
  of tuning days with ≥1 fill that finished green. **Ex-top3** = tuning total minus 3 best trades (concentration
  check). **Held-out** = total $ on the frozen ~97-day held-out window (2026-03-03/04 → 2026-07-22), touched once.
- **2025H1 / 2025H2 / 2026 $** = regime-split total P&L (tuning-scope fills, per each cell's own `regime_split`
  block in the results JSON) — this is the "does 2025 tape change the verdict" column.
- **p_raw** sidedness (pre-registered, same convention as the prior run, unchanged): `bear-level-rejection`,
  `bull-reclaim-quality`, `sr-flip-retest` = two-sided t vs zero. `break-retest`, `range-pingpong`,
  `premarket-level` = one-sided sign-flip permutation (small p = positive edge).
- **q (BH-98)** — Benjamini-Hochberg computed **by this synthesis**, fresh, across all 98 fullhist cells' raw p's
  (same convention/no re-normalization, matching the prior run's method so the two are comparable run-over-run).
- **Verification** — only cells at 4/4 gates are eligible for the verification pass. **Zero cells are eligible
  this run**, so all 98 read `not-tested`; the given survivors list (`[]`) is trivially satisfied.
- **vs 44-day-era** — this cell's own delta vs the prior run's matching cell (matched 1:1 by `cell_id`, which is
  identical across both runs — the grids are frozen and unchanged). Bold tags mark a **SIGN FLIP** (expectancy
  crossed zero), **GATE FLIP** (gates-passed count changed), or `sig-flip` (matrix significance crossed the 0.05
  line in either direction). Unflagged cells show `was <old Exp>` for reference.

<details>
<summary><b>Full 98-cell table (click to expand — it's long)</b></summary>

| Family | Cell (plain chart language) | n | Exp $/tr | Day-WR | Ex-top3 $ | Held-out $ | 2025H1 $ | 2025H2 $ | 2026 $ | p_raw | q (BH-98) | Gates | Verification | vs 44-day-era |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| premarket-level | fade first RTH touch PM flip level, ±$0.20 zone, next-bar confirm; direction per approach side | 1 | +493.64 | 100% | +0 | -1596 | — | +494 | -1596 | 1 | 1.000 | 2/4 | not-tested | was +0 |
| premarket-level | fade first RTH touch PM flip level, ±$0.35 zone, next-bar confirm; direction per approach side | 1 | +493.64 | 100% | +0 | -685 | — | +494 | -685 | 1 | 1.000 | 2/4 | not-tested | was +0 |
| premarket-level | fade first RTH touch PM flip level, ±$0.20 zone, no confirm; direction per approach side | 1 | +482.19 | 100% | +0 | -2362 | — | +482 | -2362 | 1 | 1.000 | 2/4 | not-tested | was +0 |
| premarket-level | go with break of PM high/low, ±$0.20 zone, next-bar confirm; direction per approach side | 17 | +186.61 | 59% | +1090 | -421 | — | +3688 | -937 | 0.0289 | 0.094 | 3/4 | not-tested | was +521 |
| premarket-level | go with break of PM high/low, ±$0.35 zone, next-bar confirm; direction per approach side | 15 | +142.11 | 53% | +439 | -1271 | — | +2647 | -1787 | 0.0668 | 0.177 | 3/4 | not-tested | was +521 |
| premarket-level | fade first RTH touch PM flip level, ±$0.35 zone, no confirm; direction per approach side | 2 | +112.76 | 50% | +0 | -1359 | — | +482 | -1615 | 1 | 1.000 | 1/4 | not-tested | was +0 |
| premarket-level | go with break of PM high/low, ±$0.20 zone, no confirm; direction per approach side | 33 | +76.80 | 50% | +384 | -586 | +58 | +2507 | -617 | 0.091 | 0.212 | 2/4 | not-tested | was +141 |
| premarket-level | go with break of PM high/low, ±$0.35 zone, no confirm; direction per approach side | 33 | +76.37 | 52% | +455 | -1743 | +58 | +1677 | -958 | 0.086 | 0.206 | 3/4 | not-tested | was +141 |
| premarket-level | fade first RTH touch PM high/low, ±$0.20 zone, next-bar confirm; direction per approach side | 37 | +25.31 | 38% | -1309 | -89 | -52 | +1935 | -1036 | 0.3144 | 0.616 | 2/4 | not-tested | was +115 |
| premarket-level | fade first RTH touch PM high/low, ±$0.35 zone, next-bar confirm; direction per approach side | 40 | +18.94 | 40% | -1488 | +1163 | +78 | +1827 | +16 | 0.353 | 0.659 | 2/4 | not-tested (fell to 2/4 gates) | **GATE FLIP** |
| premarket-level | fade first RTH touch PM high/low, ±$0.35 zone, no confirm; direction per approach side | 67 | -40.82 | 34% | -4476 | -1039 | +119 | +131 | -4024 | 0.9202 | 1.000 | 0/4 | not-tested | **SIGN FLIP** |
| premarket-level | fade first RTH touch PM high/low, ±$0.20 zone, no confirm; direction per approach side | 60 | -43.63 | 32% | -4329 | -1611 | +68 | +1049 | -5346 | 0.9313 | 1.000 | 0/4 | not-tested | **SIGN FLIP** |
| premarket-level | go with break of PM flip level, ±$0.35 zone, no confirm; direction per approach side | 2 | -174.55 | 50% | +0 | -229 | +8 | -357 | -229 | 1 | 1.000 | 0/4 | not-tested | **SIGN FLIP** |
| premarket-level | go with break of PM flip level, ±$0.20 zone, no confirm; direction per approach side | 3 | -182.01 | 33% | +0 | -408 | +8 | -357 | -605 | 1 | 1.000 | 0/4 | not-tested | **SIGN FLIP** |
| premarket-level | go with break of PM flip level, ±$0.20 zone, next-bar confirm; direction per approach side | 1 | -190.72 | 0% | +0 | +490 | — | -191 | +490 | 1 | 1.000 | 1/4 | not-tested | was +0 |
| premarket-level | go with break of PM flip level, ±$0.35 zone, next-bar confirm; direction per approach side | 1 | -190.72 | 0% | +0 | +641 | — | -191 | +641 | 1 | 1.000 | 1/4 | not-tested | was +0 |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 10c, retest ±35c zone, next bar closes on flip side | 398 | -3.72 | 38% | -3634 | +1372 | -4270 | +1654 | +1137 | 0.6929 | 1.000 | 1/4 | not-tested | was -5 |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 20c, retest ±35c zone, next bar closes on flip side | 388 | -6.19 | 36% | -4557 | +572 | -4521 | +1827 | +291 | 0.521 | 0.928 | 1/4 | not-tested | was -6 |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 10c, retest ±35c zone, retest bar closes on flip side | 489 | -6.34 | 38% | -5323 | +768 | -4324 | +2427 | -1204 | 0.4301 | 0.781 | 1/4 | not-tested | was -6 |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 10c, retest ±15c zone, retest bar closes on flip side | 511 | -6.84 | 36% | -5732 | -492 | -3579 | -217 | +301 | 0.3565 | 0.659 | 0/4 | not-tested | was -8 |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 20c, retest ±35c zone, retest bar closes on flip side | 470 | -8.56 | 38% | -6247 | +905 | -4583 | +2107 | -1549 | 0.3032 | 0.616 | 1/4 | not-tested | was -9 |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 20c, retest ±15c zone, retest bar closes on flip side | 490 | -9.49 | 34% | -6887 | -475 | -3582 | -713 | -356 | 0.2117 | 0.461 | 0/4 | not-tested | was -9 |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 10c, retest ±15c zone, next bar closes on flip side | 406 | -14.69 | 32% | -7748 | +1119 | -5482 | +475 | -956 | 0.0811 | 0.199 | 1/4 | not-tested | was -15 |
| sr-flip-retest | Call: S/R flip up, retest from above; flip margin 20c, retest ±15c zone, next bar closes on flip side | 402 | -15.56 | 30% | -8164 | +603 | -5519 | +1106 | -1843 | 0.0761 | 0.196 | 1/4 | not-tested | was -15 |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 10c, retest ±15c zone, next bar closes on flip side | 390 | -19.21 | 32% | -9599 | +277 | -1890 | -3150 | -2452 | 0.0493 | 0.140 | 1/4 | not-tested | was -18 |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 20c, retest ±15c zone, next bar closes on flip side | 390 | -21.86 | 30% | -10559 | +117 | -2143 | -4012 | -2370 | 0.0223 | 0.078 | 1/4 | not-tested | was -21 |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 10c, retest ±35c zone, retest bar closes on flip side | 488 | -26.48 | 31% | -14854 | -110 | -5738 | -5380 | -1804 | 0.0009 | 0.0080 | 0/4 | not-tested | was -26 |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 10c, retest ±35c zone, next bar closes on flip side | 395 | -27.10 | 30% | -12517 | -78 | -2939 | -5638 | -2126 | 0.005 | 0.027 | 0/4 | not-tested | was -26 |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 20c, retest ±35c zone, retest bar closes on flip side | 473 | -27.14 | 31% | -14769 | -19 | -6221 | -5153 | -1463 | 0.0009 | 0.0080 | 0/4 | not-tested | was -27 |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 20c, retest ±35c zone, next bar closes on flip side | 384 | -29.23 | 29% | -13108 | +176 | -3719 | -5317 | -2190 | 0.0028 | 0.021 | 1/4 | not-tested | was -27 |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 20c, retest ±15c zone, retest bar closes on flip side | 504 | -31.65 | 27% | -17889 | +694 | -7076 | -6989 | -1885 | <0.0001 | <0.0001 | 1/4 | not-tested | was -31 |
| sr-flip-retest | Put: S/R flip down, retest from below; flip margin 10c, retest ±15c zone, retest bar closes on flip side | 514 | -33.41 | 25% | -19050 | +261 | -7519 | -7825 | -1831 | <0.0001 | <0.0001 | 1/4 | not-tested | was -33 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; RSI<68 req; no reset req; ≤$3.50 off session low | 562 | -7.23 | 39% | -6494 | -1887 | +892 | -2896 | -2057 | 0.3322 | 0.638 | 0/4 | not-tested | was -7 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; no RSI cap; no reset req; ≤$3.50 off session low | 586 | -7.49 | 40% | -6824 | -2370 | +938 | -2420 | -2908 | 0.3115 | 0.616 | 0/4 | not-tested | was -7 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; RSI<68 req; RSI-reset≤55 in last hr req; ≤$3.50 off session low | 559 | -7.71 | 39% | -6741 | -1887 | +516 | -2898 | -1926 | 0.3012 | 0.616 | 0/4 | not-tested | was -8 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; no RSI cap; RSI-reset≤55 in last hr req; ≤$3.50 off session low | 575 | -8.84 | 40% | -7517 | -2352 | +562 | -3019 | -2627 | 0.2316 | 0.493 | 0/4 | not-tested | was -9 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; no RSI cap; no reset req; any extension | 775 | -10.69 | 40% | -10720 | -4076 | -194 | -2080 | -6013 | 0.1193 | 0.266 | 0/4 | not-tested | was -10 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; RSI<68 req; no reset req; ≤$3.50 off session low | 805 | -10.95 | 38% | -11250 | -3883 | +753 | -4398 | -5172 | 0.0501 | 0.140 | 0/4 | not-tested | was -11 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; no RSI cap; no reset req; ≤$3.50 off session low | 829 | -11.26 | 38% | -11765 | -4191 | +826 | -4348 | -5810 | 0.0442 | 0.135 | 0/4 | not-tested | was -12 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; no RSI cap; RSI-reset≤55 in last hr req; any extension | 749 | -11.51 | 39% | -11056 | -4026 | -353 | -2396 | -5875 | 0.0942 | 0.215 | 0/4 | not-tested | was -11 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; RSI<68 req; RSI-reset≤55 in last hr req; ≤$3.50 off session low | 799 | -11.62 | 37% | -11713 | -3883 | -69 | -4335 | -4876 | 0.0372 | 0.118 | 0/4 | not-tested | was -12 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; RSI<68 req; no reset req; any extension | 741 | -12.05 | 38% | -11363 | -4457 | +214 | -3430 | -5714 | 0.0785 | 0.197 | 0/4 | not-tested | was -12 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; no RSI cap; no reset req; any extension | 1070 | -12.52 | 37% | -15824 | -5628 | -719 | -4703 | -7970 | 0.0163 | 0.064 | 0/4 | not-tested | was -12 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; no RSI cap; RSI-reset≤55 in last hr req; ≤$3.50 off session low | 817 | -12.90 | 38% | -12973 | -4583 | +4 | -4561 | -5983 | 0.0205 | 0.074 | 0/4 | not-tested | was -13 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.25 zone; RSI<68 req; RSI-reset≤55 in last hr req; any extension | 726 | -13.35 | 37% | -12127 | -4585 | -178 | -3314 | -6203 | 0.0516 | 0.140 | 0/4 | not-tested | was -13 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; no RSI cap; RSI-reset≤55 in last hr req; any extension | 1034 | -13.55 | 36% | -16443 | -5988 | -1139 | -4804 | -8068 | 0.0096 | 0.041 | 0/4 | not-tested | `sig-flip` |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; RSI<68 req; no reset req; any extension | 1037 | -13.86 | 36% | -16807 | -6040 | -923 | -5829 | -7622 | 0.0074 | 0.033 | 0/4 | not-tested | was -14 |
| bull-reclaim-quality | Call on reclaim above resistance; ±$0.15 zone; RSI<68 req; RSI-reset≤55 in last hr req; any extension | 1013 | -14.89 | 35% | -17521 | -6231 | -1343 | -5878 | -7868 | 0.0041 | 0.025 | 0/4 | not-tested | was -15 |
| range-pingpong | Fade edge of 0.80-3.50 range, 3+ touches/side, ±$0.20 zone, wait 1 bar inside range; both directions | 961 | -8.25 | 38% | -10814 | -7469 | -6582 | +101 | -8920 | 0.8925 | 1.000 | 0/4 | not-tested | was -8 |
| range-pingpong | Fade edge of 0.80-3.50 range, 2+ touches/side, ±$0.20 zone, wait 1 bar inside range; both directions | 966 | -9.43 | 38% | -11987 | -8452 | -7559 | -95 | -9903 | 0.9262 | 1.000 | 0/4 | not-tested | was -9 |
| range-pingpong | Fade edge of 0.80-3.50 range, 3+ touches/side, ±$0.20 zone, enter at tag-bar close; both directions | 1201 | -10.27 | 38% | -14982 | -8944 | -11380 | +249 | -10151 | 0.967 | 1.000 | 0/4 | not-tested | was -10 |
| range-pingpong | Fade edge of 0.80-3.50 range, 3+ touches/side, ±$0.10 zone, enter at tag-bar close; both directions | 1075 | -11.55 | 36% | -15092 | -5335 | -11406 | +2277 | -8619 | 0.9724 | 1.000 | 0/4 | not-tested | was -11 |
| range-pingpong | Fade edge of 0.80-3.50 range, 3+ touches/side, ±$0.10 zone, wait 1 bar inside range; both directions | 859 | -12.01 | 39% | -13197 | -5176 | -4602 | -1700 | -9190 | 0.9512 | 1.000 | 0/4 | not-tested | was -11 |
| range-pingpong | Fade edge of 1.20-3.50 range, 3+ touches/side, ±$0.20 zone, wait 1 bar inside range; both directions | 441 | -12.21 | 36% | -7832 | -5799 | -4321 | +409 | -7269 | 0.8649 | 1.000 | 0/4 | not-tested | was -10 |
| range-pingpong | Fade edge of 0.80-3.50 range, 2+ touches/side, ±$0.20 zone, enter at tag-bar close; both directions | 1207 | -12.30 | 36% | -17485 | -7926 | -13770 | +74 | -9071 | 0.988 | 1.000 | 0/4 | not-tested | was -12 |
| range-pingpong | Fade edge of 0.80-3.50 range, 2+ touches/side, ±$0.10 zone, wait 1 bar inside range; both directions | 861 | -12.98 | 39% | -14053 | -5607 | -5346 | -1812 | -9621 | 0.9636 | 1.000 | 0/4 | not-tested | was -12 |
| range-pingpong | Fade edge of 0.80-3.50 range, 2+ touches/side, ±$0.10 zone, enter at tag-bar close; both directions | 1077 | -13.65 | 36% | -17379 | -4532 | -13475 | +1998 | -7755 | 0.9878 | 1.000 | 0/4 | not-tested | was -13 |
| range-pingpong | Fade edge of 1.20-3.50 range, 3+ touches/side, ±$0.20 zone, enter at tag-bar close; both directions | 552 | -13.93 | 36% | -10119 | -3562 | -8393 | +796 | -3652 | 0.9386 | 1.000 | 0/4 | not-tested | was -12 |
| range-pingpong | Fade edge of 1.20-3.50 range, 3+ touches/side, ±$0.10 zone, enter at tag-bar close; both directions | 485 | -14.48 | 39% | -9456 | -2864 | -7167 | -258 | -2463 | 0.9314 | 1.000 | 0/4 | not-tested | was -14 |
| range-pingpong | Fade edge of 1.20-3.50 range, 2+ touches/side, ±$0.20 zone, wait 1 bar inside range; both directions | 442 | -14.62 | 35% | -8913 | -6588 | -5290 | +297 | -8059 | 0.9087 | 1.000 | 0/4 | not-tested | was -12 |
| range-pingpong | Fade edge of 1.20-3.50 range, 2+ touches/side, ±$0.20 zone, enter at tag-bar close; both directions | 555 | -16.42 | 36% | -11547 | -3503 | -9821 | +796 | -3593 | 0.9657 | 1.000 | 0/4 | not-tested | was -15 |
| range-pingpong | Fade edge of 1.20-3.50 range, 2+ touches/side, ±$0.10 zone, enter at tag-bar close; both directions | 484 | -17.11 | 38% | -10711 | -2314 | -8422 | -258 | -1914 | 0.9581 | 1.000 | 0/4 | not-tested | was -16 |
| range-pingpong | Fade edge of 1.20-3.50 range, 3+ touches/side, ±$0.10 zone, wait 1 bar inside range; both directions | 382 | -19.97 | 35% | -10080 | -4109 | -3951 | -628 | -7160 | 0.9566 | 1.000 | 0/4 | not-tested | was -18 |
| range-pingpong | Fade edge of 1.20-3.50 range, 2+ touches/side, ±$0.10 zone, wait 1 bar inside range; both directions | 381 | -22.36 | 35% | -10970 | -4390 | -4730 | -740 | -7441 | 0.9681 | 1.000 | 0/4 | not-tested | was -21 |
| break-retest | Break level by 30c, retest ±25c zone within 60min, wait for close beyond level; both directions | 1129 | -11.16 | 42% | -15697 | -8404 | -11553 | -3522 | +2475 | 0.9579 | 1.000 | 0/4 | not-tested | was -10 |
| break-retest | Break level by 30c, retest ±25c zone within 60min, enter on the touch; both directions | 1271 | -11.39 | 42% | -17581 | -7783 | -10453 | -5665 | +1636 | 0.9746 | 1.000 | 0/4 | not-tested | was -11 |
| break-retest | Break level by 30c, retest ±10c zone within 60min, enter on the touch; both directions | 1231 | -11.88 | 39% | -17718 | -11147 | -9307 | -6911 | +1597 | 0.9798 | 1.000 | 0/4 | not-tested | was -11 |
| break-retest | Break level by 30c, retest ±25c zone within 30min, enter on the touch; both directions | 1221 | -12.17 | 41% | -17963 | -6766 | -12485 | -3526 | +1145 | 0.9823 | 1.000 | 0/4 | not-tested | was -11 |
| break-retest | Break level by 30c, retest ±25c zone within 30min, wait for close beyond level; both directions | 1086 | -12.69 | 41% | -16882 | -6855 | -12842 | -2475 | +1533 | 0.9741 | 1.000 | 0/4 | not-tested | was -12 |
| break-retest | Break level by 15c, retest ±25c zone within 60min, wait for close beyond level; both directions | 1514 | -13.88 | 44% | -24119 | -12693 | -11471 | -8013 | -1537 | 0.9951 | 1.000 | 0/4 | not-tested | was -14 |
| break-retest | Break level by 15c, retest ±10c zone within 60min, wait for close beyond level; both directions | 1379 | -14.16 | 42% | -22624 | -14840 | -11378 | -7234 | -914 | 0.9964 | 1.000 | 0/4 | not-tested | was -14 |
| break-retest | Break level by 30c, retest ±10c zone within 60min, wait for close beyond level; both directions | 1041 | -14.19 | 39% | -17874 | -10732 | -9451 | -5334 | +9 | 0.9834 | 1.000 | 0/4 | not-tested | was -13 |
| break-retest | Break level by 15c, retest ±10c zone within 60min, enter on the touch; both directions | 1582 | -14.32 | 42% | -25754 | -14265 | -14043 | -7415 | -1198 | 0.9985 | 1.000 | 0/4 | not-tested | was -14 |
| break-retest | Break level by 15c, retest ±25c zone within 60min, enter on the touch; both directions | 1638 | -14.57 | 43% | -26960 | -11746 | -12359 | -9711 | -1792 | 0.9985 | 1.000 | 0/4 | not-tested | was -14 |
| break-retest | Break level by 15c, retest ±25c zone within 30min, wait for close beyond level; both directions | 1500 | -15.46 | 44% | -26286 | -10173 | -15152 | -6750 | -1285 | 0.9978 | 1.000 | 0/4 | not-tested | was -15 |
| break-retest | Break level by 15c, retest ±25c zone within 30min, enter on the touch; both directions | 1620 | -15.63 | 42% | -28416 | -10589 | -15914 | -8078 | -1325 | 0.999 | 1.000 | 0/4 | not-tested | was -15 |
| break-retest | Break level by 30c, retest ±10c zone within 30min, enter on the touch; both directions | 1149 | -17.40 | 36% | -23087 | -10374 | -13325 | -5990 | -675 | 0.9978 | 1.000 | 0/4 | not-tested | was -17 |
| break-retest | Break level by 15c, retest ±10c zone within 30min, enter on the touch; both directions | 1527 | -17.43 | 41% | -29708 | -13096 | -16936 | -7536 | -2139 | 0.9997 | 1.000 | 0/4 | not-tested | was -17 |
| break-retest | Break level by 15c, retest ±10c zone within 30min, wait for close beyond level; both directions | 1349 | -17.90 | 42% | -27238 | -12556 | -15280 | -6835 | -2025 | 0.9998 | 1.000 | 0/4 | not-tested | was -18 |
| break-retest | Break level by 30c, retest ±10c zone within 30min, wait for close beyond level; both directions | 978 | -20.17 | 36% | -22824 | -9698 | -12577 | -4952 | -2197 | 0.9984 | 1.000 | 0/4 | not-tested | was -19 |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; any touch; touch alone, no confirm | 1103 | -10.29 | 33% | -13924 | -5941 | -4277 | -4146 | -2924 | 0.0463 | 0.138 | 0/4 | not-tested | was -9 |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; any touch; touch alone, no confirm | 873 | -17.96 | 34% | -18252 | -4307 | -8680 | -5392 | -1603 | 0.00705 | 0.033 | 0/4 | not-tested | `sig-flip` |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 2nd+ touch; touch alone, no confirm | 546 | -19.21 | 32% | -13034 | -1477 | -5334 | -1621 | -3535 | 0.0203 | 0.074 | 0/4 | not-tested | was -18 |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; any touch; red candle at the level | 781 | -20.86 | 31% | -18725 | -3935 | -6988 | -6334 | -2972 | 0.00331 | 0.022 | 0/4 | not-tested | was -19 |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; any touch; red candle at the level | 655 | -21.13 | 34% | -16272 | -5016 | -7384 | -3975 | -2482 | 0.0139 | 0.057 | 0/4 | not-tested | was -19 |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 3rd+ touch; touch alone, no confirm | 327 | -24.65 | 30% | -10328 | -1703 | -6016 | -1243 | -802 | 0.0242 | 0.082 | 0/4 | not-tested | was -25 |
| bear-level-rejection | **[LIVE BASELINE]** Put on rejection; penny-exact; any touch; close back below the level (= `detect_level_rejection`) | 518 | -28.84 | 32% | -17565 | -1133 | -8737 | -1801 | -4400 | 0.00648 | 0.033 | 0/4 | not-tested | `sig-flip` |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 2nd+ touch; touch alone, no confirm | 476 | -29.58 | 32% | -16343 | -1328 | -7695 | -2752 | -3635 | 0.00285 | 0.021 | 0/4 | not-tested | was -28 |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 3rd+ touch; touch alone, no confirm | 364 | -30.96 | 26% | -13460 | +1313 | -6646 | -1243 | -3380 | 0.00087 | 0.0080 | 1/4 | not-tested | was -31 |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; any touch; close back below the level | 471 | -32.16 | 31% | -17773 | -3280 | -8809 | -3731 | -2607 | 0.00691 | 0.033 | 0/4 | not-tested | `sig-flip` |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 3rd+ touch; red candle at the level | 274 | -35.76 | 27% | -11825 | -2606 | -3536 | -3408 | -2854 | 0.00342 | 0.022 | 0/4 | not-tested | was -37 |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 2nd+ touch; red candle at the level | 464 | -36.99 | 28% | -19519 | -788 | -8155 | -5565 | -3445 | 0.00012 | 0.0023 | 0/4 | not-tested | was -36 |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 2nd+ touch; red candle at the level | 411 | -37.32 | 30% | -17692 | -1853 | -8440 | -4439 | -2459 | 0.00083 | 0.0080 | 0/4 | not-tested | was -37 |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 2nd+ touch; close back below the level | 422 | -40.88 | 31% | -19605 | -1442 | -7648 | -4931 | -4672 | 0.00014 | 0.0023 | 0/4 | not-tested | was -39 |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 3rd+ touch; close back below the level | 247 | -41.58 | 28% | -12467 | -1159 | -4492 | -3332 | -2448 | 0.00465 | 0.027 | 0/4 | not-tested | was -41 |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 3rd+ touch; red candle at the level | 296 | -42.99 | 26% | -14719 | +1357 | -4933 | -4080 | -3711 | <0.0001 | 0.0010 | 1/4 | not-tested | was -42 |
| bear-level-rejection | Put on rejection of overhead level; penny-exact level; 3rd+ touch; close back below the level | 269 | -46.63 | 23% | -14689 | +490 | -5880 | -2779 | -3885 | 0.0002 | 0.0028 | 1/4 | not-tested | was -45 |
| bear-level-rejection | Put on rejection of overhead level; ±$0.20 zone; 2nd+ touch; close back below the level | 380 | -53.75 | 28% | -22692 | -207 | -10288 | -7101 | -3036 | <0.0001 | 0.0003 | 0/4 | not-tested | was -53 |

</details>

Results provenance: `bear_level_rejection-results-fullhist-2026-07-23.json` ·
`bull_level_reclaim_quality-results-fullhist-2026-07-23.json` · `break_retest_continuation-results-fullhist.json` ·
`range_pingpong-results-fullhist.json` · `sr_flip_retest-results-fullhist-2026-07-23.json` ·
`premarket_level_interaction-episodes-fullhist.json` — all under `analysis/edge-matrix/`. BH-FDR, cell-matching to
the prior run, and flip detection computed fresh for this synthesis (98/98 cells matched 1:1 by frozen `cell_id`,
zero ambiguous matches).

---

## EXPLICIT FLIPS — every cell whose verdict changed vs the prior run

9 of 98 cells flipped (sign, gate-count, or matrix-significance). **Zero flipped from loser to winner.**

| Cell | Family | Flip type | Old → New | Why |
|---|---|---|---|---|
| fade PM h/l ±$0.35 next-bar | premarket | **GATE FLIP** (was the only 4/4 cell) | n=12→40, Exp +172.65→+18.94, 4/4→2/4 gates, q 0.156→0.659 | Tripled tuning n (ET-frame fix) revealed the true mean was 9x smaller than the small-sample estimate. This is the headline finding — see below. |
| fade PM h/l ±$0.35 no-confirm | premarket | **SIGN FLIP** | n=20→67, Exp +46.58→-40.82 | Same frame fix; 2025 was flat/small-positive, 2026 tape is -$4,024 on this cell — see REGIME READ. |
| fade PM h/l ±$0.20 no-confirm | premarket | **SIGN FLIP** | n=18→60, Exp +58.14→-43.63 | Same mechanism. |
| go-with PM flip-level ±$0.20 no-confirm | premarket | **SIGN FLIP** | n=1→3, Exp +7.87→-182.01 | Still below n=15 floor both times — noise, not signal (flagged, not actionable). |
| go-with PM flip-level ±$0.35 no-confirm | premarket | **SIGN FLIP** | n=1→2, Exp +7.87→-174.55 | Same — still below floor. |
| bear baseline (`detect_level_rejection`, LIVE) | bear-level-rejection | `sig-flip` (crossed into matrix-sig) | q 0.079→0.033 | +10 fills tightened the CI around an already-large negative mean (-$24.88→-$28.84); reinforces, does not reverse. |
| bear ±$0.20/any-touch/no-confirm | bear-level-rejection | `sig-flip` | q 0.071→0.033 | Same mechanism. |
| bear ±$0.20/any-touch/close-below | bear-level-rejection | `sig-flip` | q 0.079→0.033 | Same mechanism. |
| bull ±$0.15/no-cap/reset/any-ext | bull-reclaim-quality | `sig-flip` | q 0.051→0.041 | Crossed the 0.05 line by a hair; already known negative, no directional change. |

**Read:** every non-premarket flip is the null becoming *more* statistically certain with 5 more days, not less.
Every premarket flip is the same underlying mechanism — the ET-frame fix recovering 56 tuning days — either
tripling a tiny n toward its true (smaller or negative) mean, or leaving a still-starved cell exactly where it
was. **No cell anywhere in the matrix flipped from losing to winning.**

---

## THE ONE STORY THAT MATTERS: the sole 4/4-gate cell from last night didn't survive its own data expansion

Last night's report flagged one cell — *"fade first RTH touch PM high/low, ±$0.35 zone, next-bar confirm"* — as
the only cell in the entire 98-cell matrix to clear all 4 pre-registered gates, at n=12, Exp=+$172.65/trade,
day-WR 55%. It was correctly **not shipped**, on the stated grounds that n=12 was below the n≥15 evidence floor
and the verification pass refuted it. Both those calls are now vindicated by data the verifier didn't even have
yet: once the ET-frame bug that was silently starving premarket bar-detection got fixed and this cell's true
tuning population showed up (n=40, more than 3x), **expectancy collapsed from +$172.65 to +$18.94 and it dropped
two full gates (4/4 → 2/4).** This is a clean, textbook illustration of why the evidence floor and the
verification pass exist — a cell that "passed everything" on 12 trades was a coin-flip away from being pure
sampling noise, and the extra data proved it. No process failure here; the process caught exactly what it was
built to catch.

---

## REGIME READ — does more/corrected tape change any verdict, and which families work in which regime?

**Headline: no.** No family and no cell shows a robust regime pocket of positive expectancy anywhere in
2025-01-02 → 2026-07-22. The regime split changes the *confidence* of the null, not its *direction*, with one
partial exception (premarket fade, below).

**Year-half read (highest-n cell per family, tuning scope):**

| Family | Cell | 2025H1 $ | 2025H2 $ | 2026 $ | Read |
|---|---|---|---|---|---|
| bear-level-rejection | penny-exact/any-touch/no-confirm (n=1103) | -4277 | -4146 | -2924 | Negative in all three periods. No regime rescue. |
| bull-reclaim-quality | ±$0.15/no-cap/no-reset/any-ext (n=1070) | -719 | -4703 | -7970 | Roughly flat 2025H1, then monotonically worse — consistent with a trending-tape regime punishing naive reclaim more over time (C22 pattern, not a new finding). |
| break-retest | 15c break / 25c retest / 12-bar / touch (n=1638) | -12359 | -9711 | -1792 | Negative in all three; least-bad in 2026 but still negative and n is thin there (263 fills). |
| range-pingpong | 0.80-3.50 range / 2+ touch / 20c (n=1207) | -13770 | +74 | -9071 | 2025H2 is flat-not-losing on n=451 — the closest thing to a bright spot in the whole matrix, and it is not a bright spot: still net negative in the other two-thirds of history on the same cell. |
| sr-flip-retest (BEAR, densest) | m10_b15_RC_BEAR (n=514) | -7519 | -7825 | -1831 | Negative in all three; tuning mean stays negative everywhere. |
| premarket-level (fade, densest) | pm_hl b35 reject-none, pooled (n=67) | **+119** | **+131** | **-4024** | **Real regime break** — flat-to-slightly-positive through all of 2025, then the mean-reversion-fade thesis fails hard in 2026 YTD. This is the one place in the matrix where "does 2025 tape change the read" has a real, non-trivial answer: 2025 alone would have looked like a weak maybe; pooling in 2026 kills it. |

**VIX-band read (highest-n cell per family, tuning scope):** every family's dollar losses concentrate in the
`mid` VIX band (15-20) simply because that's where 258/386 days live (population-weighted, not a VIX effect).
`high`-VIX bands show occasional small positive flickers (bear +$800 on n=27, sr-BEAR -$79 — near flat — on
n=10) but at n<30 these are noise, not evidence, consistent with the standing C5 doctrine (VIX *character* beats
VIX *level* as a discriminator, and level alone shows nothing here).

**sr-flip-retest tuning-negative / held-out-positive split — persists, unchanged in shape:** BULL side: 6/8 cells
held-out-positive despite negative tuning mean everywhere (day-WR still ≤38%, fails the day-consistency lens
outright). BEAR side: 5/8 held-out-positive. This is the same recent-tape regime signature flagged in the prior
report (C22: backward-looking classifiers/tuning windows anti-correlate with recovery/trending periods) — **not
new**, and the 5 added days (which fall inside the held-out window) mechanically reinforce it rather than testing
it independently. Still a watch item, not a candidate: day-consistency fails regardless of the held-out dollar
sign.

---

## RANKED VERDICT — FOCUS-DOCTRINE lens (day-consistency > total; one-good-trade cadence)

1. **premarket-level-interaction (PM high/low, fade arm)** — was "not an edge claim, a data-backfill claim" last
   night; **now it's a refuted claim.** The backfill happened (n 12→40 on the flagged cell, 24→80 tuning days
   family-wide) and expectancy collapsed. **Downgrade from ACCRETE to DEAD** for the fade arm specifically (the
   go-with arm stays ACCRETE — still positive at n=15-17, still below floor, see below).
2. **sr-flip-retest, BULL side** — unchanged verdict: day-WR ≤38% fails the day-consistency lens outright
   regardless of the held-out dollar sign; tuning-negative/held-out-positive remains a regime signature, not
   entry edge. Still a watch item.
3. **bull-level-reclaim-quality** — unchanged: RSI/reset/extension conditioning still moves expectancy toward
   zero without crossing it (best cell -$7.23/tr, day-WR 39%, matching last night's -$7.16/40% within noise).
   Conditioning-as-loss-reducer thesis holds; conditioning-as-entry-maker thesis stays refuted.
4. **range-pingpong** — unchanged: 16/16 cells negative, day-WR ≤39%, held-out negative on the best cells. The
   2025H2 near-flat read above does not change this — it's one-third of one cell's history, not a signal.
5. **break-retest-continuation** — unchanged: 16/16 negative, day-WR up to 44% (highest of any RTH family) but
   worst totals. No regime rescues it.
6. **bear-level-rejection** — unchanged and reinforced: the live baseline detector cell is now BH-significant on
   its own (q=0.033, was 0.079) at -$28.84/trade over 518 fills. nth-touch thesis inversion (more touches ⇒
   worse) holds identically. 14/18 cells are now BH-significant losers (was 11/18).

**Cross-family structural finding, restated with more confidence:** 82/82 RTH cells negative in both runs, and
23/98 matrix-wide are now BH-significant losers (was 19/98) — the null got *more* certain with more (and
frame-corrected) data, which is the opposite of what a real-but-underpowered edge would do. The standing
conclusion holds: the next discriminating experiment is exit-side/friction, not an eighth entry grid.

---

## SHIP / ACCRETE / DEAD triage

### SHIP-CANDIDATES: **NONE.** (unchanged — 0/98 cells clear 4/4 gates + BH-FDR + verification, was 0/98)

### ACCRETE (revised)

| Item | Status this run | Becomes decidable when |
|---|---|---|
| **premarket PM-high/low, go-with-break arm** | Still positive: ±$0.20/next-bar n=17 Exp +$186.61 (3/4 gates), ±$0.35/next-bar n=15 Exp +$142.11 (3/4 gates) — both still below the n≥15 evidence floor (barely) and still missing gate 2 (day-majority). Both grew from n=1-2 last night to n=15-17 now purely from the frame fix, same direction as before. | n≥25 on the go-with arm specifically (current growth rate suggests this is reachable within 1-2 months of forward accrual); the standing rerun loop below will track it automatically. |
| **premarket PM-high/low, fade arm** | **DEMOTED to DEAD this run** — see below. | N/A |
| **sr-flip-retest BULL, wide-zone cells** | Unchanged from prior: watch item, not a candidate. | Forward day-WR >50%, sustained. |
| **bull-reclaim conditioning as a VETO layer** | Unchanged from prior: loss-reducer, not entry-maker; only relevant if bull reclaim is ever re-armed. | Same condition as prior report. |

### DEAD (updated)

- **premarket PM-high/low, FADE arm** — **NEW THIS RUN.** Was the sole ACCRETE/near-candidate item; the
  ET-frame-corrected data (n 12→40 on the flagged cell, up to n=67 on the densest fade cell) shows this thesis
  worked weakly in 2025 (+$119, +$131 across the two halves) and fails outright in 2026 (-$4,024 pooled). Kill
  the fade arm; keep only the go-with-break arm in ACCRETE.
- **premarket PM-FLIP-level arm** — unchanged DEAD verdict, and the fullhist run **confirms it stays starved even
  after the frame fix**: all 8 pm_flip cells remain at n=1-3, still below the evidence floor. The frame fix
  recovered PM high/low bars; it did not create PM flip-level formations that structurally don't exist on sparse
  premarket data. This is now a *doubly*-confirmed dead end, not just a data-starved one.
- **bear-level-rejection entry refinements** — unchanged DEAD, now with higher confidence: 14/18 cells
  BH-significant losers (was 11/18). nth-touch inversion holds.
- **range-pingpong zone-fade** — unchanged DEAD: 16/16 negative both runs.
- **break-retest-continuation** — unchanged DEAD: 16/16 negative both runs.
- **sr-flip-retest BEAR side** — unchanged DEAD: 6/8 BEAR cells BH-significant losers both runs (same 6 cells).

---

## Honest accounting of the nulls

- **Positive-edge coherence check (matrix-wide, one-sided, BH-98):** **0 survivors**, identical to the prior run.
  Two independent runs, two data vintages (one with a data bug, one without), same answer: there is no
  multiplicity-surviving positive edge anywhere in this 98-cell vocabulary under the frozen exit shape.
- **Gate-4 eligibility:** 0/98 this run vs 1/98 last night — the ceiling went *down*, and the one cell that had
  briefly cleared it is now explained (small-n artifact, corrected).
- **BH-significant losers:** 23/98 this run vs 19/98 last night — the floor of statistical certainty in the
  losing direction went *up*.
- Both directions of movement point the same way: **more (and more correct) data made the null more certain, not
  less.** That is what a true null is supposed to do when you add evidence. A real-but-underpowered edge would
  have moved the other way — toward significance on the positive side, or at minimum toward instability. It
  didn't.
- The premarket family is the one place where "more data changed a verdict," and it changed it in the
  conservative direction (killed a false positive), not the exciting one.

## Standing rerun — unchanged

Stub + protocol: [`backtest/tools/edge_matrix_rerun.py`](../../backtest/tools/edge_matrix_rerun.py). This
synthesis did not re-run the tool; it read the `*-fullhist` artifacts already on disk (generated 2026-07-22
20:17-20:25, after the 5-day OPRA gap backfill and the premarket ET-frame fix landed). Next forward accrual
should target the premarket go-with-break arm specifically — it is the only ACCRETE-tier item left with a
plausible path to n≥25 in reasonable time.

## Disclosures

- Same disclosures as the prior report apply unchanged (real OPRA fills only, no BS-synthetic in gate math, p_raw
  sidedness differs by pre-registered family convention, cells overlap heavily so BH is a disclosed-conservative
  multiplicity control rather than a fully-independent one).
- **New this run:** the day-count-delta correction above (5 days, not 9x) and the premarket ET-frame provenance
  note are both disclosed as part of this synthesis, not as part of any of the six frozen preregs — they are
  observations about what changed between two runs, not new pre-registered claims.
- Regime-split `total_pnl` figures are **tuning-scope only** (per each cell's own `regime_split.scope` field)
  except premarket's, which pools tuning+held-out (`"scope": "all real fills (tuning+heldout pooled); disclosure
  only, not a gate"` — stated in the source JSON, carried through here unchanged).
