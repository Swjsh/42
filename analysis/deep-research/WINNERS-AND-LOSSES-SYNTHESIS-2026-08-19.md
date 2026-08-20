# WINNERS AND LOSSES — SYNTHESIS

**Written:** `2026-08-20 00:11:52 Thursday EDT` (`setup/scripts/et_clock.py`, `market_hours=False`).
Filed under the 2026-08-19 session. **ANALYSIS AND PROPOSAL ONLY** — nothing armed, no
`params*.json` touched, no order placed, no engine file edited. Every recommendation below is a
pre-registered hypothesis with a named kill criterion. J alone decides what ships.

**Process disclosure, first, because it changes how you read this file:** the two Opus matrix
lanes (bigger-winners, smaller-losses) **returned an empty result set** to this synthesis
(`ALL RESULTS: []`). Nothing was handed up to rank. Rather than synthesize a void, this session
re-derived the arithmetic spine from the ledger itself and ran the counterfactuals that the
lanes' substrate actually supports. **Every number in this file was computed fresh this session
and is reproducible from the sources named in §7** — none is inherited from a lane report.

---

## ⛔ VERDICT BOX

> ### The single highest-EV change available is **already written, already pre-registered, already FDR-cleared — and its forward clock expired today.**
>
> **`R_tp100_f50`** — for the `ribbon_ride` family, keep TP1 at +100% but sell **half** the
> position instead of two-thirds, leaving a bigger runner.
> (`analysis/recommendations/prereg-tp1-reachability-2026-08-06.json`, frozen and committed
> **before** its runner existed — git-provable at commit `24c4832d`.)
>
> It was the **only** Benjamini-Hochberg survivor of a 28-cell family (p=0.002617, q=0.10). It
> passes 7 of 8 frozen gates and 3 of 4 auto-ratify bar components. It failed **one** gate —
> G4 sub-window stability — and it failed it on **dispersion, not on sign**: all four sub-windows
> are positive (+$228.95 / +$333.20 / +$253.20 / +$94.70); two of them simply carry fewer than
> 5 changed trades. That is a **power failure, not evidence against.**
>
> The prereg named the exact condition that would resolve it:
> *"Re-adjudicate when risky-1's live +50% arm reaches n≥30 ribbon fills post-2026-08-03."*
>
> **VERIFIED THIS SESSION: risky-1 has 31 ribbon-family round trips post-2026-08-03. The clock
> has expired. The re-adjudication is owed.**
>
> **Honest probability the effect is real: ~35%.**
> For: pre-registered before the run, 1-of-28 BH survivor, walk-forward 0.80, OOS delta +$347.90,
> survives drop-best-trade (+$725.10) and drop-best-day (+$725.10), and it *improves* the runner
> anchor (+$628.05) rather than trading it away. Against: the only population broad enough to
> test it is a **replay**, not live fills; on our own arms the week-book effect (+$593.95) is
> **entirely 2026-08-04** (+$1,060.20 that day, −$155/session across the other three); and 35
> live sessions is one VIX regime. 35% is not a green light. It is "this is the one thing in the
> building that has earned a forward test."
>
> **Nothing else in this synthesis clears its refutation.** Everything else below is either a
> null, a protect-what-we-have finding, or a flagged provenance question. That is the correct
> answer from this data, and it is stated as such rather than dressed up.

---

## 1. The framing question, answered with arithmetic

### 1.1 The "1.6 percentage points" figure needs correcting before it is acted on

The 1.6pp gap is real but it is **population-specific**: it describes the n=63
`core-decisions`-matched subpopulation of **safe-2 + bold-2 only**, measured **gross**. The
book-wide, cost-inclusive number is larger. All three are correct; they answer different
questions. Recomputed fresh this session from `fills_fifo.mine_real_arm_fills` +
`setup/scripts/cost_model.py`:

