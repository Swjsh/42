# PIVOT — 0DTE SPY Premium-Selling Scorecard

**Date:** 2026-06-21 (Sunday, markets closed — offline cached-data research, $0 cost)
**Harness:** `backtest/autoresearch/_pivot_premium_selling.py` (full grid) + `backtest/lib/simulator_credit.py` (multi-leg OPRA-fills sim, built ALONGSIDE `simulator_real.py` — that file untouched) + `backtest/lib/multileg_structures.py` (leg geometry).
**Data:** Real OPRA 5m option fills, `backtest/data/options/` — **365 trading days, 2025-01-02 .. 2026-06-18.** SPY 5m master union (through 06-18). Per-leg fills priced bar-by-bar; net credit = sum of signed per-leg fills; short legs receive bid (open − $0.02 slip), long wings pay ask (open + $0.02 slip); commission $0.65/contract/side.
**Assigned structure:** **Call Credit Spread (CCS)** — bearish income (sell OTM call + buy further-OTM call), the bear-side income the directional book lacks. Grid also ran IC / PCS / IB / BWIC for context (900 cells total, 180 per structure).

---

## VERDICT: DEAD (for the assigned CCS)

The Call Credit Spread is **negative-expectancy on real OPRA fills across the ENTIRE 150-cell grid** (n≥20). It clears **zero** gate-bar axes that matter and the best cell does not beat a random-strike null. The pivot thesis ("selling should be STRONGER in the recent chop regime") is **falsified for CCS** — recency is consistently the WORST sub-window, not the strongest.

### CCS grid aggregate (150 cells with n≥20 trades)
| Gate axis | Cells passing |
|---|---|
| OOS-2026 expectancy/tr > 0 | **0 / 150** |
| Freshest-25-day (chop regime) expectancy > 0 | **0 / 150** |
| IS-2025-H1 expectancy > 0 | **0 / 150** |
| drop-WORST-5-days expectancy > 0 | **0 / 150** |
| Full gate (all axes) | **0 / 150** |

Best full-sample expectancy of ANY CCS cell: **−$5.04/tr.** Best OOS: **−$4.27/tr.**

### Best CCS cell (least-bad, by OOS expectancy) — `CCS 10:30 / short_offset=4 / wing=1 / pt=0.50 / stop=2.0x`
| Metric | Full sample | OOS-2026 | IS-2025-H1 | Freshest 25d (chop) |
|---|---|---|---|---|
| n | 141 (224 skipped, **61.4% skip-rate**) | 55 | 56 | 25 |
| expectancy/tr | **−$8.27** | **−$4.27** | −$12.56 | **−$11.28** |
| win-rate | 0.333 | — | — | — |
| posQ (OOS) | — | **1 of 2 quarters** | — | — |
| max single-day loss | −$61.6 | — | — | — |
| book maxDD | −$1,166 | — | — | — |
| drop-TOP-5 exp | −$9.88 | −$7.90 | — | — |
| drop-WORST-5 exp | **−$6.67** | — | — | — |
| avg credit collected | $14.09 | avg defined max-loss $85.9 | avg short-strike %OTM 0.62% | — |
| exit mix | STOP 64 / PT 73 / EOD 4 | intrabar-stop-would-have-hit: **78 / 141** | tail_survivable: True | — |

### Beats-random-null gate (L172) — FAILED
Random-strike null (same 10:30 entry + pt/stop management, short_offset drawn uniformly from {2,3,4} per day, 20 reps): **mean expectancy −$9.64/tr, range [−11.33, −8.03].**
The best structured CCS (−$8.27 full / −$4.27 OOS) sits **inside the null's noise band**. The (negative) result is generic theta drag of any in-band call-spread — **the strike/entry selection adds no edge.** Per L172, an "edge" that a random null reproduces is not an edge.

---

## Why CCS bleeds (root cause, honest)

