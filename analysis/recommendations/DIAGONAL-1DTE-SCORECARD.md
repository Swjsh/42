# DIAGONAL 1DTE SCORECARD — vwap_continuation (#1 live edge)

**Date:** 2026-06-21 (Sunday, markets closed — offline real-fills research, $0)
**Sim:** `backtest/autoresearch/_diagonal_sim.py` (cross-expiry, real fills, each leg priced from its OWN expiry cache)
**Detector:** `_edgehunt_vwap_continuation.detect_signals` — byte-for-byte the live `vwap_continuation_watcher` port. No edits to detectors/params/risk_gate/orchestrator/heartbeat/simulator_real.
**Raw output:** `analysis/recommendations/diagonal-vwap-continuation.json`
**Window:** 2025-01-02 .. 2026-06-16 — 166 vwap_continuation signals on 166 days (C=90 / P=76).

---

## VERDICT: NO_IMPROVEMENT — the diagonal makes the edge WORSE, not safer. J's call on the 1DTE long stands.

**0 of 18 cells clear the clean-win bar.** Not one cell even beats the 0DTE baseline, let alone the 1DTE-long. The structure does the OPPOSITE of the hypothesis: it INFLATES the stop-out rate and DEEPENS the drawdown.

---

## The three-way comparison

| Structure | OOS exp/tr | Sortino | maxDD | net premium-at-risk/tr (3 lots) |
|---|---|---|---|---|
| **0DTE long (live baseline)** | **+$36** | **0.90** | **−$939** | ~$? (0DTE ITM-2) |
| **1DTE long-alone (the upgrade)** | **+$59** | **0.78** | **−$1,944** | **$1,251** |
| **Diagonal — best cell** (2DTE long ATM / short gap+3) | **+$8.21** | **0.13** | **−$1,551** | smaller |
| **Diagonal — ITM-2/gap+2** (apples-to-apples vs the live ITM-2 edge) | **−$52.65** | **−0.82** | **−$6,808** | **$685** |

The single "least-bad" diagonal cell (2DTE-long/ATM/gap+3) is still **+$8/tr OOS vs the 0DTE's +$36** — it gives back ~78% of the dollar lift AND posts a worse maxDD (−$1,551 vs −$939) AND a Sortino of 0.13 (vs 0.90). Every other cell is **negative** OOS.

---

## ROOT CAUSE — why the premium-offset backfired (the honest mechanism)

The hypothesis was: short 0DTE leg's credit lowers net premium-at-risk → smaller dollar loss per −8% stop → maxDD inflation cut. The credit-collection half is REAL — the diagonal does cut premium-at-risk to **$685 vs $1,251 for the 1DTE long-alone (ratio 0.55)**. But that is exactly what kills it, for two compounding reasons:

1. **The −8% percent-stop acts on the SMALLER net debit.** Same −8% rule, half the base ($685 vs $1,251) → the stop fires on roughly **half the adverse SPY move**. The stop becomes hair-trigger.

2. **The short leg's gamma works AGAINST the long intraday.** Both legs are the same side. On an adverse move the long loses value AND the short (which we're short) gains value — so `net_value = long − short` falls FASTER than the long alone. The cushion the credit was supposed to provide only exists at *expiry*; intraday the short is a second source of mark-to-market loss on the net.

**Result:** in the ITM-2/gap+2 cell the **PERCENT_STOP fires on 141 of 147 trades (96%)**, WR collapses to **4.1%**, and maxDD blows out to **−$6,808** (3.5× the 1DTE-long's −$1,944, 7× the 0DTE's −$939). The "defined-risk cushion" turned the position into a stop-out machine.

The only cells that aren't catastrophic are the wide-gap / ATM ones (gap+3) where the short credit is thin enough that the net debit stays large-ish and the stop is less twitchy — but those barely collect any offset, so they're just a noisier, drawdown-heavier version of the long-alone with most of the dollar-lift surrendered.

---

## Gate result (11-gate, every cell)

- **RISK gates FAIL universally:** no cell reaches Sortino ≥ 0.90 (best 0.13); no cell holds maxDD within 15% of −$939 (best −$1,551, i.e. 65% deeper).
- **OOS expectancy ≤ 0** in 17 of 18 cells; the one positive cell (+$8.21) fails the Sortino + maxDD gates anyway.
- **Tail-defined: PASS everywhere** (`all_tails_covered=True`, max short assignment $0 — held-overnight rate ~0%, so the short almost always closes intraday or settles worthless; the long always covers). The tail was never the problem.

