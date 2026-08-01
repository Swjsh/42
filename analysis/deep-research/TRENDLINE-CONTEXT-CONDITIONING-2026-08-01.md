# TRENDLINE-CONTEXT CONDITIONING -- 2026-08-01 (WS8)

**Verdict: NULL** -- no BH-FDR survivor meets the frozen decision rule.

Pre-registered: `analysis/recommendations/prereg-trendline-context-conditioning-2026-08-01.json (commit 9d4d242c; absorbed by a same-second concurrent commit -- disclosed)`. Generated 2026-08-01T12:56:09 ET. Population: the 66 structure-stop level-anchored trades (+$6,894.85 real OPRA) of engine-fullhist-replay-2026-07-23; conditioning re-slice only -- no new entries, no P&L changes, nothing arms. R2026 stratum n=35. Lookback<5d: 0 trades; trigger-bar label gaps: 0.

## The 16 pre-registered tests (ALL reported; BH-FDR q*=0.10)

| Test | cell n | cell $/tr | cell WR | comp n | comp $/tr | comp WR | diff $/tr | p | BH |
|---|---|---|---|---|---|---|---|---|---|
| C1_aligned|FULL|B1.00 | 19 | 210.83 | 0.579 | 47 | 61.47 | 0.447 | +149.36 | 0.1342 |  |
| C1_aligned|R2026|B1.00 | 12 | 189.48 | 0.583 | 23 | 21.97 | 0.478 | +167.52 | 0.2216 |  |
| C2_opposing|FULL|B1.00 | 23 | 99.93 | 0.435 | 43 | 106.89 | 0.512 | -6.96 | 0.9430 |  |
| C2_opposing|R2026|B1.00 | 13 | 135.57 | 0.538 | 22 | 46.21 | 0.500 | +89.36 | 0.5100 |  |
| C1_aligned|FULL|B0.50 | 10 | 152.38 | 0.500 | 56 | 95.91 | 0.482 | +56.46 | 0.6553 |  |
| C1_aligned|R2026|B0.50 | 5 | 186.79 | 0.600 | 30 | 61.50 | 0.500 | +125.29 | 0.5091 |  |
| C2_opposing|FULL|B0.50 | 20 | 72.83 | 0.400 | 46 | 118.22 | 0.522 | -45.39 | 0.6459 |  |
| C2_opposing|R2026|B0.50 | 11 | 72.87 | 0.455 | 24 | 82.39 | 0.542 | -9.52 | 0.9473 |  |
| C1_aligned|FULL|B2.00 | 31 | 128.38 | 0.452 | 35 | 83.29 | 0.514 | +45.09 | 0.6165 |  |
| C1_aligned|R2026|B2.00 | 19 | 124.38 | 0.474 | 16 | 25.99 | 0.562 | +98.39 | 0.4490 |  |
| C2_opposing|FULL|B2.00 | 28 | 120.93 | 0.464 | 38 | 92.34 | 0.500 | +28.59 | 0.7577 |  |
| C2_opposing|R2026|B2.00 | 16 | 162.28 | 0.562 | 19 | 9.610 | 0.474 | +152.66 | 0.2397 |  |
| C1_aligned|FULL|ANY | 66 | 104.47 | 0.485 | 0 | — | — | — | — (cell n=66, complement n=0) |  |
| C1_aligned|R2026|ANY | 35 | 79.40 | 0.514 | 0 | — | — | — | — (cell n=35, complement n=0) |  |
| C2_opposing|FULL|ANY | 29 | 146.41 | 0.483 | 37 | 71.59 | 0.486 | +74.82 | 0.4157 |  |
| C2_opposing|R2026|ANY | 16 | 162.28 | 0.562 | 19 | 9.610 | 0.474 | +152.66 | 0.2391 |  |

## Mutually exclusive cells (descriptive, every band x stratum)

### B1.00|FULL

| Cell | n | total | $/trade | WR | w/ intraday TL-tag |
|---|---|---|---|---|---|
| ALIGNED_ONLY | 6 | $+1,586.95 | $+264.49 | 0.667 | 1 |
| OPPOSING_ONLY | 10 | $-120.40 | $-12.04 | 0.300 | 2 |
| BOTH_SIDES | 13 | $+2,418.85 | $+186.07 | 0.538 | 3 |
| NO_LINE | 37 | $+3,009.45 | $+81.34 | 0.486 | 3 |

### B1.00|R2026

| Cell | n | total | $/trade | WR | w/ intraday TL-tag |
|---|---|---|---|---|---|
| ALIGNED_ONLY | 4 | $+1,275.95 | $+318.99 | 0.750 | 1 |
| OPPOSING_ONLY | 5 | $+764.60 | $+152.92 | 0.600 | 2 |
| BOTH_SIDES | 8 | $+997.85 | $+124.73 | 0.500 | 2 |
| NO_LINE | 18 | $-259.35 | $-14.41 | 0.444 | 3 |

### B0.50|FULL

| Cell | n | total | $/trade | WR | w/ intraday TL-tag |
|---|---|---|---|---|---|
| ALIGNED_ONLY | 5 | $+1,144.95 | $+228.99 | 0.600 | 1 |
| OPPOSING_ONLY | 15 | $+1,077.80 | $+71.85 | 0.400 | 5 |
| BOTH_SIDES | 5 | $+378.80 | $+75.76 | 0.400 | 0 |
| NO_LINE | 41 | $+4,293.30 | $+104.71 | 0.512 | 3 |

