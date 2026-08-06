# LEVER 1 — THE DAILY LOSS CAP / CIRCUIT BREAKER

**2026-08-06, after the close.** Clock verified this session: `python setup/scripts/et_clock.py`
→ `2026-08-06 16:45:23 Thursday EDT`, `market_hours=False`. Analysis only — no trading-path
file touched, nothing armed, nothing shipped.

Pre-registered in [`PREREG-LEVER-DAILY-CAP-2026-08-06.md`](PREREG-LEVER-DAILY-CAP-2026-08-06.md),
committed **`b8bbe7a8`, before any runner in this study existed** (git-provable).

---

## VERDICT — read this and stop

> **The daily loss cap works, and it cannot do what J asked.**
>
> A realized-P&L fleet day breaker at **−$600** takes Wednesday from **−$1,935 → −$710** and
> costs **exactly $0.00** on Tuesday and Thursday. That is the best any Tuesday-safe cell in a
> 98-cell grid achieves. **−$710 is a hard floor, not a tuning choice** — pushing Wednesday
> below it requires a threshold tighter than Tuesday's own −$363 realized drawdown, and every
> such cell destroys Tuesday (−$1,093 to −$3,901).
>
> **So a daily cap gets you ~63% of the way to J's "near −$500" and no further. The remaining
> $210 is not in this lever** — it is in the exit config Lane 0 measured at 68.9% of the day.
>
> Verdict **PREREG**, pre-declared before any number was computed. 100% of the fleet cap's
> book benefit is the day that motivated it.

**One finding that changes the design, not just the number:**

> **Rule 5 is EQUITY-based. For this job that is the WRONG basis.** Priced on 27,927 real OPRA
> 1-min marks covering all 71 (symbol, date) pairs in the book: the same −$600 breaker on an
> **equity** basis was **ARMED on Thursday** — the **+$1,465** day — from **10:57 ET**, worst
> mark **−$711.00 at 10:59 ET**. It cost $0 *only* because all three of Thursday's winners
> (+$1,501) were already open and the single entry that followed was a −$36 loser. **That is
> timing luck, not safety margin.** On a **realized** basis Thursday never armed at all —
> Thursday's realized P&L never went negative. Unrealized drawdown on a runner is not a loss.
> **If a day breaker is ever built here, it must read REALIZED P&L.**

---

## 1. What J asked, answered in one table

| | Wednesday 08-05 | Tuesday 08-04 | Thursday 08-06 | 26-day book |
|---|---|---|---|---|
| **Actual** | **−$1,935.00** | +$3,624.00 | +$1,465.00 | +$1,782.01 |
| FLEET realized cap −$600 | **−$710.00** (+1,225) | +$3,624.00 (**$0.00**) | +$1,465.00 (**$0.00**) | +$3,007.01 |
| **+ per-arm 4-consec halt** *(post-hoc)* | **−$710.00** (+1,225) | +$3,624.00 (**$0.00**) | +$1,465.00 (**$0.00**) | **+$3,213.01** |
| FLEET realized cap −$750 | −$912.00 (+1,023) | $0.00 | $0.00 | +$2,805.01 |
| LIVE Rule 5 (−30%/−50% of SoD) | −$1,935.00 (**+$0.00**) | $0.00 | $0.00 | +$1,782.01 |

*(All figures SPY-options-only, real broker fills. The brief's all-in numbers include a
crypto-twin residual: Wed −$1,943.66 vs −$1,935.00 here. Both right, different scopes.)*

**Rule 5 as configured is not a loss-magnitude control. It never armed once in 26 dates, at
any per-arm level from −15% of SoD outward.** risky-3 booked its −$1,462 Wednesday having used
48.8% of its own −50% budget, with **$1,529.95 of headroom still remaining.**

---

## 2. The grid — every cell, including the rejected ones

**HARD GATE (frozen in prereg §6): any cell costing more than $0.00 on 2026-08-04 is
REJECTED FOR SHIPPING.** **98 cells run in total** — 74 in the frozen grid, 4 comparators,
4 post-hoc compositions, 16 in the equity/mark-to-market arm. **57 of the 82 book cells survive
the Tuesday gate.** Every one is in the JSON; the tables below are complete, not filtered.
`ratio` = dollars of upside surrendered per dollar of tail loss prevented (lower is better).
`bind` = share of traded (arm, date) sessions where the breaker armed. `G` = ✗ rejected.