1. **The OPRA cache band is the binding constraint, not a tuning detail.** The cache is a fixed ~$10-wide band (11 contiguous $1 strikes/side, ±$5 around ATM — `multileg_structures.band_strikes`). A CCS at short_offset=4 + wing=1 puts the long wing at ATM+5 (edge of band); offset=4 + wing=2 → ATM+6 → **100% skip.** The least-bad cell already SKIPS 61% of days. The cache **cannot price** the textbook 16-delta / 30-wide condor; we are forced into narrow $1 wings collecting ~$14 against ~$86 defined max-loss — a **6:1 risk:credit** ratio. One stop-out (−$86) erases ~6 winners.
2. **WR is a theta trap (C4 / L46).** Even at the better cells WR sits 33–55% (not the 70%+ a real OTM seller gets), because the narrow band forces near-the-money shorts (avg short strike only **0.62% OTM**). Selling 0.6%-OTM 0DTE calls is selling almost-ATM gamma — you eat every up-move.
3. **bar.close MTM understates stops (the classic seller backtest trap, already instrumented).** `intrabar_stop_would_hit = 78 / 141`: on 55% of trades the intrabar-worst MTM would have tripped the −200% stop even when the bar CLOSE did not. **Real fills would be worse than the −$8.27 headline**, not better.
4. **Recency falsifies the thesis.** The pivot bet was that premium-selling profits in the current chop. Across all 150 CCS cells the freshest-25-day expectancy is negative AND worse than full-OOS (best cell −$11.28 recency vs −$4.27 OOS). The recent regime has had enough sharp single-direction up-legs to steamroll near-ATM call sellers; "chop" at the index level still carries directional 0DTE thrusts that gut a 0.6%-OTM short call.

The tail (gate axis 4) is technically survivable per the kill-switch on a 1-lot (max day −$61.6, book DD −$1,166 ≈ ~2 Safe-kill-days of cushion) — but **survivable losses are still losses.** Tail-survivability does not rescue a structurally negative edge.

---

## Context: the other four structures (NOT the assigned deliverable, flagged for honesty)

| Structure | Best OOS exp/tr | Recency exp/tr | Gate-passers (900-cell grid) |
|---|---|---|---|
| PCS (bullish put CS) | −$1.21 | −$6.60 | 0 |
| **CCS (assigned)** | **−$4.27** | **−$11.28** | **0** |
| IB (iron fly) | +$2.68 | −$4.32 | 0 |
| BWIC (broken-wing IC) | +$8.54 | −$2.08 | 0 |
| **IC (iron condor)** | **+$23.03** | **+$9.00** | 0 |

**Whole-grid result: 0 of 900 cells pass the full gate.** PCS, IB, BWIC are all negative-or-marginal on recency. **One LEAD is worth a follow-up:** the IC cell `10:30 / off2 / w2 / pt0.5 / 1.5x` is POSITIVE on every magnitude axis — +$16.53 full, **+$23.03 OOS**, +$28.96 IS25, +$9.00 recency, **82.7% WR**, drop-worst-5 still **+$19.81**, tiny book DD (−$269). It fails the gate on ONE axis only: **posQ = 2 < 4**, which is **structurally unreachable** because OOS-2026 contains only 2 calendar quarters. That gate threshold is mis-specified for a 2-quarter OOS window. **BUT:** IC carries a **55.6% skip-rate** (needs BOTH sides in the ±$5 band → only trades narrow-range days = survivorship toward calm days), and a random-strike null has NOT yet been run for IC. Before IC could be called an EDGE it needs: (a) a random-strike/entry null (L172), (b) a band-skip survivorship check (is the +EV just "we only traded the calm days"?), (c) a posQ gate re-spec for the 2-quarter OOS. Filed as a LEAD, not shipped.

---

## Gate-bar scorecard (CCS, adapted premium-selling bar)