### B0.50|R2026

| Cell | n | total | $/trade | WR | w/ intraday TL-tag |
|---|---|---|---|---|---|
| ALIGNED_ONLY | 3 | $+833.95 | $+277.98 | 0.667 | 1 |
| OPPOSING_ONLY | 9 | $+701.60 | $+77.96 | 0.444 | 4 |
| BOTH_SIDES | 2 | $+100.00 | $+50.00 | 0.500 | 0 |
| NO_LINE | 21 | $+1,143.50 | $+54.45 | 0.524 | 3 |

### B2.00|FULL

| Cell | n | total | $/trade | WR | w/ intraday TL-tag |
|---|---|---|---|---|---|
| ALIGNED_ONLY | 7 | $+878.40 | $+125.49 | 0.429 | 2 |
| OPPOSING_ONLY | 4 | $+284.60 | $+71.15 | 0.500 | 0 |
| BOTH_SIDES | 24 | $+3,101.35 | $+129.22 | 0.458 | 6 |
| NO_LINE | 31 | $+2,630.50 | $+84.85 | 0.516 | 1 |

### B2.00|R2026

| Cell | n | total | $/trade | WR | w/ intraday TL-tag |
|---|---|---|---|---|---|
| ALIGNED_ONLY | 5 | $+497.40 | $+99.48 | 0.400 | 2 |
| OPPOSING_ONLY | 2 | $+730.60 | $+365.30 | 1.000 | 0 |
| BOTH_SIDES | 14 | $+1,865.80 | $+133.27 | 0.500 | 5 |
| NO_LINE | 14 | $-314.75 | $-22.48 | 0.500 | 1 |

### ANY|FULL

| Cell | n | total | $/trade | WR | w/ intraday TL-tag |
|---|---|---|---|---|---|
| ALIGNED_ONLY | 37 | $+2,648.95 | $+71.59 | 0.486 | 3 |
| OPPOSING_ONLY | 0 | $+0.00 | — | — | 0 |
| BOTH_SIDES | 29 | $+4,245.90 | $+146.41 | 0.483 | 6 |
| NO_LINE | 0 | $+0.00 | — | — | 0 |

### ANY|R2026

| Cell | n | total | $/trade | WR | w/ intraday TL-tag |
|---|---|---|---|---|---|
| ALIGNED_ONLY | 19 | $+182.65 | $+9.61 | 0.474 | 3 |
| OPPOSING_ONLY | 0 | $+0.00 | — | — | 0 |
| BOTH_SIDES | 16 | $+2,596.40 | $+162.28 | 0.562 | 5 |
| NO_LINE | 0 | $+0.00 | — | — | 0 |

## Day-level robustness (BH survivors only)

- (no BH survivors -- section empty by construction)

## Disclosures (frozen in prereg)

- n=66 small; conditioning read on an already-selected profitable cohort; hypothesis-generating only -- NOTHING arms from this study.
- Cohort is 100% structure-stop trades; the premium-stop TL_only leak (-$1,830/124tr) is out of population by design.
- 7/66 trades carry the intraday `trendline_rejection` trigger tag (a different, single-day detector); per-cell overlap column above.
- Context computed retrospectively with today's detector code on historical bars -- mechanism-faithful to what a score-contributor would see at decision time (same code, same no-look-ahead window), but the multi-day engine did not exist live for most of the window.
- Bars are the SIP/IEX cache patchwork (DATA-PROVENANCE.md); wall-v1 frame both sides of every join (et_frame doctrine); real-OPRA P&L only, zero synthetic.
- Sacred runner cohort (35 winners +$15,774) untouched -- read-only study.

*Decision rule applied (frozen): NULL -> the trendline program is VISIBILITY-ONLY (watch surface + premarket line, shipped this session); no further trendline-entry research without a new evidence class.*

---

## Post-run addendum (hand-written after the runner's output; the runner regenerates everything above)

- **Why the two ANY-aligned tests are degenerate (a finding, not a bug):** every one of the
  66 entries -- and every trade has 2-8 ACTIVE lines on its 5-day window -- had at least one
  same-side active line SOMEWHERE. Multi-day trendline EXISTENCE is a constant, not a signal:
  a 5-day swing-pivot fit essentially always produces standing lines. Any future trendline
  conditioning idea must therefore be PROXIMITY- or property-based (distance, respect_count,
  slope), never existence-based -- and proximity, tested at three pre-registered bands here,
  did not clear the bar.
- **The honest near-miss, stated once and not proposed:** aligned-support at the primary
  $1.00 band reads +$149.36/trade over its complement (19 vs 47, p=0.134, BH rank-1
  threshold 0.0071) and the sign is positive in R2026 too (+$167.52, p=0.222). Under the
  frozen rule this is NULL -- reported here because ALL cells get reported, explicitly NOT
  a proposal (the prereg forbids the soft-propose). If a future, larger real-fills
  population re-opens this question, it needs its own prereg and must cite this NULL.
- **Frame integrity evidence:** 0/66 trigger-bar label gaps -- every trade's lookback
  window ends exactly at entry minus 5 minutes in the shared wall-v1 frame (entry+1
  convention respected; no cross-frame joins anywhere).