### L1-PCT — per-arm cap as % of REAL start-of-day equity

| cell | nBlk | total | WED after | TUE | THU | ex-WED | harmed | ratio | bind | G |
|---|---|---|---|---|---|---|---|---|---|---|
| −4% of SoD | 40 | −$277 | −$965 | **−$1,093** | $0 | −$1,247 | 3 | 1.12 | 23.0% | ✗ |
| −6% of SoD | 9 | +$585 | −$1,200 | $0 | $0 | −$150 | 1 | 0.54 | 6.8% | ✓ |
| −8% of SoD | 5 | +$670 | −$975 | $0 | $0 | −$290 | 1 | 0.34 | 2.7% | ✓ |
| **−10% of SoD** | 1 | +$664 | −$1,271 | $0 | $0 | $0 | 0 | **0.00** | 1.4% | ✓ |
| −12% of SoD | 1 | +$664 | −$1,271 | $0 | $0 | $0 | 0 | 0.00 | 1.4% | ✓ |
| −15% / −20% / −25% | 0 | $0 | −$1,935 | $0 | $0 | $0 | 0 | — | 0.0% | inert |
| **LIVE Rule 5 (−30%/−50%)** | **0** | **$0** | **−$1,935** | $0 | $0 | $0 | 0 | — | **0.0%** | **inert** |

### L1-ABS — per-arm cap, absolute dollars *(latching and non-latching are identical at every surviving cell — verified, not assumed)*

| cell | nBlk | total | WED after | TUE | THU | harmed | ratio | bind | G |
|---|---|---|---|---|---|---|---|---|---|
| −$150 | 19 | +$406 | −$705 | **−$1,093** | $0 | 1 | 0.80 | 6.4% | ✗ |
| −$250 | 12 | −$54 | −$965 | **−$1,093** | $0 | 1 | 1.03 | 5.1% | ✗ |
| −$400 | 3 | +$613 | −$1,322 | $0 | $0 | 0 | 0.36 | 2.6% | ✓ |
| **−$600** | 1 | +$664 | −$1,271 | $0 | $0 | 0 | **0.00** | 1.3% | ✓ |
| −$800 / −$1200 | 0 | $0 | −$1,935 | $0 | $0 | 0 | — | 0.0% | inert |

### L1-FLEET-ABS — fleet-wide pooled realized cap *(the winning family)*

| cell | nBlk | total | WED after | TUE | THU | ex-WED | harmed | ratio | bind | G |
|---|---|---|---|---|---|---|---|---|---|---|
| −$150 | 99 | −$1,918 | −$221 | **−$3,803** | $0 | −$3,632 | 3 | 1.45 | 38.5% | ✗ |
| −$250 | 61 | −$2,597 | −$450 | **−$3,901** | $0 | −$4,082 | 3 | 1.88 | 26.9% | ✗ |
| −$400 | 15 | +$496 | −$710 | $0 | $0 | −$729 | 1 | 0.74 | 7.7% | ✓ |
| −$500 | 14 | +$475 | −$710 | $0 | $0 | −$750 | 1 | 0.75 | 7.7% | ✓ |
| **−$600** ⭐ | **7** | **+$1,225** | **−$710** | **$0** | **$0** | **$0** | **0** | **0.22** | **3.9%** | ✓ |
| −$750 / −$800 | 5 | +$1,023 | −$912 | $0 | $0 | $0 | 0 | 0.25 | 3.9% | ✓ |
| −$1000 / −$1200 | 3 | +$572 | −$1,363 | $0 | $0 | $0 | 0 | 0.38 | 3.9% | ✓ |
| −$1500 | 0 | $0 | −$1,935 | $0 | $0 | $0 | 0 | — | 0.0% | inert |

### L1-FLEET-PCT — pooled cap as % of pooled SoD equity

| cell | nBlk | total | WED after | TUE | harmed | G |
|---|---|---|---|---|---|---|
| −4% pooled | 22 | +$17 | −$1,363 | $0 | 2 | ✓ but noise |
| −6% pooled | 8 | −$729 | −$1,935 | $0 | 1 | ✓ but negative |
| −8% and looser, incl. LIVE | 0 | $0 | −$1,935 | $0 | 0 | inert |

