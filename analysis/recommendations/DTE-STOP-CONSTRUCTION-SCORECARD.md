# DTE x STOP-CONSTRUCTION SCORECARD

## HEADLINE — does the 1DTE + dollar-anchored-stop lever generalize across the edge stack?

**Partially. The MECHANISM generalizes; the WIN does not — it requires a clean 0DTE baseline to lift.**

The 1DTE-contract + dollar-anchored-stop lever (replace the live -8% PERCENT premium stop with a fixed DOLLAR-loss cap = the edge's own median 0DTE per-trade loss at that tier) was tested on three long-premium directional 0DTE edges, all on the SAME byte-for-byte harness, each with its dollar-stop **re-derived per edge AND per tier** (C29 — never transferred from #1):

| edge | tier | re-derived $-stop | 0DTE/-8% baseline clears 11-gate? | 1DTE/$-stop vs baseline | maxDD move | Sortino | **clean win?** |
|---|---|---|---|---|---|---|---|
| **#1 vwap_continuation** (Bold/ITM-2) | ITM-2 | **$67.68** | **YES** | OOS exp/tr +$36.34 → **+$73.91 (2.03×)**, OOS total +$1,952 | **-$939 → -$879 (IMPROVES -6%)** | 14.31 → **25.70 (+80%)** | **✅ YES** |
| **#1 vwap_continuation** (Safe-2/ATM — WP-5 live tier, the GATING test) | ATM | **$35.88** | **YES** | OOS exp/tr +$25.00 → **+$57.59 (2.30×)**, OOS total +$1,712 | **-$570 → -$574 (flat, +0.7%)** | 14.59 → **32.55 (+123%)** | **✅ YES — ATM_CLEAN_WIN (plateau 0.7–1.2×)** |
| #2 vwap_reclaim_failed_break (dormant) | ITM-2 | $66.24 | NO (OOS<0, L173 fail) | OOS +$573 (concentrated, not broad) | -$1,176 → -$1,881 (**+60% WORSE**) | 15.07 → 12.20 (drops) | ❌ NO |
| #2 vwap_reclaim_failed_break (dormant) | ATM | $33.84 | NO (L173 fail) | OOS +$354 (concentrated) | -$817 → -$1,091 (**+33% WORSE**) | 13.41 → 12.78 (drops) | ❌ NO |
| #4 vix_regime_dayside (dormant) | ATM | $36.48 | NO (L173 fail) | OOS +$461.76 (+89%/tr, thin ~25 OOS tr) | **-$549 → -$620 (+12.9%, inside bar)** | 10.06 → **16.05 (+60%)** | ❌ NO (fails L173 only) |

**The two-part finding (honest, per C7/OP-20):**

1. **The dollar-stop MECHANISM transfers cleanly to #4.** On #4 the lever did exactly what it did on #1 — held maxDD ~flat (+12.9%, well inside the +25% bar), grew OOS dollars (+89%/tr), lifted Sortino +60%, and the dollar cap held even 2DTE worst-day flat at -$36.48 (no kill-switch blowout, unlike #1's 2DTE). #4 PASSES all four NUMERIC clean-win legs. It fails the structural bar on **one** gate — L173 (`oos_drop_top5 ≤ 0`) — and that failure **pre-exists** the DTE/stop choice: #4's own 0DTE baseline already fails L173. The lever amplifies an edge; it cannot manufacture one.

2. **The lever does NOT transfer to #2 — and for a different, harder reason.** On #2 the mechanism itself broke: maxDD got WORSE (opposite of #1/#4), Sortino dropped, WR collapsed. #2's reclaim entries sit closer to their structural stop than #1's continuation entries, so a dollar cap at the median loss bites into the body of winners (the diagonal/L-failure mode the harness header warned about). #2's OOS lift is also concentrated in a few days (L173 negative), not broad-based like #1.

**Conclusion:** the EXPIRY + stop-construction lever is the campaign's real find, but it is **edge-specific, not a blanket transform.** It only produces a clean SHIPPABLE win where the 0DTE baseline already clears the 11-gate bar — which today is **#1 alone**. #2 and #4 stay dormant; #4 is blocked by an ENTRY-quality problem (OOS concentration / L173), not a stop or DTE problem, so the path to unlocking #4's already-confirmed lift is to fix its entry breadth, not to re-tune its stop. **The ship-package is #1's 1DTE/dollar-anchored upgrade (it alone roughly doubles OOS expectancy).**

Per-edge detail follows.

---

# DTE x STOP-CONSTRUCTION SCORECARD — edge #1 `vwap_continuation`

**Run date:** 2026-06-21 (Sunday, markets CLOSED — research sim only, $0, no live edits)
**Sim:** `backtest/autoresearch/_dte_stop_construction.py` (validated; reuses `_dte_expansion_sim` settlement byte-for-byte + the LIVE `_edgehunt_vwap_continuation` detector byte-for-byte)
**Family:** `vwap_continuation` (the #1 detector) | **Tier:** ITM-2 (offset -2, the LIVE tier) | **Window:** 2025-01-02..2026-06-16 | **Signals:** 166
**Fills:** real per-DTE OPRA day-T bars + honest overnight gap + expiry-intrinsic settlement. No synthetic mid-life marks.

## VERDICT: **CLEAN_1DTE_UPGRADE**

There IS a clean-win cell. **`b_dollar_anchored` at 1DTE** keeps materially MORE OOS dollars than the 0DTE/-8% baseline AND caps maxDD *below* baseline AND nearly doubles Sortino AND clears the full structural+L173 bar AND keeps the worst day far inside both kill switches. The unexplored lever (stop CONSTRUCTION, not stop level) was real: the maxDD-doubling the diagonal surfaced was entirely an artifact of applying a -8% PERCENT stop to the bigger 1DTE premium. Capping the DOLLAR loss instead of the percent kills the doubling and the +theta lift survives as a clean win.

## CALIBRATION (frozen from the 0DTE -8% run at ITM-2, then applied unchanged at 1/2 DTE)

- **dollar_thresh = $67.68** (median per-trade dollar loss on the 85 0DTE -8% losers)
- median entry premium: 0DTE $2.55 -> 1DTE $3.57 -> 2DTE $4.48 (the premium grows with DTE — this is WHY a fixed -8% percent = a bigger dollar loss at higher DTE)
- percent-scaled pct: 0DTE -8.00% -> 1DTE -5.71% -> 2DTE -4.55% (the pct that holds the dollar loss == 0DTE)

## THE FULL MATRIX (real fills, ITM-2)

| construction | DTE | n | WR% | exp/tr | OOS n | OOS exp/tr | OOS total | maxDD | Sortino | worstDay | posQ | 11-gate (struct+L173) | CLEAN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **a. percent -8% (LIVE baseline)** | 0 | 157 | 45.9 | +51.27 | 50 | **+36.34** | 1817.16 | **-939.12** | **14.31** | -223.68 | 5/6 | PASS | — (baseline) |
| a. percent -8% | 1 | 166 | 42.8 | +67.25 | 51 | +59.02 | 3010.26 | -1943.76 | 12.45 | -313.68 | 5/6 | PASS | NO (maxDD doubles) |
| a. percent -8% | 2 | 165 | 42.4 | +71.57 | 50 | +66.13 | 3306.66 | -3007.68 | 7.63 | -1140.0 | 4/6 | PASS | NO (maxDD 3.2x; worstDay blows Bold kill) |
| **b. dollar-anchored ($67.68)** | 0 | 157 | 48.4 | +59.32 | 50 | +46.30 | 2315.16 | -879.84 | 19.37 | -67.68 | 5/6 | PASS | NO (DTE=0) |
| **b. dollar-anchored ($67.68)** | **1** | **166** | **41.6** | **+83.77** | **51** | **+73.91** | **3769.62** | **-879.84** | **25.70** | **-67.68** | **6/6** | **PASS** | **✅ CLEAN_WIN** |
| b. dollar-anchored ($67.68) | 2 | 165 | 39.4 | +89.17 | 50 | +92.45 | 4622.70 | -2240.64 | 11.64 | -1140.0 | 5/6 | PASS | NO (maxDD 2.4x; worstDay blows kill) |
| **c. chart/level (price-only)** | 0 | 157 | 80.9 | +85.04 | 50 | +36.50 | 1824.90 | -2724.0 | 5.46 | -1173.0 | 5/6 | **FAIL** (L173 oos_drop_top5<=0) | NO |
| c. chart/level | 1 | 166 | 70.5 | +108.95 | 51 | +11.52 | 587.39 | -3480.01 | 5.46 | -1416.0 | 5/6 | **FAIL** (L173) | NO |
| c. chart/level | 2 | 165 | 63.6 | +104.36 | 50 | +60.40 | 3020.10 | -5710.5 | 3.75 | -2160.0 | 5/6 | **FAIL** (L173) | NO |
| **d. percent-scaled** | 0 | 157 | 45.9 | +51.27 | 50 | +36.34 | 1817.16 | -939.12 | 14.31 | -223.68 | 5/6 | PASS | NO (== baseline at 0DTE by construction) |
| **d. percent-scaled** | 1 | 166 | 39.8 | +73.74 | 51 | +63.60 | 3243.79 | -1387.37 | 18.87 | -223.89 | 6/6 | PASS | NO (maxDD +48% > +25% bar) |
| d. percent-scaled | 2 | 165 | 37.6 | +81.30 | 50 | +85.85 | 4292.69 | -2151.52 | 10.35 | -1140.0 | 5/6 | PASS | NO (maxDD 2.3x; worstDay blows kill) |

Clean-win bar (all 5 required): OOS dollars > 0DTE baseline AND maxDD <= +25% worse than -$939 AND Sortino >= 14.31 AND structural+L173 PASS AND worstDay >= -$835 (Bold) / -$600 (Safe).

## THE WINNING CELL — b_dollar_anchored @ 1DTE, in detail

| metric | 0DTE -8% baseline | dollar-anchored 1DTE | delta |
|---|---|---|---|
| OOS exp/trade | +$36.34 | **+$73.91** | **+$37.57/tr (2.03x)** |
| OOS total | $1,817 | **$3,770** | +$1,952 |
| maxDD | -$939.12 | **-$879.84** | **BETTER by $59 (-6.3%, not worse)** |
| Sortino (ann.) | 14.31 | **25.70** | +80% |
| worst day | -$223.68 | **-$67.68** | inside Safe (-$600) AND Bold (-$835) |
| positive quarters | 5/6 | **6/6** | improved |
| structural + L173 bar | PASS | **PASS** | held |

## THE DTE x STOP INTERACTION (the core finding)

1. **The maxDD-doubling was a stop-construction artifact, not a DTE risk.** With the -8% PERCENT stop, maxDD goes -$939 (0DTE) -> -$1,944 (1DTE) -> -$3,008 (2DTE) — it scales with the premium because a fixed percent of a bigger premium is a bigger dollar loss. Swap to the **dollar-anchored** stop and 1DTE maxDD collapses to -$879 — *below* the 0DTE baseline — while the theta-room lift is retained. **Capping the dollar loss is the lever.**

2. **The dollar-anchored stop capped the maxDD-doubling WITHOUT collapsing WR/lift (it did NOT repeat the diagonal's failure mode).** WR barely moved (42.8% -> 41.6% at 1DTE) and OOS per-trade actually ROSE to +$73.91. The diagonal failure was "tighter stop -> stop out more -> lift evaporates"; here the $67.68 cap is calibrated to the median 0DTE loss, so it trims only the fat-tail stop-outs (the ones the bigger premium would otherwise amplify) — not the body of winners. Worst day went from -$313 to -$67.68: the tail is gone, the body is intact.

3. **The chart-stop (bad at 0DTE) did NOT become viable at 1DTE.** Hypothesis tested and rejected. It posts a seductive WR (70.5% at 1DTE) and high raw exp/tr ($108.95), but it is a theta/tail trap: OOS total *collapses* to $587 at 1DTE (the price-stop lets losers run to deep intrinsic before exiting), maxDD blows out to -$3,480, Sortino craters to 5.46, and it FAILS the L173 OOS-drop-top5 gate at every DTE (its OOS profit is concentrated in a handful of days — drop the top 5 and OOS goes negative). The -8% truncation IS the 0DTE risk management, and a pure price-stop transfers no better to 1DTE. **This is the classic C3/L172 "WR is a theta trap, expectancy/concentration is the edge" pattern — confirmed again.**

4. **percent-scaled is a partial win but not clean.** It holds the dollar loss equal to 0DTE *in expectation* (per-DTE pct calibrated off the median premium), but because it scales off the MEDIAN premium it under-caps the right tail when an individual entry premium runs above median — 1DTE maxDD lands at -$1,387 (+48%), failing the +25% maxDD bar despite a strong Sortino (18.87). The dollar-anchored stop caps every trade's dollars individually, which is why it — and only it — clears.

## WHY 2DTE doesn't clean-win under ANY stop

Every 2DTE cell either fails the +25% maxDD bar or blows the Bold kill switch on the worst day (-$1,140), even dollar-anchored (-$2,240 maxDD, -$1,140 worstDay). Two overnight sessions of gap risk + expiry settlement reintroduce a tail the per-trade dollar cap can't reach (gap-through and settlement exits bypass the intraday floor). 1DTE is the sweet spot: one overnight, dollar-capped intraday tail.

## HOW EACH STOP TRADES OFF lift / maxDD / WR across DTE

- **percent -8%:** lift grows with DTE but maxDD grows FASTER (the foot-gun). Net: bigger OOS total, much worse risk. Fails clean-win at every DTE>0.
- **dollar-anchored:** lift grows with DTE, maxDD held flat at 1DTE (-$879) then reappears at 2DTE (overnight tail). Best risk-adjusted profile at 1DTE — THE winner.
- **chart/level:** highest WR + highest raw exp/tr, WORST everything-else. Concentration-fails L173 at every DTE. A trap.
- **percent-scaled:** between percent and dollar-anchored — caps median dollars but not the right tail; partial at 1DTE (Sortino good, maxDD +48% over bar).

## RECOMMENDATION

`vwap_continuation` is already LIVE at 0DTE / ITM-2 / -8% percent stop. This matrix shows a validated, OOS-positive, broad-based (6/6 quarters), structural+L173-clearing upgrade: **move it to 1DTE with a dollar-anchored ($67.68/trade-equivalent, i.e. ~median 0DTE per-trade dollar loss) stop in place of the -8% percent stop.** It roughly doubles OOS per-trade (+$36->+$74) while LOWERING maxDD and worst-day and nearly doubling Sortino — same downside dollars, more upside from gentler theta, exactly as hypothesized.

Per OP-11/OP-22 this clears the auto-ship bar (OOS positive, broad-based, anchor/structural no-regression, A/B filed here). It is NOT shippable in this session: SUNDAY + markets-closed research guard forbids any live edit (risk_gate / simulator_real / orchestrator / heartbeat / params). It ships in an after-hours weekday block as: (1) wire a dollar-anchored per-trade stop construction into `simulator_real`/`risk_gate`, (2) flip `vwap_continuation` DTE 0->1 for ITM-2, (3) parity-test live vs backtest, then report for REVOKE.

### Open caveats (honest)
- **Implementation gap:** the live engine currently has a percent stop + a chart/level stop; it has NO dollar-anchored stop construction. Shipping this requires adding that construction to the live executor (the sim has it; the engine does not). That is real wiring work, gated behind the parity test.
- **Dollar threshold is account-tier-specific:** $67.68 is the median 0DTE loss at the ITM-2 / 3-lot configuration. It must be re-derived (or expressed as "median-0DTE-loss-at-current-tier") for any other strike tier or lot count — a fixed-percent stop is tier-portable, a fixed-dollar stop is not (cf. C29: exit knobs don't transfer across strike tiers).
- **DTE cache sub-window:** per-DTE n (157/166/165) reflects the OPRA cache coverage; fill_rate is the authority (0.946 / 1.00 / 0.994) — all high, no coverage concern.

**Artifacts:** full JSON at `analysis/recommendations/dte-stop-construction.json`.

---

# DTE x STOP-CONSTRUCTION SCORECARD — edge #1 `vwap_continuation` @ **ATM** (Safe-2's LIVE tier — the GATING test)

**Run date:** 2026-06-21 (Sunday, markets CLOSED — research sim only, $0, no live edits)
**Sim:** `backtest/autoresearch/_dte_stop_construction.py --family vwap_continuation --tier ATM` (the harness already supports `--tier ATM`; the matrix runner re-derives the dollar-stop from the 0DTE -8% run *at the passed tier* — no edit needed). Reuses `_dte_expansion_sim` settlement byte-for-byte + the LIVE `_edgehunt_vwap_continuation` detector byte-for-byte.
**Family:** `vwap_continuation` (the #1 detector) | **Tier:** **ATM (offset 0)** — per WP-5, #1 should run ATM on Safe-2 (the live $2K account), NOT the OTM-2 it currently fires. | **Window:** 2025-01-02..2026-06-16 | **Signals:** 166 on 166 days
**Fills:** real per-DTE OPRA day-T bars + honest overnight gap + expiry-intrinsic settlement. No synthetic mid-life marks.

## VERDICT: **ATM_CLEAN_WIN** — the upgrade clears the clean-win bar at Safe-2's live tier AND the sensitivity is a robust plateau.

`b_dollar_anchored` at 1DTE is the clean-win cell at ATM (the harness flags `DTE_STOP_CLEAN_WIN` with this exact cell). It keeps materially MORE OOS dollars than the 0DTE/-8% baseline, holds maxDD essentially flat (within 0.7%), more than doubles Sortino, posts 6/6 positive OOS quarters, and clears the full structural+L173 bar. The 1DTE/-8%-percent isolator confirms the **stop construction — not the DTE move — does the work** (see §isolation below).

## CALIBRATION (C29 — RE-DERIVED at ATM; **NOT** the ITM-2 $67.68)

- **dollar_thresh = $35.88** = #1's MEDIAN per-trade dollar loss on the **82 0DTE ATM -8% losers** (computed fresh from the 0DTE ATM run, exactly per the task's step 1). This is ~half the ITM-2 $67.68 because ATM entry premiums are smaller — C29 satisfied (the dollar-stop is tier-specific and was re-derived, not transferred).
- median entry premium: 0DTE $1.35 -> 1DTE $2.495 -> 2DTE $3.34 (premium grows with DTE — why a fixed -8% percent = a bigger dollar loss at higher DTE).
- percent-scaled pct: 0DTE -8.00% -> 1DTE -4.33% -> 2DTE -3.23%.

## A/B AT ATM — baseline vs dollar-anchored vs 1DTE/-8% (isolating stop vs DTE)

| cell | n | WR% | OOS n | OOS exp/tr | OOS total | maxDD | Sortino | worstDay | posQ | 11-gate (struct+L173) | CLEAN |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **0DTE / -8% percent (BASELINE)** | 156 | 47.4 | 49 | **+$25.00** | $1,225.14 | **-$570.24** | **14.59** | -$211.68 | 6/6 | PASS | — (baseline) |
| **1DTE / dollar-anchored $35.88 (UPGRADE)** | 166 | 38.6 | 51 | **+$57.59** | **$2,937.06** | **-$574.08** | **32.55** | **-$35.88** | **6/6** | **PASS** | **✅ ATM_CLEAN_WIN** |
| 1DTE / -8% percent (DTE-only isolator) | 166 | 43.4 | 51 | +$46.08 | $2,350.14 | -$1,673.04 | 10.51 | -$292.80 | 4/6 | PASS (struct) | NO |

**Reading the A/B:**
- **OOS exp/tr: +$25.00 → +$57.59 = 2.30×** (materially more OOS dollars — the lift survives and is large).
- **maxDD: -$570.24 → -$574.08** — flat (0.67% worse, far inside the +25% material-worsen bar; the harness leg `maxdd_not_materially_worse=true`).
- **Sortino: 14.59 → 32.55 (+123%)** — holds/improves, easily.
- **worst day -$35.88** (= exactly the dollar cap) vs the **Safe-2 -$600/day kill switch** — a ~17× margin. No kill-switch risk.
- **posQ 6/6**, structural+L173 **PASS** (the harness `clean_win_legs.CLEAN_WIN=true`, all 5 legs green).

**Isolation (stop vs DTE):** the 1DTE/-8%-percent cell — same DTE move, OLD stop — keeps the OOS lift (+$46.08/tr) but its **maxDD nearly TRIPLES to -$1,673** and Sortino DROPS to 10.51 with posQ only 4/6. So moving to 1DTE *without* the dollar cap is NOT a clean win — the -8% percent stop applied to the bigger 1DTE premium reintroduces the maxDD-doubling (same mechanism the ITM-2 run found). **The dollar-anchored stop is the load-bearing change; the DTE move only supplies the theta-room lift.**

## SENSITIVITY — sweep the dollar-stop ±30% around the derived $35.88 (is the win a plateau?)

| multiplier | $-stop | OOS n | OOS exp/tr | OOS total | maxDD | Sortino | worstDay | struct | **clean win?** |
|---|---|---|---|---|---|---|---|---|---|
| 0.7× | $25.12 | 51 | +$56.67 | $2,890.00 | -$401.92 | 43.81 | -$25.12 | PASS | ✅ YES |
| 0.8× | $28.70 | 51 | +$58.48 | $2,982.40 | -$459.20 | 39.15 | -$28.70 | PASS | ✅ YES |
| 0.9× | $32.29 | 51 | +$56.09 | $2,860.34 | -$516.64 | 35.42 | -$32.29 | PASS | ✅ YES |
| **1.0× (derived)** | **$35.88** | **51** | **+$57.59** | **$2,937.06** | **-$574.08** | **32.55** | **-$35.88** | **PASS** | **✅ YES** |
| 1.1× | $39.47 | 51 | +$55.27 | $2,818.59 | -$631.52 | 28.46 | -$39.47 | PASS | ✅ YES |
| 1.2× | $43.06 | 51 | +$55.43 | $2,827.18 | -$688.96 | 26.46 | -$43.06 | PASS | ✅ YES |
| 1.3× | $46.64 | 51 | +$53.19 | $2,712.62 | -$746.24 | 23.48 | -$46.64 | PASS | ❌ NO (maxDD -$746 > +25% bar vs -$570 baseline) |

**The clean win is a BROAD PLATEAU, not a fragile spike.** It holds across **0.7×–1.2× ($25.12–$43.06)** — a ~1.7× span of the threshold. Across that whole range OOS exp/tr stays $55–$58, structural PASS holds, Sortino stays 26–44 (all comfortably > the 14.59 baseline), and worst-day stays inside the Safe-2 kill switch with huge margin. The derived $35.88 sits mid-plateau, not at an edge. The win only drops out at 1.3× ($46.64), and ONLY because maxDD (-$746) then exceeds the +25% material-worsen band vs the -$570 baseline — i.e. the failure at the high end is the *risk* gate tightening, the *lift* never collapses. **Not overfit to the exact $ threshold.**

## RECOMMENDATION (Safe-2 — the live account)

The ATM result is the GATING test for Safe-2, and it **PASSES as a CLEAN WIN**. At Safe-2's correct (WP-5) ATM tier, moving #1 `vwap_continuation` from **0DTE / -8%-percent** to **1DTE / dollar-anchored ($35.88 = its own median 0DTE ATM per-trade loss)** roughly **2.3× the OOS per-trade expectancy** ($25.00 → $57.59) while holding maxDD flat (-$570 → -$574), more than doubling Sortino (14.6 → 32.6), and pinning the worst day at -$35.88 (a ~17× cushion under the -$600 Safe-2 kill). Per OP-11/OP-22 this clears the auto-ship bar (OOS positive, broad-based 6/6 quarters, anchor/structural+L173 no-regression, sensitivity-plateau robust, A/B filed here).

**It is NOT shippable in this session** (SUNDAY + markets-closed research guard — no live edit to risk_gate / simulator_real / orchestrator / heartbeat / params). It ships in an after-hours weekday block, COMBINED WITH the WP-5 strike-fix, as: (1) wire the dollar-anchored per-trade stop construction into `simulator_real`/`risk_gate` (the engine today has percent + chart/level stops only — no dollar construction; this is real wiring work), (2) flip Safe-2 #1 to ATM + 1DTE + dollar-stop $35.88, (3) parity-test live vs backtest, then report for REVOKE.

### Open caveats (honest)
- **Two coupled changes:** Safe-2 deployment requires BOTH the WP-5 strike-fix (OTM-2 → ATM) AND this DTE/stop upgrade. This scorecard validates the DTE/stop upgrade *at the ATM tier* — i.e. it validates the package on the assumption WP-5 lands first/with it. The dollar-stop $35.88 is derived AT ATM, so it is only correct once Safe-2 is actually firing ATM.
- **Dollar threshold is tier-specific (C29):** $35.88 is the median 0DTE loss at ATM / 3-lot. It is NOT the ITM-2 $67.68 (Bold). Express it live as "median-0DTE-loss-at-current-tier" or re-derive on any lot-count / tier change — a fixed-dollar stop is not tier-portable.
- **2DTE still doesn't clean-win at ATM:** the 2DTE dollar-anchored cell fails the +25% maxDD bar (-$1,145) and blows the Bold worst-day (-$930) — two overnight sessions reintroduce a gap/settlement tail the intraday dollar cap can't reach. 1DTE is the sweet spot at ATM, same as ITM-2.
- **Implementation gap is identical to ITM-2:** the live executor has no dollar-anchored stop construction yet; that wiring (gated behind a parity test) is the only thing between this validated result and the live SHIP.

**Artifacts:** full JSON at `analysis/recommendations/dte-stop-construction.json` (last write = this ATM run; `tier: "ATM"`, `verdict: "DTE_STOP_CLEAN_WIN"`, winner `b_dollar_anchored DTE=1`).

---

# GENERALIZATION #2 — edge `vwap_reclaim_failed_break` (the lever does NOT transfer)

**Run date:** 2026-06-21 (Sunday, markets CLOSED — research sim only, $0, no live edits)
**Sim:** same `backtest/autoresearch/_dte_stop_construction.py`; `--family vwap_reclaim_failed_break` dispatch added (detector `_sub_struct_vwap_reclaim_failed_break.detect_signals` registered BYTE-FOR-BYTE in `_dte_expansion_sim.FAMILIES` via a uniform-signature wrapper; detector body untouched).
**Family:** `vwap_reclaim_failed_break` (#2) | **Tiers:** ATM (Safe-2 validated tier) + ITM-2 (Bold validated tier) | **Window:** 2025-01-02..2026-06-16 | **Signals:** 86 on 86 days
**Backfill:** 18 missing #2 signal-day contracts fetched into `options_1dte`/`options_2dte` (1521/1539 were already cached from the overlapping vwap_continuation backfill); fill-rate now complete. `vix_regime_dayside` (#4) DTE cache was already 100% present (0 missing).

## VERDICT: **NO_CLEAN_WIN at 1DTE (lever does not transfer to #2)**

The 1DTE+dollar-stop lever that DOUBLED #1 does **not** transfer to #2 at either validated tier. **Root cause: #2's 0DTE/-8% baseline itself FAILS the 11-gate structural bar at BOTH tiers** — it is not a clean structural edge to begin with, so there is no clean baseline to lift. This confirms the prompt's honest caveats (smaller n, same-day-null caveat, ~breakeven chart-stop). The dollar-anchored stop at 1DTE makes maxDD WORSE (not better, the opposite of #1), Sortino DROPS, and the L173 OOS-drop-top5 gate still FAILS.

## RE-DERIVED DOLLAR-STOPS (C29 — computed per edge AND per tier; NOT the #1 $67.68)

| tier | dollar_thresh (= #2's median 0DTE per-trade loss at that tier) | n 0DTE losers | median 0DTE entry premium |
|---|---|---|---|
| **ITM-2 (Bold)** | **$66.24** | 43 | $2.58 |
| **ATM (Safe-2)** | **$33.84** | 41 | $1.40 |

(#1's ITM-2 stop was $67.68 — close to #2's ITM-2 $66.24 by coincidence of similar premium, but the ATM stop is half that. Both correctly re-derived, none transferred.)

## THE MATRIX — ITM-2 (Bold), real fills, n=86 signals

| construction | DTE | n | WR% | exp/tr | OOS n | OOS exp/tr | OOS total | maxDD | Sortino | worstDay | posQ | 11-gate | CLEAN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **a. percent -8% (baseline)** | 0 | 81 | 46.9 | +60.04 | 23 | **-4.05** | -93.19 | -1176 | 15.07 | -264 | 5/6 | **FAIL** (OOS<0, L173 -69.43) | — |
| a. percent -8% | 1 | 86 | 46.5 | +78.28 | 24 | -2.25 | -54.06 | -2363 | 8.87 | -1020 | 5/6 | FAIL | NO |
| a. percent -8% | 2 | 85 | 44.7 | +92.82 | 23 | +63.82 | 1467.84 | -1826 | 10.61 | -831 | 4/6 | FAIL | NO |
| **b. dollar ($66.24)** | 0 | 81 | 49.4 | +67.59 | 23 | +13.82 | 317.93 | -1059 | 19.50 | -264 | 5/6 | FAIL (L173) | NO |
| **b. dollar ($66.24)** | **1** | 86 | 44.2 | +92.55 | 24 | +19.99 | 479.70 | **-1881** | **12.20** | -1020 | 5/6 | **FAIL** (L173 -74.13) | **NO** |
| b. dollar ($66.24) | 2 | 85 | 41.2 | +108.24 | 23 | +99.77 | 2294.64 | -1228 | 16.65 | -831 | 4/6 | PASS | ⚠ 2DTE-only (outside bar; worstDay -$831 at Bold kill edge) |
| **d. percent-scaled** | 1 | 86 | 40.7 | +75.72 | 24 | +4.47 | 107.35 | -1974 | 9.48 | -1020 | 5/6 | FAIL | NO |
| d. percent-scaled | 2 | 85 | 37.6 | +93.99 | 23 | +91.50 | 2104.41 | -1214 | 13.83 | -831 | 4/6 | FAIL | NO |
| c. chart/level | 0/1/2 | 81/86/85 | 68-81 | high | — | — | — | -1131..-2289 | — | -627..-1446 | — | FAIL/mixed | NO (theta trap) |

**1DTE/dollar vs 0DTE baseline (ITM-2):** OOS dollars +$573 (lift survives) BUT maxDD -$1176→-$1881 (**+60% WORSE**, fails the +25% bar), Sortino 15.07→12.20 (**drops**, fails the holds/improves leg), L173 still FAILS. Clean-win bar = NO.

## THE MATRIX — ATM (Safe-2), real fills, n=86 signals

| construction | DTE | n | WR% | exp/tr | OOS n | OOS exp/tr | OOS total | maxDD | Sortino | worstDay | posQ | 11-gate | CLEAN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **a. percent -8% (baseline)** | 0 | 80 | 48.8 | +44.99 | 22 | +4.35 | 95.64 | -817 | 13.41 | -342 | 5/6 | **FAIL** (L173 -43.5) | — |
| a. percent -8% | 1 | 86 | 43.0 | +44.62 | 24 | -2.11 | -50.52 | -1658 | 7.15 | -651 | 5/6 | FAIL | NO |
| a. percent -8% | 2 | 85 | 49.4 | +98.13 | 23 | +44.78 | 1029.96 | -874 | 18.62 | -334 | 5/6 | FAIL | NO |
| **b. dollar ($33.84)** | 0 | 80 | 51.2 | +50.91 | 22 | +17.42 | 383.22 | -714 | 18.05 | -342 | 5/6 | FAIL (L173) | NO |
| **b. dollar ($33.84)** | **1** | 86 | 38.4 | +60.37 | 24 | +18.71 | 449.16 | **-1091** | **12.78** | -651 | 5/6 | **FAIL** (L173 -45.19) | **NO** |
| b. dollar ($33.84) | 2 | 85 | 34.1 | +76.91 | 23 | +41.64 | 957.78 | -440 | 44.45 | -34 | 4/6 | FAIL | NO |
| **d. percent-scaled** | 1 | 86 | 36.0 | +50.72 | 24 | +6.77 | 162.58 | -1202 | 10.03 | -651 | 5/6 | FAIL | NO |
| c. chart/level | 2 | 85 | — | +170.92 | 23 | +60.40 | 4125.30 | -921 | 13.52 | -819 | — | PASS | ⚠ 2DTE chart-stop = the known trap; outside the 1DTE bar |

**1DTE/dollar vs 0DTE baseline (ATM):** OOS dollars +$354 BUT maxDD -$817→-$1091 (**+33% WORSE**), Sortino 13.41→12.78 (**drops**), L173 still FAILS, WR collapses 43.0%→38.4%. Clean-win bar = NO.

## WHY THE LEVER TRANSFERS TO #1 BUT NOT #2 (the mechanism)

1. **#1's 0DTE baseline was a clean, structural, OOS-positive edge that PASSED the 11-gate bar.** #2's is NOT — it fails L173 (OOS-drop-top5 < 0) at 0DTE on BOTH tiers and is OOS-NEGATIVE at ITM-2. You cannot make a clean 1DTE win out of an unclean 0DTE baseline; the lever amplifies an edge, it does not manufacture one.
2. **#1's dollar cap held WR flat (the cap trimmed only the fat tail).** #2's dollar cap COLLAPSES WR at 1DTE (ITM-2 46.5%→44.2%, ATM 43.0%→38.4%) and maxDD goes UP, not down — this is the diagonal/L-failure mode (tighter stop → stop out the body → no clean lift), exactly the honest risk the harness header flags. #2's reclaim entries sit closer to their structural stop than #1's continuation entries, so a dollar cap calibrated to the median loss bites into the body.
3. **The only "clean" cells are at 2DTE** (b_dollar @ ITM-2; c_chart @ ATM) — outside the prompt's 1DTE bar, carrying two overnight sessions of gap+settlement tail (worst-days -$831 / -$819, at the Bold kill-switch edge), and the ATM one rides the chart-stop construction that #1's run proved is a concentration trap. Neither is a shippable clean upgrade.

## RECOMMENDATION

**Do NOT ship a 1DTE+dollar-stop change for #2.** The lever does not transfer at the 1DTE bar at either validated tier; the clean-win bar fails on maxDD (worsens), Sortino (drops), and L173 (still fails) — and the 0DTE baseline it would replace already fails the structural bar. #2 stays as-is (dormant). This is a true negative result, reported honestly per C7/OP-20: the #1 result is edge-specific and does NOT generalize blindly to weaker long-premium directional edges. The infrastructure (detector dispatch + DTE backfill) is now in place for #4 (`vix_regime_dayside`), which should be run next as its own A/B before any conclusion.

### Caveats (honest)
- **#2 is a weaker edge than #1:** smaller n (86 signals vs 166), 0DTE structural-bar FAIL at both tiers, and the same-day-null caveat the standalone `sub-struct_vwap_reclaim_failed_break.json` already flagged. The negative transfer result is consistent with that prior weakness, not a harness artifact.
- **Window:** the DTE harness runs to 2026-06-16 (vs the standalone #2 module's 2026-05-15); the regenerated `_dte_signal_days.json` already reflects the full window. n=86 here vs the module's smaller count is the wider window, not drift.
- **DTE cache:** #2 1DTE/2DTE now fully backfilled (18 contracts fetched 2026-06-21); fill_rate complete.

**Artifacts:** ITM-2 + ATM matrices captured during the run; harness writes the single-tier JSON to `analysis/recommendations/dte-stop-construction.json` (last write = ATM).

---

# DTE x STOP-CONSTRUCTION SCORECARD — edge #4 `vix_regime_dayside` (ATM Safe-2)

**Run date:** 2026-06-21 (Sunday, markets CLOSED — research sim only, $0, no live edits)
**Sim:** `backtest/autoresearch/_dte_stop_construction.py --family vix_regime_dayside --tier ATM` (extended its `--family` dispatch to the #4 detector byte-for-byte; #1's path and output untouched)
**Family:** `vix_regime_dayside` (the byte-for-byte `_b5_vix_regime_dayside.detect_opt_signals` at its ROBUST config `slope_rule=not_rising, low_margin=0.25` — the b5 scorecard's `robust_clearing_cell`; chart-stop = `_b5._swing_stop` verbatim; VIX feed = the pinned B2 reconstruction `causal_vix_median(78)` + `vix_slope(5)`) | **Tier:** ATM (offset 0, the dormant edge's live tier — #4 is ATM-only/Safe-2) | **Window:** 2025-01-02..2026-06-16 | **Signals:** 85
**Fills:** real per-DTE OPRA day-T bars (1DTE/2DTE cache already 100% backfilled for #4's signal-days via the union backfill — no fetch needed) + honest overnight gap + expiry-intrinsic settlement. No synthetic mid-life marks.

## VERDICT: **NO_CLEAN_WIN — the lever's MECHANISM transfers, but the EDGE fails the 11-gate bar at EVERY DTE (incl. 0DTE baseline)**

The dollar-stop lever's *mechanism* reproduces #1's result cleanly: capping the dollar loss holds maxDD ~flat across DTE, improves Sortino, and grows OOS dollars. BUT the #4 ATM edge does **not** clear the 11-gate structural bar even at its own 0DTE/-8% baseline — it fails **L173 (`oos_drop_top5 <= 0`)** at every DTE. There is no structurally-clean 0DTE floor for the lever to upgrade, so per the BAR no DTE>0 cell is a clean win. This is the honest "the lever may not transfer cleanly" outcome the task flagged for #4 (smaller-n, chart-stop-only ~breakeven).

## CALIBRATION (C29 — RE-DERIVED for #4 at ATM; NOT transferred from #1)

- **dollar_thresh = $36.48** (median per-trade dollar loss on the 47 0DTE -8% losers at ATM) — **distinct from #1's $67.68** (C29 satisfied: re-derived per edge AND per tier).
- median entry premium: 0DTE $1.48 -> 1DTE $2.66 -> 2DTE $3.51 (premium grows with DTE — same reason the -8% percent stop = a bigger dollar loss at higher DTE).
- percent-scaled pct: 0DTE -8.00% -> 1DTE -4.45% -> 2DTE -3.38%.

## THE FULL MATRIX (real fills, ATM)

| construction | DTE | n | WR% | exp/tr | OOS n | OOS exp/tr | OOS total | maxDD | Sortino | worstDay | posQ | 11-gate (struct+L173) | CLEAN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **a. percent -8% (baseline)** | 0 | 80 | 41.2 | +24.88 | 24 | **+19.77** | 474.60 | **-549.36** | **10.06** | -145.44 | 5/6 | **FAIL** (L173 oos_drop5=-19.83) | — (baseline) |
| a. percent -8% | 1 | 85 | 30.6 | +19.57 | 25 | +22.26 | 556.38 | -739.92 | 4.76 | -184.08 | 6/6 | **FAIL** (drop5_full + L173) | NO |
| a. percent -8% | 2 | 84 | 32.1 | +25.19 | 24 | +42.26 | 1014.30 | -1080.96 | 4.73 | -219.60 | 5/6 | **FAIL** (L173 oos_drop5=-30.84) | NO |
| **b. dollar-anchored ($36.48)** | 0 | 80 | 41.2 | +27.94 | 24 | +21.08 | 505.80 | -328.32 | 15.87 | -36.48 | 5/6 | **FAIL** (L173 oos_drop5=-11.79) | NO (DTE=0) |
| **b. dollar-anchored ($36.48)** | **1** | **85** | 25.9 | +31.75 | 25 | **+37.45** | **936.36** | **-620.16** | **16.05** | **-36.48** | 5/6 | **FAIL** (L173 oos_drop5=-14.83) | NO (fails 11-gate) |
| b. dollar-anchored ($36.48) | 2 | 84 | 25.0 | +44.68 | 24 | +44.56 | 1069.56 | -401.28 | 22.45 | -36.48 | 6/6 | **FAIL** (L173 oos_drop5=-21.49) | NO |
| **c. chart/level (price-only)** | 0 | 80 | 75.0 | -8.03 | 24 | -16.45 | -394.80 | -3290.04 | -0.44 | -1799.82 | 3/6 | **FAIL** (oos_exp<0, posQ, L173, ...) | NO |
| c. chart/level | 1 | 85 | 62.4 | +16.99 | 25 | -77.69 | -1942.21 | -2489.11 | 0.87 | -1275.00 | 3/6 | **FAIL** (oos_exp<0, top5=234.7, L173) | NO |
| c. chart/level | 2 | 84 | 60.7 | +36.97 | 24 | -75.46 | -1811.10 | -4117.20 | 1.49 | -1737.00 | — | **FAIL** (oos_exp<0, L173) | NO |
| **d. percent-scaled** | 0 | 80 | 41.2 | +24.88 | 24 | +19.77 | 474.60 | -549.36 | 10.06 | -145.44 | 5/6 | **FAIL** (L173) | NO (DTE=0) |
| **d. percent-scaled** | 1 | 85 | 25.9 | +28.93 | 25 | +32.51 | 812.83 | -515.59 | 12.36 | -102.39 | 5/6 | **FAIL** (L173 oos_drop5=-21.01) | NO |
| d. percent-scaled | 2 | 84 | 22.6 | +33.03 | 24 | +12.33 | 296.01 | -557.89 | 14.12 | -92.78 | 5/6 | **FAIL** (L173 oos_drop5=-44.02) | NO |

## FINDINGS (honest, per C7/C18)

1. **The dollar-stop MECHANISM transfers exactly as for #1 — it just cannot rescue a sub-bar edge.** 1DTE/dollar vs 0DTE/-8% baseline: OOS total +$461.76 ($475 -> $936), maxDD only +12.9% (-$549 -> -$620, well inside the +25% bar), Sortino +60% (10.06 -> 16.05), worst day capped at exactly -$36.48 (the dollar cap working as designed). On the four numeric clean-win legs (lift_kept / maxdd_ok / sortino_holds / killswitch) **1DTE/dollar PASSES all four** — it fails ONLY the structural 11-gate.

2. **The blocker is L173, and it pre-exists the DTE/stop choice.** The 0DTE/-8% baseline itself fails `oos_drop_top5 = -19.83 <= 0`: drop the 5 best OOS days and the ATM #4 OOS expectancy goes negative. The edge's OOS profit is concentrated in a handful of days. The dollar-stop reduces the concentration somewhat (oos_drop5 improves -19.83 -> -14.83 at 1DTE) but does not flip it positive. Unlike #1 — whose 0DTE baseline CLEARED the bar, giving the lever a clean floor to lift — #4 has no clean floor.

3. **C29 confirmed live:** #4's re-derived dollar-stop ($36.48) is ~half of #1's ($67.68), driven by #4's smaller ATM entry premiums ($1.48 vs $2.55 median). Transferring #1's $67.68 would have over-capped #4 by ~85% and corrupted the A/B. The per-edge/per-tier re-derivation was load-bearing.

4. **chart-stop-only is a hard trap for #4 (worse than for #1).** It posts a 75% 0DTE WR but OOS expectancy is *negative* at every DTE (-$16 / -$78 / -$75), maxDD blows to -$2.5K..-$4.1K, worst day -$1.3K..-$1.8K (blows even the Safe-2 -$600 kill switch). This corroborates the b5 scorecard's chart-stop-only OOS ~breakeven (+$0.15/tr) note: the -8% premium truncation IS #4's risk management. C3/L172 "WR is a theta trap" — confirmed a second time.

## RECOMMENDATION

**Do NOT ship a #4 DTE/stop change.** The edge does not clear the 11-gate bar at any DTE (incl. baseline) — it is not auto-ship-eligible and there is nothing clean to upgrade. #4 remains dormant pending a fix to its OOS concentration (L173), which is an ENTRY-quality problem (too few load-bearing OOS days), not a stop-construction or DTE problem. The dollar-stop lever is confirmed sound as a mechanism but cannot manufacture an edge that the entry does not already have.

### Caveats (honest)
- **Smaller n than #1:** 85 signals / oos_n 24-25 (vs #1's 166 / 50-51). The 1DTE/dollar OOS lift is real but rests on ~25 OOS trades — thin.
- **The #4 A/B baseline mirrors b5 but is NOT identical:** b5's scorecard runs `simulate_trade_real` (lib.simulator_real) and reports the robust ATM cell CLEARING all 8 gates (oos_exp +$79.49, oos_drop5 +$25.91). This DTE harness uses `_dte_expansion_sim`'s settlement machinery (real OPRA day-T bars + intrinsic settlement) — a DIFFERENT fill path — under which the same config's 0DTE baseline reads oos_exp +$19.77 and fails L173. The lever A/B is internally consistent (all cells use the SAME harness), but the absolute level / gate result is harness-dependent: the b5 simulator_real result is the production authority for whether #4 clears gates; this harness is the authority for the DTE/stop DELTA. The transferable finding is the DELTA (dollar-stop holds maxDD flat, grows OOS, +Sortino); the absolute "does #4 clear" verdict belongs to b5.
- **2DTE:** unlike #1 (where 2DTE blew the kill switch), #4's dollar-stop holds 2DTE worst-day at -$36.48 too — but it still fails L173, so it is not a win.

**Artifacts:** full JSON at `analysis/recommendations/dte-stop-construction-vix_regime_dayside.json`.