So the structure clears ONLY the tail-defined sub-gate and fails the entire economic + risk-adjusted core.

---

## Honest note (the upside-cap the brief asked us to quantify)

The brief flagged that the short leg also caps UPSIDE if the move blows past the short strike. We measured the net: the upside-cap is a minor contributor — the dominant damage is the stop-rate inflation above, not the capped winners. In the best (2DTE/ATM/gap+3) cell, TP1 still fires 41 times; the problem is the 99 percent-stops, not the 41 caps. The diagonal doesn't trade dollar-lift for risk like the plain 1DTE upgrade does — **it loses BOTH**: it surrenders the dollar lift AND deepens the drawdown.

---

## Conclusion

The 1DTE-long's SHARPE_TRADEOFF (keeps +$23/tr OOS but doubles maxDD) is a genuinely better deal than the diagonal, which loses the lift and keeps/worsens the risk. **The clean 1DTE upgrade does not exist via a same-side diagonal.** Per the gate, this is documented and **J's call stands** on the plain 1DTE long.

If a future attempt is made to rescue the dollar-lift while taming maxDD, the lever is NOT a short-leg offset — it is the **stop denominator**: e.g. a percent-stop scaled to the long-leg premium rather than the net debit, or a chart/level-only stop (no percent stop) so a thinner net debit doesn't translate into a twitchier stop. That is a stop-mechanics change to the live edge, not a multi-leg structure, and is out of scope here (no edits to risk_gate/simulator_real).

---
---

# ANGLE B — NEUTRAL CALENDAR vs the iron-condor LEAD

**Sim:** `backtest/autoresearch/_calendar_premium_sim.py` (cross-expiry, real OPRA fills, each leg priced from its OWN expiry cache — the same loader the diagonal uses).
**Structure:** SELL 0DTE strangle (short_offset $ OTM each side) + BUY 1DTE/2DTE same-strike call+put. The long back-leg is the only structural difference vs the iron condor (a longer-dated option at the SAME strike instead of a defined-risk wing at a different strike).
**Compared against:** the IC LEAD from `PIVOT-PREMIUM-SELLING-SCORECARD.md` — OOS +$23/tr, 82.7% WR, book DD −$124, but **gate-6 FAIL** (random-strike null p95 +$26.03 ≥ real → generic theta, not selection alpha).
**Raw output:** `analysis/recommendations/calendar-premium.json`. Grid: straddle/strangle × {off2,3,4} × {1DTE,2DTE} × {09:40,10:30,11:00} × pt0.5 × {2.0× stop, EOD-only}. Random-strike null (30 seeds, offset∈{2,3,4}) on every off2 cell.

## VERDICT (Angle B): DEAD — same L172 gate-6 failure as the condor. The back-leg fixes the TAIL but NOT the selection question.

**0 of all calendar cells beat their random-strike null.** Every off2 cell's null p95 EXCEEDS the "chosen" offset-2 OOS expectancy — randomizing the short strike reproduces/exceeds the calendar's EV. There is no strike-selection alpha. The honest prior in the task brief is confirmed: a calendar is still fundamentally theta-harvest, and it inherits the condor's gate-6 death.

### The null kill (the decisive table)
| Calendar cell | OOS exp | strike-null p95 | beats null? |
|---|---|---|---|
| 1DTE 10:30 off2 (condor-comparable) | +$29.44 | **+$36.85** | **NO** |
| 1DTE 11:00 off2 | +$27.23 | **+$34.35** | **NO** |
| 1DTE 09:40 off2 | +$9.09 | **+$24.12** | **NO** |
| 2DTE 10:30 off2 | +$3.56 | **+$61.47** | **NO** |
| 2DTE 09:40 off2 | +$92.45 | **+$179.86** | **NO** |
| 2DTE 11:00 off2 | +$45.98 | **+$107.75** | **NO** |

The 2DTE cells look fat in headline OOS (+$45 to +$92) but their nulls are *fatter* ($107–$180) — a random short strike with a 2-day back-leg harvests even more generic theta. This is the L172 trap in the inverse (selling) direction, identical to the condor finalize-pass result.

