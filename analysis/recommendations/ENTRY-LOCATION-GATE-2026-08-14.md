# ENTRY-LOCATION-GATE — verdict

**Prereg:** `prereg-entry-location-gate-2026-08-14.json` (frozen before the runner).
**Runner:** `backtest/autoresearch/entry_location_gate_2026_08_14.py`.
**Raw:** `analysis/recommendations/entry-location-gate-2026-08-14.json`.
**Population:** `engine-fullhist-replay-2026-07-23` — real-OPRA-fills replay, 2025-01-02..2026-07-22.

---

## VERDICT: DO NOT ARM. The bull side is NOT-RUN; the bear side fails its own pre-registered test.

| | |
|---|---|
| **Bull (calls)** | **NOT-RUN.** n=29 after causal exclusions; the largest cell gates 21 trades, every cell below the pre-registered n>=30 floor. **The question J actually asked — "why did we buy calls at the top?" — cannot be answered by this population.** |
| **Bear (puts)** | 4 cells measured, **0 of 4 survive BH-FDR at q=0.10.** |

This is a null against the pre-registered metric. Nothing is armed, and
`min_contracts_equity_scaled` stays disarmed — its re-arm condition (a validated entry-quality
gate) is **not** met.

---

## What the data does say (reported in full, per prereg "report ALL cells")

Bear baseline: n=144, total $2,068.55, mean **$14.36/trade**, win rate 25.7%.

| cell | n gated | gated mean | kept mean | perm p | book delta if gated | blocked winners |
|---|---|---|---|---|---|---|
| `prox<=0.10` | 44 | **−$45.47** | **+$40.69** | 0.0453 | +$2,000.90 | 5 (**$2,445.40**) |
| `prox<=0.20` | 70 | −$3.56 | +$31.32 | 0.380 | +$249.10 | 15 ($5,659.80) |
| `prox<=0.30` | 89 | +$15.80 | +$12.04 | 0.929 | −$1,406.10 | 22 ($8,521.40) |
| `run>=2.0` | 37 | +$32.37 | +$8.14 | 0.593 | −$1,197.65 | 12 ($5,085.15) |
| `run>=3.0` and all 6 AND-combos | 6–24 | — | — | — | — | **NOT-RUN** (n<30) |

**Why `prox<=0.10` fails despite p=0.0453:** BH-FDR at q=0.10 over 4 cells requires the
smallest p <= 0.025. It is 0.0453. **Uncorrected significance on the tightest band of a swept
family is exactly the false positive the correction exists to catch.**

**The blocked-winner column is doing its job (prereg G3, C20):** gating `prox<=0.10` removes
44 trades = 39 losers (−$4,446.30) **and 5 winners (+$2,445.40)**. The gate is not free; it
pays $2,445 of winners to avoid $4,446 of losers. At `prox<=0.30` the trade flips outright —
the book gets **worse** by $1,406. **C20 confirmed: widen the proximity band and a location
veto starts cutting breakouts.**

**`run>=2.0` runs the OPPOSITE way to the hypothesis:** puts entered after a big down day made
**+$32.37** vs +$8.14 for the rest. Gating them would have cost $1,198. The "don't trade after
an extended move" intuition is contradicted on the bear side — worth remembering before it is
proposed again.

---

## EXPLORATORY — declared, and deliberately NOT in the FDR family

Win rate was **not** the pre-registered metric (that is delta expectancy), so it is excluded
from the correction and **cannot support a decision**. Recorded because mean-dollar tests on
0DTE are dominated by a handful of large winners, and because the pattern is coherent:

| cell | gated WR | kept WR |
|---|---|---|
| `prox<=0.10` | **11.4%** (n=44) | 32.0% (n=100) |
| `prox<=0.20` | 21.4% (n=70) | 29.7% (n=74) |
| `prox<=0.30` | 24.7% (n=89) | 27.3% (n=55) |

Against a 25.7% baseline this decays **monotonically** toward the baseline as the band widens —
the "coherent across adjacent bands, not an effect that appears at one band and vanishes at its
neighbours" property the prereg demanded. That is suggestive of a real gradient rather than
band-shopping. **It is not evidence to act on.** Acting requires a NEW prereg naming win rate
as the primary metric, frozen before the next run.

---

## Validity gates