| population | n | win rate | avg win | avg loss | breakeven WR | **gap** |
|---|---:|---:|---:|---:|---:|---:|
| core subset, safe-2+bold-2, gross (the quoted figure) | 63 | 26.98% | $278.80 | $111.60 | 28.59% | **1.60 pp** |
| **whole book, 5 arms, 303 trips, NET of real fees** | 303 | 23.10% | $223.63 | $75.51 | 25.24% | **2.14 pp** |
| **signal level** (collapse arms trading the same contract same day) | 108 | 22.22% | $566 | $185 | 24.60% | **2.38 pp** |

**Use 2.14pp as the book number and 2.38pp as the honest one.** The signal-level row is the
independence-correct unit: 303 round trips collapse to **108 distinct (date, contract) signals**,
63% of which were traded by more than one arm. The gap gets *wider*, not narrower, once you stop
double-counting — because collapsing arms concentrates the same wins and losses into fewer,
larger observations.

Reconciliation to the ledger: gross **−$1,805.00**, regulatory fees **−$134.90**, CAT
**−$1.08**, **net −$1,940.98**. This matches `analysis/recommendations/trade-matrix.json`
`totals.net_incl_cat` to the cent, and `trade-matrix`'s own `crosscheck_vs_fills_fifo` reports
`AGREE` with zero problems.

### 1.2 The same gap in the three units that matter

- **−$1,940.98** total, over 35 sessions and 303 round trips
- **−$55.46 per session**
- **−$6.41 per round trip**

### 1.3 Four ways to close it — the exchange rate

Net avg win **$223.63**, net avg loss **$75.51**, ratio **2.96×**. To erase −$1,940.98:

| lever | required move | equivalent |
|---|---|---|
| **A. More winners** | convert **6.5** losing trades into average winners | **+2.14 pp** win rate |
| **B. Bigger winners** | avg winner $223.63 → **$251.36** | **+12.4%** on the tail |
| **C. Smaller losers** | avg loser $75.51 → **$67.18** | **−11.0%** per loss |
| **D. Fewer costs** | eliminate *all* fees | **only 7.0%** of the deficit ($136 of $1,941) |

**Lever D is worth stating out loud so it stops being a suspect: costs are not the problem.**
Total regulatory drag is $135.98, $0.449 per round trip. Even a frictionless account is still
−$1,805. Any story that blames fees for this book is wrong by a factor of 14.

**Levers B and C are within touching distance of each other — 12.4% vs 11.0%.** That is the
whole strategic question in one line: the book needs roughly **one-eighth more tail or
one-ninth less bleed.** Neither is a heroic number. Both are inside the range that a single
exit-side parameter plausibly moves. That is why the exit side is where this synthesis spends
its attention, and why the entry side is not re-litigated.

---

## 2. THE RANKED DECISION LIST

Ranked by expected value net of the probability it is an artifact. Each carries the measured
effect **gross and after costs**, what would have to be true for it to be wrong, and a kill
criterion.

---

### #1 — RE-ADJUDICATE the frozen TP1 prereg `R_tp100_f50` *(the only live candidate)*

**The change:** `ribbon_ride` only — `tp1_qty_fraction` 0.667 → **0.50**, `tp1_premium_pct`
stays +100%. Sell half at TP1, run half. No other knob moves; `profit_lock_arm_scope` stays
`post_tp1` in every cell of the family, so this is **not** the five-times-dead pre-TP1
arm-scope knob — that mechanical distinction is declared in the prereg itself.

**Measured effect (from the frozen scorecard, `tp1-reachability-2026-08-06.json`):**

| metric | value |
|---|---:|
| popA (391-day replay, n=191) aggregate delta | **+$910.05** |
| popA ex-best-trade | +$725.10 |
| popA drop-best-day | +$725.10 |
| popA runner-anchor cohort delta | **+$628.05** (improves, does not trade away) |
| popA OOS (2026-01-01..07-22) delta | +$347.90 |
| walk-forward fraction | **0.80** (bar: ≥0.70) |
| raw p-value / BH family | **0.002617** / 1 survivor of 28 at q=0.10 |
| week-book (our 5 arms, 08-03..06) total delta | +$593.95 |
| TP1 fire rate, popA | 20.4% |