**Why this family is incoherent and should be ignored:** pooled SoD equity was ~$8K pre-reset
(4 arms × ~$2K) and ~$27K post-reset (5 arms × ~$5.5K). The same % is a wildly different
dollar cap in the two eras. Read the absolute-dollar table instead.

### L2-CONSEC — halt the arm after N consecutive losing closed round trips

| cell | nBlk | total | WED after | TUE | THU | ex-WED | harmed | ratio | bind | G |
|---|---|---|---|---|---|---|---|---|---|---|
| per-arm, N=2 | 76 | −$845 | −$705 | **−$1,969** | $0 | −$2,075 | 4 | 1.28 | 38.5% | ✗ |
| per-arm, N=3 | 32 | +$203 | −$965 | **−$1,093** | $0 | −$767 | 1 | 0.89 | 14.1% | ✗ |
| **per-arm, N=4** ⭐ | 13 | **+$974** | −$1,167 | **$0** | **$0** | **+$206** | **0** | 0.26 | 7.7% | ✓ |
| per-arm, N=5 | 6 | +$443 | −$1,618 | $0 | $0 | +$126 | 0 | 0.44 | 5.1% | ✓ |
| FLEET, N=2..5 | 70–121 | −$919 to −$1,757 | — | −$2,087 to −$3,803 | $0 | — | 2–4 | 1.33–1.46 | 26.9–53.8% | ✗ all |

**N=4 is the only cell in the entire frozen grid with a positive ex-Wednesday delta.** Its
+$206 comes from three independent dates: 2026-06-30 (+$44), 2026-07-02 (+$132),
2026-07-20 (+$30). Small, but 3/3 positive and none of them is the motivating day.

**N=3 is instructive about why fleet-scope consecutive-loss dies:** it blocks 5 risky-3
positions on **Tuesday** for **−$1,093** — the arm lost 3 straight, then made +$524 and +$788.

### L3-RETRACE — halt on X% give-back of the intraday realized peak — **DEAD**

| scope / arming | 20% | 30% | 40% | 50% |
|---|---|---|---|---|
| per-arm, peak>0 | −$1,669 ✗ | −$1,300 ✗ | −$678 ✗ | −$788 ✗ |
| per-arm, peak≥$100 | −$1,669 ✗ | −$1,300 ✗ | −$678 ✗ | −$788 ✗ |
| FLEET, peak>0 | −$2,087 ✗ | 0 blocked | 0 blocked | 0 blocked |
| FLEET, peak≥$100 | −$2,087 ✗ | 0 blocked | 0 blocked | 0 blocked |
| **391-day replay, both arms** | **0 blocked** | **0 blocked** | **0 blocked** | **0 blocked** |

**Every retrace cell is either actively harmful (all of its damage on Tuesday, insurance-cost
ratios of 7.16 to 19.31) or completely inert.** It never touches Wednesday — Wednesday's
realized P&L never went positive, so there was no peak to retrace from. **Verdict: NULL. Do
not re-propose.**

### POST-HOC compositions — labelled post-hoc, chosen after the frozen grid

| cell | nBlk | total | WED after | TUE | THU | ex-WED | harmed | ratio | bind |
|---|---|---|---|---|---|---|---|---|---|
| **FLEET −$600 AND per-arm 4-consec** ⭐ | 16 | **+$1,431** | **−$710** | $0 | $0 | **+$206** | 0 | **0.20** | 6.4% |
| FLEET −$600 AND per-arm 5-consec | 11 | +$1,351 | −$710 | $0 | $0 | +$126 | 0 | 0.20 | 3.9% |
| FLEET −$750 AND per-arm 4-consec | 14 | +$1,229 | −$912 | $0 | $0 | +$206 | 0 | 0.22 | 9.0% |
| per-arm −$600 OR 4-consec | 13 | +$974 | −$1,167 | $0 | $0 | +$206 | 0 | 0.26 | 7.7% |

### Comparators

| cell | nBlk | total | WED after | TUE | ex-WED |
|---|---|---|---|---|---|
| CAP-3 entries per (arm,symbol,date) | 12 | +$720 | −$1,282 | $0 | +$67 |
| Lane-0 NAIVE fleet −$600 (path-inconsistent) | 7 | +$1,225 | −$710 | $0 | $0 |
| Lane-0 NAIVE fleet −$500 | 12 | +$228 | −$710 | $0 | −$997 |

