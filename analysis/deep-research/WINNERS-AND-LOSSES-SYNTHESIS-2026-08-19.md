# WINNERS AND LOSSES — SYNTHESIS

**Written:** `2026-08-20 00:55:09 Thursday EDT` (`setup/scripts/et_clock.py`, `market_hours=False`).
Filed under the 2026-08-19 session. **ANALYSIS AND PROPOSAL ONLY** — nothing armed, no
`params*.json` touched, no order placed, no engine file edited. Every recommendation below is a
pre-registered hypothesis with a named kill criterion. J alone decides what ships.

**Revision note (this pass):** an earlier version of this file was written when the two Opus
matrix lanes had returned an empty set. **They have since returned four candidates, and all four
have been through adversarial refutation. All four were REFUTED.** This revision folds those four
results in (§3), adds one convergent population finding that this session then refuted against
itself (§3.6), and re-verifies the arithmetic spine from the canonical ledger. Numbers recomputed
fresh this session are marked ✅ and are reproducible from the sources in §7.

---

## ⛔ VERDICT BOX

> ### NULL RESULT. Four lanes, four candidates, four refutations. Nothing new survived.
>
> The bigger-winners lane and the smaller-losses lane between them produced **four** surviving
> candidates — a strike clamp, a sizing floor, a trailing-stop mode, and a re-entry cooldown.
> **Every one died under refutation, and three died on the same structural fact: leave-best-two-
> days-out flips the sign.** Details in §3. This is the correct answer from this data, and it is
> stated as a null rather than dressed into a recommendation.
>
> ### The single highest-EV change available is one that was already written two weeks ago.
>
> **`R_tp100_f50`** — for the `ribbon_ride` family, keep TP1 at +100% but sell **half** the
> position instead of two-thirds, leaving a bigger runner.
> (`analysis/recommendations/prereg-tp1-reachability-2026-08-06.json`, frozen and committed
> **before** its runner existed — git-provable at commit `24c4832d`.)
>
> It was the **only** Benjamini-Hochberg survivor of a 28-cell family (p=0.002617, q=0.10). It
> passes 7 of 8 frozen gates and 3 of 4 auto-ratify bar components. It failed **one** gate —
> G4 sub-window stability — and it failed it on **dispersion, not on sign**: all four sub-windows
> are positive (+$228.95 / +$333.20 / +$253.20 / +$94.70); two simply carry fewer than 5 changed
> trades. That is a **power failure, not evidence against.**
>
> The prereg named the exact condition that would resolve it:
> *"Re-adjudicate when risky-1's live +50% arm reaches n≥30 ribbon fills post-2026-08-03."*
> **risky-1 has 31 ribbon-family round trips post-2026-08-03. The clock has expired. The
> re-adjudication is owed.**
>
> **Honest probability the effect is real: ~35%.**
> For: pre-registered before the run, 1-of-28 BH survivor, walk-forward 0.80, OOS delta +$347.90,
> survives drop-best-trade and drop-best-day (+$725.10 both), and it *improves* the runner anchor
> (+$628.05) rather than trading it away. Against: the only population deep enough to test it is a
> **replay**, not live fills; on our own arms the week-book effect (+$593.95) is **entirely
> 2026-08-04**; and 35 live sessions is one VIX regime. 35% is not a green light. It is "this is
> the one thing in the building that has earned a forward test."
>
> ### The second-highest-EV action is a DELETION THAT MUST NOT HAPPEN.
>
> The sizing lane's only "execute now" item was *delete the cheap-premium boost knob*. Refutation
> found it **computed on the wrong population**: 8 of its 20 rows were never boosted fills at all
> (5 pre-date the knob's arming, 2 are ladder-elite, 1 sits on a dead equity-scaler day). The true
> boosted population is **n=12, net +$116 — positive.** Its own kill bar requires NET<0.
> **The bar is not triggered. Executing that deletion would remove a knob on the strength of P&L
> from trades it never made.** See §2/#3.

---

## 1. The framing question, answered with arithmetic

### 1.1 The "1.6 percentage points" figure could not be reproduced — and the real gap is WIDER

The brief's framing number is **1.60pp** (n=63, safe-2+bold-2, gross). ✅ **This session could not
reproduce that population from the canonical 303-row table, and says so rather than repeating it.**
All 101 safe-2+bold-2 rows carry `engine_state_source = core-decisions:exec.broker.id`, so
"core-decisions-matched" does not narrow 101 → 63; no date cutoff lands on 63 either (62 through
2026-08-07, 64 through 2026-08-10). The n=63 subset comes from a different or earlier build.

What **is** reproducible, computed fresh from `trade-matrix.json` (built 2026-08-19 22:00 ET,
`crosscheck_vs_fills_fifo: AGREE`):

| population | n | win rate | avg win | avg loss | breakeven WR | **gap** |
|---|---:|---:|---:|---:|---:|---:|
| safe-2 + bold-2, **all rows**, gross | 101 | 23.76% | $207.08 | $80.81 | 28.07% | **+4.31 pp** |
| safe-2 + bold-2, all rows, net incl CAT | 101 | 23.76% | $206.74 | $81.14 | 28.19% | **+4.42 pp** |
| **whole book, 5 arms, 303 trips, gross** | 303 | 23.10% | $224.06 | $75.06 | 25.09% | **+1.99 pp** |
| **whole book, 5 arms, 303 trips, NET incl CAT** | 303 | 23.10% | $223.63 | $75.51 | 25.24% | **+2.14 pp** ✅ |

**Use 2.14pp as the book number.** The quoted 1.6pp tells the same qualitative story — the book is
a hair short of breakeven — but on the reproducible population the shortfall is **larger, not
smaller.** Every gap-closure percentage below is denominated against **2.14pp / −$1,940.98**.

Ledger reconciliation ✅: gross **−$1,805.00**, regulatory fees **−$134.90**, CAT **−$1.08**,
**net −$1,940.98**.

### 1.2 The same gap in the three units that matter ✅

- **−$1,940.98** total, over 35 sessions and 303 round trips
- **−$55.46** per session
- **−$6.41** per round trip

### 1.3 Four ways to close it — the exchange rate ✅

Net avg win **$223.63**, net avg loss **$75.51**, ratio **2.96×**. Converting one loser into an
average winner is worth **$299.14**. To erase −$1,940.98:

| lever | required move | equivalent |
|---|---|---|
| **A. More winners** | convert **6.49** losing trades into average winners | **+2.14 pp** win rate |
| **B. Bigger winners** | avg winner $223.63 → **$251.36** | **+12.4%** on the tail |
| **C. Smaller losers** | avg loser $75.51 → **$67.18** | **−11.0%** per loss |
| **D. Fewer costs** | eliminate *all* fees | **only 7.0%** of the deficit ($136 of $1,941) |

**Lever D is stated out loud so it stops being a suspect: costs are not the problem.** Total
regulatory drag is $135.98, **$0.449 per round trip.** Even a frictionless account is still
−$1,805. Any story that blames fees for this book is wrong by a factor of 14.

**Levers B and C are within touching distance — 12.4% vs 11.0%.** The book needs roughly
**one-eighth more tail or one-ninth less bleed.** Neither is heroic. Both sit inside the range a
single exit-side parameter plausibly moves. That is why this synthesis spends its attention on the
exit side, and why the entry side is not re-litigated (`LOSER-SEPARABILITY-2026-08-19.md` settled it).

### 1.4 ⭐ THE ONE NUMBER TABLE — how much of the 2.14pp gap each candidate closes

Every matrix collapsed into one column. This is the conversion the brief asked for.

| candidate | claimed net effect | % of −$1,941 deficit | **pp of the 2.14pp gap** | status |
|---|---:|---:|---:|---|
| TRAIL_25 stop mode | +$4,030 | 207% | **4.44 pp** | ❌ REFUTED |
| Drop the watcher lane | +$2,139 | 110% | **2.36 pp** | ❌ REFUTED (this session, §3.6) |
| MINCON-FLAT sizing floor | +$1,529 | 78.8% | **1.69 pp** | ❌ REFUTED |
| **`R_tp100_f50` TP1 fraction** | **+$1,174** (scaled) | **60.5%** | **1.29 pp** | ⚠️ **LIVE — forward-test eligible, ~35%** |
| Re-entry cooldown 3 min | +$1,031 | 53.1% | **1.14 pp** | ❌ REFUTED |
| Re-entry cooldown, *defensible* subset | +$548 | 28.2% | **0.60 pp** | ❌ REFUTED (0.02σ of one day) |
| Strike clamp OTM+2→ATM (flat cost) | +$737 | 38.0% | **0.81 pp** | ❌ REFUTED |
| Strike clamp (strike-corrected cost) | +$364 | 18.8% | **0.40 pp** | ❌ REFUTED |
| **Do NOT tighten the stop** | **protects $3,035** | **avoids −156%** | **avoids −1.56 pp** | ✅ **PROTECT** |
| **Do NOT delete the boost knob** | **protects +$116** | **6.0%** | **0.13 pp** | ✅ **PROTECT** |

> **Read the table this way.** The only positive-EV row with evidence behind it closes **1.29 of
> the 2.14 points — roughly 60%, not all of it.** Every row that appears to close *more* than the
> whole gap is refuted, and that is not coincidence: **an effect larger than the deficit itself,
> discovered on 35 days, is a concentration artifact almost by construction.** The two PROTECT rows
> are worth more than they look — they are the only rows with no artifact risk, they cost nothing,
> and they prevent a loss.

---

## 2. THE RANKED DECISION LIST

Ranked by expected value net of the probability it is an artifact. Each carries the measured
effect **gross and after costs**, what would have to be true for it to be wrong, and a kill
criterion.

---

### #1 — RE-ADJUDICATE the frozen TP1 prereg `R_tp100_f50` *(the only live candidate)*

**The change:** `ribbon_ride` only — `tp1_qty_fraction` 0.667 → **0.50**, `tp1_premium_pct` stays
+100%. Sell half at TP1, run half. No other knob moves; `profit_lock_arm_scope` stays `post_tp1`
in every cell of the family, so this is **not** the five-times-dead pre-TP1 arm-scope knob — that
mechanical distinction is declared in the prereg itself.

**Measured effect** (frozen scorecard `tp1-reachability-2026-08-06.json`):

| metric | value |
|---|---:|
| popA (391-day replay, n=191) aggregate delta | **+$910.05** |
| popA ex-best-trade / drop-best-day | +$725.10 / +$725.10 |
| popA runner-anchor cohort delta | **+$628.05** (improves, does not trade away) |
| popA OOS (2026-01-01..07-22) delta | +$347.90 |
| walk-forward fraction | **0.80** (bar: ≥0.70) |
| raw p / BH family | **0.002617** / 1 survivor of 28 at q=0.10 |
| week-book (our 5 arms, 08-03..06) delta | +$593.95 |
| TP1 fire rate, popA | 20.4% |

**Gross vs net:** the popA and week-book deltas are **exit-price deltas on the same contracts at
the same entries**. Entry-side fees are identical on both sides of the comparison; the exit-side
fee difference is a fraction of a cent per contract on changed proceeds. **Gross and net are the
same number to within ~$1 across the whole population.** This is the one lever in this file where
costs genuinely do not matter, because it changes *when* you sell, not *how often* you trade.

**Gap closure:** popA delta +$910.05 across 31 changed trades = **+$29.36 per TP1-firing trade**.
Our book has **40 ribbon-family TP1 exits** (of 44 total `tp1` exits ✅). Scaled: **+$1,174 →
60.5% of the deficit → 1.29 pp of the 2.14 pp gap.**

> ⚠️ **That scaling is a cross-population extrapolation and is labelled as one.** The alternative
> — extrapolating our own week-book (+$593.95 over 4 sessions) to 35 sessions — gives +$5,197,
> which is absurd, and **flips to −$5,440 the moment 2026-08-04 is removed.** The week sample is
> too short and too 08-04-dependent to carry any extrapolation. The popA-scaled 60.5% is the
> defensible figure precisely because popA is 391 days deep and survives its own drop-best-day
> test. Treat 60.5% as a central estimate with wide, asymmetric error bars — not a forecast.

**What would have to be true for this to be wrong:** that the runner's edge in the 391-day replay
does not exist in live fills — i.e. that the replay's exit model (`walk_exit_manager` → the real
`exit_manager.plan_exit_actions`) is systematically kinder to a held runner than a real market sell
is. Given the established fact that **exits in this rig are already credited ~0.13 of the traded
range better than a real market sell** (`setup/scripts/exit_fill_realism.py`), and that a bigger
runner means *more* exposure to that optimism, this is a live and specific concern, not a
hypothetical. **This is the most likely way #1 fails.**

