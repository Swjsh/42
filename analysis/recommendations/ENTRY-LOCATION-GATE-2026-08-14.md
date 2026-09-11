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
`prereg-entry-range-context-2026-08-14.json`. The shadow counter already records
`range_pts` on every entry, so the population accumulates from today either way.

**RESULT (2026-08-14, after that prereg was frozen and run):** NOT-RUN, all 16 cells — and the
BULL side, which generated the hypothesis, runs OPPOSITE to it. See
[`ENTRY-RANGE-CONTEXT-2026-08-14.md`](ENTRY-RANGE-CONTEXT-2026-08-14.md).

---

## UPDATE 2026-09-11 (fold, OP-22) — the BULL population that made this NOT-RUN is now n=133

**Trigger:** 3 consecutive red days (09-08 −$116, 09-10 −$790, 09-11 −$619; 09-09 had no
options fills). J: "what are we gonna do about it to learn and make money."

### What the 3 red days actually share — follow-through, not regime

Per-entry SPY excursion, 60-minute horizon from entry (fav = in the trade's direction),
measured off Alpaca 5m RTH bars 2026-08-18..2026-09-11, joined to real fills:

| | n | median FAV | median ADV | % entries ≥$0.80 FAV | % ≥$1.20 |
|---|---|---|---|---|---|
| GREEN days | 100 | **$1.16** | $0.60 | **61%** | 47% |
| RED days | 63 | **$0.43** | $0.88 | **17%** | 11% |

On red days the tape simply does not follow through after our entry. This is the cleanest
separator found; it is a *description* of the loss, and the search for a **predictive** version
of it is where the three kills below happened.

### THREE CANDIDATE FIXES TESTED AND KILLED THIS SESSION

1. **Morning chop/efficiency gate — KILLED.** Efficiency ratio over 09:30–11:00
   (|net| / path, 5m closes) does not separate: GREEN median **0.211** vs RED **0.193**
   (n=16 traded days). A morning-price-action stand-down filter has no signal here.
2. **Loosen the structure stop — KILLED (this was my first hypothesis; the data refused it).**
   Replay of today's 5 entry events against their actual `trigger_level_exact`: base rule
   (1 closed 5m bar beyond level) captured **−2.31** SPY total; 2-consecutive-close
   confirmation **−2.01**; a $0.25 buffer **−3.59** (worse). Widening does not rescue the day
   because SPY was *lower than the entry price* 9–99 min after **all five** entries.
3. **Entry-gap (spot−level) day-level gate — KILLED.** Median gap by day vs day P&L over 23
   traded days: GREEN 0.267 vs RED 0.202 — and broken outright by 2026-07-29 (gap 0.13,
   **+$1,341**) and 2026-08-13 (gap 0.09, **+$1,748**). Consistent with C20 / L102 / L219.

### What today's tape says the problem actually is — entry LOCATION

All 5 bull entries fired with spot within pennies of the reclaimed level, into a **$2.72**
RTH range, and SPY finished below every one of them:

| entry ET | spot | `trigger_level_exact` | gap | fills P&L |
|---|---|---|---|---|
| 10:01 | 766.27 | 765.48 | 0.79 | −$417 |
| 10:51 | 764.73 | 764.63 | **0.10** | −$374 |
| 13:06 | 765.64 | 765.48 | 0.16 | +$175 |
| 13:26 | 766.17 | 766.08 | **0.09** | −$32 |
| 13:51 | 765.90 | 765.78 | **0.12** | −$21 |

Mechanism, one sentence: **`BULLISH_RECLAIM_RIDE_THE_RIBBON` fires the moment price crosses
back above the level, so by construction spot ≈ level, and the v15.3 structure stop
(`exit_manager.py:140` — first CLOSED 5m bar beyond `trigger_level`) then sits inside a single
bar's noise** — today's 5m bars averaged ~$0.30 range against a $0.09–$0.12 stop. The 5 fills
all exited at +5:00 to +5:01 across four arms simultaneously, which is the expected signature:
`trigger_level` comes from the SHARED producer (`build_shared_signal.py`), so **all arms exit
on the same bar close regardless of their risk profile — on the exit side the 4-arm fleet is
~1 sample, not 4.** That materially thins the evidence base behind the go-live gate.

Kill #2 above means the answer is NOT to widen that stop. The live question is whether the
engine should be buying the reclaim *extension* at all, versus J's own stated structure
(zones + wait-for-return): today J's rising support ray `q6rYVR` sat at ~765.0 and was touched
five consecutive 5m bars 14:30–14:55, while every engine entry was ~$1 ABOVE it.

### THE ACTIONABLE FINDING: this doc's own bull-side test is no longer blocked

The 2026-08-14 verdict above records the bull side as **NOT-RUN, n=29**, below the
pre-registered n≥30 floor — i.e. *"the question J actually asked — why did we buy calls at the
top? — cannot be answered by this population."* **That is no longer true.**

Distinct bull entry EVENTS (date + entry minute + strike, real fills) since the
`engine-fullhist-replay-2026-07-23` population cutoff: **133**, across 22 trading days
2026-07-28 → 2026-09-11 (279 raw fill rows across arms). That is **4.4× the n≥30 floor**.

**Next action (filed as `BULL-ENTRY-LOCATION-RERUN-2026-09-11` in `automation/overnight/queue.md`):**
re-run `backtest/autoresearch/entry_location_gate_2026_08_14.py` against the extended
population under the SAME frozen prereg (`prereg-entry-location-gate-2026-08-14.json`) — same
cells, same BH-FDR q=0.10, same blocked-winner accounting. No new hypothesis, no new knob: the
test was already designed and frozen; it was only ever starved of n. Report ALL cells per
prereg. This is measurement only and is freeze-compatible; any resulting gate is a prereg for
the 2026-10-30 window, NOT a September change.

**Caveat on this update:** excursion and replay numbers are SPY-dollar terms off 5m bars, not
option P&L — the 13:06 cell made +$175 in premium while SPY closed −$0.30 from entry (intrabar
TP1). SPY terms are the right unit for *entry location*; they are not a P&L claim.

---

## UPDATE 2026-09-11 (part 2, fold, OP-22) — BULL-ENTRY-LOCATION-RERUN executed: MEASURED for the first time, NULL after BH-FDR

Ran `backtest/autoresearch/entry_location_gate_rerun_2026_09_11.py` (new driver; imports
`build_cells`, `gated`, `evaluate`, `bh_fdr`, `PROX_BANDS`, `RUN_BANDS`, `MIN_CELL_N` etc.
verbatim from the frozen `entry_location_gate_2026_08_14.py` — no cell, threshold, FDR, or
blocked-winner logic changed) against an EXTENDED population.

**Discrepancy flagged before results (honesty bar, not a blocker):** this prereg
(`prereg-entry-location-gate-2026-08-14.json`) already carries `"status": "NULL"` /
`"adjudicated_at_et": "2026-09-05 00:38 ET"` from the P4+P5 batch adjudication pass — but that
adjudication's own text says the LITERAL cells "were never run at floor-n (still NOT-RUN by the
prereg's own n>=30 rule)" and closed the prereg using a DIFFERENT, superseding study instead
(`analysis/deep-research/2026-09-03-money/entry-location.md`, chase-at-range-extreme, n=186).
This run is not reopening a closed prereg against doctrine — it fills in the one thing that
adjudication explicitly left undone (the literal frozen cells, never actually run on bull data),
and its result agrees with that adjudication's NULL conclusion. The prereg JSON was NOT modified.

### Population build

- Original 191-trade replay (`engine-fullhist-replay-2026-07-23.json`, 2025-01-02..2026-07-21)
  concatenated with real fills 2026-07-28..2026-09-11: `journal/trades.csv` (`fill_quality ==
  real_fill`) plus `automation/state/pnl-statement.json` `round_trips` for 2026-09-11 (today,
  not yet backfilled into trades.csv). Deduped to distinct entry EVENTS by (date, entry minute,
  strike): **133 distinct bull events** — matches this doc's own 2026-09-11 (part 1) claim
  exactly. 84 new put events also added (not previously blocked, but now larger-n).
- Bars: pinned `backtest/data/spy_5m_2025-01-01_2026-07-08.csv` (untouched) merged with a NEW
  `backtest/data/spy_5m_2026-07-09_2026-09-11_extension.csv`, fetched fresh via
  `backtest/tools/alpaca_bars.py` (SIP feed, already-wired credentials, no new vendor).

### Root cause found and fixed before results were trustworthy

First pass at the extended population returned population n=205 with bull n=**44** only — most
of the new data silently vanished. Root cause, one sentence: the frozen `features()` requires
the entry timestamp to land EXACTLY on a 5-minute bar boundary, which is true by construction
for the backtest-replay population (verified: 100% of the original 191 entries are grid-aligned)
but NOT true for real fills from the live 1-minute heartbeat — 191 of 217 new events (88%,
verified by direct count) land on an off-grid minute (e.g. 10:51, 13:06, 13:26) and were
excluded as `"no_causal_features"`, not because the data was causally unavailable but because of
a grid-alignment mismatch between two different data sources. Fixed with `features_floor()` in
the new driver: the IDENTICAL causal rule (bars strictly before the entry bar; entry price =
entry bar's open) applied to the 5m bar whose interval CONTAINS the entry timestamp instead of
requiring exact equality — no cell, threshold, or FDR/blocked-winner accounting touched. After
the fix: population n=388 (C=153, P=235), 20 total exclusions (down from 223 pre-fix + orig).

**G1 control: PASS, exactly.** The original 191-trade population's own subtotal reconciles to
the cent on the extended bars: kept 181/191 trades summing $3,727.60, excluded 10 summing
$1,081.15 — 3,727.60 + 1,081.15 = **$4,808.75**, the published total. (The extension also
resolved 8 of the original doc's 18 "past cache end" exclusions; only the 10 "lacking causal
bars" ones remain, exactly as this doc's original G1 note described.) **G2 monotonicity: PASS**
both sides (gated-n grows non-decreasing with band width).

### Bull (C) — MEASURED for the first time. n=153, mean $28.01, WR 32.7%

| cell | n_gated | gated mean | kept mean | p | survives BH-FDR q0.10 | book_delta if gated | blocked winners |
|---|---|---|---|---|---|---|---|
| `prox<=0.10` | 61 | +$100.50 | −$20.05 | 0.0497 | NO | −$6,130.55 | 23 ($11,528.55) |
| `prox<=0.20` | 77 | +$59.41 | −$3.79 | 0.302 | NO | −$4,574.45 | 27 ($12,137.45) |
| `prox<=0.30` | 90 | +$32.74 | +$21.26 | 0.851 | NO | −$2,946.65 | 32 ($13,100.65) |
| `run>=2.0` | 58 | +$74.90 | −$0.61 | 0.222 | NO | −$4,344.10 | 21 ($10,896.10) |
| `run>=3.0` | 30 | +$109.17 | +$8.22 | 0.184 | NO | −$3,275.10 | 11 ($6,312.10) |
| `prox<=0.20 AND run>=2.0` | 30 | +$181.80 | −$9.49 | **0.0112** | NO | −$5,453.90 | 14 ($7,597.90) |
| `prox<=0.30 AND run>=2.0` | 37 | +$103.14 | +$4.05 | 0.159 | NO | −$3,816.10 | 16 ($8,159.10) |
| `prox<=0.10 AND run>=2.0` (26) / `run>=3.0` (18); `prox<=0.20 AND run>=3.0` (19); `prox<=0.30 AND run>=3.0` (23) | — | — | — | — | — | — | **NOT-RUN** (n<30) |

**Every measured bull cell runs OPPOSITE to the hypothesis** — gated_mean > kept_mean in all 7
measured cells. Buying calls close to the intraday high, and/or after a big up day, made MORE
money than the rest of the bull population, not less. The closest-to-significant cell
(`prox<=0.20 AND run>=2.0`, p=0.0112 — the smallest p in the whole 14-cell family) would, if
gated, have thrown away **$5,453.90** of net book value. **Nothing survives BH-FDR q=0.10**
(m=14; smallest p=0.0112 needed ≤ (1/14)×0.10=0.00714 at rank 1 — it does not clear it).

### Bear (P) — re-measured on the extended population, same shape as 2026-08-14

n=235, mean $5.89, WR 28.5%. `prox<=0.10` gated mean −$43.24 vs kept +$26.31, p=0.0335 (needs
≤0.00714, fails). All other cells weaker. Nothing survives, consistent with the original run.

### What this settles

1. **The bull-side blocker from 2026-08-14 (NOT-RUN, n=29) is closed.** The literal frozen
   cells are MEASURED for the first time on bull data, at n=153 (5.3× the n≥30 floor).
2. **The naive proximity/run gate does not survive its own pre-registered correction on either
   side**, at roughly 2× the original data volume — the SECOND independent confirmation of
   NULL (the first being the 2026-09-05 adjudication's superseding chase-at-range-extreme
   study), and the first to run the literal frozen cells rather than a proxy operationalization.
3. **This does not explain the 3 red days.** The 2026-09-08/09-10/09-11 bull entries sat at
   gaps of 0.09–0.79 — squarely inside cells that this run says would have been *profitable to
   keep*, not gate. Whatever caused the 3 red days, "entered too close to the high" is refuted
   by the data a second time. The live mechanism remains the ribbon-flip/structure-stop
   interaction described in the 2026-09-11 (part 1) update above, not entry location.

### Files written this run

- `backtest/data/spy_5m_2026-07-09_2026-09-11_extension.csv` (new; pinned CSV untouched)
- `backtest/autoresearch/entry_location_gate_rerun_2026_09_11.py` (new driver)
- `analysis/recommendations/entry-location-gate-2026-09-11.json` (raw output)
- this section (OP-22 append, no new dated file)

Nothing armed. Config freeze (to 2026-10-30) untouched — this is measurement only, filed as a
prereg result for the 10-30 window per the original ship_rule.

---

## FOLLOWTHROUGH-HEADROOM-2026-09-11 (separate prereg, folded here as its nearest living doc)

Prereg: `analysis/recommendations/prereg-followthrough-headroom-2026-09-11.json`, frozen and
committed (`dbe35ce7`) **before** `backtest/autoresearch/followthrough_headroom_2026_09_11.py`
existed. Question: does a CAUSAL feature at entry predict FAV60 follow-through? Primary
hypothesis: HEADROOM — distance to the nearest OPPOSING level (the obstacle ahead), explicitly
declared **not** a repeat of this doc's own prox/run study (which measured distance to the
extreme *behind* the entry — opposite geometry).

### The hard part, resolved before computing anything

F1/F2 need the level set as it stood *before* each entry. Three candidate sources were checked:

| source | verdict |
|---|---|
| `automation/state/core-decisions.jsonl` `levels_active` (live production, per-tick, real-time) | **USED** — the only genuine as-of log found. First non-empty row `2026-07-28T09:30:05`; key absent entirely before `2026-07-27T22:45:52` (checked directly, not inferred). |
| `analysis/swarm-benchmark/replay-*/key-levels.json` | **REJECTED** — self-labelled `"replay_mode": true`, `protocol_version: "...(replay-mode algorithmic)"`. An algorithmic recomputation for a benchmark tool, not the level state that was actually live. Using it would be exactly the undeclared proxy the prereg forbids. |
| `journal/*.md` dailies | **REJECTED** — earliest file `2026-04-29`, and no structured programmatic level list even where present. |

**Consequence, stated up front:** F1/F2 can only be computed for entries dated **>= 2026-07-28**.
The original 191-trade replay population (2025-01-06..2026-07-21) is excluded from F1/F2
*entirely* — a window-wide absence of any historical level log, not a per-entry gap. F3/F4/F5
need no level state and ran over the full 388-row population (same population as this doc's own
2026-09-11 extension update, same `features_floor()` causal-alignment helper, reused verbatim —
not rebuilt).

### Result: population n=388 (C=153 / P=235), 24-cell closed family

Exclusions: `no_causal_features`=20 (bar-coverage, identical mechanism to this doc's earlier
update), `headroom_predates_2026_07_28`=181, `headroom_no_levels_row`=3 (date has coverage but
no logged tick before that specific entry minute), `headroom_no_opposing_level`=15 (entry sat
beyond every logged level on that side — no resistance/support left in the active set).

11 of 24 cells reached n_gated>=30 AND n_kept>=30 (MIN_CELL_N both sides, no band pooling); 13
NOT-RUN. BH-FDR q=0.10 run across the full 11-cell measured family via
`backtest/lib/canonical_battery.py`'s `bh_fdr`/`one_sample_p` (not reimplemented).

| cell | n_g / n_k | $gated | $kept | p | required (BH rank) | FAV60 agree? | G3 blocked-winner | counts |
|---|---|---|---|---|---|---|---|---|
| C `F1_headroom_abs<=0.25` | 41/66 | +47.10 | −25.80 | 0.130 | 0.027 | NO | $4,966 blocked-winner | NO |
| P `F1_headroom_abs<=0.25` | 40/42 | +6.33 | −31.52 | 0.311 | 0.055 | NO | $2,659 blocked-winner | NO |
| C `F1_headroom_abs<=0.5` | 60/47 | +26.27 | −28.68 | 0.149 | 0.036 | NO | $6,252 blocked-winner | NO |
| C `F2_headroom_atr<=0.5` | 30/36 | +35.67 | −6.42 | 0.501 | 0.073 | yes | $3,823 blocked-winner | NO |
| P `F3_er_prior30<=0.15` | 42/162 | +8.02 | +13.23 | 0.865 | 0.100 | yes | $2,866 blocked-winner | NO |
| C `F3_er_prior30<=0.3` | 30/75 | +57.84 | +17.65 | 0.601 | 0.091 | yes | $5,376 blocked-winner | NO |
| P `F3_er_prior30<=0.3` | 84/120 | +20.25 | +6.49 | 0.580 | 0.082 | NO | $6,932 blocked-winner | NO |
| C `F5_range_used>=0.7` | 61/90 | +132.92 | −38.92 | **0.00184** | 0.00909 | yes | $12,097 vs $3,989 avoided | **NO — G3 refuted** |
| P `F5_range_used>=0.7` | 119/108 | +11.38 | −7.65 | 0.412 | 0.064 | yes | $11,705 blocked-winner | NO |
| C `F5_range_used>=0.9` | 33/118 | +135.06 | +1.26 | 0.120 | 0.018 | yes | $6,710 blocked-winner | NO |
| P `F5_range_used>=0.9` | 83/144 | +27.08 | −11.94 | 0.175 | 0.045 | yes | $9,100 blocked-winner | NO |

`F4_atr_prior12` (dead-tape gate, <=$0.20/$0.30 over the prior 12 5m bars) never reaches
MIN_CELL_N on either side (max n_gated=14/388) — real-fill entries essentially never occur in
that low-ATR band. NOT-RUN on all 4 cells, not a null on the hypothesis itself.

### Verdict: NULL. Zero survivors. Kill condition 1 (headroom) TRIGGERED.

**HEADROOM is DEAD as pre-registered.** All 4 measured F1/F2 cells fail BH-FDR by a wide
margin (best p=0.130 against a required 0.027-0.073) — logging this as a null per the prereg's
own instruction, not softened, not re-swept at new bands. Where headroom is measurable at all
(2026-07-28 onward only), tight headroom did **not** predict worse follow-through; if anything
the sign runs the other way (gated_mean > kept_mean in 3 of 4 F1/F2 cells) — the same
"engine's own entry selection already screens this" shape this doc's bull prox/run study found
in August, on a different feature. Kill condition 2 (every cell's gated_mean > kept_mean,
book-wide) does **not** trigger — F3 `P<=0.15` runs the hypothesized direction (gated worse) —
so the global "losses are elsewhere" statement cannot be made from this study alone, only the
narrower headroom-specific version above.

One cell, `C F5_range_used>=0.7`, is BH-FDR significant (p=0.00184, comfortably inside its
0.00909 threshold) and passes G_drop3 (sign preserved after dropping the 3 largest-|pnl|
trades) and G_oos (IS +159.22 vs kept, OOS +184.05 vs kept — same sign, chronological median
split). **It is still not a survivor**: G3's blocked-winner rule refutes it —
$12,097 of blocked-winner dollars against only $3,989 of avoided-loser dollars if this cohort
were gated. Framed plainly: entries occurring after the day's range was already ≥70% spent
performed *better*, not worse, which is the opposite of what a "day's range spent = dead tape,
gate it" veto assumes — so the correct action on this evidence is "do not gate here," not
"gate here." Flagging as a directionally-interesting observation for a possible *separate*,
freshly-preregistered study (requiring rather than excluding this state) — not actionable
under this prereg's closed cell family, and no new threshold was added or swept per that
constraint.

### Files written

- `backtest/autoresearch/followthrough_headroom_2026_09_11.py` (new runner)
- `analysis/recommendations/followthrough-headroom-2026-09-11.json` (raw, all 24 cells)
- this section (OP-22 append — no new dated one-off markdown)

Nothing armed. Config freeze (to 2026-10-30) untouched — measurement only, exactly as the
prereg's `freeze_compliance` block requires. `automation/overnight/queue.md` and
`analysis/deep-research/` not touched (owned by the concurrent ARM-EXIT-DEGENERACY session).