---

## 3. Is −$600 a plateau or a fitted spike? — the decisive test

Every $25 from −$50 to −$2,500, on the book; every $25 from −$25 to −$1,000, on the replay.

**The answer is neither, and the shape is the finding: the cliff is on the TIGHT side.**

```
FLEET cap      total    WED after   TUE       harmed
  -$300       -$884     -$450      -$1,814      3   <-- destroys Tuesday
  -$350       -$945     -$450      -$1,814      3   <-- destroys Tuesday
  -$375       +$517     -$710          $0       1   <-- clears Tuesday's -$363 low by $12
  -$500       +$475     -$710          $0       1
  -$525       +$454     -$710          $0       1   <-- last cell that harms 2026-07-02
  -$550 ┐                                            +$1,225   -$710   $0   0 harmed
  -$600 ├ THE SAFE BAND: -$550 .. -$1,350          +$1,225 -> +$572, monotone
  -$625 ┘   33 contiguous $25 cells, 0 days harmed, Tuesday $0.00 at every one
  -$750       +$1,023   -$912          $0       0
  -$1,300     +$572     -$1,363        $0       0
  -$1,375+    $0        -$1,935        $0       0   <-- inert
```

- **Safe band width: $800** (−$550 to −$1,350). Inside it, benefit degrades *monotonically and
  gracefully*; there is no spike. **Getting the threshold too LOOSE just wastes the lever.
  Getting it too TIGHT breaks Tuesday.**
- The boundaries are not fitted — they are **mechanical**, and each is one specific day:

| boundary | value | the day that sets it |
|---|---|---|
| Tuesday's own realized low | **−$363.00** at 09:56 ET | 2026-08-04, then made +$3,987 on 20 more entries |
| Deepest realized low ANY day recovered from | **−$526.99** at 10:27 ET | 2026-07-02, then made **+$771** on 6 more entries |
| Wednesday's realized low | **−$1,935.00** | 2026-08-05, recovered **$0** |

- **The −$600 candidate's entire safety margin is $73.01** — the gap between it and 2026-07-02's
  −$526.99. That is **14%**. Say it out loud: a day that dips past −$600 and then recovers has
  never happened in 26 dates, but the nearest miss is $73 away.

**The 391-day replay reproduces the identical shape, independently:**

```
single-arm cap   total     nBlk  harmed  helped   bind
   -$100        +$252.90    20     6      12     12.8%   <-- tight-side damage
   -$150        +$183.10    13     3       9      8.5%   <-- tight-side damage
   -$200        +$773.80     6     0       5      3.5%   <-- best, 0 harmed
   -$250        +$723.80     5     0       4      2.8%
   -$400        +$486.00     2     0       2      1.4%
   -$575        +$246.00     1     0       1      0.7%
   -$600+        $0.00       0     0       0      0.0%   <-- inert
```

Gate-clean from −$200 to −$575 (16 contiguous cells, 0 of 141 days harmed). Cliff on the tight
side, exactly as on the book. **Two populations, one shape.**

---

## 4. Leave-one-day-out — the honesty column

| candidate | full-sample | most load-bearing date | total WITHOUT it | share from that one date |
|---|---|---|---|---|
| FLEET −$600 | +$1,225.00 | 2026-08-05 | **$0.00** | **100.0%** |
| per-arm −$600 | +$664.00 | 2026-08-05 | **$0.00** | **100.0%** |
| **per-arm 4-consec** | +$974.00 | 2026-08-05 | **+$206.00** | **78.8%** |
| per-arm 5-consec | +$443.00 | 2026-08-05 | +$126.00 | 71.6% |

**The fleet cap has literally no book evidence outside the day that motivated it** — worse than
CAP-3's already-disclosed 91%, worse than anything currently on the table. What keeps it out of
the noise bin is (a) the independent 141-traded-day replay and (b) the mechanical boundary
argument in §3. Neither is an evidence bar. **PREREG, not SHIP.**

---

## 5. The equity-basis arm — and the finding that matters most

Rule 5 watches **equity**, not realized P&L. Realized-only trips strictly later, so the whole
grid above is a **floor**. So the equity version was priced properly: real OPRA 1-min bars for
**all 71 (symbol, date) pairs**, **27,927 real marks**, zero dates dropped for missing data;
minute-by-minute fleet P&L = realized from actual exit fills (partial exits handled per-leg) +
unrealized on the open remainder; latching, path-consistent, blocks new entries only.