**Costs:** the popA and week-book deltas are **exit-price deltas on the same contracts at the
same entries** — the entry-side fee is identical in both arms of the comparison, and the
exit-side fee difference is a fraction of a cent per contract on changed proceeds. **The gross
and net effect are the same number to within ~$1 across the whole population.** This is the one
lever in this file where costs genuinely do not matter, because it changes *when* you sell, not
*how often* you trade.

**How much of the 2.14pp gap it closes:** popA delta is +$910.05 across 31 changed trades =
**+$29.36 per TP1-firing trade**. Our book has **40 ribbon-family TP1 exits**. Scaled:
**+$1,174 → 60.5% of the −$1,941 deficit → 1.29 pp of the 2.14 pp gap.**

> ⚠️ **That scaling is a cross-population extrapolation and must be labelled as one.** The
> alternative estimate — extrapolating our own week-book (+$593.95 over 4 sessions) to 35
> sessions — gives +$5,197, which is absurd, and **flips to −$5,440 the moment you remove
> 2026-08-04.** The week sample is too short and too 08-04-dependent to carry any extrapolation.
> The popA-scaled 60.5% is the defensible figure precisely because popA is 391 days deep and
> survives its own drop-best-day test. Treat 60.5% as a central estimate with wide, asymmetric
> error bars, not a forecast.

**What would have to be true for this to be wrong:** that the runner's edge in the 391-day
replay does not exist in live fills — i.e. that the replay's exit model
(`walk_exit_manager` → the real `exit_manager.plan_exit_actions`) is systematically kinder to a
held runner than a real market sell is. Given the established fact that **exits in this rig are
already credited ~0.13 of the traded range better than a real market sell**
(`setup/scripts/exit_fill_realism.py`), and that a bigger runner means *more* exposure to that
optimism, this is a live and specific concern, not a hypothetical.

**KILL CRITERION (inherited verbatim from the frozen prereg, not invented here):**
> Cell-attributable net **≤ −$300 over the first 10 live sessions**, OR live runner-cohort
> regression (any 2 live runner trades worse than their control counterfactual).

**Status: FORWARD-TEST ELIGIBLE, NOT SHIP-ELIGIBLE.** `clears_full_bar: false` in its own
scorecard. The auto-ratify rail (OP-11) requires sub-window stability and it does not have it.
The correct next move is the re-adjudication the prereg itself specifies — run risky-1's live
+50% A/B against its own control now that n=31 ≥ 30 — **not** to soften G4 to let it through.

---

### #2 — DO NOT TIGHTEN THE STOP. *(A protect-what-we-have finding. Closes 0pp — prevents losing ~1.5pp.)*

**The change: none. This is a "do not do the obvious thing" item**, and it is the highest-
confidence finding in this entire session.

Measured this session across all 302 path-covered round trips — **how deep did eventual winners
dig before they paid?** (MAE excluding the entry bar, so it is C6-clean):

| winners whose MAE reached | count | share of all 70 winners | winner P&L they carry |
|---|---:|---:|---:|
| −10% or worse | 33 | 47.1% | **$8,518** |
| −15% or worse | 20 | 28.6% | $5,196 |
| **−20% or worse** | **12** | **17.1%** | **$3,035** |
| −25% or worse | 7 | 10.0% | $2,291 |
| −30% or worse | 5 | 7.1% | $1,769 |
| **−50% or worse** | **0** | **0.0%** | **$0** |

**Read the −20% row against the deficit.** The winners that a strictly-enforced −20% premium
stop would have killed carry **$3,035 — that is 19.4% of all winner dollars, and 1.56× the
entire −$1,941 book deficit.** Tightening the stop does not shave losers; it decapitates the
right tail that is the only thing making this book nearly work.

**Read the −50% row too:** **zero** eventual winners ever dug past −50%. The existing −50%
catastrophe cap has **never cut a winner on this sample.** It is correctly placed and costs
nothing. Leave it exactly where it is.

