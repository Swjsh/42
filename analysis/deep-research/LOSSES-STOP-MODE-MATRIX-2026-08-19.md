# LOSSES — STOP-MODE FULL MATRIX (2026-08-19)

**Lane:** smaller losses. **Lever:** stop mode — premium vs structure/chart vs time vs ATR vs
trailing vs SPY-move. **Dataset:** [`analysis/recommendations/trade-matrix.json`](../recommendations/trade-matrix.json)
— all 303 closed round trips, 5 arms, 2026-06-26..2026-08-19.
**Scope: ANALYSIS ONLY.** Nothing armed, no `params*.json` touched, no order placed.

Machine-readable companions: [`LOSSES-STOP-MODE-MATRIX-2026-08-19.json`](LOSSES-STOP-MODE-MATRIX-2026-08-19.json)
(every cell) · [`LOSSES-STOP-MODE-SCREEN-2026-08-19.json`](LOSSES-STOP-MODE-SCREEN-2026-08-19.json)
(gate screen) · [`LOSSES-STOP-MODE-HUNT-2026-08-19.json`](LOSSES-STOP-MODE-HUNT-2026-08-19.json)
(artifact hunt). Builders: `backtest/tools/stop_mode_matrix_2026_08_19.py`,
`..._report_...py`, `..._screen_...py`, `..._artifact_hunt_...py`.

---

## VERDICT — three sentences

> ### 1. The stop **MODE** axis does not separate. **Zero of 34 cells** pass all six honesty gates; the ranking completely reshuffles when you change the upside rule or the population, so no mode is "the" answer.
> ### 2. **One fact is unanimous: having a stop beats not having one — 34/34 cells beat NO_STOP under both upside shapes, on both populations.** That is the whole robust content of this lane.
> ### 3. 🚨 The pre-registered stop-mode clock's interim **has already flipped sign** and the brief's cited `+$1,809` is **stale**. Current reading: **−$264.70**, reversed by a single day (2026-08-17, −$2,073.30 = **49.8%** of the clock's own summed |per-day delta|).

