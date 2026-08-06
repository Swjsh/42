# LOSS ANATOMY — where the loss dollars actually live (LANE 0)

**Run:** 2026-08-06, after the close. Clock verified by this session, not trusted from the brief:

```
$ python setup/scripts/et_clock.py
2026-08-06 16:37:38 Thursday EDT
market_hours=False
```

**Posture:** market closed → analysis-only anyway. **Nothing under `automation/state/`, `setup/scripts/`,
`backtest/lib/`, or any `params*.json` was modified.** New code lives in `backtest/tools/`; the only
outputs are this file and its JSON sibling.

**Authority:** real broker fills + real OPRA 1-min bars, live-fetched this session. No synthetic prices,
no `simulate_trade_real`, no oracle in any live-executable column (the two oracle cells in this file are
labelled `ORACLE` in their own names).

---

## LINE 1 — THE ONE SENTENCE

> ### The loss is **not** in the trades. Our worst single position out of 208 real fills is **−$664**, the median loser is **−$32**, and no per-trade instrument — not even an impossible oracle one — can turn Wednesday into a −$500 day. The loss is in the **DAY**: 208 ordinary trades pile into one −$1,935 day because five "independent" arms are one bet in five sizes (mean pairwise daily-P&L correlation **0.787**). **A day-level tail cap is the right instrument; per-trade tuning is the wrong axis, and this is provable in one line: an ORACLE −$100-per-trade cap gets Wednesday to −$847, while a LIVE fleet day breaker at −$600 gets it to −$710 and costs $0 on Tuesday, $0 on Thursday, and $0 on the other 23 days.**

And the mechanism split of Wednesday inverts the prior audit: **68.9% EXIT-config, and entry LOCATION
is a net CREDIT of +$315.49.**

---

## 0. POPULATIONS — stated before any number is read