This is corroborated by the direct counterfactual: a tighter-stop overlay was tested at
−10/−15/−20/−25/−30/−40/−50% across all 302 trades. **Every width except one is worse than
baseline, and the surface is non-monotonic** (−50%: −$2,233, −40%: −$3,014, −30%: −$2,326,
−25%: −$2,352, −20%: −$1,830, −15%: −$2,292, −10%: −$2,636 vs baseline −$1,931). A knob whose
response surface has no monotone structure is measuring noise, not a mechanism (C14).

**KILL CRITERION for this finding itself:** if a future window shows ≥5 winners with MAE past
−50%, the catastrophe cap is no longer free and this analysis must be redone.

---

### #3 — AUDIT THE PROVENANCE OF THE `VWAP_CONTINUATION` FAMILY *(not a filter — a governance question)*

**The observation.** Net P&L by setup family, all 302 path-covered trips, net of costs:

| setup family | n | WR | net | avg/trade | days |
|---|---:|---:|---:|---:|---:|
| BULLISH_RECLAIM_RIDE_THE_RIBBON | 153 | 20.3% | **+$112** | +$0.7 | 19 |
| BEARISH_REJECTION_RIDE_THE_RIBBON | 75 | 29.3% | **+$88** | +$1.2 | 20 |
| bollinger_squeeze | 17 | 35.3% | −$96 | −$5.6 | 11 |
| vix_regime_dayside | 4 | 0.0% | −$154 | −$38.5 | 2 |
| VWAP_RECLAIM_FAILED_BREAK (both casings) | 8 | 12.5% | −$419 | −$52.4 | 6 |
| **VWAP_CONTINUATION (both casings)** | **45** | **22.2%** | **−$1,461** | **−$32.5** | 9 |

The **ribbon family (228 trips) is net +$199. The VWAP family (53 trips incl. reclaim variants)
is net −$1,881** — 97% of the book's entire deficit, from 17.5% of the trades.

**And here is why it is NOT a recommendation to drop it.** Refuted on this project's own C4
concentration doctrine:

- **2026-08-05 alone is 72.8% of the family's loss. The worst two days are 96.2%.**
- 53 trips collapse to only **21 distinct signals** across **11 days**.
- Dropping the family also destroys **$1,513 of winner dollars (11 winners)**, including the two
  largest 08-04 winners (+$640 risky-1, +$523 risky-3).
- LOO is 35/35 "positive" — **and that is not reassurance.** When an effect is a large negative
  sum, removing any single day still leaves it negative. LOO only fails when one day carries
  >100% of the effect. **On a 96%-two-day effect, LOO has no power.** This is the same false
  comfort that the midday filter produced in `LOSER-SEPARABILITY-2026-08-19.md` before it was
  killed on exactly these grounds.

**What survives refutation is not a trade filter — it is a provenance question.** The frozen TP1
prereg states plainly that popA (the 391-day replay) is a **ribbon-family population** and
therefore **"popA cannot test vwap … these cells are DESCRIPTIVE / n-small labeled, ineligible"**
to ship. So: **`VWAP_CONTINUATION` is trading live on these arms with no validation on the only
deep population this project owns.** That is an OP-32 constraint-provenance question — *why is
this family armed, and on what evidence?* — and it should be answered before its P&L is either
defended or blamed.

**KILL CRITERION for opening the audit:** if the provenance audit surfaces a ratification record
with popA-equivalent depth, close the question and leave the family alone. If it surfaces none,
the family belongs in shadow until it has one — but **that decision is J's, and it is a
governance call, not something this data supports as a statistical filter.**

---

## 3. REFUTED — every candidate that died, and what killed it