| basis | Wed after | TUE | THU | book total | harmed | dates ARMED at any minute | of those, days that ended PROFITABLE |
|---|---|---|---|---|---|---|---|
| **REALIZED −$600** | −$710 | $0 | $0 | +$1,225 | 0 | **2 of 26** (08-05, 07-27) | **0** |
| **EQUITY −$600** (bar close) | −$710 | $0 | $0 | +$1,225 | 0 | **3 of 26** (08-05, 07-27, **08-06**) | **1** ⚠ |
| EQUITY −$600 (bar VWAP) | −$710 | $0 | $0 | +$1,225 | 0 | 3 of 26 | 1 ⚠ |
| EQUITY −$500 | −$710 | $0 | $0 | +$475 | 1 | 4 of 26 | 2 ⚠ |
| EQUITY −$400 | −$710 | **−$524** | $0 | −$7 | 2 | 6 of 26 | 3 ⚠ |
| EQUITY −$750 | −$912 | $0 | $0 | +$1,023 | 0 | 2 of 26 | **0** |

**The two bases give the SAME Wednesday answer (−$710) and the SAME Tuesday/Thursday cost
($0).** The equity basis buys nothing on Wednesday because the 776C spiral legs held only 2–4
minutes each — realized and marked P&L converge almost immediately. **So the −$710 floor is
confirmed on both measurement bases.**

**What the equity basis DOES change is the risk profile, badly:**

```
dates where the EQUITY -$600 breaker was ARMED at some minute
  2026-07-27  first below 13:52 ET   worst -$828.00 at 14:00 ET   day ended   -$828
  2026-08-05  first below 10:12 ET   worst -$1,938.00 at 14:05 ET day ended -$1,935
  2026-08-06  first below 10:57 ET   worst -$711.00  at 10:59 ET  day ended +$1,465  <-- !!
```

**Thursday — the +$1,465 day — spent part of its session with a −$600 equity breaker ARMED.**
Cost $0 for one reason only: safe-2 (+$375), risky-1 (+$296) and risky-3 (+$830) were **all
already open** by 10:32 ET, and the only entry after the trip was a −$36 loser at 14:21 ET.
Move any of those three entries 25 minutes later and a latching equity breaker deletes a
+$1,501 day.

- **On a realized basis Thursday never armed at all** — Thursday's realized P&L path was
  `0 → +$296 → +$1,126 → +$1,501 → +$1,465`. It never went negative.
- **Deepest EQUITY drawdown on a day that ended profitable: −$711.00 (Thursday).**
  Deepest **REALIZED** drawdown on a day that ended profitable: **−$526.99** (2026-07-02).
- **An equity-based −$600 has NEGATIVE margin against an observed winning day. A realized-based
  −$600 has +$73.**

> **DESIGN CONCLUSION: a 0DTE day breaker must read REALIZED P&L. Rule 5's equity basis
> penalises holding a runner through its drawdown — which is the entire mechanic of the
> chandelier profit-lock. This is a lever-design finding, not a threshold finding, and it
> applies to whatever Rule 5 is eventually retuned to.**

---

## 6. Summary statistics J asked for

**Dollars of upside surrendered per dollar of tail loss prevented** (over blocked positions):

| candidate | upside surrendered | loss prevented | **ratio** | reading |
|---|---|---|---|---|
| per-arm −$600 / −10% SoD | **$0.00** | $664.00 | **0.00** | surrenders nothing — but only recovers $664 |
| **FLEET −$600** | $347.00 | $1,572.00 | **0.22** | 22¢ of upside per $1 of tail loss stopped |
| **FLEET −$600 + 4-consec** | $347.00 | $1,778.00 | **0.20** | best in study |
| FLEET −$750 | $347.00 | $1,370.00 | 0.25 | |
| per-arm 4-consec | $347.00 | $1,321.00 | 0.26 | |
| 391-day replay −$200 | **$0.00** | $773.80 | **0.00** | blocked nothing profitable in 141 days |
| *(rejected)* FLEET −$250 | $2,932.99 | $1,558.98 | **1.88** | surrenders $1.88 to save $1 |