**KILL CRITERION** (inherited verbatim from the frozen prereg, not invented here):
> Cell-attributable net **≤ −$300 over the first 10 live sessions**, OR live runner-cohort
> regression (any 2 live runner trades worse than their control counterfactual).

**Status: FORWARD-TEST ELIGIBLE, NOT SHIP-ELIGIBLE.** `clears_full_bar: false` in its own
scorecard. The auto-ratify rail (OP-11) requires sub-window stability and it does not have it. The
correct next move is the re-adjudication the prereg specifies — risky-1's live +50% A/B against
its own control at n=31 ≥ 30 — **not** softening G4 to let it through.

---

### #2 — DO NOT TIGHTEN THE STOP *(protect-what-we-have; closes 0pp, prevents losing ~1.56pp)*

**The change: none.** This is a "do not do the obvious thing" item, and it is the
highest-confidence finding in the entire session.

✅ Recomputed this session across all 70 winners (100% path coverage) — **how deep did eventual
winners dig before they paid?** MAE excluding the entry bar, so it is C6-clean:

| winners whose MAE reached | count | share of winners | winner $ carried | vs book deficit |
|---|---:|---:|---:|---:|
| −10% or worse | 33 | 47.1% | **$8,518.10** | 4.39× |
| −15% or worse | 20 | 28.6% | $5,195.52 | 2.68× |
| **−20% or worse** | **12** | **17.1%** | **$3,034.88** | **1.56×** |
| −25% or worse | 7 | 10.0% | $2,290.84 | 1.18× |
| −30% or worse | 5 | 7.1% | $1,768.76 | 0.91× |
| −40% or worse | 2 | 2.9% | $1,203.98 | 0.62× |
| **−50% or worse** | **0** | **0.0%** | **$0.00** | **0.00×** |