| candidate | headline that attracted it | **what killed it** |
|---|---|---|
| **Target at +200%, full size** | Best cell of the whole grid: **+$3,384** net (−$1,931 → +$1,453), LOO 35/35 positive | **Fires on 10 of 302 trades — and they are ~4 signals.** 2026-07-29 C740 is the *same contract* on three arms; 2026-08-04 is two contracts on two arms. **Top 3 = 57.9%, top 5 days = 93.3%** of the delta. It is the **max of a 56-cell grid** searched on one 35-day sample, and it assumes a limit order fills at the **bar high** of a 0DTE option with a ~100¢ spread. |
| **Target at +150%** | +$2,973 | Same disease, worse: **13 of 18 improved trades touched the target on a bar that CLOSED BELOW it** — spike-only fills that a real limit order would very likely not get. |
| **Target at +100%** | +$1,554 | **Top 1 trade = 38.3%, top 3 = 81.5%** of the delta. Also degrades 15 trades by −$725. |
| **Any tighter stop (−10% … −50%)** | "cut losses small" | **Non-monotonic surface, every width but one below baseline.** §2 shows why: 17.1% of winners dig past −20%. Tightening cuts the tail, not the bleed. |
| **Breakeven stop after +K% favorable** | Best cell +$2,945 at K=+25% | **Sign-flips on a 3-cent fill assumption** (K=+30%: +$419 at 0¢, **−$92** at 2¢, +$1,009 at 5¢). Kills 11 winners. One signal swings **−$1,533**. A knob that inverts on a slippage assumption smaller than one tick is not a knob. |
| **WIDENING the stop** | The intuitive answer to "stopped out then it paid" | **Already SETTLED — do not re-open.** `STOPPED-THEN-PAID-2026-08-04.md`: widening turns 08-04 from −$1,111 to +$2,097, but the identical mechanism on 08-05 never turns profitable at any width (best −$613), and the **391-day matching archetype is monotonically WORSE at every width** (−$2,703.80 at −50%). Marked regime-conditional, not shippable. |
| **Drop the VWAP family** | Book −$1,931 → −$51 (97% of the deficit), LOO 35/35 | **96.2% of the effect is two days**; destroys $1,513 of winner dollars; LOO has no power on an effect of this shape. Survives only as the provenance question in §2/#3. |
| **All 7 pre-entry filters** | VIX, score margin, spread, quality rank, level distance, confluence, midday | Prior lane, `LOSER-SEPARABILITY-2026-08-19.md`. Six lost money outright; the survivor (block 11:30–13:00) was killed because it blocks 33% of the book, carries 66% two-day concentration, and would have cut the +$195 winner that motivated the question. |

**Six of the eight rows above were killed by the same two failure modes: day-concentration and
correlated-arm double-counting.** That is not eight independent refutations. It is one structural
fact about this dataset, discovered eight times.

---

## 4. INTERACTIONS — where these levers collide

**These are not independent knobs. Stacking the individually-positive ones produces a jointly
negative book.** The grid proves it directly: baseline −$1,931; best target alone (+200%) gives
+$1,453; adding a −20% stop overlay to that same target drops it to **+$1,022**; adding −40%
drops it to **+$370**. Every stop overlay makes every target cell worse. Two "improvements",
stacked, give back a third to two-thirds of the gain.

| collision | winner | why |
|---|---|---|
| **#1 (bigger runner) vs #2 (any stop tightening)** | **#1 wins outright.** | They pull the same mechanism in opposite directions. #1 keeps more contracts alive past TP1 precisely so they can reach the right tail; any tighter stop increases the chance that surviving size is killed on the way. **You cannot hold a bigger runner and a tighter stop and expect both effects.** Choose the runner. |
| **#1 (TP1 fraction) vs the target grid (+150/+200%)** | **#1 wins.** | They are the *same finding seen twice*. Every top-delta trade in the +200% cell exited at `tp1` — the "target edge" is literally "we took TP1 and the contract kept running." #1 expresses that mechanism as a **pre-registered, FDR-controlled, 391-day-validated fraction change**; the target grid expresses it as an **unregistered max-of-56-cells on 4 signals**. Same insight, one of them has evidence. |
| **Strike vs sizing** | **Neither ships; they are one decision.** | Established: dollar gain falls monotonically as you go OTM while percent gain rises. `STRIKE-MATRIX-2026-08-18.md` shows ITM-2's apparent +$65.69/trade vs ATM's +$41.88 is **2.6–2.9× the notional** — a bigger bet, not a better strike, and the ranking **inverts** on capital-normalized return. Any strike change is a size change wearing a disguise, and must be evaluated at constant risk or not at all. |
| **#1 (bigger runner) vs strike** | **Unresolved, and it matters.** | A bigger runner held further OTM decays faster; the same fraction change on ITM-1 and OTM+2 are not the same trade. The TP1 prereg holds strike fixed. **If #1 is ever re-adjudicated, strike must stay frozen** or the two effects become inseparable — the exact C29 failure (exit knobs ratified on one strike tier don't transfer to another). |
| **Cost model vs everything** | **Costs are neutral here.** | At $0.449/round trip, fees change no ranking in this file. They only bite on levers that change trade *count* — and no lever in the surviving list does. |

