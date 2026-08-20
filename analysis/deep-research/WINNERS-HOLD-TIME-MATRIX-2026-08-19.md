# HOLD-TIME MATRIX — are we cutting winners early, or holding them too long?

_Lane: BIGGER WINNERS. Clock verified before work: `setup/scripts/et_clock.py` →
`2026-08-20 00:22:47 Thursday EDT, market_hours=False`._
_Builder: [`setup/scripts/hold_time_matrix.py`](../../setup/scripts/hold_time_matrix.py) ·
data: [`WINNERS-HOLD-TIME-MATRIX-2026-08-19.json`](WINNERS-HOLD-TIME-MATRIX-2026-08-19.json)_
_Dataset: `analysis/recommendations/trade-matrix.json` — 303 closed round trips, 5 arms,
35 trading days, 2026-06-26 → 2026-08-19 + full-day OPRA 1-minute bars (109/109 contract-days
cached, 0 fetches, 0 rows dropped)._

---

## VERDICT — 🔴 **NO EDGE. Hold time is not the lever. Do not arm any cell.**

**One line, as asked:** *no cell beats production by more than its own concentration can
explain* — the two big winners are **one day** (2026-08-04 carries **156–240%** of their whole
effect), and the only leave-one-day-out survivor (**T20**) wins by less than a **2-minute**
shift of the same grid moves the book, and **loses −$2,010 out-of-sample**.

| | |
|---|---:|
| Production (broker truth, gross) | **−$1,805** |
| Production (broker truth, net of real fees) | **−$1,940** |
| Production (net, symmetric realistic sell model — the comparison baseline) | **−$4,132** |
| Best cell by net P&L: **EOD_cap50** (ride to 15:50, −50% catastrophe cap) | **+$34,296** |
| …its delta vs production, gross / net | **+$36,041 / +$38,429** |
| …**share of that delta from 2026-08-04 alone** | **156%** 🚨 |
| …**delta on the other 34 days** | **−$21,505** |
| …worst single arm-day | **−$5,072** on a $1.6–5.5K account → **Rule 5 halts the arm first** |

**What is true:** the tail is genuinely on the table. The median trade traded **+62.7%** above
its entry premium at some point in the day, and **61.1%** of trades made their day-high
*after* we sold. **What is false:** that a clock can collect it.

---

## 1. The number J asked for — how long after our exit did MFE occur?

Entry-bar-**exclusive** OPRA highs, entry → 15:50 ET, all 303 trades. ⚠️ **BACKWARD-LOOKING
DIAGNOSTIC** — this says whether the tail was still available, never that it was collectable.

| | |
|---|---:|
| trades whose **day-high came after our exit** | **185 / 303 = 61.1%** |
| minutes from our exit to the day-high — **median** | **+5.9 min** |
| …p10 / p25 | −17.2 / −3.2 min *(we exited **after** the high)* |
| …p75 / p90 | **+124.9 / +254.0 min** |
| …mean | +65.6 min *(mean ≫ median — a fat right tail, not a shifted centre)* |
| **median day-MFE, % above entry** | **+62.7%** |
| median minute of the day-MFE (from entry) | 31.8 min |
| …winners / losers | 39.8 min / 25.7 min |
| day-high landed **within the first 10 minutes** | 33.7% |
| never traded above entry at all | 6.9% |

**Read it honestly.** Production's median hold is **6.0 minutes**; the median day-high lands
**5.9 minutes later**. So the typical trade is cut *right at the shoulder* of its own move —
that part of J's instinct is correct. But the distribution is bimodal-in-effect: a third of
trades peaked before minute 10 (holding longer strictly hurts them) and a quarter had already
peaked *before we sold*. The median is a coin-flip, and the money lives in the p75–p90 tail
that **cannot be identified at entry**.

---

## 2. THE FULL MATRIX — every cell, pure clock exit

Sell the **entire** position T minutes after entry, hard-capped at the 15:50 flatten. Nothing
consults a future bar — a clock exit needs only the clock (C6 clean). `dNET` = delta vs
production under the identical sell model. Production is marked ⬅.