- **G1 control** — PASS. Published population total $4,808.75 across 191 trades; ours $3,219.80
  across 173 after 18 bar-coverage exclusions (8 dates past the cache end 2026-07-08, 10 lacking
  >=3 causal prior bars or a >=0.25pt range). Difference is exactly the excluded trades.
- **G2 patch binds** — PASS, both directions monotone non-decreasing: bull 14/19/21, bear
  44/70/89 as the band widens. The gate is not inert (C14).
- **G3 blocked-winner pricing** — PASS. Every cell carries blocked winners as its own column.
  *Anchor caveat:* the prereg's named anchors (2026-08-13 winner, 2026-08-14 loser) fall
  **outside** this population's window (ends 2026-07-22) and are therefore **not** evaluated
  here. That half of G3 is UNMET and is carried into the shadow counter below.
- **G4 NOT-RUN honesty** — PASS. 18 of 22 cells report NOT-RUN rather than a null result.
- **G5 read-only** — PASS. Nothing armed, no params touched.

---

## Limits a reader must carry forward

1. **Population is TAKEN trades only.** This can reallocate trades we made; it cannot discover
   one we skipped. A "gate that improves the book" is a filter that removes a cohort.
2. **Tier mix does not match today's live engine.** This population is TRENDLINE 124 / SUPER 37
   / LEVEL 19 / ELITE 11; the live fleet logs ELITE on 903/903 rows. Transfer is not assumed.
3. **Bull n is the binding constraint,** and it is a *data* problem, not an analysis problem —
   no cleverness fixes n=29.

## What happens next

The bull question cannot be answered with existing data, so **measure forward**: a shadow
counter records the location features on every live entry, both directions, and accumulates
until the bull cells clear n>=30. That is the only honest path from here, and it also closes
the unmet half of G3 (the 08-13/08-14 anchors get scored the moment they are in-population).


---

## ANCHOR RESULT (added after the shadow counter closed G3's unmet half)

The prereg's named anchors fall outside the replay window, so they were scored separately via
`setup/scripts/entry_location_shadow.py` using the SAME imported feature function.

| day | entry | dist from extreme | range so far | outcome | blocked by `prox<=0.10`? |
|---|---|---|---|---|---|
| 2026-08-13 | 09:51 C | **0.027** | 2.74 pt | **+$1,985 (the winner)** | **YES** |
| 2026-08-13 | 10:27 C | 0.044 | 5.01 pt | −$90 | YES |
| 2026-08-13 | 11:41 C | 0.674 | 5.18 pt | −$410 | no |
| 2026-08-13 | 14:36 C | 0.407 | 5.18 pt | +$532 | no |
| 2026-08-14 | 09:46 C | 0.141 | **0.81 pt** | **−$1,198 (the loser)** | **NO** |
| 2026-08-14 | 12:56 P | 0.034 | 2.95 pt | −$250 | YES |

**THE HYPOTHESIS IS REFUTED ON THE BULL SIDE BY ITS OWN ANCHORS.** The tightest proximity gate
would have **blocked the +$1,985 winner** and **allowed the −$1,198 loser**. The 11:41 loser sat
mid-range (0.674) and no band touches it. Buying near the intraday high was the WINNING
behaviour on 08-13 and the losing behaviour on 08-14 — **location does not separate them.**

This is the C20 warning arriving in the sharpest possible form, and it settles the intuition
behind J's question ("why did we buy calls if we ran up all day yesterday?"). The intuition is
reasonable and the data does not support it: proximity-to-high is not what went wrong.

### What the anchors DO separate on — a hypothesis GENERATED here, not tested here

`range_pts` (the day's established range at entry):

- 08-13 09:51 **winner**: **2.74 pt** already established
- 08-14 09:46 **loser**: **0.81 pt** — dead chop, 16 minutes into the session

Every 08-13 entry had >= 2.74 pt of range; the 08-14 morning had 0.81. That is handoff item
**N4 (range/chop context)** appearing unprompted in the anchor data.

**It is NOT tested here and must not be acted on.** It was generated by looking at two days,
which is the definition of a post-hoc pattern. It needs its own frozen prereg before any run —
see `prereg-entry-range-context-2026-08-15.json`. The shadow counter already records
`range_pts` on every entry, so the population accumulates from today either way.