---

## 5. WHAT IS UNKNOWABLE FROM THIS DATA

These are not caveats appended for form. Two of them are structural and one is disqualifying.

**5.1 — The path data cannot answer the question the lanes were sent to answer.**
Verified this session: **0 of 302 rows in `trade-matrix.json` carry a single bar after the
actual exit** (max delta between last path bar and exit timestamp: −0.0 minutes). The option
price series terminates the instant we sold.

This means:
- **"Would a WIDER stop have recovered?"** — **structurally undecidable.** The trade exited at
  the tighter stop; what the contract did afterwards is simply not in the file.
- **"Would we have made MORE by holding past our exit?"** — **structurally undecidable** for any
  exit that was final.
- Only **tighter stops and earlier targets** are computable, because those fire *inside* the
  observed window. That is the entire computable universe on this substrate — and it happens to
  be **the wrong half**, since §2 shows tightening is destructive.

**This is very likely why both lanes returned nothing. It is a data-availability gap, not a
statement about the market.** Closing it requires re-fetching full-session 1-minute OPRA bars for
every traded contract, not more analysis of the current file. **That is the single highest-value
piece of infrastructure work this synthesis can point at**, and it is a prerequisite for ever
answering the winners question properly.

**5.2 — We have never had an out-of-sample period.**
Engine-replay depth equals the live-trading window: **35 sessions, 2026-06-26 → 2026-08-19.**
Every number in this file is in-sample. The 391-day popA replay is the *only* thing resembling
breadth in this building, and it is a **replay** — same code, same assumptions, synthetic exit
path — not independent evidence. Every recommendation here carries that caveat, and #1 carries
it doubly because its 60.5% gap-closure figure is extrapolated *from* popA.

**5.3 — One VIX regime, and one day.**
- **VIX at entry never left 14.41–19.86** across all 303 trades and all 35 sessions. Daily median
  VIX max: 19.86. **This book has never traded a VIX-20+ tape.** Nothing here generalizes to a
  volatility expansion, and the right-tail mechanic that everything depends on is exactly the
  thing a regime change would alter.
- **2026-08-04 net +$3,613 is 186% of the book's entire net deficit.** Ex-that-one-day the book
  is **−$5,554**. Ex-top-5-days: **−$10,683**. Only **12 of 35 days (34.3%)** are positive.
  **All five arms peaked on the same day**, which is the correlation warning made visible.
  Any counterfactual measured on this book is, mechanically, a statement about a handful of days.

**5.4 — n is not what it looks like.**
303 round trips → **108 distinct (date, contract) signals** → **49 (date, side) waves**. 63% of
signals were traded by more than one arm. The five arms run one shared signal at r=0.846 /
95.7% sign agreement. **Never quote 303 as a sample size.** Every table in this file that
matters has been recomputed at signal level, and the gap gets worse (2.38pp), not better.

**5.5 — Two disclosed data gaps, not resolved here.**
- 5 exits carry no logged reason (`fleet_eod.py` force-flattens and only prints), one of them
  −$440. Excluded from no analysis, but their exit stage is unknown.
- `stop_mode` is populated as structure=143 / premium=75 / None=84, yet `exit_stage` records
  **154 premium_stop firings**. Those two do not reconcile. Flagged, not investigated — it does
  not change any number above, but it means the configured-stop field cannot be trusted as a
  description of what actually fired.

---

