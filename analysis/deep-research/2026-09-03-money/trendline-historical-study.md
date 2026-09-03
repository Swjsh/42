# Trendline rising-support historical study (T3)

**Prereg:** [`prereg-trendline-rising-support-2026-09-03.md`](../../recommendations/prereg-trendline-rising-support-2026-09-03.md)
(frozen before this study ran — read it for every exact definition; this doc reports
results only, does not restate the rules).

**Run at ET:** 2026-09-03 17:44:19 Thursday EDT (`python setup/scripts/et_clock.py`).
Full run of `backtest/tools/trendline_study_historical-study.py`: **2.36s**, 45 sessions
(2026-06-26 -> 2026-09-03, every session with both a 1m and 5m cache in that window).
Raw output: [`trendline-historical-study.json`](trendline-historical-study.json).

**VERDICT: REFUTED.** Neither a bull `trendline_bounce` nor a bear `trendline_break`
SHADOW trigger clears the pre-registered bar, in the primary config or in any of the 8
configs tested. Full falsifier condition #1 fires: the primary config's TOUCH event has
lines in only 26/45 sessions, and only **18** of those sessions ever produce a qualifying
touch — below the `>= 25 sessions` bar. See §6 for why.

---

## 1. Primary config decision-rule scorecard (`5m_premkt`, ALL-wick, H=60min)

| | n events | n sessions | rate | rate 95% CI | baseline rate | mean move ($) | mean-move 95% CI | n-bar | rate-bar | mean-bar | VERDICT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **TOUCH** (bull) | 79 | 18 | 0.481 | [0.25, 0.70] | 0.562 | -0.023 | [-0.27, 0.21] | FAIL (need >=25 sess) | FAIL (CI-lower < baseline) | FAIL (CI crosses 0) | **NOT SUPPORTED** |
| **BREAK** (bear) | 25 | 25 | 0.480 | [0.28, 0.68] | 0.428 | -0.061 | [-0.25, 0.13] | borderline (n=25 sessions exactly, n=25 events < 40) | FAIL (CI-lower 0.28 < baseline 0.428) | FAIL (CI crosses 0) | **NOT SUPPORTED** |

All three bar-clearing conditions (n, rate-vs-baseline, mean-move>0) must hold. Neither
event type clears any of the three on the primary config.

## 2. All 8 configs (FACT — every cell is a direct read of the JSON, not extrapolated)

`n_sess_line` = sessions where a valid rising-support line existed at all (first two
confirmed pivot lows, second higher than first). `touch`/`break` columns are H=60 stats.

| config | n_sess_line /45 | touch n / n_sess | touch rate [CI] | touch baseline | touch mean-move [CI] | break n / n_sess | break rate [CI] | break baseline | break mean-move [CI] |
|---|---|---|---|---|---|---|---|---|---|
| **5m_premkt \| wick (PRIMARY)** | 26 | 79 / 18 | 0.48 [0.25, 0.70] | 0.56 | -0.02 [-0.27, 0.21] | 25 / 25 | 0.48 [0.28, 0.68] | 0.43 | -0.06 [-0.25, 0.13] |
| 5m_premkt \| body | 31 | 83 / 22 | 0.42 [0.31, 0.54] | 0.56 | -0.04 [-0.18, 0.13] | 31 / 31 | 0.45 [0.29, 0.65] | 0.44 | -0.14 [-0.36, 0.07] |
| 5m_rth \| wick | 28 | 65 / 21 | **0.66 [0.51, 0.79]** | 0.49 | 0.33 [-0.19, 0.91] | 27 / 27 | 0.59 [0.41, 0.78] | 0.45 | 0.08 [-0.49, 0.68] |
| 5m_rth \| body | 25 | 19 / 12 | 0.53 [0.20, 0.76] | 0.50 | 0.07 [-0.82, 0.78] | 24 / 24 | 0.42 [0.21, 0.63] | 0.46 | -0.41 [-1.06, 0.24] |
| 15m_premkt \| wick | 17 | 20 / 8 | 0.45 [0.19, 0.75] | 0.53 | -0.04 [-1.07, 1.73] | 12 / 12 | 0.67 [0.42, 0.92] | 0.48 | 0.52 [-0.12, 1.20] |
| 15m_premkt \| body | 20 | 13 / 8 | 0.23 [0.00, 0.43] | 0.51 | -0.83 [-1.29, -0.25] | 16 / 16 | 0.44 [0.19, 0.69] | 0.48 | -0.13 [-0.80, 0.65] |
| 15m_rth \| wick | 20 | 19 / 11 | 0.37 [0.13, 0.60] | 0.47 | -0.29 [-0.72, 0.06] | 13 / 13 | 0.46 [0.23, 0.77] | 0.52 | 0.18 [-0.30, 0.71] |
| 15m_rth \| body | 26 | 12 / 7 | 0.58 [0.25, 0.81] | 0.43 | -0.08 [-0.63, 0.19] | 14 / 14 | 0.50 [0.21, 0.79] | 0.54 | 0.23 [-0.35, 0.81] |

