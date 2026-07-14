# Trendline FADE entry battery -- TREND-FADE-PREREG (2026-07-14)

Prereg: `prereg-trendline-fade-battery-2026-07-14.json` (frozen, run verbatim). Elapsed: 180.8s. 78191 qualifying lines, 51534 candidate episodes across 3 fade variants.

Motivation: S1's break-battery killed CONTINUATION entries 12/12 but disclosed the opposite-direction null beating the real trade OOS in 10/12 cells. This battery promotes fading to a first-class, pre-registered hypothesis (own nulls, own pass bar) with 2 new variants S1 never tested.

| Cell | n | Exp/tr | OOS Exp | WF | p | BH-sig | Beats nulls | Verdict |
|---|---|---|---|---|---|---|---|---|
| F1_fade_immediate::body::resistance(fade-of-bullish) | 8993 | 16.0 | 53.81 | None | 0.0457 | YES | both | **FAIL** |
| F1_fade_immediate::body::support(fade-of-bearish) | 11095 | -13.82 | -57.14 | -8.282 | 0.048 | YES | both | **FAIL** |
| F1_fade_immediate::wick::resistance(fade-of-bullish) | 4802 | -8.59 | -18.18 | None | 0.4267 | no | both | **FAIL** |
| F1_fade_immediate::wick::support(fade-of-bearish) | 5672 | -34.59 | -5.8 | None | 0.0004 | YES | both | **FAIL** |
| F2_fade_reclaim_confirmed::body::resistance(fade-of-bullish) | 933 | -86.29 | -224.99 | None | 0.0013 | YES | neither | **FAIL** |
| F2_fade_reclaim_confirmed::body::support(fade-of-bearish) | 893 | -147.03 | 84.37 | None | 0.0 | YES | both | **FAIL** |
| F2_fade_reclaim_confirmed::wick::resistance(fade-of-bullish) | 513 | 85.7 | 67.84 | 0.698 | 0.0193 | YES | both | **FAIL** |
| F2_fade_reclaim_confirmed::wick::support(fade-of-bearish) | 476 | -104.95 | -34.31 | None | 0.004 | YES | both | **FAIL** |
| F3_fade_low_volume::body::resistance(fade-of-bullish) | 4072 | 29.76 | 78.16 | 20.604 | 0.0275 | YES | both | mechanical PASS -> **FAIL** (post-hoc stability audit, see below) |
| F3_fade_low_volume::body::support(fade-of-bearish) | 4314 | -1.37 | 0.66 | None | 0.9152 | no | both | **FAIL** |
| F3_fade_low_volume::wick::resistance(fade-of-bullish) | 1821 | 21.23 | -73.79 | -1.041 | 0.2737 | no | both | **FAIL** |
| F3_fade_low_volume::wick::support(fade-of-bearish) | 1952 | -16.46 | 115.86 | None | 0.3954 | no | both | **FAIL** |

Verdict counts (mechanical, frozen pass_bar): {'PASS': 1, 'FAIL': 11, 'INCONCLUSIVE_UNDERPOWERED': 0}
Verdict counts (final, after post-hoc stability audit): **{'PASS': 0, 'FAIL': 12, 'INCONCLUSIVE_UNDERPOWERED': 0}**

## Post-hoc stability audit (added before any ship decision -- OP-33/fable-too-good)

The one mechanical PASS (`F3_fade_low_volume::body::resistance(fade-of-bullish)`, n=4072) carried
a tell in its own summary row: `is_expectancy=$3.79/tr` (statistically indistinguishable from
zero) against `oos_expectancy=$78.16/tr`, producing `wf=20.604` -- an extreme walk-forward ratio
driven by a near-zero IS denominator, not by genuinely stable pre/post-boundary performance. This
study's own frozen `pass_bar` (in the prereg) never tested sub-window stability, but the mission's
OP-11 auto-ratify bar does (`OOS_positive AND WF>=0.70 AND sub_window_stable AND
anchor_no_regression`) -- so this cell was re-derived (no threshold/variant/null changed) for
monthly/quarterly/date-concentration diagnostics before any ship/REVOKE call.

**Result: fails sub_window_stable, decisively.**
- OOS-only monthly expectancy: 2026-01 = **-$630/tr**, 2026-02 = **-$322/tr** (2 of 7 OOS months
  strongly negative), 2026-03 = **+$501/tr** (the OOS-positive result's entire foundation), then
  2026-04..07 modest positive ($28-$287/tr).
- **The entire OOS-positive total ($111,139) traces to March 2026 alone (+$169,955)** -- OOS
  excluding March is net **NEGATIVE ~-$58,816**.
- **Date concentration:** 340 unique dates across 4072 trades, but the **top 10 single days sum to
  249.2% of the cell's entire full-sample total_pnl** -- meaning the other 330 dates net to
  roughly **-149%** of total, a large negative tail more than offset by a handful of outsized
  days. Single worst case: **2026-03-27 alone = 52.4% of total_pnl** (38 trades, one day).

This is a concentration artifact (a few outsized days, dominated by one March-2026 cluster), not a
generalizable edge. **Final verdict: FAIL.** Runner: `backtest/tools/_fade_battery_artifact_hunt.py`
(ad hoc, read-only reuse of `trendline_fade_battery.py`, no variant/threshold/null edited).

## Bottom line

**12/12 cells FAIL.** Fading confirmed trendline breaks (immediate, reclaim-confirmed, or
low-volume-filtered) does not clear the evidence bar on this dataset/exit-shape, matching S1's
break-continuation study's own 12/12 KILL. The disclosed "opposite-direction null beats real
trade in 10/12 cells" finding that motivated this study turns out NOT to translate into a
standalone tradeable fade edge once tested as a first-class hypothesis with its own nulls,
BH-FDR, and (critically) sub-window stability -- both break-continuation AND break-fade are
KILLED for this signal source. Nothing ships. Nothing arms. No params/config/trading-path file
touched. No orders placed.