The single surrendered winner in every surviving fleet cell is the same trade:
**risky-1's 772P, +$347**, entered 11:48 ET Wednesday after the fleet was already −$1,363.

**Bind frequency** — cheap insurance or a strategy change?

| candidate | (arm,date) sessions armed | calendar dates armed | days armed that ended PROFITABLE |
|---|---|---|---|
| FLEET −$600 (realized) | 3.9% | **2 of 26 = 7.7%** | **0** |
| FLEET −$600 + 4-consec | 6.4% | 4 of 26 = 15.4% | 0 |
| per-arm 4-consec | 7.7% | 4 of 26 = 15.4% | 0 |
| 391-day replay −$200 | — | **5 of 141 = 3.5%** | 0 |
| *(rejected)* FLEET −$250 | 26.9% | 26.9% | ≥2 |
| *(rejected)* per-arm 2-consec | **38.5%** | — | ≥2 |

**The surviving cells fire on 3.5–7.7% of sessions and have never once fired on a day that
ended green. That is cheap insurance.** The rejected cells fire on 27–54% of sessions — those
are strategy changes wearing a guard's costume and must never be judged on a no-harm bar.

---

## 7. Methodology corrections made to prior work

Three, all material enough to name:

1. **Lane 0's `day_breaker` is path-INCONSISTENT.** It computed each entry's running realized
   total over the ORIGINAL closed set — *including positions its own rule would have blocked* —
   so a blocked loser still pushed the counter down and over-blocked later entries. Both
   shapes are computed here; the path-consistent walk is primary. **At −$600 they agree
   (+$1,225). At −$500 they do not: +$475 path-consistent vs +$228 naive.**

2. **The replay's sequentiality assumption is FALSE, and it was inherited unverified.** Lane 0's
   comment reasoned that a one-position-at-a-time walk means cumulative-by-entry-order *is*
   cumulative-realized. Checked directly against `entry_time_et + hold_minutes`: **6 same-day
   pairs in the 141-day population have the next trade entering while the previous is still
   open.** Crediting a still-open trade's P&L into the breaker's running total is look-ahead
   (C6). `replay_sim` now walks real close times. **Material at −$100 (+$252.90 correct vs
   +$407.10 look-ahead-inflated, a $154.20 error); immaterial at −$150 and looser.**

3. **Prereg/implementation mismatch, self-caught.** Prereg §4 describes Rule 5's *latching*
   semantics ("day closed for that account"); the first implementation used a re-armable gate.
   Both are now run. **Identical at every surviving cell (−$400, −$500, −$600, −$750) —
   verified rather than assumed.**

**Data finding.** Exactly one of 735 ledger rows' positions has a BUY with no matching SELL:
**safe-2 / SPY260626P00732000 / 2026-06-26, 3 contracts, $294.00.** A 0DTE put with no recorded
exit — it expired. `reconstruct_positions` drops it, and so does Lane 0's book, consistently.
**The headline book of +$1,782.01 is therefore ~$294 optimistic against true cash.** The
verifier now pins it as a known singleton so a second one goes RED.

---

## 8. Verification

`backtest/tools/lever_daily_cap_verify_2026_08_06.py` — **61/61 assertions PASS.** Nothing is
read back from the runners' own JSON; every headline is recomputed from the raw ledger / raw
replay artifact by a second code path:

- **A** — day and arm P&L re-derived as pure ledger cash flow (`Σ sell − Σ buy` × multiplier),
  no position reconstruction at all. Matches.
- **B** — brief anchors. *(Corrected: the brief's Wednesday risky-1 −$485 is the **776C spiral
  only**; risky-1's whole Wednesday is −$138 options-only, reconciling with the brief's all-in
  −$140.39. Both asserted separately.)*
- **C** — every SoD equity from the fleet/guard logs cross-checked against Alpaca's own
  portfolio history (prior-session close). 10/10 match to the cent.
- **D** — risky-3 Wednesday = 24.40% of SoD, 48.80% of its −50% budget, $1,529.95 headroom.
- **E** — `simulate_multi()` with one spec reproduces `simulate()` exactly on 6 different rules.
- **F** — headline cells re-derived by dumb hand-order walks. Includes the two mechanical
  boundaries (−$363.00 Tuesday, −$526.99 / 2026-07-02).