## 6. PRE-REGISTRATIONS

Nothing below is armed. Nothing edits params. Each is a hypothesis with a kill criterion.

**PR-1 — `R_tp100_f50` re-adjudication (INHERITED, clock expired).**
Hypothesis: on `ribbon_ride`, selling 0.50 rather than 0.667 at a +100% TP1 raises net expectancy
via the runner. Test as specified by the frozen prereg: risky-1's live +50% arm A/B against its
own control, now that n=31 ≥ 30 ribbon fills post-2026-08-03.
**Kill:** cell-attributable net ≤ −$300 over the first 10 live sessions, OR any 2 live runner
trades worse than their control counterfactual.
**Do not** soften G4 to ship it. Re-adjudicate or leave frozen.

**PR-2 — Stop floor is protected, not tuned.**
Hypothesis: the −50% catastrophe cap costs zero winner-dollars and the −20% premium stop is
already inside the noise band. **Kill:** ≥5 eventual winners in any future window show MAE past
−50%, at which point the cap is no longer free and §2 must be recomputed.

**PR-3 — VWAP-family provenance audit (governance, not statistics).**
Hypothesis: `VWAP_CONTINUATION` is armed on these arms without popA-depth validation.
**Kill:** a ratification record with popA-equivalent depth is found → close the question, leave
the family alone. This is explicitly **not** a proposal to filter the family out on its P&L; that
version is refuted in §3 on two-day concentration.

**PR-4 — Post-exit path backfill (infrastructure prerequisite).**
Hypothesis: re-fetching full-session 1-minute OPRA bars for every traded contract makes the
wider-stop and held-longer questions decidable for the first time. **Kill:** if OPRA coverage
for the 2026-06-26 → 2026-08-19 window proves unavailable or gap-ridden, say so and close the
lane rather than substituting a synthetic path — a modelled post-exit path would reintroduce
exactly the look-ahead this file exists to avoid.

---

## 7. REPRODUCTION

All figures recomputed this session. Sources, in order of authority:

- `automation/state/fleet/fills_fifo.py#mine_real_arm_fills` — FIFO round trips, `attribution=="engine"`, per arm
- `setup/scripts/cost_model.py#fee_breakdown` — OCC/ORF/TAF/SEC, `fee_total_ex_cat`; CAT applied per arm-day
- `analysis/recommendations/trade-matrix.json` — canonical 303-row table (built 2026-08-19 22:00 ET); `crosscheck_vs_fills_fifo: AGREE`
- `analysis/recommendations/prereg-tp1-reachability-2026-08-06.json` + `tp1-reachability-2026-08-06.json` — frozen prereg + scorecard
- `analysis/deep-research/LOSER-SEPARABILITY-2026-08-19.md` — the pre-entry null
- `analysis/deep-research/STOPPED-THEN-PAID-2026-08-04.md` — the settled widen-the-stop verdict
- `analysis/deep-research/STRIKE-MATRIX-2026-08-18.md` — strike/notional confound
- `setup/scripts/exit_fill_realism.py` — the ~0.13-of-range exit optimism

**Every counterfactual in §2–§4 resolves non-firing trades to their ACTUAL realized outcome** and
uses bars strictly after the entry bar (C6). Ties within a bar resolve to the stop (conservative).
No row was dropped silently; the 1 row lacking path data (303 → 302) is disclosed at every use.

---

## Bottom line for J

**The losers were never separable, and this file does not find a way to make them so. What it
finds is that the one lever with real evidence behind it was already written two weeks ago,
already survived a 28-cell FDR correction, and was left frozen pending a forward clock that
expired today.** Re-adjudicating `R_tp100_f50` is the highest-EV move available — at ~35%
confidence, closing perhaps 1.29 of the 2.14 points needed.

**Everything else says: don't touch the stop, don't chase the target grid, and find out why the
VWAP family is armed.**

And the most useful thing in this document may be §5.1: **the question "would we have made more
by holding longer" is not answerable with the data we currently keep.** That is fixable, and
fixing it is worth more than another pass over the same 35 days.