**Best single cell: `5m_rth | wick` touch** — rate CI-lower (0.51) *does* clear its
baseline (0.49), the only cell where that happens. It still fails the study's other two
bars: only 21 sessions (< 25) and the mean-move CI [-0.19, 0.91] straddles zero (no real
$-edge, just a slightly-better-than-coinflip directional rate on a small, RTH-only,
premarket-blind sample). Not evidence for a build — it is the weakest possible "maybe,"
and it disappears once premarket is included (`5m_premkt|wick` touch rate 0.48 < its own
0.56 baseline).

## 3. 5m vs 15m

15m has fewer valid lines per session-count (17-26 of 45 vs 25-31 of 45 on 5m) and much
smaller n at every horizon (12-20 touch events vs 65-83 on 5m) — the $0.25 tolerance and
1-2-bar horizons leave little room. No 15m cell clears the decision bar; several actually
point the WRONG way (15m_premkt|body touch mean-move CI **[-1.29, -0.25]** — entirely
negative, i.e. touches on that specific cut were followed by continued DECLINE, the
opposite of the bull thesis; n=13/8 sessions is too small to trust but it is the one cell
where the sign itself, not just the magnitude, argues against the setup).

## 4. Wick vs body

No consistent winner. Wick beats body on `5m_rth` touch rate (0.66 vs 0.53) and roughly
ties on `5m_premkt`; body beats wick on `15m_rth` touch rate (0.58 vs 0.37) but loses badly
on `15m_premkt` touch (0.23 vs 0.45, and the only negative-mean-move-CI cell in the table).
Neither mode systematically outperforms once baseline-normalized — this dimension is not
where the signal (if any) would live.

## 5. Premarket-anchored vs RTH-only

This is the most consequential axis, and it cuts against J's chart reading, not for it:
RTH-only (`5m_rth|wick`) is the strongest cell in the whole table (rate 0.66, mean-move
+0.33), while premarket-anchored (`5m_premkt|wick`) — the version built to reproduce J's
own 08:20-premarket-low anchor — is the WEAKEST directional cell (rate 0.48, actually below
its own baseline; mean-move -0.02, flat). **Including the premarket low as an eligible
anchor makes the line worse, not better**, under this literal rule. §6 explains the
mechanism: premarket produces extra noisy pivots that get selected as "the first two"
before the structurally meaningful ones J is actually looking at.

## 6. Today's exhibit (2026-09-03) vs J's by-eye read — FACT