| | **A — THE BOOK** | **B — THE REPLAY** |
|---|---|---|
| source | `automation/state/fills-ledger.jsonl`, `attribution=="engine"`, options, non-crypto → `exit_shape_parity_study.reconstruct_positions` (the repo's ONE definition of a position) | `analysis/recommendations/engine-fullhist-replay-2026-07-23.json` `trades` |
| authority | **real broker fills** | entries frozen + exits re-walked through the **live** `exit_manager.plan_exit_actions` via `exit_manager_walk.walk_exit_manager` |
| n | **208 positions**, **26 distinct ET dates**, 2026-06-26 → 2026-08-06 | **191 trades**, **141 traded days**, inside a **387-RTH-day** window 2025-01-02 → 2026-07-22 |
| net | **+$1,782.01** | **+$4,808.75** |
| arms | 6 (safe-1/2/3, bold-2, risky-1/3) | ONE arm-equivalent, qty 3, RIDE_THE_RIBBON family only |

**Two disclosures up front.**

1. **The brief calls A "the 25-day book." It is 26 dates** — today (2026-08-06) is the 26th and is
   included. Both counts are in the JSON; nothing here is quoted at n=25.
2. **The brief calls B "391-day." The artifact's own metadata says `n_calendar_rth_days: 387`.**
   Reported as measured. The trade count is 191, not 190.

⚠️ **A structural caveat that governs every cross-population read below:** B is **one arm at qty 3**.
A cannot be compared to B dollar-for-dollar, and B **structurally cannot produce a Wednesday** — its
worst day in 387 RTH days is **−$825**. That is not a reassurance. It is the finding (§3).

---

## 1. WHERE THE LOSS DOLLARS LIVE — Pareto at the day, flat at the trade

### 1a. Per TRADE — there is no fat tail to cap

| | BOOK (n=208) | BOOK ex-08-04..06 (n=165) | REPLAY (n=191) |
|---|---:|---:|---:|
| losing trades | 157 (75.5%) | 128 (77.6%) | 135 (70.7%) |
| **total loss $** | **8,813.99** | 5,384.99 | **15,469.30** |
| mean loss | 56.14 | 42.07 | 114.59 |
| **median loss** | **32.00** | 24.50 | **90.40** |
| p75 | 75.00 | 54.00 | 128.00 |
| p90 | 110.00 | 85.00 | 242.00 |
| p95 | 162.00 | 117.00 | 282.00 |
| **max single loss** | **664.00** | 355.00 | **579.00** |
| worst single trade's share of all loss $ | **7.5%** | 6.6% | **3.7%** |
| worst 10% of trades' share | 40.8% | 39.3% | 29.0% |

**Read it:** the biggest single losing trade in 399 real-and-replayed trades combined is **−$664**.
The typical loser is **−$32** (book) / **−$90** (replay). There is nothing here for a per-trade cap
to bite on.

### 1b. Per DAY — one day is a third of the book's entire loss

| | BOOK (26 days) | BOOK ex-week (23 days) | REPLAY (141 traded days) |
|---|---:|---:|---:|
| losing days | 19 (73.1%) | 18 (78.3%) | 93 (66.0%) |
| **total loss $** | **6,137.01** | 4,202.01 | **13,549.70** |
| mean loss | 323.00 | 233.44 | 145.70 |
| median loss | 217.00 | 179.00 | 89.40 |
| p75 | 381.00 | 346.00 | 173.00 |
| p90 | 828.00 | 388.00 | 298.20 |
| p95 | 1,935.00 | 828.00 | 390.00 |
| **max day loss** | **1,935.00** | 828.00 | **825.00** |
| **worst single day's share** | **31.5%** | 19.7% | 6.1% |
| worst 10% of days' share | **45.0%** | 28.9% | 32.5% |
| worst 20% of days' share | 57.6% | 47.1% | 49.6% |

**HONEST DISCLOSURE, stated before anyone quotes the 45%:** the book's extreme day-concentration is
substantially the week that motivated the question. Strip 08-04..08-06 and worst-10%-of-days falls
**45.0% → 28.9%**. The cross-population stable number is **~29–33%** — the replay independently says
**32.5%** across 141 days. So: *concentrated, yes; 45%-concentrated, only in the presence of a Wednesday.*

### 1c. THE VERDICT ON INSTRUMENT — with the number

Both populations agree the **ratio** max-day ÷ median-day is ~9× (book 1,935/217 = 8.9×; replay
825/89.4 = 9.2×). But the book's −$1,935 day is **14 positions whose worst member is −$664** — a *sum
of ordinary trades*, not one extraordinary trade. Therefore:

| instrument | Wednesday after | cost Tue | cost Thu | cost on the other 23 days | live-executable? |
|---|---:|---:|---:|---:|:--:|
| `ORACLE` per-trade cap −$100 | **−$847** | 0 | 0 | +931 | ❌ **NO** |
| `ORACLE` per-trade cap −$200 | −$1,320 | 0 | 0 | +355 | ❌ **NO** |
| `ORACLE` per-trade cap −$500 | −$1,771 | 0 | 0 | 0 | ❌ **NO** |
| **FLEET realized-day breaker −$600** | **−$710** | **0** | **0** | **0** | ✅ **YES** |
| FLEET realized-day breaker −$750 | −$912 | 0 | 0 | 0 | ✅ YES |
| FLEET realized-day breaker −$500 | −$710 | 0 | 0 | **−997** (2026-07-02) | ✅ YES |
| FLEET realized-day breaker −$250 | −$450 | **−1,894** | 0 | −428 | ✅ YES |
| PER-ARM realized-day breaker −$500 | −$1,271 | 0 | 0 | 0 | ✅ YES |

> **A LIVE day instrument beats an IMPOSSIBLE trade instrument.** That single comparison settles the
> axis question. **If losses are Pareto-concentrated the tail cap is right — and they are, at the DAY
> level only. Per-trade tuning is the wrong instrument. Say it that way to the other lanes.**

**Breaker semantics (no look-ahead, C6).** Cumulative realized counts only positions whose LAST exit
fill printed at or before the candidate entry's timestamp. A position already open when the breaker
trips is **not** force-liquidated — it runs to its actual exit, matching Rule 5's real "no new trades"
semantics. Realized-only trips **strictly later** than the live equity-based kill switch (which also
sees unrealized MTM), so **every saving above is a FLOOR**.

### 1d. The 391-day replay independently validates the day breaker

Same rule, applied to population B (one arm, qty 3, different family, different era):

| cap | n blocked | total Δ | days HARMED | days helped |
|---:|---:|---:|---:|---:|
| −$100 | 21 | **+407.1** | 6 | 13 |
| −$120 | 15 | +295.3 | 4 | 10 |
| −$150 | 13 | +183.1 | 3 | 9 |
| **−$200** | 6 | **+773.8** | **0** | 5 |
| −$250 | 5 | +723.8 | **0** | 4 |
| −$300 | 3 | +581.0 | **0** | 3 |
| −$400 | 2 | +486.0 | **0** | 2 |
| −$500 | 1 | +246.0 | **0** | 1 |
| −$600 | 0 | 0.0 | 0 | 0 |

**Positive at every cap tested, and ZERO days harmed at −$200 and looser, across 141 traded days.**
Scale-match honestly: B is one arm at qty 3, so its −$200 row is the analogue of the book's −$600 row,
not of its −$200 row. Both populations land on the same shape — **a realized-loss day breaker set at
the right level is free.**

### 1e. What the book's benefit is really made of — say it out loud

The fleet −$600 cell's **entire +$1,225 is Wednesday**. Ex-Wednesday it is **exactly $0.00** on 25 other
days, because on no other day did the fleet book −$600 of realized loss and then keep entering. That is
**100% of the measured benefit from the motivating day** — worse than cap-3's already-disclosed 91%.

It clears a **does-no-harm** bar on 26 days AND an independent **does-no-harm** bar on 141 replay days.
It does **not** clear an evidence bar on the book. **Lane 0's verdict is therefore PREREG, not SHIP.**

### 1f. Independent reproduction of the CAP-3 numbers (harness validation)

This session's pipeline, built from scratch off the raw fills ledger, reproduces the already-circulating
cap-3 numbers **to the dollar**: cap 3 entries per (arm, symbol, date) → total **+$720**, Wed **+$653**,
Tue **$0.00**, Thu **$0.00**, ex-Wednesday **+$67**, **12 positions removed**, **0 days harmed**. The
brief's numbers were +$720 / +$653 / $0.00 / $0.00 / +$67 / 12. **Match.** Treat the rest of this file's
arithmetic as coming off a harness that has now been independently cross-checked.

---

## 2. WEDNESDAY, DECOMPOSED INTO BUCKETS THAT SUM

`ACTUAL = −$1,935.00` SPY options (+ −$8.66 crypto-twin residual = the −$1,943.66 day). 14 positions.

**Method.** Each bucket is a **counterfactual book**, never a label. Levers:

| lever | definition | data |
|---|---|---|
| **(e) friction** | re-price every entry and exit fill at its OWN minute's real OPRA 1-min VWAP | 1,168 real OPRA bars fetched live (390 + 382 + 396) |
| **(c) size** | scale every position to Rule 6's floor of **3 contracts**, legs pro-rata | ledger; linear-in-qty, disclosed |
| **(b) re-entry** | keep only ordinal-1 of each (arm, symbol, date) wave — i.e. **CAP-1** | ledger |
| **(d) exit-config** | **observed sibling execution**: on the 772P three arms bought inside 62s at 1.69 / 1.65 / 1.63; risky-1 (TP1 +50% via `exit_patch`) realised **+$69.40/contract**, risky-3 and safe-2 (TP1 +100%, never reachable) realised **−$83.00/contract**. Credit the losers with the sibling's realised per-contract outcome. | **real broker fills on both sides — nothing modelled** |
| **(a) entry location** | **the RESIDUAL** — what the day still costs with zero friction, doctrinal-minimum size, one entry per contract, and the best exit config that actually existed in the fleet that day | derived |

### 2a. THE ANSWER — exact Shapley over all 24 orderings

Waterfalls are order-dependent and this one is violently so (the SIZE lever swings **+$927.26 → −$366.80**
depending on where it sits). That is C15 interaction, not data ambiguity — so the headline uses the
**exact Shapley value**, which is order-independent **and still sums exactly**.

| bucket | Shapley $ | share of the −$1,935 |
|---|---:|---:|
| **(d) EXIT-CONFIG — TP1 unreachable** | **−1,332.52** | **68.9%** |
| **(b) RE-ENTRY COUNT** | **−657.74** | **34.0%** |
| **(c) POSITION SIZE** | **−335.72** | **17.4%** |
| (e) FRICTION / spread | **+75.49** | −3.9% *(a small benefit)* |
| **(a) ENTRY LOCATION** *(residual)* | **+315.49** | **−16.3%** *(a CREDIT)* |
| **SUM** | **−1,935.00** | **100.0%** |

`sum_check_must_be_zero = 0.0` on both waterfalls and on the Shapley decomposition. The buckets SUM.

**The residual is the headline nobody expected.** With zero friction, three contracts per position, each
signal taken **once**, and every arm given the exit configuration that a sibling arm actually ran that
same day, **Wednesday 2026-08-05 is a +$315.49 WINNER.** The two call ideas still lose (−$186 combined at
minimum size, taken once each); the put pays for them three times over.

### 2b. RECONCILIATION — the prior 70.4% / 29.6% split is on the wrong axis

The prior audit's numbers are arithmetically correct and I reproduce them exactly:

| event | $ | share |
|---|---:|---:|
| A — 776C spiral ×10 | −1,279.00 | 66.1% |
| A′ — 777C | −84.00 | 4.3% |
| **"ENTRY-side" = A + A′** | **−1,363.00** | **70.4%** |
| B — 772P | −572.00 | **29.6%** |

**But that is an EVENT-level split — *which contract* lost money — presented as a MECHANISM split —
*which lever* lost money. On the mechanism axis it inverts.** Two specific errors it induces:

1. It charges the whole 776C spiral to "entry." In mechanism terms **92.0% of that spiral is re-entry
   count and size**, not entry location: cap-1 alone takes it −$1,279 → −$221 (82.7%), and resizing to
   3 contracts takes it to **−$102** (a further 9.3%). **The idea was worth −$102. The execution of it
   was worth −$1,177.**
2. It charges the put to "exit" at only **−$572**, because it nets risky-1's +$347 against the other two.
   The exit-config lever is worth **+$1,682.40 standalone / +$1,332.52 Shapley** — **more than the entire
   event's face value**, because fixing the config doesn't just erase −$572, it converts the event into
   **+$1,110**.

> **Correction for the record: Wednesday was 68.9% an EXIT-CONFIG failure. Entry location was a net
> CREDIT. The 70.4%-entry-side framing points the next lane at the wrong half of the machine.**

### 2c. Friction is not a factor, in either direction

| | $ |
|---|---:|
| entry side (fill vs same-minute OPRA VWAP) | **−85.67** *(we bought BELOW the minute's VWAP — better than average)* |
| exit side | **+113.30** *(we sold below VWAP — a real cost)* |
| **net** | **+27.63** |

**1.4% of the day.** Sign convention: positive = a real cost. Caveat: the 1-min VWAP is the average of
everyone's prints in that minute — a fair, reproducible reference, **not** a claim that we could
certainly have hit it. Whichever way you read it, spread/slippage did not make Wednesday.

### 2d. Two honest understatements in bucket (d), both conservative

- risky-1 paid the **worst** entry of the three arms (1.69 vs 1.65 / 1.63), so crediting the other two
  with *its* per-contract result **under-states** the config effect.
- safe-2 is a Safe arm (`tp1_qty_fraction` 0.8) vs risky-1's Bold 0.667. At safe-2's own fraction the
  fixed outcome is ≈ **+$87.20/contract**, not the +$69.40 credited — another ≈**$53** left on the table.

Bucket (d) is a **lower bound**. It is also **below** the previously-published $2,196 best-executable
oracle, as it must be.

### 2e. Wednesday's ordinal ladder

| ordinal | n | $ |
|---:|---:|---:|
| 1st | 6 | −877.00 |
| 2nd | 2 | −145.00 |
| 3rd | 2 | −260.00 |
| 4th | 2 | −202.00 |
| 5th | 2 | −451.00 |

---

## 3. CONCENTRATION — the fleet is ONE BET IN FIVE SIZES

### 3a. By arm (book, all 26 days)

| arm | n pos | net $ | **loss $** | **share of ALL loss $** | worst day |
|---|---:|---:|---:|---:|---|
| **risky-3** | 54 | +499.00 | **3,270.00** | **37.1%** | **2026-08-05 −1,458** |
| safe-2 | 49 | −280.99 | 1,884.99 | 21.4% | 2026-08-05 −339 |
| risky-1 | 37 | +1,116.00 | 1,381.00 | 15.7% | 2026-06-30 −148 |
| bold-2 | 10 | −70.00 | 1,165.00 | 13.2% | 2026-07-27 −355 |
| safe-3 | 34 | +760.00 | 557.00 | 6.3% | 2026-07-27 −87 |
| safe-1 *(retired)* | 24 | −242.00 | 556.00 | 6.3% | 2026-07-09 −105 |

risky-3 carries **37.1% of all loss dollars on 26% of the positions** — and **75% of Wednesday**.

*(Note: worst-day figures here are **SPY options only**. risky-3's Wednesday is −$1,458.00 in options;
the brief's −$1,462.29 is that plus −$4.29 of crypto-twin residual. Both are right; they measure
different things. Same for the day total: −$1,935.00 options vs −$1,943.66 all-in.)*

### 3b. The diversification question, answered

| metric | value | what independence would look like |
|---|---:|---|
| **mean pairwise daily-P&L correlation** (15 pairs) | **0.787** | ~0 |
| best-populated pairs | risky-1\|safe-3 **0.991** (n=13) · risky-3\|safe-1 **0.981** (n=8) · risky-3\|safe-3 **0.929** (n=14) · safe-2\|safe-3 **0.902** (n=8) · risky-1\|risky-3 **0.664** (n=15) | |
| daily **sign agreement**, every pair with n≥7 | **86% – 100%** | ~50% |
| **diversification ratio** sd(Σarms)/Σsd(arms) | **0.812** | **0.447** for 5 independent equal arms |
| entry-minutes with >1 arm on the same contract | **50 of 126 (39.7%)** | |
| **positions inside a multi-arm same-minute cluster** | **131 of 208 = 63.0%** | |
| **loss dollars inside those clusters** | **$5,072.00 = 57.5% of all loss dollars** | |

> ### ✅ **MAJOR FINDING — SAY IT PLAINLY: the fleet provides essentially ZERO diversification. Five arms trading off one shared signal producer, filling the same contract in the same minute 63% of the time, at correlation 0.79 and 86–100% sign agreement, is ONE BET IN FIVE SIZES. The "5 arms" framing is an illusion for risk purposes.**

**This is also the mechanistic answer to §0's caveat.** Population B (one arm) has a worst day of −$825
in 387 RTH days. Population A (five correlated arms) produced −$1,935 in 26 days. **The fat day-tail is
manufactured by fleet-parallel correlated participation, not by the strategy.** Any day-level cap is,
in substance, a cap on the pile-on.

**Small-n discipline:** bold-2 and safe-1 pairs rest on n=1–5 common days and are **NOT** load-bearing.
The claim stands on the five pairs with n≥8, all ≥0.66 and four of them ≥0.90.

### 3c. Counter-evidence against over-claiming a pure COUNT cap

`corr(n_positions_per_day, loss magnitude)` on losing days = **0.323** (n=19) — **weak**. One day took
**28 positions for −$217**; Wednesday took **14 for −$1,935**. Trade count alone does not predict
magnitude. **Wednesday was a conjunction** — count × size × correlated arms × broken exit. Do not let
any lane sell a bare count cap as *the* fix on this evidence.

---

## 4. TIME OF DAY — and the refutation of the obvious read

Raw loss dollars per bucket are meaningless without the denominator, so `loss $/entry` is the
opportunity-normalised column and `n` is printed in every row.

| entry bucket | BOOK n | BOOK loss$/entry | BOOK net/entry | REPLAY n | REPLAY loss$/entry | **REPLAY net/entry** |
|---|---:|---:|---:|---:|---:|---:|
| **09:30** | 41 | 47.6 | **+25.6** | 23 | 101.4 | **+63.9** |
| 10:00 | 30 | 57.5 | −50.7 | 4 *(small n)* | 185.8 | −16.7 |
| 10:30 | 7 | 25.3 | +189.1 | 15 | 132.6 | **−54.0** |
| 11:00 | 15 | 61.8 | −60.8 | 11 | 49.1 | +134.1 |
| 11:30 | 16 | **107.1** | −35.6 | 21 | 85.0 | −42.9 |
| 12:00 | 5 | 0.0 | +463.6 | 19 | 71.4 | −39.1 |
| 12:30 | 18 | 43.9 | −23.7 | 14 | 58.5 | +72.3 |
| 13:00 | 14 | 16.4 | +6.9 | 23 | 53.6 | +57.7 |
| 13:30 | 20 | 34.5 | −11.3 | 17 | 67.8 | +73.3 |
| 14:00 | 12 | 12.3 | −3.6 | 22 | 93.8 | +2.7 |
| 14:30 | 24 | 15.8 | +32.2 | 18 | 62.4 | +59.3 |
| 15:00 | 6 | 14.0 | −14.0 | 4 *(small n)* | 82.5 | −82.5 |

### ❌ "Wednesday's damage was 09:58–10:20, so stand down at the open" — **REFUTED**

**09:30 is the single most PROFITABLE bucket in the 391-day replay** (net **+$1,470.70**, **+$63.90/entry**)
and is net-positive in the book too (**+$1,050**, **+$25.60/entry**). Wednesday's morning damage is a
Wednesday fact, not a population fact. Reading it as a time-of-day signal is exactly the trap J's
"recency > aggregate… but don't invent a gate from one day" correction warns about.

**What weak signal there is:** the 10:00–12:00 band is net-negative in both populations — book
**−$1,677** (ex-week **−$830**), replay **−$302.20**. It is not clean (the book's 10:30 and the replay's
11:00 are both strongly positive), n is modest, and no threshold survives both. **VERDICT: NULL. No
time-of-day standdown is supported.** Late-day standdown is already graveyarded; this file adds that
**open standdown is refuted too, on 391 days.**

---

## 5. THE NUMBERS THE OTHER LANES SHOULD CONSUME

```
WEDNESDAY  −1,935.00  =  exit_config −1,332.52
                       + reentry     −657.74
                       + size        −335.72
                       + friction       +75.49
                       + entry_loc     +315.49      (Shapley, order-independent, sums exactly)

PER-TRADE  book: median loss 32 · p90 110 · MAX 664 (n=157 losers)
           replay: median 90.40 · p90 242 · MAX 579 (n=135 losers)
           -> NO fat per-trade tail exists. Per-trade caps are the wrong axis.

PER-DAY    book: median 217 · p90 828 · MAX 1,935 · worst day = 31.5% of all loss $
           replay: median 89.40 · p90 298.20 · MAX 825 · worst 10% of days = 32.5%
           -> Pareto at the DAY. Tail cap at the DAY.

FLEET DAY BREAKER −600 (realized, blocks new entries only, no forced liquidation):
           WED +1,225 (day -1,935 -> -710) · TUE 0 · THU 0 · other 23 days 0 · 0 days harmed
           391-day replay, scale-matched -200: +773.80, 0 of 141 days harmed
           BUT: 100% of the book benefit is Wednesday. PREREG, do not ship blind.

CONCENTRATION  mean pairwise arm daily-P&L r = 0.787 · sign agreement 86-100%
               diversification ratio 0.812 (vs 0.447 if independent)
               63.0% of positions in multi-arm same-minute clusters, carrying 57.5% of loss $
               -> the fleet is ONE BET IN FIVE SIZES

TIME OF DAY    NULL. 09:30 is the BEST replay bucket (+63.90/entry). No standdown supported.
```

---

## 6. CAVEATS — read before quoting anything above

1. **26 days is 26 days.** Population A's day-level statistics rest on 19 losing days, one of which is
   31.5% of the total. Every book-only number here is small-n and is labelled where it matters.
2. **100% of the fleet-breaker's book benefit is the day that motivated it.** Disclosed in §1e. The
   141-day replay does-no-harm result is the only thing keeping it out of the noise bin.
3. **Population B cannot test fleet effects at all.** One arm, qty 3, one family. It validates the
   day-breaker *mechanism*; it cannot validate a *fleet* threshold.
4. **Bucket (d) is a lower bound**, and deliberately so (§2d). It is not the $2,196 oracle.
5. **Bucket (c) assumes P&L is linear in qty** when rescaling legs pro-rata. Real TP1 fractions round to
   whole contracts; at n=14 positions the rounding is immaterial but it is an assumption, not a fact.
6. **The friction reference is a 1-min VWAP, not an achievable quote.** §2c.
7. **The Shapley split is exact for the four levers as defined.** A differently-defined lever set gives
   a different split — this is an attribution over a chosen basis, which is stated, not hidden.
8. **`corr(count, magnitude) = 0.323`** — the count story is weak in general (§3c) even though it is
   strong on Wednesday. Do not generalise Wednesday's ordinal ladder to the population.
9. Population A includes **`safe-1`, a retired arm** (24 positions, all pre-2026-07-11). Left in because
   the loss dollars were real; its 6.3% share should not be read as live exposure.

---

## 7. VERIFICATION (OP-33) — 41/41, by a second independent code path

Every load-bearing number above was re-derived straight off the **raw fills ledger** and the **replay
artifact** by `backtest/tools/loss_anatomy_verify_2026_08_06.py` — deliberately **not** read back out of
the JSON the runners wrote — and asserted. Run this session:

```
PASS  book n_positions                     got=208        want=208
PASS  book net                             got=1782.01    want=1782.01
PASS  book WED total (options only)        got=-1935.0    want=-1935.0
PASS  book worst single POSITION loss      got=-664.0     want=-664.0
PASS  book median position loss            got=32.0       want=32.0
PASS  book ex-week net (23 days)           got=-1371.99   want=-1371.99
PASS  WED put per-contract gap (r1 vs r3)  got=152.4      want=152.4
PASS  WED 776C idea taken ONCE at qty3     got=-102.0     want=-102.0
PASS  fleet-600 WED after                  got=-710.0     want=-710.0
PASS  fleet-600 delta ex-WED               got=0.0        want=0.0
PASS  fleet-600 n days harmed              got=0          want=0
PASS  ORACLE per-trade -100, WED after     got=-847.0     want=-847.0
PASS  replay worst DAY                     got=-825.0     want=-825.0
PASS  replay worst TRADE                   got=-579.0     want=-579.0
   ... 41 checks, all passed.
```

One bug this pass caught and fixed before publication: the multi-arm cluster counter keyed on a *set of
arms* and therefore counted **arms**, not **positions** (131 vs 133 against an independent count). The
arm-based definition is the correct one for the diversification claim and is what §3b now reports.

Two brief figures also reconcile rather than match, and both are correct — they measure different things:
the brief's per-arm/day-total numbers are **all-in** (include crypto-twin residual), this file's are
**SPY options only**. risky-3 Wed: −$1,458.00 options vs −$1,462.29 all-in. Day: −$1,935.00 vs −$1,943.66.

---

## ARTIFACTS

| path | what |
|---|---|
| `analysis/deep-research/LOSS-ANATOMY-2026-08-06.md` | this file |
| `analysis/deep-research/LOSS-ANATOMY-2026-08-06.json` | every number above, machine-readable (`q1_distribution`, `q2_wednesday_decomposition`, `q3_concentration`, `q4_time_of_day`, `q5_which_instrument`, `synthesis`, `verification`) |
| `backtest/tools/loss_anatomy_2026_08_06.py` | distributions, concentration, time-of-day (Q1/Q3/Q4) |
| `backtest/tools/loss_anatomy_wed_decomp_2026_08_06.py` | Wednesday buckets + exact Shapley + real-OPRA friction (Q2) |
| `backtest/tools/loss_anatomy_instrument_2026_08_06.py` | day-breaker vs per-trade-cap vs count-cap ladders, both populations (Q5) |
| `backtest/tools/loss_anatomy_verify_2026_08_06.py` | the 41-assertion independent verification pass (§7) |

All three runners are **analysis-only**: they write nothing outside `analysis/deep-research/`, import no
broker order path, and place no orders.