**Read the −20% row against the deficit.** Winners that a strictly-enforced −20% premium stop
would have killed carry **$3,034.88 — 19.4% of all winner dollars, and 1.56× the entire −$1,941
deficit.** Tightening the stop does not shave losers; it decapitates the right tail that is the
only thing making this book nearly work.

**Read the −50% row too:** ✅ **zero** eventual winners ever dug past −50%. The existing −50%
catastrophe cap has **never cut a winner on this sample.** It is correctly placed and costs
nothing. Leave it exactly where it is.

Corroborated by direct counterfactual: a tighter-stop overlay tested at −10/−15/−20/−25/−30/−40/−50%
across all 302 path-covered trades is **worse than baseline at every width but one, and the surface
is non-monotonic** (−50%: −$2,233 · −40%: −$3,014 · −30%: −$2,326 · −25%: −$2,352 · −20%: −$1,830 ·
−15%: −$2,292 · −10%: −$2,636 vs baseline −$1,931). A knob whose response surface has no monotone
structure is measuring noise, not a mechanism (C14).

**Gross vs net:** this item changes no trade count, so fees are identical on both sides. Gross and
net protection are the same $3,034.88 to within $0.45/trip.

**KILL CRITERION:** if a future window shows **≥5 eventual winners with MAE past −50%**, the
catastrophe cap is no longer free and §2/#2 must be recomputed from scratch.

---

### #3 — DO NOT DELETE THE CHEAP-PREMIUM BOOST KNOB *(protect; the lane's only "execute now" item is wrong)*

**The change: none — specifically, do not execute the sizing lane's Stage 1.**