### What the back-leg DID fix (the one real structural difference)
The same-strike back leg caps the steamroller better than the condor's wing: above/below the strike the long and short intrinsic **cancel exactly** (validated: SPY 600, 585C → short owes $15, long worth $15, net $0), so only the net debit + 1-day carry is ever at risk. Result: book DD **−$75 to −$355** across cells (vs the iron-fly's −$1,378), `max_short_intrinsic = $0` on essentially every trade (the short is bought back / settled before going deep ITM). The tail is genuinely tamer than any naive 0DTE seller. **But tail-protection without selection alpha is not an edge** — it's a passive theta sleeve a coin-flip strike replicates.

### Honest caveats (do not let the tame tail flatter the result)
1. **Phantom-fill trap caught and removed.** The first cut managed PT/stop on cross-leg intrabar extremes (long.high WITH short.low) → over-stated favorable net by $0.5–$1.3/sh and produced a fake +$100/tr, 89% WR. Re-marked on **bar close** (the condor sim's `eod_close_mark` basis, L49 seller-backtest discipline) → edge collapsed to +$29/tr, 57% WR, Sortino 0.67. The honest number is the close-MTM one.
2. **84.7%–87.4% skip rate.** The calendar only fills on narrow-range days the ±$5 OPRA band can price both legs of — pure band-skip survivorship (it self-selects calm days). The fat-Sortino best cell (2DTE/11:00/off4, Sortino 6.98) trades only ~13% of days and was not null-tested (off4); the off2 cells that WERE null-tested all fail.
3. **Tail not universally inside the Safe kill.** One high-vol day (2025-04-07) carried a $9.70 net debit = $970 > the $600 Safe-2 daily kill on a 1-lot → `all_tails_survivable = False`. Benign-but-not-guaranteed, exactly like the condor's narrow-wing-conditional tail.

### Calendar gate-bar scorecard (best null-tested cell, 1DTE 10:30 off2 pt0.5)
| # | Gate | Result | Pass |
|---|---|---|---|
| 1 | OOS expectancy/tr > 0 | +$29.44 | ✅ |
| 2 | n ≥ 20 (OOS) | 22 | ✅ |
| 3 | posMonths ≥ 4/6 | 4/6 | ✅ |
| 4 | tail-survivable (1-lot) | book DD −$355; one day $970 > $600 kill | ⚠️ mostly |
| 5 | drop-top5 AND drop-worst5 > 0 | +$11.25 / +$44.31 | ✅ |
| **6** | **beats random-strike null (L172)** | **+$29.44 < null p95 +$36.85** | **❌** |
| 7 | IS-2025-H1 > 0 | +$64.98 | ✅ |
| 8 | recency / broad-based | 4/6 months positive | ✅ |

**7/8 — fails gate 6, the only one that distinguishes alpha from theta drag.** Per OP-11/L172 this is explicitly NOT shippable under the standing profitable-edge authorization (that authorization covers validated *edges*; a null-failing theta artifact is the named carve-out).

## Net Angle B conclusion
The long back-leg buys real **steamroller survivability** (book DD an order of magnitude tighter than the iron fly, same-strike intrinsic cancellation = defined risk tighter than a condor wing) — but it does **NOT** buy a **selection edge**. The calendar is OOS-positive, broad-based, recency-positive, and tail-tame, yet a random short strike reproduces/exceeds its expectancy on every null-tested cell. **Same verdict as the condor: generic theta, gate-6 FAIL, DEAD as a ratifiable edge.** The tail-protection is the only structural improvement and it is not enough. Consistent with the doctrine note in PIVOT-PREMIUM-SELLING-SCORECARD.md: 0DTE premium-selling in our ±$5 cache band cannot reach the far-OTM (≈16-delta) strikes a real seller needs, so every in-band neutral structure — condor, fly, or calendar — is forced near-ATM and is generic theta no strike-selection rule rescues.

## Files (Angle B)
- Sim: `backtest/autoresearch/_calendar_premium_sim.py` (`--validate` / `--smoke` / full sweep)
- Raw: `analysis/recommendations/calendar-premium.json`
- Reused byte-for-byte: cross-expiry leg loader from `_dte_expansion_sim.py`; day/entry grid + scoring + OPRA conventions from `_pivot_premium_selling.py`.