| cell | net $ | gross $ | win rate | avg win | avg loss | max DD | **ΔNET vs prod** | top-day share of Δ | Δ ex-best-day | days Δ>0 | worst arm-day |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| T3 | −5,409 | −2,587 | 32.0% | 39 | −45 | −5,409 | −1,277 | −2.50 | −4,471 | 18/35 | −698 |
| T5 | −1,741 | 910 | 39.9% | 62 | −51 | −3,011 | +2,391 | 1.40 | −961 | 22/35 | −1,058 |
| **⬅ PRODUCTION** | **−4,132** | **−1,805** | **22.8%** | **214** | **−81** | **−6,164** | — | — | — | 10/35 days + | **−1,484** |
| T8 | −1,400 | 1,704 | 39.3% | 82 | −60 | −3,056 | +2,732 | 1.14 | −392 | 17/35 | −922 |
| T10 | −2,606 | −111 | 36.3% | 95 | −68 | −5,291 | +1,526 | 1.51 | −775 | 18/35 | −1,338 |
| T12 | −2,276 | 1,025 | 32.3% | 130 | −73 | −6,332 | +1,856 | 1.08 | −139 | 18/35 | −1,562 |
| T15 | −1,614 | 586 | 35.3% | 145 | −87 | −6,856 | +2,519 | **0.69** | **+789** | 17/35 | −1,708 |
| T18 | −1,406 | 1,337 | 37.0% | 173 | −109 | −9,736 | +2,726 | 1.05 | −139 | 17/35 | −2,479 |
| **T20** | **+996** | **3,924** | 37.6% | 197 | −114 | −9,806 | **+5,128** | **0.71** | **+1,511** | 18/35 | −2,380 |
| T22 | +130 | 1,802 | 34.6% | 223 | −118 | −10,392 | +4,262 | 1.09 | −394 | 17/35 | −2,932 |
| T25 | −3,957 | −2,162 | 35.6% | 207 | −135 | −13,293 | +176 | 28.34 | −4,800 | 15/35 | −3,348 |
| T30 | −5,747 | −4,130 | 34.3% | 209 | −138 | −14,032 | −1,614 | −3.29 | −6,927 | 14/35 | −3,938 |
| T35 | −7,776 | −5,701 | 34.0% | 208 | −146 | −13,360 | −3,643 | −1.51 | −9,162 | 14/35 | −4,818 |
| T40 | −9,323 | −7,853 | 35.3% | 206 | −160 | −14,192 | −5,190 | −1.29 | −11,861 | 15/35 | −5,236 |
| T45 | −10,465 | −8,343 | 31.7% | 244 | −164 | −15,359 | −6,333 | −1.16 | −13,693 | 16/35 | −5,527 |
| T60 | −13,498 | −12,105 | 29.0% | 310 | −190 | −22,353 | −9,365 | −1.39 | −22,372 | 8/35 | −6,441 |
| T90 | −4,967 | −3,527 | 28.1% | 474 | −208 | −27,206 | −835 | −30.10 | −25,957 | 13/35 | −7,767 |
| T120 | −1,903 | 64 | 28.4% | 583 | −240 | −34,213 | +2,229 | 15.28 | −31,823 | 11/35 | −8,724 |
| **EOD (15:50)** | **+20,868** | 22,450 | 26.7% | **1,069** | −296 | **−36,119** | **+25,000** | **2.40** 🚨 | **−34,933** | 8/35 | −9,537 |

**With the shipped −50% catastrophe cap layered on the clock:**

| cell | net $ | ΔNET | top-day share of Δ | Δ ex-best-day | trades stopped at cap |
|---|--:|--:|--:|--:|--:|
| T15_cap50 | −1,668 | +2,465 | 0.70 | +735 | 37 / 303 |
| T20_cap50 | **+1,355** | **+5,487** | **0.66** | **+1,870** | 59 / 303 |
| T25_cap50 | −3,393 | +739 | 6.73 | −4,236 | 87 / 303 |
| EOD_cap50 | **+34,296** | **+38,429** | **1.56** 🚨 | **−21,505** | 239 / 303 |