The sizing lane recommended deleting `fleet_executor.py` L1271-1282's cheap-premium boost (sets
`_boosted_qty = 10` when `premium < $0.50` and `10 > planned_qty`) on the strength of a 20-row
population netting **−$675**. Refutation found the population is wrong:

- The knob was armed **2026-08-03 17:53 ET**, after the close — first eligible session 2026-08-04.
- **5 rows pre-date arming** (2026-06-29, 07-02, 07-06 ×3) — the knob did not exist.
- **2 rows are qty-12** — impossible for this knob, which can only ever produce exactly 10; qty 8/12
  are the risky ladder's base/elite tiers.
- **1 row sits on the dead 2026-08-14 equity-scaler day** the lane's own document excludes everywhere else.
- Those **8 misattributed rows carry −$791.**

**True boosted population: n=12 fills over 5 sessions.**

| reading | net |
|---|---:|
| as traded | **+$116.31** |
| marginal vs qty 5 | **+$57.96** (cutting to 5 would have *lost* $58) |
| marginal vs the qty-8 ladder base | **+$20.36** |

The pre-registered bar is *"n≥10 boosted fills or 10 sessions, NET<0 → delete."* The n-threshold is
met (12 ≥ 10); **the NET<0 condition is FALSE on all three readings**, and only 5 sessions have
elapsed. **Zero of three ways out, not the claimed four of four. The kill bar is not triggered.**

**Honesty note, against my own recommendation:** the +$58 is *also* unusable as evidence *for* the
knob — top-session share is 305% (2026-08-10 alone is +$177). This is not "the boost knob works."
It is **"the deletion is unjustified and the measurement must be redone on the right rows."**

**KILL CRITERION:** re-measure on the **true boosted population only** (arm=risky-3, premium<$0.50,
resulting qty **exactly 10**, date ≥ 2026-08-04, excluding 2026-08-14). Delete the knob when that
population reaches **n≥10 fills AND ≥10 sessions AND net<0 on the marginal-vs-ladder-base reading.**
Until all three hold, the knob stays.

---

### #4 — AUDIT THE PROVENANCE OF THE NON-RIBBON "WATCHER" LANE *(governance, not a filter)*

✅ Recomputed fresh this session. Net P&L by setup family, all 303 trips, net incl CAT:

| setup family | n | WR | gross | **net** | verdict |
|---|---:|---:|---:|---:|---|
| BULLISH_RECLAIM_RIDE_THE_RIBBON | 153 | 20.3% | +$182.00 | **+$111.02** | core |
| BEARISH_REJECTION_RIDE_THE_RIBBON | 75 | 29.3% | +$119.00 | **+$87.38** | core |
| BOLLINGER_SQUEEZE | 17 | 35.3% | −$91.00 | −$95.81 | watcher |
| VIX_REGIME_DAYSIDE | 4 | 0.0% | −$153.00 | −$154.13 | watcher |
| VWAP_RECLAIM_FAILED_BREAK | 8 | 12.5% | −$416.00 | −$419.49 | watcher |
| **VWAP_CONTINUATION** | **46** | **21.7%** | **−$1,446.00** | **−$1,469.94** | watcher |

Collapsed to the two lanes ✅:

| lane | n | WR | gross | **net** |
|---|---:|---:|---:|---:|
| **CORE RIBBON** (both `*_RIDE_THE_RIBBON`) | 228 | 23.2% | +$301.00 | **+$198.40** |
| **WATCHER LANE** (everything else) | 75 | 22.7% | −$2,106.00 | **−$2,139.38** |

**The core ribbon lane is net POSITIVE. The watcher lane carries 110% of the book's entire deficit
from 24.8% of the trades.** Note the win rates are nearly identical (23.2% vs 22.7%) — **this is
not a win-rate difference, it is a payoff-shape difference**, exactly what a right-tail book should
be measured on.

**But this is NOT a recommendation to drop the lane — see §3.6, where this session refutes it.**
It survives only as an **OP-32 constraint-provenance question**. The frozen TP1 prereg states
plainly that popA is a **ribbon-family population** and therefore *"popA cannot test vwap … these
cells are DESCRIPTIVE / n-small labeled, ineligible"* to ship. **So the watcher families are
trading live with no validation on the only deep population this project owns.** The question is
*why are they armed, and on what evidence?* — governance, not statistics.

**KILL CRITERION for opening the audit:** if the audit surfaces a ratification record with
popA-equivalent depth, close the question and leave the families alone. If it surfaces none, they
belong in shadow until they have one — **but that is J's call, and it is a governance decision,
not something this data supports as a statistical filter.**

---

## 3. REFUTED — every candidate that died, and what killed it

### 3.1 THE FOUR LANE CANDIDATES