- **G** — replay sequentiality measured, not inherited (the 6 overlaps above).
- **H** — safe-1/safe-2 share one broker account only *after* the 2026-07-11 repoint;
  safe-1's last trade is 2026-07-09, so no pooled-equity double count anywhere in the book.

**Start-of-day equity provenance.** 189/208 positions (90.9%) sit in an (arm, date) cell with a
REAL logged SoD equity, from `automation/state/fleet/{arm}/decisions.jsonl` (first flat tick)
and `automation/state/daily-loss-guard-{date}.jsonl` (the premarket REARM row — exactly what
Rule 5 arms from). The 4 uncovered cells (safe-2 on 06-26/07-02/07-06, bold-2 on 06-26/07-02)
predate the guard log and are left **UNCAPPED** in every %-cell. **Nothing is interpolated,
extrapolated, or reconstructed.** Conservative: it can only understate a %-cell's saving.

---

## 9. Multiple comparisons — stated, not buried

**98 cells scored against a 26-date book containing exactly ONE Wednesday.** The best-looking
cell is selected in-sample by construction. The 141-traded-day replay is the only
out-of-sample check available and **it cannot express a fleet threshold** (it has no fleet) and
**cannot validate the consecutive-loss lever at all** (consec-4 fires 0 times in 141 days — a
single arm averaging 1.35 trades/day essentially never has 4 losers in one session).

---

## 10. If this is ever pre-registered forward — the frozen candidate

Not a ship. This is the threshold to freeze **before** a confirming run:

```
INSTRUMENT   fleet-wide REALIZED-P&L day breaker, LATCHING
THRESHOLD    -$600.00 of realized P&L, pooled across all live arms
BASIS        REALIZED only. NOT equity. (section 5 — this is the load-bearing choice)
ACTION       block NEW entries for the rest of the session; never force-liquidate
RESET        at the ET date boundary
OPTIONAL     + per-arm halt after 4 consecutive losing closed round trips
             (adds +$206 of ex-Wednesday evidence across 3 independent dates)

EXPECTED     Wednesday-shaped day capped at ~-$710
             fires on ~4-8% of sessions
             ~$0.20-0.22 of upside surrendered per $1 of tail loss prevented
KILL IF      it fires on a day that ends profitable, OR total delta < 0 after 20 sessions
```

**Do not tighten below −$550 without new evidence.** −$525 already harms 2026-07-02, and −$375
sits $12 from Tuesday's −$363 low.

---

## 11. Graveyard check — run before any number was computed, no collision

Not stop width (either direction) · not stopped-then-paid · not pre-TP1 profit-lock arming ·
not hold-longer / hold_to_time / trail_only_no_tp1 · not take-profit-earlier · not level-target
exits · not filter-5 deletion or filter-8 relax · not min-contracts · not wick closed-bar entry
· not bull-vix-soft-mode · not the arm-looseness knob · not a per-setup TIME cooldown · not a
late-day or open standdown.

**Not a regime standdown**, which is the closest-sounding graveyard entry: that is a *pre-emptive
classifier bet* and its classifier failed on 2026-08-02 (20.9% 8-way accuracy vs a 39.1%
majority baseline). This lever requires **no forecast** — it reacts to already-booked realized
loss.

**Its nearest LIVE relative is Rule 5 itself.** This study re-parameterises an existing guard
and reports that, as configured, that guard **never armed once in 26 dates.**

---

## Artifacts

| file | what |
|---|---|
| `analysis/deep-research/PREREG-LEVER-DAILY-CAP-2026-08-06.md` | frozen prereg, commit `b8bbe7a8` |
| `analysis/deep-research/LEVER-DAILY-CAP-2026-08-06.json` | every cell, every sweep point, all provenance |
| `analysis/deep-research/LEVER-DAILY-CAP-2026-08-06.md` | this document |
| `backtest/tools/lever_daily_cap_2026_08_06.py` | frozen grid runner (66 cells, 2 populations) |
| `backtest/tools/lever_daily_cap_headroom_2026_08_06.py` | fine sweep, headroom, LODO, plateau |
| `backtest/tools/lever_daily_cap_mtm_2026_08_06.py` | equity/mark-to-market arm, 27,927 real OPRA marks |
| `backtest/tools/lever_daily_cap_verify_2026_08_06.py` | 61/61 independent re-derivation |
