# G6 — J's weekly-put hold-to-Friday battery — VERDICT: KILL (gap-exposed, null-failed)

**Ran:** `_dte34_multiday_hold_sim.py` on the REAL 3-4DTE OPRA multi-day cache (options_3dte /
options_4dte, 1485/1476 contract files), vwap_continuation signal (166 signals), ITM2
stop=−0.2 target=0.5 chart_stop=on. Result: `analysis/recommendations/multiday-dte34-hold.json`.

## The DTE ladder (OOS expectancy, random-entry null p, held-overnight %, gap loss)

| DTE | hold | n | OOS_exp | OOS_WR | drop3 | p_null | held% | gap_loss$ |
|---|---|---|---|---|---|---|---|---|
| 0 | intraday | 157 | $36.34 | 40.0% | $45.13 | **0.005** | 0% | 0 |
| 1 | intraday | 166 | $59.02 | 41.2% | $59.05 | **0.01** | 0% | 0 |
| 2 | intraday | 165 | **$66.13** | 42.0% | $58.94 | **0.045** | 1.2% | 0 |
| 3 | TRUE multi-day | 165 | $53.21 | 46.0% | $62.65 | 0.075 ✗ | 17.6% | **−$4,050** |
| 4 | TRUE multi-day | 163 | $44.65 | 44.9% | $66.63 | 0.105 ✗ | 26.4% | **−$6,413** |

## Verdict — the hold-to-Friday thesis is KILLED
The specific idea J asked to test — **buy an OTM weekly put and HOLD it across days to Friday
with an underlying-level/wider stop** — does not survive:
1. **Null-failed.** At 3-4DTE the random-entry null is NOT beaten (p=0.075 / 0.105 > 0.05): the
   multi-day-hold "edge" is statistically indistinguishable from entering at random. (0/1/2DTE
   beat it at p 0.005/0.01/0.045.)
2. **Gap-exposed.** The held positions bleed **−$4,050 (3DTE) / −$6,413 (4DTE)** on overnight
   gaps — exactly the risk the honest prior flagged. The WR (44-46%) is undermined by this tail.
3. **Doesn't even hold.** held-overnight is only 17.6% / 26.4% — even at the wider stop most
   positions resolve intraday, so it doesn't actually deliver "ride the move across days." The
   sim's own tag: **MULTIDAY-HOLD-NOT-REACHED.**
4. **Doesn't beat 2DTE anyway.** 3DTE OOS $53 < 2DTE OOS $66; 4DTE $44 lower still.

**The nail: null-dominated + overnight-gap-bleed + doesn't-hold.** A kill is a deliverable.

## What IS real (the by-product, not shippable tonight)
The **DTE lever** 0→1→2DTE is validated on OOS expectancy (**$36 → $59 → $66**, monotone,
nulls intact) — entering vwap_continuation at 1-2DTE (lower theta on entry premium) then
exiting SAME-DAY beats 0DTE. BUT this is the SAME 2DTE lever already **corrected to HOLD**
earlier this session (fails walk-forward WF≈0.556 < 0.70; the $2K sizing floor gives 1.6 lots
< the 3-lot floor). So it is not re-opened here — G6 adds the multi-day-HOLD kill on top.

**Re-open condition:** a fresh signal that actually stays held past day-T (held% ≫ 26%) AND a
gap-hedge (spread structure) that caps the −$4-6K overnight tail. Until then: 0DTE stays the
instrument; weekly-hold is shelved with the nail pinned.