| # | Gate | Result |
|---|---|---|
| 1 | OOS-2026 expectancy/tr > 0 (net costs/slippage per leg) | **FAIL** (best −$4.27) |
| 2 | n ≥ 20 | PASS (best cell n_oos=55) |
| 3 | posQ ≥ 4 of 6 | **FAIL** (best=1; also structurally capped at 2 in OOS) |
| 4 | Tail-survivable (defined-risk, max-day + maxDD ≤ kill-switch) | PASS on 1-lot (−$62 day / −$1,166 DD) — but moot given neg EV |
| 5 | drop-top5 AND drop-WORST-5 both > 0 (both tails) | **FAIL** (drop-worst5 −$6.67; not a few-disaster-days artifact — it bleeds broadly) |
| 6 | Beats random-strike/entry null (L172) | **FAIL** (−$8.27 inside null band [−11.33, −8.03], mean −$9.64) |
| 7 | IS-2025-H1 expectancy > 0 | **FAIL** (best −$12.56) |
| 8 | Recency (freshest ~25d chop) ≥ full-OOS — thesis check | **FAIL / FALSIFIED** (recency WORSE: −$11.28 vs −$4.27) |

**CCS clears 1 of the 8 gate axes (n≥20 only). VERDICT: DEAD.**

---

## Doctrine note (candidate lesson)

The C3/L58 inversion thesis (selling theta inverts the long-premium tax) does **not** survive the cache's band constraint: forced near-ATM shorts (0.6% OTM) with 6:1 risk:credit narrow wings turn "theta income" back into negative-EV near-ATM gamma-selling. **Premium-selling in 0DTE SPY needs FAR-OTM short strikes (≈16-delta) that our ±$5 OPRA band cannot reach** — so the cache cannot validate the textbook condor, and the structures it CAN price are near-ATM and negative. Any future premium-selling research must first widen the OPRA cache band (fetch ±$15–$20 strikes) before the class can be honestly tested. Candidate lesson for `markdown/doctrine/LESSONS-LEARNED.md`.

---

## Files
- Harness: `backtest/autoresearch/_pivot_premium_selling.py`
- Sim: `backtest/lib/simulator_credit.py`, `backtest/lib/multileg_structures.py`
- Full 900-cell results: `backtest/autoresearch/_state/pivot_premium_selling/results.json`

---

## RESOLUTION — the IC LEAD is closed (2026-06-21, finalize pass)

The IC LEAD above (line 66) left three open items before IC could be called an EDGE:
(a) a random-strike/entry null (L172), (b) a posQ re-spec for the 2-quarter OOS window,
(c) the band-skip survivorship caveat. The finalize pass
(`backtest/autoresearch/_pivot_premium_finalize.py` → `.../finalize.json`) resolved (a)
and (b) decisively. **The IC LEAD does NOT clear the bar — final IC verdict: LEAD, not EDGE.**

### (b) posQ re-spec — PASSES (was a mis-specified gate, not a real failure)
The grid's `posQ` used calendar quarters; OOS-2026 spans only Q1+Q2 → max posQ = 2, so
`posQ>=4` was structurally unreachable for EVERY one of the 900 cells. Recomputed over **6
monthly OOS sub-windows (Jan–Jun 2026)**: the leading IC cells score **5/6 and 6/6** — PASS.
So posQ was never the real blocker; it was a window artifact. Disclosed and corrected.

### (a) Random-strike / random-entry null for IC — FAILS (the decisive result)
30-seed nulls on the same days/structure/wing/management as the real IC cells:

| IC cell | real OOS exp | strike-null mean | strike-null **p95** | beats strike? | entry-null p95 | beats entry? | beats-null |
|---|---|---|---|---|---|---|---|
| 10:30 o2 w2 pt.5 EOD | +$22.95 | +$19.36 | **+$26.03** | **NO** | +$13.71 | yes | **NO** |
| 10:30 o2 w2 pt.5 1.5× | +$23.03 | +$19.40 | **+$26.03** | **NO** | +$13.23 | yes | **NO** |
| 09:40 o2 w2 pt.5 2.0× | +$21.77 | +$16.44 | **+$27.19** | **NO** | +$13.25 | yes | **NO** |
| 11:00 o2 w2 pt.5 1.5× | +$18.88 | +$14.21 | **+$20.88** | **NO** | +$13.23 | yes | **NO** |

