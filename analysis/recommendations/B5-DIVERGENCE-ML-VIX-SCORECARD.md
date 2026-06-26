# B5 — Divergence-Rescue + ML-on-Futures + VIX-Regime-Convergence — HONEST Scorecard

**Date:** 2026-06-21 · **Batch:** B5 (rescue the B4 leads + distill the convergent VIX-regime axis)
**Bar:** standing all-8-gate suite. 0DTE = real OPRA fills (C1); futures = pure point-P&L, no theta (`pnl=(exit-entry)*point_value*qty-costs`, 1 micro, $1.24 RT, 1-tick slippage each side). OOS = clean calendar split (IS=2025 / OOS=2026). Every fix threshold frozen on IS days only — no OOS leakage.
**Headline:** **2 NEW edges cleared all 8 gates** — (1) a **NEW FUTURES edge** (MES→MNQ divergence catch-up, rescued by min-divergence-persistence ≥ 2 bars) and (2) a **NEW 0DTE ATM edge** (VIX-regime + day-trend-side). The ML-on-futures lead is **DEAD** (theta-removal did not rescue it). The reverse divergence direction is **DEAD** (asymmetry confirmed: SPX leads, not NDX).

---

## Ranked table

| # | Candidate | Kind | Arena | Gates | OOS/trade | drop-top5/tr (gate-5) | Verdict | Status |
|---|-----------|------|-------|-------|-----------|----------------------|---------|--------|
| 1 | **MES→MNQ divergence catch-up + persistence≥2** | rescue-futures | MNQ (point-P&L) | **8/8** ✅ | **+$71.46** (n=41 OOS) | **+$3.65** ✅ | **CONFIRMED — NEW FUTURES EDGE** | SHIP dormant→review→enable on futures edition |
| 2 | **VIX-regime + day-trend-side** | convergence | 0DTE ATM/Safe-2 | **8/8** ✅ | **+$79.49** (oos_n=21) | **+$25.91** ✅ | **CONFIRMED — NEW 0DTE ATM EDGE** | SHIP dormant→review→enable (ATM book slot) |
| 3 | **ML direction model on futures (live-weights)** | rescue-ml | MES/MNQ | 1/8 ❌ | −$13.81 (MES) / −$27.12 (MNQ) | −$35.07 ❌ | **REJECT — theta-removal did NOT rescue** | DEAD on both 0DTE + futures |
| 4 | **MNQ-leads → trade MES (reverse) + fixes** | symmetry-futures | MES (point-P&L) | 7/8 ❌ (g5) | +$28.59 (best near-miss) | −$7.50 ❌ | **REJECT — not rescuable, asymmetry confirmed** | DEAD (all 66 cells fail gate-5) |

---

## (a) MES/MNQ divergence rescue — did it clear gate-5 → a NEW futures edge? **YES.** ✅

**RESCUE SUCCEEDED. This is a NEW deployable FUTURES directional edge.** The B4 lead failed exactly one gate (gate-5, drop-top5-days, at −$4.70/trade — irreducible tail concentration). B5 swept four candidate concentration fixes; **exactly one cleared gate-5 while every other gate held.**

