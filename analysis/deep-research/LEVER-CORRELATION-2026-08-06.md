# LEVER 5 — FLEET CONCENTRATION: are we five bets, or one bet in five sizes?

> **Clock verified this session** — `python setup/scripts/et_clock.py` → **`2026-08-06 16:45:23 Thursday EDT`, `market_hours=False`.**
> After-hours. **Analysis only — no trading-path file was touched, nothing was armed, nothing was shipped.**
> Machine-readable twins: [`LEVER-CORRELATION-2026-08-06.json`](LEVER-CORRELATION-2026-08-06.json) ·
> [`LEVER-CORRELATION-STAGGER-2026-08-06.json`](LEVER-CORRELATION-STAGGER-2026-08-06.json)
> Verification: **47/47 assertions PASS**, re-derived from the RAW ledger by a second independent code path
> (`lever_correlation_verify_2026_08_06.py` does not import the runner's helpers).

---

## VERDICT

**YES — the fleet is one bet in five sizes. Per-contract correlation is r = 0.846 (r² = 0.716) with 95.7% sign
agreement across 139 matched trade pairs. Every one of the 15 pairwise daily correlations is positive. Say it
plainly: on the days that matter the "risk profile" differences are cosmetic.**

**AND CAPPING IT IS THE WRONG INSTRUMENT — decisively, on the hard gate.** Every arm-concurrency cap
{1, 2, 3} **FAILS Tuesday no-harm**, in **100% of 2,000 tie-break orderings**, and **loses money book-wide**.
The reason is mechanical, not statistical: **because the arms are one bet, a cap on the pile-on is a pure
leverage reduction — it removes winners and losers in the same proportion.** The cap blocks trades that are
*better* than the population average (cap-3 blocked mean **+$42.50** vs population **+$8.57**).

**And it cannot even reach Wednesday.** The contract that did the damage — `SPY260805C00776000`, 10 entries,
−$1,279 — **never had more than TWO arms in it at once.** Wednesday's put topped out at three. A 3-arm cap
changes 2026-08-05 by **exactly $0.00**. Wednesday was not a concentration event at the arm level; it was
**serial re-entry by one arm** wearing a fleet costume.

🎯 **Lane 5's contribution to "how do we not lose $2,000 on a Wednesday" is a KILL, not a lever.** It removes
three plausible-sounding instruments from the board so no other lane spends a cycle on them, and it hands the
day-level lanes the reason their instrument is the right shape.

---

## The one table that settles it

Every `(date, contract)` in the book, bucketed by the **maximum number of arms that ever held it
simultaneously**, against what that bucket earned. Real broker fills, no model.

| Max concurrent arms | Contract-days | Positions | Net P&L |
|---|---|---|---|
| **1** | 35 | 54 | **−$1,895.99** |
| **2** | 12 | 40 | −$679.00 |
| **3** | 11 | 41 | **+$1,769.00** |
| **4** | 12 | 66 | +$238.00 |
| **5** | 1 | 7 | **+$2,350.00** |

And the same cut across the three days in question — note the **10-entries / 2-arms** line, which is the whole
argument in one row:

| Date | Contract | Max concurrent arms | Entries | Net P&L |
|---|---|---|---|---|
| Tue 08-04 | `C00763000` | **5** | 7 | **+$2,350** |
| Tue 08-04 | `C00769000` | 4 | 8 | +$1,831 |
| **Wed 08-05** | **`C00776000`** | **2** | **10** | **−$1,279** |
| Wed 08-05 | `P00772000` | 3 | 3 | −$572 |
| Thu 08-06 | `P00770000` | 3 | 3 | +$1,501 |

The slope runs the **wrong way for a cap**. The single most concentrated contract-day in the entire book — the
only 5-arm pile-on we have ever had — is **Tuesday's 763C, and it made +$2,350**. The *lonely* end of the
spectrum is where the money bleeds: **1-arm contract-days are −$1,896**, which is more than the entire book's
profit.

⚠️ **n-small, and I will not oversell it:** 26 dates, one 5-arm observation. This is not "concentration is
good." It is "concentration is **not** where the loss dollars live," which is all that is needed to reject the
instrument.

---

## 1. Correlation — the answer, with the number

### 1a. Daily P&L, pairwise (real fills, days both arms traded)

| Pair | n days | Pearson r | Sign agreement |
|---|---|---|---|
| risky-1 \| safe-3 | 13 | **0.991** | **100%** |
| risky-3 \| safe-1 | 8 | **0.981** | **100%** |
| risky-3 \| safe-3 | 14 | 0.929 | 85.7% |
| bold-2 \| risky-3 | 4 | 0.906 | 100% |
| safe-2 \| safe-3 | 8 | 0.902 | 87.5% |
| risky-1 \| safe-2 | 9 | 0.892 | 88.9% |
| risky-3 \| safe-2 | 9 | 0.738 | 88.9% |
| bold-2 \| safe-3 | 5 | 0.729 | 60.0% |
| bold-2 \| risky-1 | 4 | 0.696 | 50.0% |
| risky-1 \| risky-3 | 15 | 0.664 | 86.7% |
| risky-1 \| safe-1 | 7 | 0.612 | 85.7% |
| bold-2 \| safe-2 | 5 | 0.605 | 80.0% |
| safe-1 \| safe-3 | 7 | 0.584 | 85.7% |

**Mean pairwise r = 0.787** (0.810 restricted to pairs with n ≥ 7). **Minimum = 0.584. Not one negative pair.**

### 1b. Trade level, per contract — the sharper test

Two positions are "the same bet" when they are the **same contract, same date, entered within 120 seconds**.
Correlating **per-contract** P&L divides out sizing — the *only* thing arms are supposed to differ by. If the
residual correlation is still ~1, the arms are not making different decisions, only different-sized copies of
one decision.

| | Value |
|---|---|
| Matched trade pairs | **139** |
| Pooled Pearson r | **0.8463** |
| Pooled **r²** | **0.7161** |
| Pooled sign agreement | **95.7%** |
| Median per-pair mean \|per-contract gap\| | **$2.20 – $6.64** on the best-populated pairs |

risky-1 \| safe-3: **r = 0.989 over 26 matched trades, 100% sign agreement, mean per-contract gap $2.20.**
Those two arms are the same trade.

### 1c. Diversification ratio

`sd(sum of arms) / sum(sd of each arm)` — 1.0 = perfectly correlated, **0.408** = six independent equal-sd arms.

| Convention | Value |
|---|---|
| Traded-days-only (each arm's sd over days **it** traded) | **0.596** |
| Zeros-filled (non-trading day scored 0.00 — **LANE 0's convention**) | **0.812** |

📌 **Reconciliation note for the synthesis:** LANE 0 published **0.812**. That is the zeros-filled figure and it
is reproduced here **exactly**. Quoting it without naming the convention overstates the correlation, because
scoring a non-trading day as $0.00 understates a sporadic arm's own volatility. **Both are correct; name which
one you are quoting.** Either way the fleet sits far above the 0.408 independence benchmark.

---

## 2. The book-level tail this creates

| | Actual fleet | Decorrelated fleet (20,000 draws) |
|---|---|---|
| Worst day | **−$1,935.00** | −$1,404.14 (mean) · −$1,458.00 (p50) |
| sd of daily P&L | **$941.53** | $539.45 |
| p10 day | −$388.00 | −$408.55 |
| Sum (invariant by construction) | +$1,782.01 | +$1,782.01 |

**Method:** each arm keeps its **own** realized daily P&L values and its **own** traded days; the values are
permuted *within* the arm, independently across arms, then re-summed by day. Marginals and participation are
preserved exactly; **only the cross-arm common factor is destroyed.**

- Correlation inflates daily **sd by 1.75×** and the **worst day by 1.38×**.
- The actual worst day sits at the **4.0th percentile** of the decorrelated distribution — real, detectable.
- **But here is the part that matters, and it cuts against my own lane's premise:** even fully decorrelated,
  this fleet still produces a **−$1,404 worst day**. Correlation is **not** what manufactured Wednesday.
  It cannot be — **75% of Wednesday was ONE arm** (risky-3, −$1,458.00 of the −$1,935.00 options-only day).
  Decorrelating five arms cannot remove one arm's own tail.

**Capital-matched single-arm comparator** — run the whole day's *fleet* contract count through **one** arm's
realized per-contract result (real per-contract dollars × real contract counts):

| Arm | n days | Worst day | sd |
|---|---|---|---|
| safe-2 | 14 | **−$4,746.00** | $2,759.68 |
| risky-3 | 19 | **−$2,551.50** | $963.60 |
| bold-2 | 7 | −$1,704.00 | $1,780.73 |
| **ACTUAL 5-arm fleet** | 26 | **−$1,935.00** | **$941.53** |
| safe-3 | 15 | −$696.00 | $1,189.40 |
| safe-1 | 8 | −$609.00 | $413.54 |
| risky-1 | 15 | −$440.00 | $1,404.66 |

Three of six arms produce a **worse** worst-day than the actual fleet when handed the same total size. **The
fleet dimension does not create the tail — TOTAL SIZE does.** Spreading that size across five correlated arms
is neither the problem nor a solution; it is a bookkeeping choice.

---

## 3(c) — N-of-5 concurrency cap · **the task's highest-weight test** · ❌ **NULL**

Only N arms may hold the same contract at the same instant. FCFS by exact broker fill timestamp. A blocked
position is dropped entirely and occupies no slot. **Pure ledger arithmetic — no model anywhere in this cell.**

| Cell | Book Δ | **TUE 08-04** | WED 08-05 | THU 08-06 | Blocked | Worst day after | **Tuesday gate** |
|---|---|---|---|---|---|---|---|
| cap-1 | **−$2,465** | **−$2,983** | +$1,713 | $0 | 101 | −$658 | ❌ **FAIL** |
| cap-2 | **−$2,558** | **−$2,360** | +$255 | $0 | 46 | −$1,680 | ❌ **FAIL** |
| cap-3 | **−$765** | **−$1,133** | **$0.00** | $0 | 18 | **−$1,935 (unchanged)** | ❌ **FAIL** |
| cap-4 | −$373 | −$373 | $0.00 | $0 | 1 | −$1,935 | ❌ **FAIL** |

### Why it fails — three independent proofs, not one

**(i) It has no selective skill.** Null = block the same *number* of positions drawn at random from the
positions that were *eligible* to be blocked (never a first entrant, since no cap can block one).

| Cell | Observed Δ | Null p50 | Null p05 → p95 | Percentile | Verdict |
|---|---|---|---|---|---|
| cap-1 | −$2,465 | −$1,426 | −$2,927 → +$230 | 0.133 | **indistinguishable from random removal** |
| cap-2 | −$2,558 | −$605 | −$2,389 → +$1,017 | **0.035** | **significantly WORSE than random** |
| cap-3 | −$765 | −$197 | −$1,544 → +$855 | 0.233 | **indistinguishable from random removal** |

Blocked-cohort mean P&L vs population mean **+$8.57**: cap-1 **+$24.41**, cap-2 **+$55.61**, cap-3 **+$42.50**.
**The cap systematically removes better-than-average trades.**

**(ii) No tie-break ordering saves Tuesday.** Most clusters have several arms filling in the *same second* —
FCFS is a race, not a policy — so the ordering was randomised within each entry minute, 2,000 draws per cell:

| Cell | Book Δ p05 → p95 | Tuesday Δ p50 | **Best possible Tuesday** | Draws harming Tuesday |
|---|---|---|---|---|
| cap-1 | −$4,075 → −$2,181 | −$3,015 | −$2,573 | **100.0%** |
| cap-2 | −$2,850 → −$1,709 | −$2,296 | −$1,940 | **100.0%** |
| cap-3 | −$1,334 → −$786 | −$1,270 | −$1,097 | **100.0%** |

**Not one ordering out of 6,000 leaves Tuesday whole.** The hard gate is not narrowly missed; it is unreachable.

**(iii) It cannot reach Wednesday at all.** Verified in the assertion suite:

- `SPY260805C00776000` — 10 entries, −$1,279 — **max 2 arms concurrent, ever.**
- `SPY260805P00772000` — **max 3 arms concurrent.**
- Therefore **cap-3 delta on 2026-08-05 = exactly $0.00**, and cap-3 leaves the worst day at −$1,935 unchanged.

The only cap that touches Wednesday meaningfully is **cap-1 (+$1,713)** — which costs Tuesday **−$2,983**.
That is the whole lane in one line: **the fleet piles on hardest on the days it is RIGHT.**

### Extension cell (mine, labelled as an extension): fleet-wide entries per contract-day

| Cell | Book Δ | TUE | WED | Gate |
|---|---|---|---|---|
| fleet-entry-cap-3 | −$2,264 | −$3,947 | +$993 | ❌ FAIL |
| fleet-entry-cap-5 | −$1,702 | −$2,711 | +$813 | ❌ FAIL |
| fleet-entry-cap-6 | −$752 | −$1,536 | +$653 | ❌ FAIL |
| fleet-entry-cap-7 | +$311 | −$375 | +$573 | ❌ FAIL |
| **fleet-entry-cap-8** | **+$554** | **$0.00** | **+$451** | ✅ **PASS** |

The one passing cell is **strictly dominated by the CAP-3-per-arm lever already on the table** (+$720 book /
+$653 Wednesday / $0 Tuesday / $0 Thursday). It is worse on every axis and 100% of its benefit is still the
motivating day. **Do not carry it forward.** Its only value is as further confirmation that the binding
variable is *entries per arm*, not *arms per contract*.

---

## 3(b) — Staggered exits: what the existing TP1 dispersion is actually worth · ❌ **NULL**

Inside a wave every arm bought effectively the same thing at effectively the same instant, so substituting one
arm's **own realized per-contract result** onto another arm's **own realized quantity** is a real observed
counterfactual, not a model. 52 multi-arm waves.

| | Total |
|---|---|
| **ACTUAL** | **+$4,037.00** |
| All arms get the wave's WORST realized per-contract result | +$187.10 |
| All arms get the wave's MEAN result | +$4,454.79 |
| All arms get the wave's BEST result (**ORACLE — not live-executable**) | +$9,158.95 |
| **Value of the current dispersion (ACTUAL − mean-uniform)** | **−$417.79** |
| Capturable spread (**ORACLE**) | $8,971.85 |

**Permutation null** (shuffle *which* arm's realized outcome lands on *which* arm's realized quantity, within
each wave, 20,000 draws): observed sits at the **16.5th percentile** — p = 0.165, inside the null.

**Verdict: exit staggering currently buys nothing.** It is a coin flip that has landed slightly on the losing
side. The current pairing of exit-config to position size is **not** better than random.

But note where the money is: the **ORACLE spread is $8,972** — more than 5× the entire book's profit. And on
Wednesday's put specifically, risky-1's `exit_patch.tp1_premium_pct = 0.5` (accounts.json `arms[3]`,
FLEET-FULLSEND-R — **the only arm carrying a TP1 patch**, verified this session) was the *sole* reachable TP1:
+$69.40/contract against −$83.00 and −$85.00 for the two arms on the registry's unreachable +100%.

📌 **HANDOFF:** that $8,972 is **not a concentration finding and Lane 5 does not claim it.** It belongs
entirely to the exit-config / catastrophe-cap lane. Lane 5's contribution is only to price it and to state that
**you cannot capture it by changing who trades — only by changing what the exit does.**

I also tested whether the fleet systematically puts the most contracts behind the worst exit config
(`corr(qty, per-contract result minus wave mean)` = **−0.099**, n = 141 legs). **Weak and inside the noise —
NULL.** It was true on Wednesday's put; it is not a systematic property. Do not generalise the anecdote.

---

## 3(a) — Staggered entry timing · ❌ **REFUTED BY ITS OWN PLACEBO**

The only modelled cell in this lane, built to the hardest standard available: **real Alpaca OPRA 1-min bars**
for the delayed entry price, exits **re-walked through the production core**
(`exit_manager_walk.walk_exit_manager` → `exit_manager.plan_exit_actions` — never `simulate_trade_real`), exit
shape resolved from each arm's **own live decision row** (`setup_name` → `strategies.REGISTRY` → `ExitShape`,
then that arm's `accounts.json` `exit_patch`), sequential one position at a time.

**L251 parity gate first:** every leg re-walked at D=0 against broker truth →
**125/141 pass (88.7%), median absolute error $10.00.** A wave is used only if **every** leg passes; 11 of 52
waves excluded and reported.

### The result looked great. It is an artifact. Here is the proof.

| Delay | **stagger** (leg 0 real, legs 1..k delayed) | **PLACEBO: all legs delayed** | **ANTI-PLACEBO: only leg 0 delayed** |
|---|---|---|---|
| 1 min | +$2,266 | +$3,044 | +$778 |
| **2 min** | **+$3,910** | **+$3,930** | +$20 |
| 3 min | +$3,560 | +$3,820 | +$260 |
| 5 min | +$2,959 | +$3,288 | +$329 |

**Delaying EVERY leg — which removes zero concentration, by construction — reproduces the "benefit" to within
0.5% ($3,930 vs $3,910).** The treatment and the placebo are indistinguishable. Whatever this cell is
measuring, **it is not de-concentration.**

Three more artifact tells, all from the harness's own decomposition:

1. **93.7%** of the 2-min cell's total is **Tuesday** — the day that already won.
2. **Every** stagger cell is **NEGATIVE on Wednesday** (−$31 / −$92 / −$73 / −$93). It does not help the day J
   is asking about.
3. **66.6%** of the total sits in **three legs**, all Tuesday, all exiting `runner_stop @ 8.59` / `@ 3.00`.

The mechanism is the graveyard shape the brief already names: with `runner_target_pct = 99.0` the runner is
effectively uncapped, so on a trend day a fixed delay **re-rolls the entry price into an unbounded runner** and
occasionally buys a dip. bold-2's Tuesday 763C: a **13-cent** higher entry (1.38 → 1.51) turns +$638 into
+$1,868 because one pullback stops clipping the 15% trail. **That is a knife-edge, not an edge** — and the
cell's own instability across a one-minute change (+$2,266 → +$3,910 → +$3,560 → +$2,959) says the same thing.

**Verdict: NULL. Not proposed, not pre-registered.** Any future entry-timing work must carry this placebo arm.

🔧 **Harness defect found and fixed in-flight (worth carrying forward):** core-lane decision rows
(`safe-2`/`bold-2`) frequently have `trigger_level_exact: null` while the **fleet sibling row for the same
contract and the same `core_tick_id` carries the real level.** Without back-filling it, `structure_stop`
silently degrades to the −20% premium fallback — safe-2's 2026-08-06 770P replayed **−$76.80 against a broker
truth of +$375.00**, a $452 error *and a sign flip*. This is the same class as the defect
`EOD-2026-08-06-SILENT-ARMS` documented in `exit_shape_parity_study.replay_position`, in a different
consumer. **The shared helper is still unfixed** — it is fenced off in this lane's local code only, and it
will bite the next study that calls it. I also measured that applying the back-fill **fleet-wide** makes parity
*worse* (it invents a 763.10 structure stop that kills risky-1's real +$640 Tuesday 763C), so the fix is
correctly scoped to core arms only.

---

## 4. The two silent arms — bold-2 and safe-3

### ⚠️ Brief correction, on broker truth

The task brief says **"four consecutive zero-trade sessions."** **Broker fills say TWO.** Both arms have real
engine option fills on **2026-08-04** (bold-2 +$479.00, safe-3 +$637.00, options-only). They are dark on
**2026-08-05 and 2026-08-06 only.** The "4th session" phrasing in `EOD-2026-08-06-SILENT-ARMS` counts
consecutive EOD *lenses written*, not zero-fill sessions.

### Netting the silence

Priced by **config-matched sibling substitution**: both silent arms run the plain registry `ribbon_ride` shape
(`tp1_premium_pct = 1.0`; safe-3's `exit_patch` is a no-op against that default), so **risky-1 is excluded from
the basis** — it is the one arm with `tp1_premium_pct = 0.5` and its result is not transferable. Quantities are
each arm's **own** realized fill size since 08-03 (bold-2 = 5, safe-3 = 3).

| Session | Status | Silence effect (**+ = silence HELPED**) |
|---|---|---|
| Tue 08-04 | **PARTICIPATED** — contributed **+$1,116.00** | n/a |
| Wed 08-05 | dark | **+$672.00** — a loss avoided |
| Thu 08-06 | dark | **−$915.00** — a gain forgone |
| **Net over the two dark sessions** | | **−$243.00** |

**Cross-validation — two independent methods, one day:** this lane's ledger-arithmetic estimate for Thursday is
**−$915.00**. The published `EOD-2026-08-06-SILENT-ARMS` figure, from **real OPRA replayed through the live
exit core** (parity-checked at 2.4% against safe-2 broker truth), is **−$911.35**. **They agree to $3.65
(0.4%).** Quote the published figure for Thursday; the agreement is what licenses the Wednesday number.

**Answer: the fleet is slightly WORSE off for having them dark — about −$243 over two sessions.** But the
honest read is not the sign, it is the size: **±$700–900 per session in each direction, netting to noise.**
The silence is **not a risk control. It is a coin flip.** Wednesday it paid; Thursday it cost more.

And the two silences are **not the same thing** and must not be fixed with one action:

| Arm | Root cause (re-verified on Thursday's own ledgers, published lens) | Character |
|---|---|---|
| **bold-2** | `RISK_DENY_PDT` ×3 at 10:32:48 / 10:34:01 / 10:34:56, each with `verdict = ENTER_BEAR` | **A hard block. A bug-shaped constraint.** |
| **safe-3** | `gate: 1 triggers < 2` — its own `gate_override.min_triggers = 2` | **Designed selectivity working as specified.** |

**bold-2's PDT block is the only one of the two that is worth clearing**, and clearing it is a *participation*
question, not a loss-magnitude one — on the evidence here it would have added **−$425 Wednesday** and
**+$565 Thursday**. ⚠️ Note carefully: **un-darkening these arms makes a Wednesday-shaped day WORSE, not
better.** Anyone arguing to restore them for upside must own that.

---

## 5. HARD GATE — Tuesday no-harm, every cell

| Cell | Tuesday Δ | Gate |
|---|---|---|
| cap-1 / cap-2 / cap-3 / cap-4 (concurrency) | −$2,983 / −$2,360 / −$1,133 / −$373 | ❌ **FAIL** (all, and in 100% of tie-break draws) |
| fleet-entry-cap 3 / 4 / 5 / 6 / 7 | −$3,947 / −$3,703 / −$2,711 / −$1,536 / −$375 | ❌ **FAIL** |
| fleet-entry-cap-8 | **$0.00** | ✅ PASS — *but strictly dominated by CAP-3-per-arm; not carried forward* |
| stagger-entry 1 / 2 / 3 / 5 min | +$2,106 / +$3,664 / +$3,220 / +$2,896 | ✅ PASS — *but REFUTED by its own placebo; NULL* |
| exit-stagger (measurement, not a proposal) | n/a | n/a — descriptive cell |

**Nothing in Lane 5 is proposed for pre-registration or shipping.**

---

## What this lane hands the other lanes

1. ✅ **Kill the concentration cap.** All three N values, all 6,000 tie-break orderings, plus a fleet-wide
   entry-cap sweep. **Do not re-propose it in a new costume.** The graveyard entry is: *a blanket cap on a
   perfectly-correlated fleet is a pure de-lever with no selective skill (p = 0.13 / 0.03 / 0.23 against a
   random-removal null), and it cannot reach 2026-08-05 because that day never exceeded 3 concurrent arms.*
2. ✅ **Kill blanket entry-staggering** — refuted by its own placebo at 0.5% separation.
3. ✅ **Kill "exit dispersion is already doing work"** — worth −$418, p = 0.165.
4. 🎯 **The correlation finding is a REASON, not a lever.** r ≈ 0.85 per-contract is precisely *why* a
   **day-level, realized-loss-triggered** instrument is the right shape and a per-arm/per-trade one is not:
   with one bet in five sizes there is nothing to diversify, so the only controllable quantity is **how much
   total size the day is allowed to lose before it stops adding more.** That is LANE 0's fleet realized-day
   breaker, and this lane independently supports its *shape* (while validating none of its thresholds).
5. ⚠️ **Correct the "correlation manufactured Wednesday" story before it hardens.** It did not.
   **75% of Wednesday was one arm**, and a fully decorrelated fleet with identical marginals still throws a
   **−$1,404** worst day. Correlation inflates the tail **1.38×**; it does not create it.
6. 🔧 **Unfixed, live, owed:** `exit_shape_parity_study.replay_position`'s structure-stop degradation, plus the
   newly-found core-row `trigger_level_exact: null` gap. Both silently turn winners into losers in any study
   that touches core-arm fills. Fenced locally here; **still broken for the next caller.**

---

## Caveats — read these before quoting any number above

1. **n = 26 ET dates, one fleet, one strategy family.** Every cross-arm statistic in this lane is n ≤ 26 days.
   **There is no second population and that is structural, not laziness:** the 391-day engine-fullhist replay
   is ONE arm at qty 3 and cannot express a fleet effect at all. Nothing here is validated across populations.
2. **The kills are stronger than the finding.** "A concentration cap fails Tuesday in 100% of orderings" is
   robust — it is arithmetic on real fills with no free parameters. "Concentration is associated with profit"
   is n-small and rests on a **single** 5-arm observation. Do not let the second borrow the first's confidence.
3. **The concurrency-profile table is confounded by conviction.** Days when more arms fire are days when more
   gates agreed. The table shows the cap is aimed at the profitable end; it does **not** establish that adding
   arms causes profit.
4. **The counterfactual assumption in every cap cell:** a blocked arm simply does not trade. It does not
   substitute a different contract. Live, the fleet executor would deny the tick; whether the arm re-fires
   later is partially captured (later entries are separate positions, re-offered) but not fully.
5. **The decorrelation bootstrap cannot remove a single arm's own tail** — it permutes each arm's realized
   values within that arm. It therefore *understates* how much of the tail is removable in principle and is a
   conservative bound on the correlation effect, not an estimate of it.
6. **3(a) carries two disclosed one-directional fidelity gaps:** `ribbon_tick_df = None` (no ribbon-flip exits
   — but constant across treatment *and* placebo, so not a between-cell bias), and the delayed entry priced at
   a real OPRA 1-min bar OPEN (a genuine print and the same point-sample convention `walk_exit_manager` uses
   internally, **not** a fillability claim). It also assumes the delayed arm still wants the trade D minutes
   later.
7. **11 of 52 waves are excluded from 3(a)** by the D=0 parity gate, including Thursday's 770P marquee wave
   (safe-2 replays +$273 vs broker +$375 after the trigger-level fix — improved from a $452 error, still
   outside tolerance). **Thursday therefore shows $0.00 in every 3(a) cell — that is an exclusion, not a
   finding**, and I have not dressed it up as one.
8. **Scope:** SPY options only, `attribution == "engine"`, non-crypto. Per-arm and per-day totals differ by
   cents-to-dollars from the briefing's all-in figures (Wed risky-3 **−$1,458.00** here vs **−$1,462.29**
   all-in; day **−$1,935.00** vs **−$1,943.66**). Both correct, different scopes — never mix them in one column.
9. **safe-1 is a RETIRED arm** (all fills pre-2026-07-11). Left in because the dollars were real; its
   correlation rows are history, not live exposure.
10. **`risky-1 | risky-3` is the MOST-populated pair (n = 15) and one of the weakest (r = 0.664)** — and it is
    the pair that both piled into Wednesday's 776C. (The outright lowest is `safe-1 | safe-3` at r = 0.584,
    n = 7, a retired arm.) The correlation story is real but it is **not uniform**, and the two arms that
    actually did Wednesday's damage are among the *less*-correlated ones in the fleet. Stated because it cuts
    against my own headline.
11. **GRAVEYARD CHECK RUN — no collision.** This lane is not stop-width (either direction), not
    stopped-then-paid, not pre-TP1 profit-lock arming, not hold-longer, not take-profit-earlier, not
    level-target exits, not a per-setup TIME cooldown, not a regime standdown, not a min-contracts rule, not
    late-day standdown. Its nearest live relative is the **per-arm CAP-3 entries** lever already open in
    another lane — which this lane's fleet-entry-cap-8 cell is **dominated by** and therefore defers to.

---

## FORWARD CHECK 2026-08-16 — the evidence half of this KILL has expired

> Re-run on the 6 sessions that happened AFTER this doc froze (2026-08-07 .. 2026-08-14, 98
> positions), using this doc's OWN `positions_from_scratch()` and `max_concurrent()` verbatim
> (L251 — a second implementation would silently disagree). **Method validated first:** the
> frozen-window cut reproduces the published table exactly — 1 = −1,896.00 (35 cd / 54 pos),
> 3 = +1,769, 5 = +2,350, every count matching. Only then was the new window read.

**The single number this KILL rested on has flipped sign.**

| max concurrent arms | frozen ≤08-06 | NEW >08-06 | |
|---|---:|---:|---|
| 1 | −1,896.00 | −1,107.00 | |
| 2 | −679.00 | −841.00 | |
| **3** | **+1,769.00** | **−2,675.00** | 🔴 **sign flip** |
| 4 | +238.00 | +242.00 | |
| 5 | +2,350.00 | *(no 5-arm days)* | |
| **3+ combined** | **+4,357** | **−2,433** | |

The whole new window is net −$4,381, so a negative bucket proves nothing on its own.
**Normalised against each window's own mean, the buckets did not merely weaken — they swapped
places:**

| arms | frozen: mean/pos (vs window +8.57) | NEW: mean/pos (vs window −44.70) |
|---|---:|---:|
| 1 (lonely) | −35.11 (**−43.68**, worst) | −33.55 (**+11.16**, better than average) |
| 3 | +43.15 (**+34.58**, best ex-5) | −99.07 (**−54.37**, worst) |
| 4 | +3.61 (−4.96) | +10.08 (**+54.79**, best) |

The lonely end and the 3-arm end traded positions outright — a ~55-point swing for 1-arm and
an ~89-point swing for 3-arm, in per-position terms.

### What this does and does not license

**DOES:** stop citing "concentration is not where the loss dollars live" as settled. It
described a 26-date sample; it does not describe the book as of 2026-08-14. Anything that
inherits this table as a premise needs to re-derive it first.

**DOES NOT: this is not a case for arming a concentration cap.** Three reasons, and I want them
on the record so nobody reads the sign flip as a green light:
1. **4-arm is the BEST bucket in the new window** (+54.79 vs window). A cap at 3 would block
   precisely the bucket that is currently carrying the book.
2. **This doc's kill was mechanical as well as empirical** — "a cap on the pile-on is a pure
   leverage reduction, it removes winners and losers in the same proportion." That argument is
   independent of the slope and has NOT been retested here.
3. **n is small and the win rates are wild** (6% to 71% across frozen buckets). One 4-arm
   cluster on 2026-08-14 (−$1,497) and one on 2026-08-13 (+$2,151) move these totals by more
   than the totals themselves.

### The generalisable point

This doc was rigorous — 47/47 assertions, a second independent code path, an explicit n-small
caveat — and its central table still decayed to the point of inversion in **ten days**. The
defect was never the analysis; it is that a frozen conclusion shipped **without a revalidation
clock**, so nothing was scheduled to notice when it stopped being true. That is the same class
as the armed-gate recency doctrine, applied to research findings rather than to gates.

Nothing was armed, disarmed, or re-armed by this check. Analysis only.