Randomizing the short strike each day among {2,3,4} **reproduces and at p95 EXCEEDS** the
"chosen" offset-2 IC expectancy. There is **no strike-selection alpha** — the +$23/tr is
generic theta any in-band narrow IC harvests, exactly the L172 trap that killed the 64
long-premium families, now confirmed in the inverse (selling) direction. IC beats only the
random-*entry* null, and only because the off-peak grid times (13:00/14:30) average worse —
that is the entry grid self-selecting, not a structural signal. **beats-null = strike AND
entry; strike = NO ⇒ gate 6 FAIL.**

### IC final gate-bar scorecard (best cell, IC 10:30 o2 w2 pt.5 EOD)
| # | Gate | Result | Pass |
|---|---|---|---|
| 1 | OOS expectancy/tr > 0 | +$22.95 | ✅ |
| 2 | n ≥ 20 (OOS) | 52 | ✅ |
| 3 | posQ ≥ 4/6 (monthly) | 5/6 | ✅ |
| 4 | tail-survivable (1-lot) | worst −$98 vs −$600; bookDD −$124 vs −$1800 | ✅ |
| 5 | drop-top5 AND drop-worst5 > 0 | +$17.2 / +$21.2 | ✅ |
| **6** | **beats random null (L172)** | **real < strike-null p95** | **❌** |
| 7 | IS-2025-H1 > 0 | +$28.96 | ✅ |
| 8 | recency (chop) > 0 | +$8.84 (09:40 cell +$19.96) | ✅ |

**7/8 — fails gate 6. NOT a ratifiable edge; must NOT ship under the standing
profitable-edge authorization** (that auth is for validated *edges*; a null-failing theta
artifact is the explicit L172 carve-out). The tail is benign ONLY because the $1–$2 wings cap
max-loss at $100–$200 — that does NOT generalize to a textbook 16-delta / 20–30-wide condor
(≈$3000 max-loss/lot) the ±$5 cache cannot price. Tail-survivability here is conditional on
staying narrow, which the band forces — not something we validated for a real condor.

### To convert LEAD → EDGE (only path)
Fetch a WIDE, delta-targeted OPRA band (true 16-delta short + 20–30-wide wing), re-test the
real max-loss tail, then find a *selection* rule (VIX-character / realized-range / time-regime
gate) that **beats the random-strike null**. Absent a null-beating selection rule, the only
honest framing is a passive mechanical theta sleeve sized for the REAL (not narrow) tail —
not a Gamma directional/selection edge.