**The winning fix: min-divergence-persistence ≥ 2 bars.**
- **Mechanism:** require the normalized-return dislocation (leader's session-VWAP broken + laggard unconfirmed, spread ≥ threshold) to have **held for ≥ 2 consecutive closed bars** up to and including the signal bar — instead of firing on a single-bar blip. This trims the lottery-ticket one-bar-spike days that drove the lead's top-5 concentration.
- **Effect on the failing gate:** gate-5 drop-top5-per-trade flips from **−$4.70 (lead, FAILED)** → **+$3.65 (winner, PASSES)**. AND OOS per-trade *improves* +$55.23 → **+$71.46** (the fix is not a concentration-vs-return tradeoff — it strictly helps both).

**Full 8-gate result (MES-leads → trade MNQ laggard, thr=0.0015, fix=d persistence≥2):**
- gate-1 OOS>0: **+$71.46/tr** (n=41, WR 41.5%, PF 2.16) ✅
- gate-5 drop-top5: **+$3.65/tr** ✅ (the decisive gate the lead failed)
- gate-6 IS first-half: **+$66.19/tr** > 0 ✅
- gate-7 beats random-null: +$71.46 vs null mean −$14.54 AND vs p95-luckiest +$21.58 (L172) ✅
- gate-8 no-truncation: chart-stop+EOD +$42.62 vs full +$45.76 — no sign flip (L171) ✅
- posQ 5/6 ✅ · top5-day 92.4% (< 200) · full-sample +$45.76/tr (n=118, total +$5,400 on 1 MNQ micro)

**Why the other three fixes FAILED (honest):**
- **(a) vol-regime ATR%-band gate** — got *close* (drop-top5 −$2.13 to −$2.59) and lifted OOS to +$104–124/tr, but **never crossed zero on gate-5.** Promising but did not clear.
- **(b) 1-entry-per-day cap** — a **structural no-op**: B4's base divergence is already exactly 1/day via the fired-flag, so the cap cannot alter drop-top5.
- **(c) top-magnitude divergence-day filter** — made concentration **WORSE** (drop-top5 −$29 to −$88) and failed gate-2.

**Bug caught + fixed mid-run (disclosed):** the original flip-persistence definition was degenerate (always == 1, because the B4 trigger requires a leader VWAP FLIP at the signal bar, so the prior bar is on the opposite side by construction — L161/L165 no-degenerate-signal discipline). Redefined as **causal spread-persistence**. Gate logic reused verbatim from the B4 module — zero drift between lead and rescue.

**Artifact:** `analysis/recommendations/b5-mesmnq-div-rescue.json`

---

## (b) ML direction model on futures point-P&L (no theta) — did it become profitable? **NO.** ❌

**REJECTED. Removing theta did NOT rescue it.** This closes the ML-direction lead on BOTH 0DTE (theta-killed in B4) and futures (cost/edge-thin-killed here).

- **The accuracy edge SURVIVES on futures** (this part is real): LR OOS direction accuracy **53.4% MES / 54.4% MNQ**, beating coin-flip 50% and train-majority 51.8/52.8% on both. Feature ranking re-confirms the live-weight axis: **VIX level is #1 by far** (GBM split-freq 0.50 MES / 0.63 MNQ), then VWAP-distance + time-of-day; VIX-slope near-dead. Consistent with C5 + the B4 feature ranking.
- **But a 53–54% next-30-min DIRECTION accuracy is too thin to overcome ATR-trailing stop-cost + 1-tick slippage + $1.24 RT.** On theta-free point-P&L the high-prob subset **LOSES on both micros:**
  - MES OOS **−$13.81/tr** (n=36, posQ 0/6, drop-top5 −$35.07)
  - MNQ OOS **−$27.12/tr** (n=44, posQ 1/6, drop-top5 −$59.26)
- **Fails 7 of 8 gates on both** (only n≥20 passes). Fails the decisive gate-1 (OOS<0), gate-5, gate-6 (IS-half), and gate-7 — it actually **UNDER-performs** the random-entry null (−13.81 vs −9.46 MES; −27.12 vs −19.90 MNQ).
- **Not a truncation artifact:** tight-target exit cross-check is equally negative (−$13.32 / −$27.85) — the loss is exit-agnostic.
- **Why:** the high-confidence subset is **80%+ LONG** (29/36 MES, 39/44 MNQ) → it's effectively a confidence-gated bull-tilt that got chopped in the 2026 OOS regime. The VIX-regime *axis* is predictive; the per-bar *direction model* is not a tradable edge. The edge lives in coarser **day+side selection** (candidates #1 and #2), not bar-level ML.

**Artifact:** `analysis/recommendations/b5-ml-futures-liveweights.json`

---

## (c) VIX-regime + day-trend-side convergence — did it clear on 0DTE or futures? **0DTE ATM: YES. Futures: NO.** ✅/❌

**CONVERGENCE CONFIRMED on the 0DTE ATM tier — clears ALL 8 gates including the drop-top5 gate the divergence lead failed — but ONLY in the 0DTE ATM option structure.** This is the distillation of the three B4 pointers (edge#2 day+side, ML feature ranking VIX #1, the vwap VIX-gate).

**ROBUST clearing cell (trustworthy: oos_n=21 ≥ 15 evidence floor):** 0DTE **ATM/Safe-2 tier**, slope_rule=not_rising, vix_low_margin=0.25:
- n=76, OOS per-trade **+$79.49**, IS-half +$36.13, **drop-top5 +$25.91** (the exact gate edge#2 / the divergence lead failed) ✅, posQ 5/6, top5-day 45.2%, edge over random-null **+$84.34** ✅
- **chart-stop-only OOS +$0.15 (POSITIVE → NOT a truncation artifact)** ✅ — this is the clean tell vs the ITM-2 cells
- Both sides profitable: C +$47.37 / 52% WR, P +$38.74 / 50% WR

**CRITICAL CAVEATS (honest):**
1. **ITM-2 SURVIVOR cells are TRUNCATION ARTIFACTS** — higher headline OOS/tr but chart-stop-only OOS flips to **−$13** (the C3/L58 premium-stop-doing-the-work signature). The **ATM tier is the ONLY clean clearing cell.** Do NOT wire this to ITM-2.
2. **Naive max-OOS auto-pick is over-concentrated** — the lm=1.0 cell (+$200/tr) has oos_n=6. An oos_n≥15 robust selector was added; the headline cell is the robust one, not the lottery cell.
3. **FUTURES: 0 of 16 cells (MES+MNQ) clear all 8** — mostly OOS-negative. Removing theta did NOT rescue it as a point-direction edge. **The alpha is intrinsic to the 0DTE ATM option bracket** — it does not transfer to futures (convergent with candidate #3's finding that the per-bar direction signal is too thin on point-P&L).

**Config (clearing cell):** 0DTE ATM_safe2 tier, slope_rule=not_rising, vix_low_margin=0.25 (VIX ≥ 0.25 pts below trailing-78bar-median AND vix_slope5 ≤ 0), day-trend side from first 3 closes vs session VWAP, morning entry window 09:35–11:30, −8% premium stop, 12-bar swing chart-stop.

**Artifact:** `analysis/recommendations/b5-vix-regime-dayside.json`

---

## (d) Reverse direction + symmetry check — MNQ-leads → trade MES? **DEAD.** ❌

**NOT RESCUED + ASYMMETRY CONFIRMED.** The divergence catch-up edge is **one-sided.**

- **Symmetry:** MES-leads → trade-MNQ (NDX laggard) is the dominant side (max OOS +$81.76/tr; best near-miss fails only 1 gate). MNQ-leads → trade-MES (SPX laggard) is the weak, non-tradeable side (max OOS +$24.18/tr; fails 2 gates). **The other lead direction does NOT have a stronger asymmetry** — asymmetry is real but in QUALITY only: **SPX(MES) leads Nasdaq(MNQ), not the reverse.**
- **Rescue (reverse side, raw):** FAILED. Gate-5 is failed by **ALL 66 cells** (both directions × 6 thresholds × 10 fix combos). The causal VIX-regime × day-trend-side alignment gate made it **WORSE** (smaller samples raise tail dependence; many drop below n≥20). 0 cells clear all 8.
- Canonical near-miss (MES→MNQ, no fix, thr=0.0005, n=190): OOS +$28.59/tr, IS-half +$46.99, beats null (−$19.77), no-truncation clean (chartstop+EOD $24.90), posQ 5/6, top5=137.9% — but **drop-top5 −$7.50 = gate-5 fail.** This is precisely the cell that candidate #1's persistence≥2 fix rescues (at the higher thr=0.0015), confirming the persistence knob — not the VIX-alignment gate — is what cracks gate-5.

**Artifact:** `analysis/recommendations/b5-mesmnq-reverse.json`

---

## SHIP recommendation (per OP-11 / OP-22 standing authorization)

Two new edges clear the auto-ship bar. **Standing authorization = build dormant-flip-ready → adversarial swarm review → enable, then report for REVOKE.** Do NOT present-and-ask (banned framing).

### EDGE #1 — MES→MNQ divergence catch-up (FUTURES) → wire to the Futures Edition

- **Instrument / account:** **MNQ micro** (Nasdaq laggard), TT sandbox futures account (acct 5WW73759, $2K) — directional edge belongs on futures per C3/L58 (no theta, point-P&L). $2K holds 1 MNQ micro comfortably.
- **Exact config:** MES-leads → trade MNQ laggard · divergence threshold **0.0015** · fix=d **min-divergence-persistence ≥ 2 bars** (causal spread-persistence: spread ≥ thr AND leader-broken/laggard-unconfirmed held ≥ 2 consecutive closed bars up to signal bar) · ATR-trail exit (chart-stop floor + chandelier 2.5×) · EOD flat.
- **Wiring:** add as a **frozen config** to the fleet champion/challenger MNQ executor (`automation/state/fleet/fleet_executor.py`) per the fleet doctrine — runs dormant/paper alongside live, NOT auto-enabled until adversarial review passes. Futures Edition heartbeat is currently DISABLED for cost (shares Max pool), so this rides the fleet executor's paper-forward track first.
- **Validation already in hand:** OOS +$71.46/tr, all 8 gates, posQ 5/6, beats null at p95, no-truncation. **Next step before enable:** swarm adversarial review (swarm_consult.py) + a paper-forward window on the fleet track to confirm the persistence knob holds out-of-sample.

### EDGE #2 — VIX-regime + day-trend-side (0DTE ATM) → wire as a regime-aware ATM book slot

- **Instrument / account:** **SPY 0DTE ATM single-leg directional**, the **Safe-2 account** (OTM-2 tier maps to the ATM clearing cell). **NOT ITM-2 (truncation artifact), NOT futures (0/16 clear).**
- **Exact config:** ATM strike (strike_offset=0), slope_rule=not_rising, vix_low_margin=0.25, day-trend side from first 3 closes vs session VWAP, entry window 09:35–11:30, −8% premium stop, 12-bar swing chart-stop, both sides (C+P) eligible.
- **Wiring:** build dormant-flip-ready exactly as edge #2 (`struct_vwap_reclaim_failed_break`) was handled → adversarial swarm review → enable. **Mandatory gate:** file an A/B scorecard + real-fills no-regression check before any live flip (OP-11). Respect the regime-concentration discipline: confidence rests on day+side selection quality, not bar timing.

---

## NEXT-ITERATION recommendation

Both new edges are validated but each has ONE soft caveat worth a targeted next pass — and the vol-regime near-miss is the highest-EV unexplored lead:

1. **PRIMARY — chase the vol-regime gate on EDGE #1 (it was the near-miss, and it lifts OOS the most).** Fix (a) vol-regime ATR%-band got drop-top5 to −$2.13 and lifted OOS to **+$104–124/tr** but never crossed zero alone. **Test fix (a)+(d) STACKED** — vol-regime ATR%-band gate AND persistence≥2 together. If persistence already clears gate-5 at +$3.65, adding the vol-regime gate may push OOS to the +$100+ range while *keeping* gate-5 positive → a materially stronger version of the same edge. Freeze the ATR-band on IS days only.
2. **SECONDARY — sweep the persistence knob on EDGE #1 (n=2,3,4 bars) to map the plateau.** B4's reclaim-rescue taught that the winning knob often sits in a wide flat favorable region (buffer plateau). Confirm n=2 is the center of a plateau, not a fragile single-value spike — re-run the full 8-gate suite at n∈{2,3,4} and report drop-top5 at each.
3. **TERTIARY — paper-forward EDGE #2 (0DTE ATM) for the real-fills no-regression check** before live flip, and confirm the Feb-2026-regime-concentration caveat (inherited from the edge#2 family) does not dominate the OOS total. File the A/B scorecard.

**DEAD ends (do not re-test): ML direction model on either arena** (theta-free did not rescue; closed on both 0DTE + futures) and the **MNQ-leads reverse direction** (all 66 cells fail gate-5; asymmetry structural).

---

## POST-SHIP-REVIEW DISCLOSURE (2026-06-21, build→adversarial-review→enable pass)

Both edges were built dormant-flip-ready and put through an independent adversarial code-review before any enable. **Result: BOTH held DORMANT** — the pipeline caught real issues before either traded. Honest disclosure of what the review found (C4/L04 — disclose concentration; C14/L153 — no detector drift):

### EDGE #3 (MES→MNQ divergence) — DOWNGRADED to *concentration-caveated lead*, NOT a clean ship
- **OOS-alone concentration (was NOT in the headline):** gate-5's **+$3.65 drop-top5 is computed over the FULL IS+OOS sample.** On the **OOS window alone (n=41)**, drop-top5 = **−$16.36/tr** and **top5-day = 120.1% of OOS P&L** — i.e. remove the 5 best OOS days and the OOS edge goes NEGATIVE. The concentration the persistence≥2 fix cured on the full sample is **still present in OOS.** The +$71.46/tr OOS headline is carried by a handful of days.
- **Order-path gap [HIGH]:** no live futures order builder reads the validated ATR stop (`ATR_STOP_MULT=1.5×`, `TRAIL_MULT=2.5×`). Same structural gap as edge #2 — the fleet executor needs a TT futures bracket builder wired to those constants before the validated result is reproducible live.
- **Verdict:** do NOT enable on the current evidence. **Gate the enable on batch-6 de-concentration** (vol-regime ATR-band + persistence stack, the PRIMARY next-iteration test) — if that lifts OOS drop-top5 above zero, edge #3 becomes a real ship; if not, it's a 2026-bull-regime artifact (C22).

### EDGE #4 (VIX-regime day+side, 0DTE Safe-2 ATM) — DORMANT, detector now PARITY-PROVEN
- **Core validation stands** (OOS +$79.49/tr, drop-top5 **+$25.91**, chart-stop-only POSITIVE = no truncation) — this remains the night's cleanest edge; its OOS is NOT concentration-fragile (unlike edge #3).
- **Parity bug found + correctly resolved:** review flagged a warmup off-by-one (live core `TREND_BARS+1` vs research `TREND_BARS+2`). The reviewer's literal "raise core to +2" fix was **verified WRONG** — the streaming wrapper fires only when the first-favorable bar (j=TREND_BARS) IS the current bar, so +2 would push the look past the entry bar and **silently kill all live firing.** Correct resolution applied: core stays `+1` (streaming-correct) with a documented rationale; the **parity test** day-filter aligned to research's `+2` (apples-to-apples). `test_parity_with_validated_research_detector` now RUNS and PASSES → live core reproduces the validated research signal set byte-for-byte over 2025→2026. Full suite **14/14 green.**
- **Remaining enable blockers (deliberate daytime tasks):** (1) VIX intraday series not wired into the live heartbeat (`ctx.vix_intraday` seam — fail-open SKIP until fed, so dormant-safe); (2) order-builder per-setup-stop refactor so the live path honors `j_vix_dayside_premium_stop_pct=-0.08` (isolated keys + filters helpers exist + tested, but the heartbeat order-builder must call them).

### THE BOTTLENECK (now #1 morning priority)
The **order-builder per-setup-stop refactor gates THREE edges** — #2 (vwap_reclaim_failed_break), #4 (vix_regime_dayside), and #3 (futures ATR stop, its analog). One refactor unlocks the live-enable path for all of them. That raises its priority well above "nice-to-have." It is a core-engine change on the riskiest file → deliberate, daytime, with its own adversarial review — NOT an overnight auto-churn.
