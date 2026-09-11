# Gamma-Crypto-1 Pass 2 — exit-parameter sweep on full daily BTC-USD history

**Verdict: ALL KILLED.** 0 of 108 exit-parameter combinations, across all 3
setups, survive Benjamini-Hochberg FDR correction against their own
random-entry null. No setup reaches the "same gate shape as Pass 1"
ratification bar. This is a legitimate, fully-computed result, not a
rounding-up — see per-setup detail below.

Run 2026-07-16 (this session). Full per-combo detail:
`analysis/recommendations/crypto-paper-{trendline-reclaim,level-reclaim,regime-pullback}-pass2.json`.

## Job 1 — daily history (the honest way to raise n)

yfinance `period="max"`, `interval="1d"` returned **4,320 daily BTC-USD
bars, 2014-09-17 .. 2026-07-16 (~11.85 years)** — vs Pass 1's 730-bar/2-year
window. This span covers the 2017 bull, 2018 bear, 2020 COVID crash, 2021
bull, 2022 bear, and 2024-26 regimes named in the task brief. Cached at
`crypto_paper/data/cache/BTC-USD_1d_full.csv` (separate from Pass 1's 2-year
daily cache — no Pass 1 file was overwritten).

Setup parameters were re-tuned for daily granularity (full reasoning in
`crypto_paper/run_pass2.py`'s `DAILY_SETUP_PARAMS` docstring — not a
mechanical bar-count /6 conversion): TRENDLINE_RECLAIM `swing_window` 5->3,
`lookback_bars` 180->90; LEVEL_RECLAIM `lookback` 60->50; REGIME_PULLBACK
`ema_length` unchanged at 20 (EMA20 is already a daily-chart convention),
`pullback_tolerance_pct` 1.5->2.0.

Running Pass 1's UNCHANGED fixed exit shape (catastrophe -20%, TP1 +15%/50%,
chandelier arm+8%/trail15%) on the deepened daily history:

| Setup | n trades (was, Pass 1 4h/2y) | Win rate | Total P&L | WF passed (65/35 split) | Yearly stability |
|---|---|---|---|---|---|
| TRENDLINE_RECLAIM | **45** (was 14) | 37.8% | +$436.50 | **PASS** (wf_ratio 0.85) | FAIL |
| LEVEL_RECLAIM | **41** (was 15) | 53.7% | +$1,216.91 | FAIL (wf_ratio 0.558) | PASS |
| REGIME_PULLBACK | **100** (was 28) | 40.0% | +$1,743.83 | FAIL (wf_ratio 0.156) | PASS |

Sample sizes roughly 3x on the same fixed exit shape, purely from using the
deeper daily history — confirms Job 1's premise. IS/OOS split: chronological
cutoff at 65% of the date range = **2022-05-26** (train 7.69y / test 4.14y).

## Job 2 — exit-parameter sweep (108 combos/setup)

Grid: catastrophe {-15%,-20%,-25%} x TP1 {+10%,+15%,+20%,OFF} x chandelier
arm {+5%,+8%,+12%} x trail {10%,15%,20%} = **108 combos**, same grid for all
3 setups. Per combo: chronological IS/OOS split (train=first 65% of the date
range), random-entry null (250 independent single-trade draws, same exit
shape, entries restricted to the OOS window), bootstrap p-value (B=2000),
Benjamini-Hochberg FDR correction **across all 108 combos of a setup**
(alpha=0.05), yearly sub-window stability (majority of years-with-trades net
positive), and — reserved for anything that clears everything else — a
cross-check against Pass 1's original, untouched 4h/2-year window.

| Setup | Cells tested | BH-FDR eligible | BH-FDR survivors | Verdict |
|---|---|---|---|---|
| TRENDLINE_RECLAIM | 108 | 108 | **0** | KILL |
| LEVEL_RECLAIM | 108 | 108 | **0** | KILL |
| REGIME_PULLBACK | 108 | 108 | **0** | KILL |

### The nail, per setup

**TRENDLINE_RECLAIM** — kill nail: *0/108 combos beat their own random-entry
null after FDR correction.* The closest near-miss —
`cat-15%_tp1off_arm+12%_trail15%` — actually passes BOTH the walk-forward
gate (wf_ratio 1.24, train +$562.62/test +$375.69) AND yearly stability
(7/12 years positive), with a RAW p-value of 0.024 (individually "significant"
at alpha=0.05). It still doesn't survive: with m=108 combos tested, BH-FDR's
rank-1 threshold is `(1/108)*0.05 ≈ 0.00046` — 0.024 isn't close. This is
the textbook case the FDR correction exists for: pick the single best-looking
cell out of 108 without correcting, and you'd have shipped a false positive
(CLAUDE.md OP-25 lesson C14 — dead/vary-and-assert knobs; this is that
failure mode's statistical twin).

**LEVEL_RECLAIM** — kill nail: *same, 0/108 survivors.* Superficially the
most attractive setup (Job 1 baseline: 53.7% WR, +$1,216.91 total on the
fixed exit shape) but its best near-miss combo
(`cat-25%_tp1+20%_arm+8%_trail15%`, p=0.011, OOS mean +$36.79/trade) still
fails walk-forward on its OWN best cell (wf_ratio 0.694, just under the 0.70
gate) even before the FDR correction is applied. The headline P&L is real
but concentrated in a train-window run-up that the OOS window doesn't
reproduce at the same rate.

**REGIME_PULLBACK** — kill nail: *same, 0/108 survivors,* and the weakest of
the three on every non-null metric too: Job 1 baseline wf_ratio 0.156 (train
+$1,608 vs test +$135), and even its best near-miss combo only reaches
wf_ratio 0.335. 100 trades is the largest sample of the three (highest-
frequency trigger), but volume didn't buy edge — most of the P&L sits in the
train window and doesn't carry into the OOS test window.

## What this means (read together with Pass 1)

Two independent passes now agree: a positive TOTAL P&L number on a fixed or
swept exit shape is not evidence of a real signal for these 3 setup
definitions on BTC/USD spot — in Pass 2, the SAME exit shapes applied to
RANDOM entries in the OOS window perform statistically indistinguishably
from the real triggers, for every one of 324 combo/setup pairs tested. The
edge, if any exists in `crypto/lib`'s trendline/level/regime primitives for
BTC, is not being captured by these 3 long-only entry definitions with any
exit shape in this grid. Candidates for a future pass (not built this
session, per scope): sweep the SIGNAL parameters (not just exits), test
short-side/mean-reversion structures, or test on a different timeframe
between 4h and 1D.

## Verdict

**ALL KILLED.** 0 survivors across TRENDLINE_RECLAIM, LEVEL_RECLAIM,
REGIME_PULLBACK — none beat their own random-entry null after Benjamini-
Hochberg correction across the 108-combo grid, the binding constraint for
all three (before wf_ratio, stability, or the 4h/2y cross-check ever come
into play, since those are computed AFTER FDR eligibility). Gamma-Crypto-1
Phase 1 remains unratified after two independent passes; no live engine
work (Phase 2/3) is warranted by this evidence.