| # | candidate | headline | **what killed it** |
|---|---|---|---|
| **A** | **Strike clamp** — force OTM+2-or-wider → ATM (117 rows) | +$219 gross / **+$737 net**, 19/26 days | **Fires its own kill criterion #4 at baseline.** Post-clamp median contract count on the clamped rows is **1** (84/117 at exactly 1; 82.9% below 3) — the criterion is literally *"median falls below 3 → the clamp must never recreate the ITM-2 problem."* It recreates it, and **violates Rule 6's min-3-contracts floor.** These are the book's *cheapest* signals (that is why they sit at OTM+2); a $30 budget cannot buy 3 ATM lots. Also: the flat $0.010/ctr cost is **contradicted by the data it came from** — measured traded-range is strike-dependent (ITM-2 $0.187 → OTM+2 $0.074), so a corrected cost cuts +$737 → **+$364** and pushes top-day share 35.3% → **66.3%**, firing kill criterion #3 too. Leave-best-2-out: gross **−$151**, corrected net **−$17**. Cluster bootstrap CI straddles zero (flat [−$357, +$1,756]; corrected [−$696, +$1,352]). |
| **B** | **MINCON-FLAT** — flat 3/5 min-contract sizing floor | **+$1,529** net forward-available | **Its "execute now" Stage 1 is computed on the wrong population and its sign is reversed** (see §2/#3 — this is the single most consequential error found in any lane). Headline itself is **arithmetic, not information**: on a losing book *any* de-levering shows positive delta — **trading nothing beats MINCON-FLAT by $1,364**, and the lane's own FLAT-1 beats it. A leverage-matched control explains only 17% of the raw delta; the remaining 83% shape residual **evaporates on leave-two-days-out** (per-contract gap +$0.78 → **+$0.01**, and both cells turn positive). Sign flips at leave-best-2-out: +$1,529 → **−$113**. Bootstrap p05 **−$276**, failing its own stated promotion bar. |
| **C** | **TRAIL_25** — 25% trailing stop, ratcheting | **+$4,030** net (SAFE shape) | **The right-tail tax its own kill criterion forbids.** Criterion #4: winner dollars falling >15% vs control is *"the signature that must NOT appear."* Against a **shape-matched** control (PREMIUM_50, identical upside rule): winner$ **−45.8% / −39.7%** — **2.6–3× the kill threshold.** The only control it looks fine against runs a *different* upside rule. Sharpest instance: the book's #1 realized winner (2026-08-06 risky-3 **+$830**) becomes **−$256** — a −$1,086 swing on the largest right-tail event in the book. Leave-best-2-out flips the sign in **all four** comparisons. Concentration was **understated ~45% by a denominator mismatch** (per-DAY numerator over per-TRADE denominator): true 0.311/0.187 vs published 0.216/0.107. |
| **D** | **Re-entry cooldown** — 3 min, same symbol, after stop exit | **+$1,031** net, LOO sign-stable 35/35 | **Search noise beats it.** p=0.051 was computed for a single cell **selected from a 90-cell scan**; best-of-75 random 15-trade removals gives **p(random ≥ +$1,031) = 0.982**, and the cell ranks **40th of 90**. Mechanism falsified where the money is: 2026-08-05 carries **69.2%** of the effect, where all 10 legs lost and exit→entry gaps of 1.0–6.0 min **discriminated nothing** — entry premium decayed monotonically, so removing later legs of a decaying series *looks* skillful by construction. **Delete-vs-delay is wrong in the direction that matters:** 7 of 15 blocked trades have an **observed** same-symbol successor within 20 min — the arm re-entered anyway. Defensible saving is **+$548 = $15.70/day against a daily-net stdev of $1,041 = 0.02σ.** |

### 3.2 The common cause — this is ONE refutation discovered four times

**Three of the four (A, B, C) die on leave-best-two-days-out. All four die on some form of
selection-on-the-same-sample.** Counting them as four independent negative results overstates the
evidence. They are **one structural fact about this dataset**, found four times:

> ✅ **The book has 35 days, 12 of them positive. 2026-08-04 alone is +$3,612.78 — 186% of the
> entire net deficit. Ex-best-day the book is −$5,553.76; ex-top-5-days it is −$10,682.70.**
> Any counterfactual measured here is, mechanically, a statement about a handful of days.

**Leave-ONE-out has no power on this shape and must stop being quoted as a robustness test.** Every
refuted candidate above passed LOO. Three of them failed the moment a *second* day was removed.
**From this point on, leave-best-TWO-out is the minimum bar in this repo.**

### 3.3 A methodological finding worth more than any candidate

**Candidate C's concentration metric was computed with mismatched units** — a per-DAY numerator over
a per-TRADE denominator. Because per-trade deltas cancel within a day, the denominator inflates and
concentration reads ~45% too low (0.216 published vs 0.311 true). **The same document used the
correct per-day measure to disqualify a rival cell at 49.8%.** Two standards were in play, and the
looser one landed on the author's own nomination.

**This is a bug that flatters whatever it measures, and it is in shipped tooling**
(`backtest/tools/stop_mode_screen_2026_08_19.py:39-57`). Flagged; not fixed here (scope).

### 3.4 Previously-refuted candidates (retained from the prior pass)

| candidate | headline | what killed it |
|---|---|---|
| Target at +200%, full size | +$3,384 net | Fires on **10 of 302 trades ≈ 4 signals**; top 3 = 57.9%, top 5 days = 93.3%. Max of a 56-cell grid; assumes a limit fills at the **bar high** of a ~100¢-spread 0DTE option. |
| Target at +150% | +$2,973 | **13 of 18** improved trades touched the target on a bar that **CLOSED BELOW it** — spike-only fills a real limit order likely never gets. |
| Target at +100% | +$1,554 | Top 1 trade = 38.3%, top 3 = 81.5% of the delta. Degrades 15 trades by −$725. |
| Any tighter stop (−10%…−50%) | "cut losses small" | Non-monotonic surface, every width but one below baseline. §2/#2 shows why. |
| Breakeven stop after +K% favorable | +$2,945 at K=+25% | **Sign-flips on a 3-cent fill assumption** (K=+30%: +$419 at 0¢, **−$92** at 2¢, +$1,009 at 5¢). A knob that inverts on less than one tick is not a knob. |
| WIDENING the stop | the intuitive answer | **Already SETTLED — do not re-open.** `STOPPED-THEN-PAID-2026-08-04.md`: 08-04 turns +$2,097, but 08-05 never turns profitable at any width, and the **391-day archetype is monotonically WORSE at every width** (−$2,703.80 at −50%). |
| All 7 pre-entry filters | VIX, score margin, spread, quality, level distance, confluence, midday | `LOSER-SEPARABILITY-2026-08-19.md`. Six lost money outright; the survivor blocked a +$195 winner. |

### 3.5 What SURVIVED refutation (stated because it is real, and small)

- ✅ **"Some stop beats no stop"** — unanimous, 34/34 cells. NO_STOP on the ribbon shape is
  **−$13,169**. The existence of a stop is not in question; only its width and mode.
- ✅ **"Don't sit at OTM+2"** survives as a *qualitative* de-risking statement — OTM+2 is never
  positive under any single-day removal. It does **not** survive as a quantified clamp.
- ✅ **Candidate C's own headline verdict** — *"the stop MODE axis does not separate, 0 of 34 cells
  pass"* — survives and is corroborated. What was refuted was the best-cell nomination that followed it.
- ✅ **No look-ahead was found in any lane's simulation code.** All four are C6-clean at the bar
  level. Every failure was **selection**, not leakage. That is a real credit to the harness.

### 3.6 ⚠️ AND THE ONE THIS SESSION REFUTED AGAINST ITSELF

The watcher-lane split (§2/#4) is the strongest *convergent* signal in the whole exercise — the
cooldown lane and the earlier VWAP analysis reached it independently, from different directions.
**Convergence made it look like corroboration. It is not.** ✅ Refuted this session on this repo's
own C4 doctrine:

| test | result |
|---|---:|
| effect of dropping the watcher lane | **+$2,139.38** |
| ex worst-1 lane day (2026-08-05) | **+$770.19** — one day is **64.0%** of the effect |
| ex worst-2 lane days | **+$321.06** |
| ex worst-3 lane days | **+$82.70** — effectively zero |
| winner dollars destroyed | **−$1,722.83** across **17 winners** |
| independence | 75 trips → **34 distinct (date, contract) signals** on 19 days |
| the lane's own best day | **2026-08-04: +$716.55** — its best day is the book's best day |

**Two independent lanes converging on the same population is not independent evidence when both are
reading the same two days.** That is the single most important methodological lesson of this
session, and it applies to my own finding, not just to the lanes'. The watcher-lane split stays a
**governance question (§2/#4), not a filter.**

---

## 4. INTERACTIONS — where these levers collide

**These are not independent knobs. Stacking the individually-positive ones produces a jointly
negative book.** The grid proves it directly: baseline −$1,931; best target alone (+200%) gives
+$1,453; adding a −20% stop overlay drops it to **+$1,022**; adding −40% drops it to **+$370**.
Every stop overlay makes every target cell worse. Two "improvements", stacked, give back a third
to two-thirds of the gain.

| collision | winner | why |
|---|---|---|
| **#1 (bigger runner) vs ANY stop tightening** | **#1 wins outright** | They pull the same mechanism in opposite directions. #1 keeps more contracts alive past TP1 *precisely so they can reach the right tail*; any tighter stop raises the chance that surviving size is killed on the way. **You cannot hold a bigger runner and a tighter stop and expect both effects.** Choose the runner. |
| **Strike vs stop mode** | **They are ONE mechanism, not two** | ✅ Verified this session: `premium_stop` firing rate rises as premium falls — ATM 36.6% (median $1.08) → OTM+2 59.0% ($0.36) → OTM+3 75.6% ($0.27). **A percentage stop on a $0.27 premium is measuring the spread, not the market.** This is why 71% of the strike lane's clamped rows exited on `premium_stop` and carried 176% of its effect. **The "strike clamp" was a stop finding wearing a strike label.** Governing the clamp by stop policy swings it 2.7× (+$1,926 at −20%, +$715 at −35%/+150%) with strike held fixed. **Any future strike work must hold the stop policy fixed, and vice versa, or the two are inseparable.** |
| **Strike vs sizing** | **Neither ships; they are one decision** | Dollar gain falls monotonically as you go OTM while percent gain rises. `STRIKE-MATRIX-2026-08-18.md`: ITM-2's apparent +$65.69/trade vs ATM's +$41.88 is **2.6–2.9× the notional** — a bigger bet, not a better strike — and the ranking **inverts** on capital-normalized return. The sizing lane independently confirmed it: changed rows were **57.4% OTM+2** vs 4.4% for unchanged, so MINCON-FLAT was **partially laundering a strike effect as a sizing effect.** Any strike change is a size change in disguise and must be evaluated at constant risk or not at all. |
| **#1 (bigger runner) vs strike** | **Unresolved, and it matters** | A bigger runner held further OTM decays faster; the same fraction change on ITM-1 and OTM+2 are not the same trade. The TP1 prereg holds strike fixed. **If #1 is re-adjudicated, strike must stay frozen** or the effects become inseparable — the exact C29 failure (exit knobs ratified on one strike tier don't transfer to another). |
| **Sizing floor vs the right tail** | **Sizing loses** | ✅ On 2026-08-19 all three winners (bold-2 +$189, safe-3 +$202, risky-1 +$292) were **already at min_contracts**, so MINCON-FLAT could not touch them at all. **A lever structurally incapable of amplifying winners, on a book whose only money is a right tail, is not the lever** — regardless of its P&L delta. |
| **Cooldown vs the watcher lane** | **The population question dominates** | The cooldown's 15 blocks are **15/15 watcher-lane setups, 0/15 core ribbon** — it is a low-power sampler of the §2/#4 population, not a churn mechanism. Its matched-control test is decisive: blocked trades **won MORE often** than their controls (20.0% vs 7.4%). If the watcher lane is the question, ask it directly; do not proxy it through a cooldown. |
| **Cost model vs everything** | **Costs are neutral here** | At $0.449/round trip, fees change no ranking in this file. They bite only on levers that change trade *count* — and no surviving lever does. **But cost is NOT neutral across strikes**: the strike-dependent traded-range correction alone cut the strike clamp by 51%. Flat per-contract cost assumptions are safe within a strike tier and unsafe across them. |

---

## 5. WHAT IS UNKNOWABLE FROM THIS DATA

Not caveats appended for form. Two are structural and one is disqualifying.

**5.1 — The path data cannot answer half the question the lanes were sent to answer.**
✅ **0 of 302 rows carry a single bar after the actual exit** (max delta between last path bar and
exit timestamp: −0.0 minutes). The option price series terminates the instant we sold. Therefore:

- *"Would a WIDER stop have recovered?"* — **structurally undecidable.**
- *"Would we have made MORE by holding past our exit?"* — **structurally undecidable** for any final exit.
- Only **tighter stops and earlier targets** are computable, because those fire *inside* the
  observed window. That is the entire computable universe on this substrate — and it is **the
  wrong half**, since §2/#2 shows tightening is destructive.

This is a **data-availability gap, not a statement about the market**, and it is very likely why
both lanes converged on tightening-flavoured candidates: *those are the only ones the file can
express.* Closing it requires re-fetching full-session 1-minute OPRA bars for every traded
contract. **That is the highest-value infrastructure work this synthesis can point at**, and a
prerequisite to ever answering the winners question properly.

**5.2 — We have never had an out-of-sample period.**
Engine-replay depth **equals** the live-trading window: **35 sessions, 2026-06-26 → 2026-08-19.**
Every number in this file is in-sample. The 391-day popA replay is the only thing resembling
breadth in this building, and it is a **replay** — same code, same assumptions, synthetic exit path
— not independent evidence. **Every recommendation carries this caveat, and #1 carries it doubly**
because its 60.5% gap-closure figure is extrapolated *from* popA.

**5.3 — One VIX regime, and one day.**
- ✅ **VIX at entry never left 14.41–19.86** across all 303 trades and all 35 sessions. **This book
  has never traded a VIX-20+ tape.** Nothing here generalizes to a volatility expansion — and the
  right-tail mechanic everything depends on is exactly what a regime change would alter.
- ✅ **2026-08-04 net +$3,612.78 is 186% of the book's entire deficit.** Ex-that-day: **−$5,553.76.**
  Ex-top-5-days: **−$10,682.70.** Only **12 of 35 days (34.3%) are positive.** All five arms peaked
  on the same day — the correlation warning made visible.

**5.4 — n is not what it looks like.**
303 round trips → **108 distinct (date, contract) signals** → **49 (date, side) waves.** 63% of
signals were traded by more than one arm; the five arms run one shared signal at r=0.846 / 95.7%
sign agreement. **Never quote 303 as a sample size.** Refutation confirmed this bites hardest
exactly where effects concentrate: the cooldown's decisive day had **n_effective = 1**, not 2,
because two arms entered the same legs seconds apart.

**5.5 — Two disclosed data gaps, not resolved here.**
- ✅ **5 exits carry no logged reason** (`fleet_eod.py` force-flattens and only prints), together
  **−$505.92**, one of them −$440. Dropped from no analysis, but their exit stage is unknown.
- ✅ **`stop_mode` does not reconcile with `exit_stage`**: `stop_mode` is populated structure=143 /
  premium=75 / None=84, yet `exit_stage` records **154 `premium_stop` firings.** Flagged, not
  investigated. It changes no number above, but **the configured-stop field cannot be trusted as a
  description of what actually fired** — which matters directly for any future stop-mode work.

---

## 6. PRE-REGISTRATIONS

Nothing below is armed. Nothing edits params. Each is a hypothesis with a kill criterion.

**PR-1 — `R_tp100_f50` re-adjudication (INHERITED; clock expired).**
*Hypothesis:* on `ribbon_ride`, selling 0.50 rather than 0.667 at a +100% TP1 raises net expectancy
via the runner. *Test:* as the frozen prereg specifies — risky-1's live +50% arm A/B against its own
control, now that n=31 ≥ 30 ribbon fills post-2026-08-03. **Strike must stay frozen** (C29).
**Kill:** cell-attributable net ≤ **−$300 over the first 10 live sessions**, OR any 2 live runner
trades worse than their control counterfactual. **Do not soften G4 to ship it.**

**PR-2 — Stop floor is protected, not tuned.**
*Hypothesis:* the −50% catastrophe cap costs zero winner-dollars and the −20% premium stop already
sits inside the noise band. **Kill:** ≥5 eventual winners in any future window show MAE past −50%,
at which point the cap is no longer free and §2/#2 must be recomputed.

**PR-3 — Boost-knob deletion is blocked pending correct measurement.**
*Hypothesis:* the cheap-premium boost knob's true population is net-positive and its kill bar is
untriggered. *Test:* re-measure on arm=risky-3, premium<$0.50, resulting qty **exactly 10**,
date ≥ 2026-08-04, excluding 2026-08-14. **Kill (i.e. delete the knob):** that population reaches
**n≥10 fills AND ≥10 sessions AND net<0 on the marginal-vs-ladder-base reading.** All three, or the
knob stays.

**PR-4 — Watcher-lane provenance audit (governance, not statistics).**
*Hypothesis:* the non-ribbon families (VWAP_CONTINUATION, VWAP_RECLAIM_FAILED_BREAK,
BOLLINGER_SQUEEZE, VIX_REGIME_DAYSIDE) are armed without popA-depth validation. **Kill:** a
ratification record with popA-equivalent depth is found → close the question, leave them alone.
**Explicitly NOT a proposal to filter the lane on its P&L** — that version is refuted in §3.6 on
two-day concentration.

**PR-5 — Post-exit path backfill (infrastructure prerequisite).**
*Hypothesis:* re-fetching full-session 1-minute OPRA bars for every traded contract makes the
wider-stop and held-longer questions decidable for the first time. **Kill:** if OPRA coverage for
2026-06-26 → 2026-08-19 proves unavailable or gap-ridden, **say so and close the lane rather than
substituting a synthetic path** — a modelled post-exit path would reintroduce exactly the
look-ahead this file exists to avoid.

**PR-6 — Leave-best-TWO-out becomes the minimum robustness bar.**
*Hypothesis:* LOO has no power on a book where one day is 186% of the deficit; three of four lane
candidates passed LOO and failed at k=2. **Proposed standard:** no candidate is nominated in this
repo without reporting **leave-best-2-days-out** and **per-day/per-day concentration**. **Kill:**
if a future window's day-level P&L distribution becomes materially less concentrated (top day
< 50% of deficit), revisit whether k=2 is still necessary.

---

## 7. REPRODUCTION

All ✅ figures recomputed this session directly from the canonical table. Sources, in order of authority:

- `analysis/recommendations/trade-matrix.json` — canonical 303-row table (built 2026-08-19 22:00 ET);
  `crosscheck_vs_fills_fifo: AGREE`; `totals.net_incl_cat = −1940.98`
- `automation/state/fleet/fills_fifo.py#mine_real_arm_fills` — FIFO round trips, `attribution=="engine"`
- `setup/scripts/cost_model.py#fee_breakdown` — OCC/ORF/TAF/SEC, `fee_total_ex_cat`; CAT per arm-day
- `analysis/recommendations/prereg-tp1-reachability-2026-08-06.json` + `tp1-reachability-2026-08-06.json`
- `analysis/deep-research/LOSER-SEPARABILITY-2026-08-19.md` — the pre-entry null
- `analysis/deep-research/STOPPED-THEN-PAID-2026-08-04.md` — the settled widen-the-stop verdict
- `analysis/deep-research/STRIKE-MATRIX-2026-08-18.md` — strike/notional confound
- `setup/scripts/exit_fill_realism.py` — the ~0.13-of-range exit optimism
- Lane sources: `LOSSES-STOP-MODE-MATRIX-2026-08-19.md/.json`, `LOSSES-REENTRY-CHURN-MATRIX-2026-08-19.md/.json`,
  `LOSSES-STOP-MODE-SCREEN-2026-08-19.json`, `WINNERS-EXIT-TARGET-MATRIX-2026-08-19.json`

**Every counterfactual resolves non-firing trades to their ACTUAL realized outcome** and uses bars
strictly after the entry bar (C6). Ties within a bar resolve to the stop (conservative). No row was
dropped silently; the 1 row lacking path data (303 → 302) is disclosed at every use, and the 5
reason-less exits (−$505.92) are disclosed in §5.5.

---

## Bottom line for J

**Four lanes ran the full matrix over every trade ever taken. Four candidates survived to
refutation. All four died — three of them on the same fact: remove the two best days and the sign
flips.** That is a null result, and it is the honest answer.

**What is left is one lever and two things not to do.**

1. **`R_tp100_f50`** — written two weeks ago, FDR-cleared, frozen pending a forward clock **that
   expired today**. ~35% confidence, closes **~1.29 of the 2.14 points** needed. Re-adjudicate it.
2. **Do not tighten the stop.** 12 winners carrying **$3,035 — 1.56× the entire deficit** — dug
   past −20% before paying. Zero ever dug past −50%; the catastrophe cap is free where it sits.
3. **Do not delete the cheap-premium boost knob.** Its kill bar was read off the wrong rows; the
   true population is **n=12, +$116, positive.**

**The most valuable thing in this document is probably §5.1:** *"would we have made more by holding
longer"* is **not answerable with the data we currently keep** — the price series ends the instant
we sell. Both lanes were therefore structurally limited to proposing ways to *cut things shorter*,
on a book whose only money is a right tail. Fixing that data gap is worth more than another pass
over the same 35 days.

**And the discipline lesson, which applies to my own work in §3.6 as much as to the lanes':**
leave-one-day-out passed every single refuted candidate. On a book where one day is 186% of the
deficit, **LOO is not a robustness test.** Leave-best-two-out is now the bar.
