# Ribbon-Scope Gap-Morning A/B — results summary

**Pre-reg (frozen before any run):**
`analysis/recommendations/ribbon-scope-gap-morning-prereg-2026-07-23.json`
**Runner:** `backtest/tools/ribbon_scope_gap_morning_ab.py`
**Raw results:** `analysis/edge-matrix/ribbon-scope-gap-morning-results-2026-07-23.json`
**Episodes:** `analysis/edge-matrix/ribbon-scope-gap-morning-episodes-2026-07-23.json`

## VERDICT: HONEST NULL — no cell clears the standing 4-gate bar or BH significance

Population: 24 top-quartile-gap days (|gap_pct| >= 0.57, computed from the 385-day
distribution) with full extended-hours cache coverage (18 tuning / 6 heldout, held-out
recomputed as last-25%-by-date of this population per the prereg's disclosed amendment).
Detector: the committed LIVE-BASELINE bear-level-rejection cell (band0.00|nth1|close_below),
unchanged across all 3 cells — only the ribbon-gate scope (and, for the ETH cell, the exit
ribbon_flip_back scope) varies.

| Cell | n (tuning fills) | Expectancy | Total P&L (tuning) | Day WR | Held-out total | Gates | p_raw | BH sig? |
|---|---|---|---|---|---|---|---|---|
| **RTH** (control, live) | 26 | +$15.03 | +$390.90 | 0.364 | **-$820.84** | 1/4 | 0.860 | No |
| **ETH** (full substitution) | 29 | -$46.12 | -$1,337.45 | 0.364 | **-$2,621.94** | 0/4 | 0.440 | No |
| **AGREE_ONLY** (entry filter) | 19 | **+$60.75** | **+$1,154.23** | **0.444** | -$2,392.11 | 1/4 | 0.571 | No |

**All 3 cells fail gate g4 (held-out positive)** — on the 6 unseen heldout gap mornings
(2026-06-16, 06-18, 06-23, 06-25, 07-08, 07-17), this signal lost money regardless of which
ribbon scope gated it. None are BH-significant at m=3, alpha=0.05 (all p_raw >= 0.44, nowhere
near any BH threshold). No cell is above the OP-16 evidence floor concern (all n >= 15).

**Comparative ranking (informational only — not a promotion signal, since nothing cleared
gates):** AGREE_ONLY (requiring RTH+ETH scope agreement on entry) has the best tuning-set
expectancy, total P&L, and day-win-rate of the three, and the smallest ex-top1 sensitivity
(-$298.63 vs RTH's -$1,061.96 and ETH's -$2,177.10 — its wins are less concentrated in one
outlier trade). Full ETH-scope substitution (entries AND exits) is the worst of the three on
every tuning metric. The RTH control sits in between. **Directionally this suggests an
agreement filter has more promise than a full scope swap** — but "no cell cleared gates" is
the actual, disclosed result; this ranking should not be read as a ship signal.

## Disagreement rate (the Part-1 whisper/brief calibration number)

| Bucket | Days | First-hour bars checked | Disagreements | Rate |
|---|---|---|---|---|
| Gap days (|gap_pct| >= 0.57) | 24 | 288 | 134 | **46.5%** |
| Normal days (|gap_pct| < 0.57) | 59 | 708 | 307 | **43.4%** |

**Finding, stated honestly:** the RTH-vs-ETH stack DISAGREEMENT RATE in the first hour is
high in both buckets (~44-47% of first-hour bars) and only ~3 points higher on gap mornings
— NOT the dramatic gap-specific spike the original oracle's dollar-level divergence finding
might suggest. This is consistent with, not contradictory to, the oracle's $6.40 finding: the
*dollar* divergence is largest specifically at big gaps (confirmed, Part A), but the
*categorical* stack flip happens whenever the three EMAs are naturally close together (near a
BULL/BEAR/MIXED boundary) — a condition that occurs on plenty of non-gap mornings too. The
Part-1 flag should therefore not assume "quiet" mornings are scope-safe; a ~43-47% baseline
disagreement rate means J's ribbon and the engine's RTH ribbon disagree on stack classification
in the first hour on roughly every other trading day, gap or not. (`entry_window_x_first_hour`
numbers are
identical to the plain `first_hour` numbers by construction here — the 09:35 entry-window
floor minus the 5-minute entry delay opens exactly at 09:30, so the window fully contains the
first hour; not a bug, just a redundant cut given current entry-window params.)

## Design notes (frozen in the pre-reg before running)

- **AGREE_ONLY re-scopes entries only, not exits** (exit ribbon_flip_back stays RTH-scope,
  identical to control) — a deliberate, disclosed asymmetry vs the ETH cell (which re-scopes
  both sides), isolating the entry-filter effect cleanly.
- **Level source stays RTH-scope in all 3 cells** — only the ribbon gate varies, per the
  queue item's own framing of this as a ribbon-scope question, not a level-scope question.
- **Held-out split recomputed for this population** (last-25%-by-date of the 24-day gap
  population, not inherited from the parent bear-level-rejection study's global heldout) —
  the inherited split degenerated to 8 tuning / 30 heldout for this population (most
  full-ETH-coverage days cluster late in the overall date range), backwards from held-out's
  purpose. Disclosed in the prereg before any results were read.
- **Caveat carried from Part A**: ETH-scope stack classification itself carries a measured
  ~10% disagreement rate vs TV's own live render even in the validated coverage regime
  (structural SIP-vs-BATS premarket feed noise). The ETH/AGREE_ONLY cells' entries should be
  read with that calibration in mind.

## Causality

3 sampled RTH-cell signal bars, truncated-frame LevelMemory recompute matched exactly
(asserted, `causality_audit` in the results JSON) — same pattern the parent bear-level-
rejection study uses, reused not re-derived.