**Best cell:** `TRAIL_25` — a 25% give-back trailing stop from the high-water mark, seeded at
entry. **Verdict on it: WEAK, do not ship.** Reasons in [§6](#6-the-best-cell-and-why-it-is-only-weak).

---

## 1. What production runs today, and what it actually did

| | |
|---|---|
| **Production cell** | STRUCTURE-primary — 5m SPY close through the entry trigger level, side-aware — plus a **−50% premium catastrophe cap** |
| Provenance | [`automation/state/params.json`](../../automation/state/params.json) `structure_stop_enabled=True` (SS-B chart-stop-primary, STOP-B 2026-07-09); `premium_stop_pct` / `premium_stop_pct_bear` = `-0.50` (chart-stop-primary, 2026-06-18) |
| **Realized, 303 trips** | **−$1,805 gross · −$1,939.90 after real fees · −$3,486.96 after fees + measured exit slippage** |
| Realized WR | 23.1% by trade · 12 of 35 days positive |

**What actually closed the book** (real exit stages, not simulation):

| exit stage | n | gross |
|---|---:|---:|
| `tp1` | 44 | **+$14,514** |
| `ribbon_flip` | 31 | +$273 |
| `time_stop` | 2 | $0 |
| *(no logged reason)* | 5 | −$504 |
| `structure_stop` | 67 | −$5,998 |
| `premium_stop` | 154 | **−$10,090** |

Every positive dollar in this book comes from 44 TP1s. Stops of both kinds subtract $16,088.
That is the shape of a right-tail book, and it frames everything below.

---

## 2. Why the matrix had to be rebuilt (and what that cost)

`trade-matrix.json`'s `path` field is the **held window only** — entry minute to realized exit
minute (verified: exit is within 1 minute of `path_last_bar_et` on 302/303 rows). It can test a
*tighter* stop and **cannot test a wider one**: there are no bars after the realized exit.

So this study re-reads the **full-day 1-minute OPRA cache** (`backtest/data/opra_1m_cache/`,
09:30→~16:14 ET; **all 109 contract-days present, zero fetches, zero gaps**) and walks each
position forward to the 15:40 ET hard time stop.

**No look-ahead (C6).** The entry **bar** is excluded from every decision. Every stop level is
decidable at entry: a fixed % of entry premium; an ATR computed from **pre-entry** option bars
only; a clock; a trail seeded at entry; or the SPY trigger level recorded on the decision row
that produced the order.

> **A look-ahead bug was found and fixed mid-study.** The SPY-move cell originally read the
> *currently forming* 5-minute SPY bar, whose high/low contain prints up to five minutes in the
> future. Every SPY-move number below uses **closed bars only** (cost: the SPY stop lags up to
> 5 minutes — disclosed, not hidden).

**The upside rule is held constant across every cell** so the downside is the only moving part,
and it is run under **two** shapes: `RIBBON` (tp1 +100%/0.667, chandelier arm +5% trail 15% —
the shape the pre-registered clock uses) and `SAFE` (tp1 +50%/0.8, trail 12.5% — `params.json`).
A cell that wins under one and loses under the other is fragile and is called fragile.

### Two things that could not be computed, stated not defaulted

| | n excluded | why |
|---|---:|---|
| ATR cells | 14 of 303 | fewer than 15 pre-entry 1-min option bars (open-bell entries). Never defaulted to zero. |
| STRUCTURE cells | 120 of 303 | the decision row carries **no `trigger_level`**. |

`trigger_level` turns out to be an **era marker, not a signal property**:

| slice | n | date span | realized gross | WR |
|---|---:|---|---:|---:|
| has `trigger_level` (**STRUCTABLE**) | 183 | 2026-07-13..08-19 | **+$736** | 30.1% |
| no `trigger_level` | 120 | 2026-06-26..08-12 | **−$2,541** | 12.5% |

So STRUCTABLE ≈ **the recent era** and is *not* representative of the book. Every result below
is reported on **both** populations, and no cell is ever scored against a population where it is
only partly computable.

### 🚨 Harness fidelity — the number that disqualifies my own STRUCTURE cell

| population · shape | realized gross | simulated STRUCTURE+cap50 | gap |
|---|---:|---:|---:|
| STRUCTABLE · RIBBON | +$736 | **−$4,668.55** | **−$5,404.55** |
| STRUCTABLE · SAFE | +$736 | −$1,337.41 | −$2,073.41 |

My structure stop is a **re-implementation, not a replay** — it misses the traded book by
thousands of dollars on the identical rows. **It is therefore never used as the delta baseline**,
because doing so would credit every alternative cell with my own re-implementation's error.
**This harness cannot adjudicate structure-vs-premium.** The live-fills evidence in [§5](#5-the-pre-registered-clock-contradicted-and-corroborated) can.

Two reference points are used instead, and never blended:
* **REALIZED** — the book as traded. Ground truth, external.
* **NO_STOP** — same harness, same upside rule, zero downside management. **Delta vs NO_STOP is
  the pure stop-lever effect**, free of the harness's upside-rule difference.

---

## 3. THE FULL MATRIX (FULL population, n=303, `RIBBON` shape)

Gross and net-after-fees-and-measured-slippage. `winner$` / `loser$` are the two halves the net
is a difference of — **the column the trap lives in.**

| cell | gross | net f+s | WR | avg loss | worst loss | **winner $** | loser $ | max DD | stop-fill % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **— PREMIUM —** | | | | | | | | | |
| PREMIUM_10 | −4,645 | −6,327 | 6.6% | **−42** | **−205** | 7,269 | −11,914 | −6,371 | 93.4% |
| PREMIUM_15 | −2,365 | −4,047 | 10.6% | −58 | −282 | 13,443 | −15,808 | −7,261 | 89.4% |
| **PREMIUM_20** | **+274** | −1,408 | 14.2% | −75 | −376 | 19,752 | −19,478 | −9,332 | 85.8% |
| PREMIUM_25 | −77 | −1,759 | 17.2% | −94 | −470 | 23,451 | −23,527 | −12,412 | 82.8% |
| PREMIUM_30 | −1,622 | −3,304 | 19.5% | −113 | −564 | 25,834 | −27,456 | −15,747 | 80.5% |
| PREMIUM_40 | −879 | −2,562 | 26.7% | −152 | −752 | 32,781 | −33,660 | −17,885 | 73.3% |
| PREMIUM_50 *(prod cap)* | −2,717 | −4,399 | 31.0% | −189 | −940 | 36,857 | −39,574 | −18,634 | 67.3% |
| PREMIUM_60 | −8,694 | −10,377 | 32.3% | −227 | −1,128 | 37,906 | −46,600 | −23,159 | 62.7% |
| PREMIUM_75 | −10,499 | −12,181 | 36.3% | −273 | −1,410 | 42,131 | −52,630 | −23,897 | 51.2% |
| **NO_STOP** *(reference)* | **−13,169** | −14,852 | 40.3% | −318 | −1,872 | 44,468 | −57,637 | −28,104 | 0% |
| **— TRAIL (give-back from HWM) —** | | | | | | | | | |
| TRAIL_10 | −3,883 | −5,564 | 28.4% | −35 | −205 | 3,644 | −7,527 | −4,130 | 100% |
| TRAIL_15 | −1,622 | −3,304 | 29.7% | −47 | −251 | 8,133 | −9,755 | −3,641 | 98.7% |
| TRAIL_20 | −465 | −2,147 | 30.0% | −56 | −334 | 11,241 | −11,706 | −5,113 | 95.4% |
| **TRAIL_25** | **+6,257** | **+4,575** | 29.0% | −64 | −418 | 19,985 | −13,727 | −6,431 | 89.4% |
| TRAIL_30 | +6,636 | +4,954 | 27.4% | −77 | −511 | 23,558 | −16,923 | −8,036 | 86.1% |
| TRAIL_40 | +1,393 | −289 | 24.1% | −107 | −698 | 25,787 | −24,394 | −13,674 | 81.8% |
| **— TIME (pure clock) —** | | | | | | | | | |
| TIME_5m | +838 | −844 | 43.6% | −54 | −520 | 9,264 | −8,426 | −2,609 | 0% |
| TIME_10m | −666 | −2,348 | 36.6% | −70 | −544 | 11,915 | −12,581 | −5,098 | 0% |
| TIME_15m | −554 | −2,237 | 38.0% | −94 | −656 | 16,185 | −16,739 | −6,934 | 0% |
| TIME_20m | +1,852 | +170 | 39.3% | −114 | −768 | 22,642 | −20,790 | −9,292 | 0% |
| TIME_30m | −3,526 | −5,208 | 36.0% | −140 | −976 | 23,195 | −26,721 | −13,334 | 0% |
| TIME_45m | −6,953 | −8,635 | 34.3% | −165 | −1,216 | 25,627 | −32,580 | −15,171 | 0% |
| TIME_60m | −9,833 | −11,515 | 33.3% | −191 | −1,392 | 28,497 | −38,330 | −18,363 | 0% |
| TIME_90m | −7,457 | −9,139 | 38.0% | −226 | −1,656 | 34,971 | −42,428 | −20,413 | 0% |
| **— ATR (pre-entry option ATR14) —** *n=289* | | | | | | | | | |
| ATR_1x | −5,880 | −7,489 | 8.0% | −52 | −240 | 7,974 | −13,853 | −7,058 | 92.0% |
| ATR_1.5x | −4,413 | −6,022 | 14.2% | −76 | −360 | 14,333 | −18,746 | −8,463 | 84.8% |
| ATR_2x | −3,950 | −5,559 | 17.6% | −99 | −480 | 19,618 | −23,568 | −11,298 | 79.6% |
| ATR_3x | −4,832 | −6,441 | 25.6% | −149 | −720 | 27,249 | −32,080 | −16,424 | 71.3% |
| ATR_4x | −619 | −2,228 | 32.9% | −197 | −960 | 37,512 | −38,131 | −16,694 | 59.9% |
| **— SPY-MOVE (underlying chart stop, closed 5m bars) —** | | | | | | | | | |
| SPYMOVE_$0.40 | +1,822 | +140 | 32.0% | −63 | −560 | 14,378 | −12,556 | −6,970 | 85.1% |
| SPYMOVE_$0.60 | **+6,895** | +5,213 | 32.0% | −91 | −560 | 25,549 | −18,654 | −9,014 | 73.3% |
| SPYMOVE_$0.80 | +4,808 | +3,126 | 32.0% | −119 | −616 | 29,011 | −24,203 | −11,571 | 63.0% |
| SPYMOVE_$1.00 | −478 | −2,161 | 32.0% | −159 | −770 | 32,304 | −32,782 | −14,417 | 56.8% |
| SPYMOVE_$1.50 | +2,280 | +598 | 36.3% | −203 | −976 | 41,431 | −39,151 | −14,568 | 38.6% |
| SPYMOVE_$2.00 | −4,982 | −6,664 | 37.0% | −245 | −1,128 | 41,773 | −46,755 | −19,664 | 29.7% |
| **— STRUCTURE —** *n=183 only, and unfaithful — see §2* | | | | | | | | | |
| STRUCTURE+cap50 | −4,669 | −5,641 | 26.2% | −131 | −660 | 12,813 | −17,482 | −8,075 | — |
| STRUCTURE+cap75 | −4,440 | −5,412 | 28.4% | −142 | −560 | 13,819 | −18,259 | −8,549 | — |

*(The `SAFE`-shape twin of this whole table, plus the STRUCTABLE population, is in the JSON.)*

---

## 4. ⚠️ THE TRAP, MEASURED

**Winner dollars rise monotonically with stop width in every single family.** That is the trap
in one sentence: the stop does not choose between good and bad trades, it chooses **how much of
the right tail you are allowed to keep.**

Take the two extremes of the premium family:

| | PREMIUM_10 | PREMIUM_20 | Δ |
|---|---:|---:|---:|
| avg loss | **−$42** *(best in the entire matrix)* | −$75 | tighter is 44% "better" |
| worst loss | **−$205** *(best in the entire matrix)* | −$376 | tighter is 45% "better" |
| max drawdown | **−$6,371** | −$9,332 | tighter is 32% "better" |
| **winner dollars** | **$7,269** | $19,752 | tighter destroys **$12,483** |
| win rate | **6.6%** | 14.2% | tighter halves it |
| **net after costs** | **−$6,327** | **−$1,408** | tighter costs **$4,919** |

> **PREMIUM_10 wins every single loss statistic and is a $4,919 failure.** Per the lane's own
> rule: a cell that shrinks losses and shrinks net P&L is a **FAILURE**, and this one is the
> cleanest example in the dataset. The same shape holds in TRAIL (TRAIL_10 has the best avg loss
> at −$35 and destroys $16,341 of winner dollars vs TRAIL_25) and in ATR (ATR_1x: best avg loss
> −$52, worst net in the family).

### And the whole width axis is smaller than one day

Across the *reasonable* premium band (−15% to −50%) net ranges from −$2,717 to **+$274** — a
**$2,991** spread over 303 round trips. The book's single best day, 2026-08-04, was **+$3,624**.
**The entire stop-width axis is worth less than one day of this book's variance.** This
corroborates, on 35 days instead of 2, the conclusion already filed in
[`STOPPED-THEN-PAID-2026-08-04.md`](STOPPED-THEN-PAID-2026-08-04.md): *no single static width
survives both regimes.*

---

## 5. The pre-registered clock — CONTRADICTED and CORROBORATED

The clock is `STOP-MODE-STRUCTURE-VS-PREMIUM-2026-08-09`
([prereg](../recommendations/prereg-stop-mode-structure-vs-premium-2026-08-09.json) ·
[ledger](../recommendations/stop-mode-shadow-ledger.jsonl) ·
[summary](../recommendations/stop-mode-shadow-summary.json)).

### 🚨 The brief's cited interim is stale, and the sign has flipped

| snapshot | n trades | n days | span | **cum delta (premium − control)** |
|---|---:|---:|---|---:|
| 2026-08-16 13:10 *(the brief's `+$1,809`)* | 95 | 5 | 08-10..08-14 | **+$1,808.60** |
| **2026-08-19 16:30 (current on disk)** | **102** | **7** | **08-10..08-18** | **−$264.70** |

**One day did it.** The clock's own per-day deltas:

| day | delta |
|---|---:|
| 2026-08-10 | +119.2 |
| 2026-08-11 | +166.0 |
| 2026-08-12 | −139.6 |
| 2026-08-13 | +581.2 |
| 2026-08-14 | **+1,081.8** |
| **2026-08-17** | **−2,073.3** |
| 2026-08-18 | 0.0 |

**2026-08-17 alone is 49.8% of the summed |per-day delta|; the top two days are 75.8%.** An
effect carried by two days pointing in opposite directions is not an effect. The clock's own
mechanism gate — *"WR should FALL while total P&L RISES"* — reads
`mechanism_signature_holds: false` in **both** snapshots. The clock's own decision rule requires
`n_days >= 20`; it had 5.

**Both readings cannot be right, and neither was ever evidence.** The `+$1,809` was two good
days out of five; the next trading day erased it. Nothing about the mechanism changed — the
sample did.

### Independent corroboration: the observed live split, date-paired, zero simulation

`stop_mode` is recorded on the decision row, so the book contains a *real* A/B: 143 trades ran
`structure`, 76 ran `premium`, and the two modes **overlap on 17 dates**. Pairing by date
removes the era/regime confound (arm mix remains, disclosed):

| | n | total | **expectancy/trade** |
|---|---:|---:|---:|
| `structure` | 127 | +$569 | **+$4.48** |
| `premium` | 68 | −$1,673 | **−$24.60** |
| **premium − structure** | | | **−$29.08 / trade** |

Premium was the better mode on **7 of 17 days**; top day = 24.9% of the summed |delta|.

**Verdict: I contradict the brief's cited interim and corroborate the clock's current reading.**
Premium stops are **not** ahead. The mechanism of the original claim was never the mechanism —
it was two days of sample. My own simulated STRUCTURE cell agrees with the *stale* direction
(premium +$4,815 on STRUCTABLE/RIBBON), and that is precisely why **I discard my own cell**: it
misses the traded book by −$5,405 on those same rows (§2), so its "premium wins" is my
re-implementation's error, not a finding. **The live-fills split is the better evidence and it
points the other way.**

---

## 6. The best cell, and why it is only WEAK

Six gates, all pre-stated. `TRAIL_25` = 25% give-back trailing stop from the high-water mark,
seeded at entry (initial level = entry −25%, ratcheting up).

| gate | FULL | STRUCTABLE (recent era) |
|---|---|---|
| G1 beats REALIZED after fees + slippage, both shapes | ✅ | ✅ |
| G2 positive vs NO_STOP under both shapes | ✅ | ✅ |
| G3 survives dropping its best day (vs NO_STOP) | ✅ | ❌ **SAFE = −$1,550** |
| G4 chronological halves agree in sign | ✅ | ❌ **h1 = −$1,406 / −$130** |
| G5 top day < 50% of summed \|delta\| | ✅ (0.17/0.20) | ✅ |
| G6 holds on both populations | ❌ | ❌ |

**Zero of 34 cells pass all six.** Four cells reach 5/6 and each fails G6 — `TIME_90m` and
`SPYMOVE_$1.50` on STRUCTABLE only; `TRAIL_25` and `TRAIL_30` on FULL only.

### `TRAIL_25` vs the realized production book

| cut | delta gross | delta after fees + slippage | top-day share | top-trade share | drop-best-day |
|---|---:|---:|---:|---:|---:|
| FULL · RIBBON | +$8,062 | +$8,062 | 0.216 | 0.047 | **+$1,466** |
| FULL · SAFE | **+$4,030** | **+$4,030** | 0.107 | 0.039 | **+$569** |
| STRUCTABLE · RIBBON | +$4,238 | — | 0.102 | 0.058 | +$6,164 |
| STRUCTABLE · SAFE | +$2,775 | — | 0.103 | 0.056 | +$422 |

Gross and after-cost deltas are equal to the dollar because **contract count is identical by
construction on both sides** — the stop lever moves gross and net by the same amount. Costs are
not what decides this lane.

**Cost-robustness (a concern I raised and then killed).** I initially feared TRAIL_25's 89% stop-fill
rate meant it collected more unmodelled fill optimism. It does not survive contact with the data:
the realized book also stops out on **252 of 303** exits. Charging an extra half-spread on
stop-like exits in *both* books:

| extra half-spread on stop exits | realized after costs | TRAIL_25 delta (RIBBON / SAFE) |
|---|---:|---:|
| $0.00 | −$3,487 | +8,062 / +4,030 |
| $0.02 | −$6,029 | +7,912 / **+4,192** |
| $0.05 | −$9,842 | +7,687 / **+4,435** |

The delta is **stable, even slightly improving**. Cost realism does not kill TRAIL_25.

### 🚨 What does kill it — and it is decisive

1. **The +$8,062 is not attributable to the stop.** It decomposes exactly:
   `TRAIL_25 stop lever vs NO_STOP = +$19,427` **plus** `harness upside-rule penalty = −$11,364`
   (NO_STOP itself is $11,364 worse than the realized book). Those two must never be silently
   netted into "TRAIL_25 beats production by $8,062." **The only clean lever number is the
   +$19,427 vs NO_STOP — and there, every one of the 34 cells is positive.** TRAIL_25 winning
   that comparison is not distinctive.
2. **It is a recent-period artifact that is not even stable within the recent period.** On FULL,
   chronological halves are **+$1,417 then +$18,010** — 93% of the effect is in the second half.
   On the recent era alone, the first half is **negative** and the SAFE shape fails drop-best-day.
   Per the standing recency doctrine, an edge that only exists lately *and* is unstable lately is
   not an edge.
3. **Shape sensitivity is 2×** (+$8,062 RIBBON vs +$4,030 SAFE) — the "edge" depends materially
   on a knob that is not the stop.

---

## 7. Independence — the number that governs every claim above

The five arms trade **one shared signal** (r = 0.846, 95.7% sign agreement).

| grouping | count |
|---|---:|
| raw round trips | 303 |
| date × side × 5-min bucket | 147 |
| **date × side × setup (used)** | **67** |
| date × side | 49 |

**n_effective = 67 independent decisions**, not 303. Every dollar figure in this document is a
sum over ~67 decisions across 35 days. Nothing here has the sample to support a ship decision,
and none is claimed.

---

## 8. Pre-registered hypothesis (NOT a fix)

**PREREG-STOP-MODE-TRAIL25-2026-08-19** — filed as a hypothesis with a kill criterion, per lane
scope. **Nothing is armed. `params.json` is untouched.**

* **Hypothesis.** Replacing structure-primary with a 25% give-back trailing stop from the
  high-water mark (seeded at entry, ratcheting up, −50% catastrophe cap retained) raises net
  expectancy on the ribbon_ride population.
* **Mechanism claim.** A trail is the only cell in the matrix that tightens *as the trade works*,
  so it keeps the tight-stop drawdown profile (max DD −$6,431 vs NO_STOP's −$28,104) without
  paying the tight-stop right-tail tax (winner dollars $19,985 vs PREMIUM_10's $7,269).
* **Falsifiable signature.** Winner dollars must stay within 15% of the control's while loser
  dollars fall. **If winner dollars fall by more than 15%, the mechanism story is wrong even if
  the dollars look good** — that is the tight-stop trap wearing a trailing-stop costume.
* **Run as:** shadow only, one row per live signal, alongside the existing stop-mode clock. Bar:
  **n_days ≥ 20**, matching the existing clock's own decision rule. Reaching the bar is
  permission to TEST, not to ship.
* **KILL CRITERIA — any one kills it.**
  1. Cumulative delta vs control negative at n_days ≥ 20.
  2. Any single day is > 35% of the summed |per-day delta| (the defect that just invalidated the
     existing clock at 49.8%).
  3. Chronological halves disagree in sign.
  4. Winner dollars fall > 15% vs control (mechanism failure).
  5. Delta flips sign when the upside shape is switched RIBBON ↔ SAFE.

### Also filed: a correction to the existing clock

The clock's summary carries `days_to_bar: 13` and `status: ACCRUING` while its interim has
already reversed sign. **Recommend it additionally emit per-day concentration
(`top_day_share`) on every run**, so that a two-day artifact cannot be read as an interim result
by the next session — which is exactly what happened to this brief.

---

## 9. What this lane did NOT find

* No stop mode is separable from the others. **Zero of 34 cells** pass all six gates.
* Tighter stops do **not** help: every "best avg loss" cell in the matrix is a net-P&L failure.
* This harness **cannot** settle structure-vs-premium (fidelity gap −$5,405, §2). The live-fills
  date-paired split can, and it says **structure +$4.48/tr vs premium −$24.60/tr**.
* Consistent with [`LOSER-SEPARABILITY-2026-08-19.md`](LOSER-SEPARABILITY-2026-08-19.md): the
  lever is not fewer losers, and — this lane's addition — **it is not smaller ones either.** The
  book's entire positive P&L is 44 TP1 exits; the top 5 realized winners (all TP1s, 4 of them on
  2026-08-04/08-06) are **22.5%** of all winner dollars. **Protect the right tail; the stop is
  the wrong knob to reach for.**