### The shape the matrix actually draws

`avg win` climbs **monotonically** with hold time — $39 (T3) → $197 (T20) → $1,069 (EOD) —
exactly as J's right-tail thesis predicts. So does `avg loss` (−$45 → −$296) and so does max
drawdown (−$5.4K → −$36.1K), while win rate *falls* (39.9% → 26.7%). **Holding longer does buy
bigger winners. It buys bigger losers faster.**

---

## 3. Why the winning cells are not findings

### 3a. EOD / EOD_cap50 / T90 / T120 = **2026-08-04, wearing a costume**

| day | EOD_cap50 Δ net |
|---|--:|
| **2026-08-04** | **+$59,933** |
| 2026-08-12 | −$6,793 |
| 2026-08-05 | −$6,760 |
| 2026-08-03 | +$4,550 |
| 2026-08-17 | +$2,870 |
| 2026-08-19 | −$2,767 |
| **all 34 other days combined** | **−$21,505** |

Delta is positive on **8 of 35 days**; median daily delta is **−$226**. The mechanism is
visible in one contract: `SPY260804C00763000`, entered at **$1.40**, printing **$9.68** at
15:50 — a genuine 6.9× that the arms took five times over. Bars verified directly against
`backtest/data/opra_1m_cache/SPY260804C00763000_2026-08-04.csv`; the data is real. The
*inference* is not: this is the same **trend-day amplifier** that
[`HOLD-WINNERS-2026-08-06.md`](HOLD-WINNERS-2026-08-06.md) already killed at gates G2 (chop)
and G4 (sub-window stability), and it dies here on the same evidence at 13 more days of data.

⚠️ **Liquidity caveat, disclosed:** the 15:50 bar on that contract printed **2 contracts** of
volume (16 at 15:49, 117 at 15:45). Exiting 8 lots into that minute at the modelled price is
optimistic even before the concentration problem.

### 3b. The cell is **unreachable**, not merely worse — Rule 5 fires first

Rule 5 is per-account, per-day: **Safe −30%**, **Bold −50%** of start-of-day equity.

| cell | worst single arm-day | arm-days worse than −$600 |
|---|--:|--:|
| **⬅ PRODUCTION** | **−$1,484** | **5 / 108** |
| T5 | −$1,058 | 2 / 108 |
| T20 | −$2,380 | 8 / 108 |
| EOD_cap50 | −$5,072 | 19 / 108 |
| **EOD** | **−$9,537** | **31 / 108** |

Against a $1,633–$5,501 account, EOD's worst day is a **−170% to −580% day**. The kill switch
halts the arm mid-morning and the 08-04 payday is never collected. **A backtest that spends a
day the live rule book would have already closed is not a counterfactual, it is fiction.**

### 3c. T20 — the only LODO survivor — is grid noise

T20 is the one cell that clears leave-one-day-out (ex-best-day **+$1,511**, top-day share
0.71, positive on 18/35 days). It does not survive anything else:

| test | result |
|---|---|
| **T18 → T20** (a **2-minute** shift) | **+$2,402** — and it is *diffuse*: top 3 trades = **6.9%** of it, so it is 303 trades of 1-minute wiggle, not a mechanism |
| **T22 → T25** (a 3-minute shift) | **−$4,086** |
| mean \|adjacent-cell move\|, 5–30 min band | **$1,392** |
| **T20's entire edge over its neighbours** | **inside that band** |
| ex-best-day: T18 / **T20** / T22 | −$139 / **+$1,511** / −$394 |
| **bootstrap over 84 signal clusters** (T20_cap50) | Δ = +$5,487, **95% CI [−$8,715, +$20,556]**, P(Δ>0) = 0.78 |
| same, EOD_cap50 | Δ = +$38,429, **95% CI [−$30,306, +$148,466]**, P(Δ>0) = 0.73 |

A real hold-time mechanism draws a **ridge**. This draws a **spike** at exactly one grid point,
flanked by two negatives. That is the definition of an argmax artifact.

### 3d. Split-half out-of-sample — the test that settles it