### Web grounding (corroborates: 0DTE IC = generic theta, fragile tail, not selection alpha)
- [The Iron Condor Illusion in 0DTE — DataDrivenInvestor](https://medium.datadriveninvestor.com/the-iron-condor-illusion-in-0dte-3813faae9429)
- [Henry Schwartz's Zero-Day SPX Iron Condor Strategy — CBOE](https://www.cboe.com/insights/posts/henry-schwartzs-zero-day-spx-iron-condor-strategy-a-deep-dive/)
- [9,000-trade 0DTE Breakeven Iron Condor — Theta Profits](https://www.thetaprofits.com/my-most-profitable-options-trading-strategy-0dte-breakeven-iron-condor/)

### Lesson candidate (L-new)
*Premium-SELLING inverts the theta sign but NOT the L172 test: a defined-risk 0DTE condor that
is OOS-positive, broad-based, recency-positive AND tail-survivable can STILL be pure generic
theta harvest. Randomize the short strike/entry on the same days — if the random control
reproduces (or exceeds at p95) the "selected" expectancy, there is no selection edge no matter
how many other gates pass. Inverse-direction confirmation of C3/L58/L172.*

### Finalize artifact
- `backtest/autoresearch/_pivot_premium_finalize.py`
- `backtest/autoresearch/_state/pivot_premium_selling/finalize.json`

---

## IRON FLY (IB) deep-dive + independent replication (2026-06-21, second pass)

> This section is the **assigned-structure** deliverable for the IRON FLY (sell ATM straddle +
> OTM wings — highest credit, tightest range), plus an **independent re-run** of the full grid,
> the IC null, and the posQ fix on a separate harness pass. It **confirms** the CCS/IC sections
> above byte-for-direction; where my null seeds differ slightly the **conclusion is identical**.

### VERDICT for the IRON FLY: **DEAD**

The iron fly is the structure the spec flagged as "highest credit, tightest range" — and it is
the textbook *pick-up-pennies-in-front-of-a-steamroller* loser on real OPRA fills:

| IB best-OOS cell | full exp/tr | OOS exp/tr | WR | max day loss | **book maxDD** | tail-survivable |
|---|---|---|---|---|---|---|
| 10:30 off2 w2 pt0.5 1.5× | −$2.1 | **+$2.68** | 0.48 | −$110 | **−$1,378** | NO (in practice) |

- The ATM short straddle collects the fattest credit but is breached on essentially every
  trending day — WR collapses to **48%** (vs the OTM IC's 85%) and the book draws down
  **−$1,378** (11× the OTM IC's −$124). The "tightest range = highest credit" intuition is
  exactly inverted by realized fills: the tight range is the steamroller's blast radius.
- Even the least-bad IB cell is barely OOS-positive (+$2.68/tr) and **full-sample NEGATIVE**
  (−$2.1/tr) — it does not survive the friction ($21/lot on 4 legs) the fatter credit was
  supposed to overcome.
- **Iron fly fails gates 1 (full-sample exp ≤ 0), 4 (book DD blows past a sane sleeve cap),
  6 (no selection), and 8.** It is the clean negative control proving the pivot thesis is
  *conditional on the neutral-OTM structure*, NOT a generic "selling premium wins."

### Independent replication of the IC leader (confirms gate-6 FAIL)

Re-ran the full 900-cell grid (cold cache) + a separate null harness
(`_pivot_premium_selling_null.py`, 200 seeds) + a focused leader re-score
(`_pivot_premium_selling_focus.py`):

- **Full grid, posQ-fixed (monthly OOS sub-windows): 18 passers — 17 IC + 1 BWIC, 0 of the
  other families.** Leader cluster identical to the CCS-section finding: IC / off2 / w2 / pt0.5,
  entries 09:40–11:00.
- **IC 10:30 o2 w2 pt0.5 EOD null (mine):** actual +$22.95 vs **strike-offset null p95 +$25.44
  (actual at 76th pctile — does NOT beat)**; entry-time null p95 +$14.71 (actual 100th pctile —
  beats). **Same direction as the finalize pass above** ($26.03 p95): randomizing the short
  strike reproduces/exceeds the chosen offset → **no strike-selection alpha → gate 6 FAIL.**
- **IC 09:40 cell (mine):** actual +$21.01 vs strike-null p95 +$27.45 (81st pctile, no beat) /
  entry-null p95 +$14.71 (100th pctile, beats). Identical pattern.

**Two independent harness passes, two independent null seedings, same verdict:** the IC is
OOS-positive + tail-survivable + broad-based + recency-positive but **fails the L172
random-strike null** — it is well-*timed* generic theta, not strike-selection edge. Per the
OP-11/L172 carve-out this is **explicitly NOT shippable** under the standing profitable-edge
authorization (that authorization covers validated edges; a null-failing theta artifact is the
named exception).

### Net pivot conclusion (both passes agree)

- **CCS (bear credit spread): DEAD** — negative-expectancy, no null beat.
- **Iron Fly (IB): DEAD** — full-sample negative, −$1,378 book DD, the steamroller's favorite.
- **PCS (bull credit spread): DEAD** — −$10 to −$14/tr, −$2,709 book DD.
- **IC (neutral OTM condor): LEAD-not-EDGE** — clears 7 of 8 gates, fails gate 6 (strike-null).
  Worth the wider-OPRA-band fetch follow-up; **not shippable today.**

The long-premium death IS inverted by *neutral defined-risk* selling, but the inversion does
not buy a selection edge — it buys generic, friction-thin, near-ATM, 55%-skip theta whose tail
is benign only because the ±$5 cache band can't price a real (≈$3,000-max-loss) condor.
**No structure in the pivot clears the full adapted bar incl. beats-null + a tail validated for
a real (non-narrow) condor. Verdict: DEAD as a ratifiable edge; IC retained as a LEAD pending
a wide-band data fetch.**

**Sources:** [IncomeOptionsTrading — 0DTE IC backtest returns & risk](https://www.incomeoptionstrading.com/blog/zero-dte-ic-spx-backtest-returns-and-risk) · [Stonks Capital — 0DTE Iron Condors deep dive](https://stonkscapital.substack.com/p/0dte-basics-part-4-iron-condors-deep) · [OptionsTradingIQ — SPX 0DTE IC backtest](https://optionstradingiq.com/option-omega/)

---

## IC LEAD — assigned 4-check validation: completes checks 2 & 4, makes the null production-consistent + seed-robust (2026-06-21, third pass)

> This pass runs the **full assigned 4-check set** on the lead cell **`IC / 10:30 ET / off2 / w2 / pt0.50 / 1.5×`** in ONE reproducible artifact. Two checks (null, posQ) were already run by the finalize pass above; **two were never quantified for the IC cell (band-skip survivorship + intrabar-stop honesty)** — those are completed here. It **independently confirms** the finalize verdict and, importantly, **corrects a strike-universe parity bug** in the null (an under-filtered null had spuriously inflated the actual's percentile). Harness: `backtest/autoresearch/_pivot_premium_ic_validate.py` (+ `_pivot_premium_selling_null.py` at 500 iters × 3 seeds for the null cross-check). Pure offline, $0. `simulator_real.py` untouched.

### VERDICT (unchanged, now triple-confirmed + fully diagnosed): **LEAD, not EDGE — NOT shippable.**

The IC clears 7 of 8 gate axes but **fails gate 6 (beats-random-strike-null, L172)** — and the new work shows that failure is **robust**, not borderline. Per the OP-11/L172 carve-out a null-failing theta artifact is **explicitly excluded** from the standing profitable-edge authorization. Nothing was flipped live; `params*.json` untouched.

### CHECK 1 — random-strike / random-entry null (L172): **FAIL (production-consistent + seed-robust)**

A first 60-iter re-seed *spuriously passed* (strike-null p95 $22.67 < actual $23.03 → "95th pctile, beats"). Diagnosing that pass surfaced **two compounding causes**, the first more important:

1. **Null-strike-universe parity bug (OP-16, primary).** The production grid (`run_variant`) and the standalone null apply a `legs_in_band(half_width=5)` pre-filter, which **always drops off=4** (longC = ATM+6 is outside the ±$5 band). My first in-script null omitted it, so the random-offset null traded off=4 "if-cached" condors **production never takes** — polluting the null mean ($15.6 vs the true $19.7) and **inflating the actual's percentile to ~95th**. Mirroring production's band filter pulls it back to **~79th**.
2. **Low-iteration p95 noise (secondary).** A 60-sample p95 is a high-variance estimator; it only *mattered* because cause #1 had pushed the actual into the fragile 95th-pctile knife-edge. With production parity the actual is at ~76–79th — nowhere near the boundary, so iteration count no longer flips the verdict.

With the band filter restored, the in-script null (400 iters, seed 99) gives **strike-null mean $19.68 / p95 $26.66 / actual at the 78.7th pctile → FAIL**, and the standalone harness at **500 iters across 3 seeds {7, 101, 2024}** converges identically:

| Null (NULL-B random short-offset {2,3,4}/day) | seed 7 | seed 101 | seed 2024 |
|---|---|---|---|
| strike-null mean | $19.92 | $20.00 | $19.86 |
| strike-null p95 | $26.35 | $26.42 | $26.38 |
| **actual $23.03 percentile rank** | **75.6%** | **76.6%** | **76.4%** |
| beats p95 | **No** | **No** | **No** |

The "chosen" offset-2 expectancy sits at the **~76th percentile** of random-offset condors — **roughly 1 in 4 random short-offset draws match or beat it.** That is the upper-middle of the noise band, not the far-right tail a real selection edge occupies. The 10:30 cell *does* beat the random-**entry**-time null (100th pctile every seed), but that is the entry grid self-selecting (off-peak 13:00/14:30 average worse), not structural signal — and L172 "beats null" requires beating the **strike** null too. **No strike-selection alpha. Gate 6 FAILS with margin.**

> **Doctrine (methodology foot-gun, OP-16):** a random-strike null MUST trade the **same strike universe as production** — apply the identical `legs_in_band` pre-filter, or the null prices condors production never takes and mis-estimates the percentile (here ~79th → ~95th, flipping a clean fail into a knife-edge). Secondarily, gate on the converged **percentile rank** over ≥300 iters / multiple seeds, never a single-seed p95 boolean. Queued for lesson-author.

### CHECK 2 — band-skip survivorship: real & large; cache cannot test the adverse tail

55.6% skip-rate (**203/365 days**), and the skip reason is **100% `missing_cache`** — NOT the band pre-filter. The ±$5 OPRA cache is centered on a per-day reference; when the 10:30 spot has drifted >~$1 from that center, the off2/w2 strikes (ATM±4) fall outside the cached set → skip. So the cache **skips exactly the days price is moving on:**

| SPY excursion after 10:30 entry (median) | **TRADED** days | **SKIPPED** days |
|---|---|---|
| move entry→close (full sample) | 0.096% | **0.547%** (5.7×) |
| move entry→close (OOS-2026) | 0.089% | **0.483%** (5.4×) |
| max intraday excursion (OOS) | 0.424% | 0.683% |
| worst single skipped-day move-to-close | — | **8.9% (full) / 1.9% (OOS)** |

The +EV is **structurally conditioned on only trading the calm ~44% of days.** The "force a trade on the skip days" counterfactual returned +$36.99/tr (combined +$27.86, *not* negative) — **but it is contaminated and cannot be used to rescue the EV:** re-centering the condor on the day's *cached* band (the only strikes available) puts a short leg **already ITM at entry on 59% of skip days** (e.g. 2025-01-31: spot 609.52, cache forces center 603, short call 605 deep ITM). Those off-center spreads profit by **mean-reversion back toward the stale cache reference**, not by surviving the move. **The ±$5 cache literally cannot price a properly-centered condor on the high-excursion days** — so the adverse tail is untestable on this data. This *is* the survivorship finding: calm-day selection by construction + an untestable tail.

### CHECK 3 — posQ re-spec: **PASS** (confirms finalize; the gate was a window artifact)

Re-scored over 6 monthly OOS sub-windows and over IS+OOS combined quarters (all three stop variants):

| stop | posMonth (OOS) | posQ (IS+OOS combined) | passes ≥4/6 |
|---|---|---|---|
| EOD | 5/6 | 6/6 | ✅ |
| 1.5× | 5/6 | 5/6 | ✅ |
| 2.0× | 5/6 | 5/6 | ✅ |

The only negative OOS month is **2026-05 (−$3 to −$6/tr)**; Jan–Apr + Jun all positive (+$10 to +$40/tr). `posQ≥4` was structurally unreachable only because OOS-2026 spans 2 calendar quarters. **Not a real blocker — corrected.**

### CHECK 4 — intrabar-stop honesty: stop-variant EV is optimistic; EOD variant trades an uncapped tail

bar.close MTM understates stops (the seller-backtest trap). For the lead geometry (n=162 taken):

| variant | close-basis STOP exits | **intrabar-worst would ALSO have stopped** (extra) | rate | OOS extra |
|---|---|---|---|---|
| 1.5× | 7 | **33** | **20.4%** | 8 |
| 2.0× | 3 | 14 | 8.6% | 4 |
| EOD (no stop) | 0 | 0 (N/A) | — | 0 |

On **1 in 5 trades** the 1.5×-stop variant let a position ride that a true intrabar stop would have closed at −1.5× credit → its headline EV is **optimistic**, not conservative. The EOD-only variant dodges stop-misfire but in exchange **holds to the close uncapped intraday** (only the defined-risk wing caps loss) — fine on $1–$2 wings (max-loss ~$100–$200/lot), but that benign tail is an artifact of the **narrow band the cache forces**, and does NOT generalize to a textbook 16-delta / 20–30-wide condor (~$3,000 max-loss/lot).

### Final gate-bar (lead cell `IC 10:30 off2 w2 pt0.5 1.5×`) — confirms the finalize scorecard

| # | Gate | Result | Pass |
|---|---|---|---|
| 1 | OOS expectancy/tr > 0 | +$23.03 | ✅ |
| 2 | n ≥ 20 (OOS) | 52 | ✅ |
| 3 | posMonth ≥ 4/6 | 5/6 | ✅ |
| 4 | tail-survivable (1-lot, narrow) | maxDay −$119 / bookDD −$269 | ✅ (narrow only) |
| 5 | drop-top5 AND drop-worst5 > 0 | +$15.0 / +$19.8 | ✅ |
| **6** | **beats random-strike null (L172)** | **actual at ~76th pctile, p95 $26.4 > $23.03** | **❌** |
| 7 | IS-2025-H1 > 0 | +$28.96 | ✅ |
| 8 | recency (chop) > 0 | +$9.00 | ✅ |

**7/8 — fails gate 6, seed-robustly. NOT a ratifiable edge.** Three independent harness passes (finalize seed 13/30-iter, IB-pass 200-iter, this pass 500-iter × 3-seed) now agree the IC is OOS-positive + broad + tail-survivable-when-narrow + recency-positive but is **well-timed generic theta, not strike-selection alpha** — and additionally is **calm-day-survivorship-conditioned** with an **untestable adverse tail** on the ±$5 cache.

### Only path LEAD → EDGE (unchanged, now with the data prerequisite proven necessary)

Check 2 makes the prerequisite concrete: the cache skips the move-days *because* it cannot price a centered condor there. To honestly test a real condor you must first **fetch a WIDE, delta-targeted OPRA band** (true ~16-delta short + 20–30-wide wing; `tools/fetch_option_data.py` ±$15–$20 strikes), then (a) re-test the REAL max-loss tail on the high-excursion days the ±$5 band currently skips, and (b) find a *selection* rule (VIX-character / realized-range / time-regime gate) that **beats the random-strike null** at >95th pctile across seeds. Absent a null-beating selection rule, the only honest framing remains a **passive mechanical theta sleeve sized for the REAL (non-narrow) tail** — not a Gamma directional/selection edge.

### Artifacts
- `backtest/autoresearch/_pivot_premium_ic_validate.py` → `_state/pivot_premium_selling/ic_validate.json` (checks 1–4 in one file)
- Null cross-check: `_pivot_premium_selling_null.py --structure IC --entry 10:30 --offset 2 --wing 2 --pt 0.5 --stop 1.5 --iters 500 --seed {7,101,2024}` → `bignull_s{7,101,2024}.log`