| config | anchor A | anchor B | touches | break |
|---|---|---|---|---|
| **5m_premkt \| wick (matches J's chart)** | **none — first two confirmed pivot lows are 05:00 ($765.80) then 05:55 ($764.70), FALLING** | — | — | — |
| 5m_premkt \| body | none (same failure mode) | | | |
| 5m_rth \| wick | 10:10 ET, $767.53 | 10:30 ET, $767.83 | 10:45, 10:50, 10:55, 15:55, 16:05 | 16:15 |
| 5m_rth \| body | 10:05 ET, $767.81 | 10:35 ET, $767.88 | (none) | (none) |
| 15m_premkt \| body | 10:45 ET, $768.17 | 12:15 ET, $772.43 | (none) | 13:00 |
| 15m_rth \| body | 10:45 ET, $768.17 | 12:15 ET, $772.43 | (none) | 13:00 |
| 15m_premkt/rth \| wick | none | | | |

**FACT, verified this session:** on `5m_premkt`, the full swing-low sequence for
2026-09-03 (window k=2, inclusive-right) is `05:00($765.80) 05:55($764.70) 06:25($764.48)
06:50($764.36) 07:30($764.21) 07:45($764.76) 08:15($764.96) 09:05($766.96) 10:10($767.53)
10:30($767.83) ...`. J's two anchors — "08:20 premarket low" and "10:10 double-bottom low"
— correspond to swing-low **#7** (08:15, $764.96, 5 min off J's stated 08:20, likely bar-
bucketing) and swing-low **#9** (10:10, $767.53, exact match) in that sequence, **not #1
and #2**. J is not picking the chronologically-first two fractal pivots of the session —
he is picking the low of the pre-dawn decline (a multi-pivot down-move, of which 08:15 is
the LAST/lowest point before the reversal, not the first pivot after it) and the next
higher low that confirms a reversal structure. The mechanical "first two, literal" rule
this study froze does not reproduce that read; **10:55 ET ("closing above and right on the
trendline")** and **14:30 ET ("breaks... we start declining")** — the two specific bars J
narrated — are never reached by the primary-config algorithm today because no line exists
under it. `5m_rth|wick` (which sidesteps the falling-pivot problem by starting the clock at
09:30) DOES produce a touch cluster at 10:45-10:55 (bracketing J's 10:55 call within one
bar) and a break at 16:15 (not 14:30 — 90 minutes later, and on a different, RTH-only-
anchored line, so not directly comparable to J's line).

**INFERENCE:** J's mental model is closer to "the low of the pre-move decline, and the
first higher low after it" (a 2-swing reversal read) than to "the first two confirmed
pivot lows of the day" — the literal rule this prereg froze is a reasonable, honest first
cut at operationalizing his description, and it demonstrably diverges from his actual
anchor choice on the one session with his own narration to check against. This is the
single most important qualitative finding of the study and the reason a revised
(non-first-two) anchor rule would need its OWN fresh preregistration before being tested —
not patched into this frozen result.

## 7. Engine cross-reference — BULLISH_RECLAIM fills vs rising-support third touch

`journal/trades.csv`, `BULLISH_RECLAIM_RIDE_THE_RIBBON` setup, 2026-06-26..2026-09-03:
**230** distinct entry events (grouped by date+time_entry, 330 raw rows collapsed for
multi-leg trades).

| | n | n sessions | mean $pnl | 95% CI (session-clustered) |
|---|---|---|---|---|
| Matched (primary-config touch within +/-10 min) | **0** | 0 | n/a | n/a |
| Unmatched | 230 | 26 | $16.09 | [-$32.57, $67.39] |

**FACT, verified this session:** zero of 230 engine BULLISH_RECLAIM entries coincide with
a primary-config rising-support third-touch within +/-10 minutes. **Not surprising, and
not evidence against rising-support lines specifically:** the live `BULLISH_RECLAIM_
RIDE_THE_RIBBON` setup fires through `detect_trendline_reclaim_bullish`
(`backtest/lib/filters.py:1101`), which is a **descending-resistance breakout through swing
HIGHS** — the bull mirror of the bear rejection detector, unchanged pivot family — not a
rising-support bounce through swing lows at all. The two mechanisms have no geometric
overlap; a zero-coincidence result is close to the null expectation from two unrelated
detectors, compounded by the primary config's touches existing in only 18/45 sessions to
begin with. This cell answers "does the engine already capture this for free" (no) rather
than "is this pattern real" (answered separately, and negatively, in §1-2).

## 8. Falsifier check (per prereg §8)

- [x] **Fewer than 25 sessions produce a valid line** — primary-config TOUCH: 18 sessions
  with >=1 qualifying touch (< 25). **Falsifier condition MET.**
- [x] **CI-lower does not clear baseline** — TOUCH: 0.25 < 0.56. BREAK: 0.28 < 0.43. **MET
  for both event types on the primary config.**
- [x] **Mean-move CI-lower <= 0** — TOUCH [-0.27, 0.21], BREAK [-0.25, 0.13], both straddle
  zero. **MET for both.**
- [ ] Extreme concentration collapsing the CI — not the binding failure here (primary
  touch top-3-session share is 48.1%, break is 12.0%; neither is the >60% trigger, and the
  result already fails on the other three grounds without needing this one).

**Three of four falsifier conditions independently fire on the primary config.** This is
not a marginal miss.

## 9. What this does and does not say

- **Does say:** the literal "first two confirmed pivot lows, second higher, no re-fit"
  rule for a rising-support line — the simplest, most direct operationalization of J's
  described process — does not produce a statistically supported bull or bear SHADOW
  trigger over 45 real sessions, on any of 4 bar-sets x 2 anchor-modes tested, at the
  pre-registered bar. The premarket-anchored cut (the one built to match J's own stated
  anchors) is the WEAKEST cell, not the strongest.
- **Does not say:** that J's actual chart-reading process has no edge — §6 shows the
  literal rule picks different anchors than J does on the one session checked against his
  own narration. A rule built around "the low that ends the pre-move decline, plus the
  next confirmed higher low" (rather than "first two pivots of the day, full stop") is an
  UNTESTED, different hypothesis and would need its own fresh prereg, not a re-run of this
  one with the threshold quietly loosened.
- **Does not say:** the engine is missing a bullish edge sitting in its own fills — §7's
  zero-coincidence result is explained by geometry mismatch (engine trades a descending-
  resistance breakout, not a rising-support bounce), not by this pattern being validated
  and simply unwired.

## Cost

$0 — pure Python over cached `backtest/data/spy_sip_cache` bars + `journal/trades.csv`
(read-only). No network/broker calls. Runtime 2.36s.