Pick the best cell on one half of the calendar, spend it on the other.

| train | best cell in train | Δ in train | **Δ out-of-sample** |
|---|---|--:|--:|
| first 17 days | T5 | +$1,374 | **+$1,017** |
| last 18 days | EOD_cap50 | +$42,891 | **−$4,462** 🔴 |
| last 18 days (plain clock only) | **T20** | +$7,139 | **−$2,010** 🔴 |

**The in-sample champion loses money out-of-sample in both families.** The only cell positive
in both halves is **T5** — a *shorter* hold than the 6.0-minute production median, and its
overall delta (+$2,391) is itself 140% one day (ex-best-day **−$961**). So even the survivor
fails LODO. Nothing clears both gates.

---

## 4. Does the optimal hold differ by entry hour?

| entry window | n | production net | median actual hold | best plain cell | that cell's net |
|---|--:|--:|--:|---|--:|
| 09:30–10:00 | 78 | −$1,874 | 4.0 min | EOD | +$33,471 ← **is 08-04** |
| 10:00–11:00 | 51 | −$934 | 3.0 min | T3 | −$1,625 *(no cell profitable)* |
| 11:00–12:00 | 45 | −$1,966 | 6.0 min | EOD | +$3,993 |
| 12:00–13:00 | 40 | −$1,135 | 23.9 min | T5 | +$677 |
| 13:00–14:00 | 40 | −$16 | 3.0 min | T5 | +$39 |
| **14:00–15:00** | 43 | **+$1,868** | 4.2 min | T25 | **+$3,522** |
| 15:00–15:50 | 6 | −$76 | 23.1 min | T5 | −$11 |

**No stable time-of-day structure.** The argmax jumps T3 → T5 → T25 → EOD across adjacent
buckets with no monotone or otherwise interpretable ordering — the signature of seven
independent argmaxes over ~45 trades each. The one bucket that looks like a finding
(**14:00–15:00 favouring a 25-minute hold**, +$1,654 delta) is **69% one day** (2026-07-29) at
n=43 rows across **17 signal clusters**. **Reported, not recommended.**

The one durable observation across the row: **14:00–15:00 is the only entry window production
is profitable in** (+$1,868 of an otherwise −$4,132 book). That is an ENTRY-TIMING lead, not a
hold-time one, and it belongs to a different lane.

---

## 5. Method, limits, and what would falsify this

**Accounting — two layers, never mixed.**
- **GROSS** — production = recorded broker P&L; counterfactual = bar close at the exit minute.
- **NET** — **both** sides repriced with **one symmetric sell model**, then real regulatory
  fees (`setup/scripts/cost_model.py`: OCC+ORF+TAF+SEC, ex-CAT). Sell fill =
  `low + 0.333 × (high − low)`. 0.333 is the position a genuine bid-hit implies; our recorded
  exits measured **0.462**, i.e. **0.129 of range too good**
  ([`COST-REALISM-2026-08-18.md`](COST-REALISM-2026-08-18.md)). Applying it to production too
  is what makes the delta honest — crediting production its optimistic real fill while charging
  the counterfactual a realistic one would manufacture an edge out of the bookkeeping.
- This is why production's **comparison** baseline (−$4,132) is worse than broker truth
  (−$1,940): the model removes $2,192 of exit optimism across 303 trades (~$7.23/trade). All
  three figures are stated everywhere; the **delta** is unaffected because both sides pay it.

**Calibration anchor:** T3 (≈ "sell immediately") lands at **−$17.85/trade** — the round-trip
spread on ~4 lots at ~$1.15 premium. The sell model reproduces the known friction, so the
absolute levels are not free parameters.

**No look-ahead (C6).** A clock exit consults only the clock. Section 1's MFE-timing block is
the sole backward-looking figure and is labelled ORACLE at every appearance. Forward statistics
are entry-bar-**exclusive** so no pre-entry tick inside the signal bar can leak in.

**Independence.** 303 rows are **not** 303 observations. The 5 arms fire one shared signal
(r=0.846, 95.7% sign agreement): 127 clusters at a 5-min window, 99 at 30-min, **84 at
60-min**, 49 by date×side, 35 days. **n_effective = 84** (60-min window — inside the 60–90 the
repo already reconciled) is used throughout; every significance claim bootstraps over
**clusters, never rows**, and the wider cluster is the conservative choice because it widens
the CI rather than flattering it.

**Disclosed limits.**
- Bars are OPRA *trades*, not quotes; a minute with no print prices off the last print
  (median staleness **0.0–0.2 min**, so this bites only in the tail).
- The −50% cap is modelled as filling at `min(cap price, that minute's realistic sell)` — a
  triggered market stop can do worse.
- 1 of 303 rows failed production repricing (no bar covering an exit leg) and **fell back to
  its recorded fill, flagged, not dropped**. 0 rows excluded, 0 values defaulted to zero.
- Thin late-day liquidity on the EOD cell is disclosed in 3a and not modelled.

---

## 6. PRE-REGISTERED HYPOTHESIS — what would have to be true for this to come back

Filed as a hypothesis with a kill criterion, **not** as a change. Nothing here is armed; no
`params*.json` was touched.

> **PREREG-HOLD-TIME-2026-08-19.** *A fixed-clock exit in the 15–22 minute band beats the
> current exit stack on the shared 0DTE signal.*
>
> **KILL CRITERION (any one fires ⇒ dead, permanently):**
> 1. **Ridge test** — the T15 / T18 / T20 / T22 cells must all be net-positive vs production
>    ex-best-day. *Already fails today* (−$139 / +$1,511 / −$394 with T15 at +$789).
> 2. **OOS test** — the in-sample argmax must carry a positive delta into the held-out half.
>    *Already fails today*: T20 → **−$2,010**, EOD_cap50 → **−$4,462**.
> 3. **Concentration test** — top-day share of the delta < 0.35 and delta positive on ≥ 60% of
>    days. *Already fails today*: 0.66–2.40 and 8–18 of 35 days.
> 4. **Survivability test** — worst modelled arm-day inside Rule 5's daily loss budget.
>    *Already fails today* for every cell longer than T20.
>
> **All four fire on today's data. The hypothesis is DEAD ON ARRIVAL and is filed as such.**
> Revisit only if a *forward-looking, entry-time-decidable* discriminator is found that
> separates the p75–p90 tail from the 33.7% of trades that peak inside 10 minutes — at which
> point the question is no longer "how long do we hold" but "which trades are allowed to run."

---

## 7. What this lane hands to the others

1. **Hold time is dead as a standalone lever.** Do not re-run the grid. The surface is negative
   everywhere net of costs except a one-day-driven tail and one noise-width spike, and it fails
   OOS in both directions. This closes the lane. Aligns with, and now outlives, the earlier
   `hold-longer book-wide` graveyard entry (−$451.50 over 21) and
   [`HOLD-WINNERS-2026-08-06.md`](HOLD-WINNERS-2026-08-06.md).
2. **The real signal in this data is an EXIT-QUALITY one, and it belongs to the stops lane.**
   A blind 5-minute clock beats production by **+$2,391** net at *the same median hold*
   (T5 = 5 min vs production 6.0 min) — and it is the only cell positive in both calendar
   halves. Production is not losing to a clock because it holds too briefly; it is losing
   because **51% of exits are `premium_stop`** (154/303) firing into the 1-minute noise band at
   worse prices than the clock would have taken. That is the already-established stop-inside-
   the-noise finding, independently reproduced here from a different direction.
3. **The tail is real but unaddressable from the exit side.** Median day-MFE **+62.7%**, 61.1%
   of day-highs after our exit — yet no clock collects it. The right-tail problem is an
   **entry-selection / runner-qualification** problem, not a hold-duration one.
4. **14:00–15:00 is the only profitable entry window** (+$1,868 vs −$4,132 book-wide, n=43).
   Handing that to the entry lane as an observation, not a filter — it is one bucket of seven
   and has not been tested for concentration as an entry rule.

---

_Analysis and proposal only. No params edited, no orders placed, nothing armed._
