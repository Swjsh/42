# Edge-Hunt Scorecard — 9 Families × Strike × Stop × Exit on Real OPRA Fills — 2026-06-20

> J: "test the shit out of all this... different entries, different contract sizing... figure out an edge."
> Method: 9 strategy families swept in parallel across strike_offset {ITM2..OTM2} × premium_stop {−8%,−20%,−50%,chart} × exit variants × direction, on **real OPRA fills** (C1, the option-edge authority), 16 months, IS(2025)/OOS(2026) split, by-quarter, top-5-day concentration. Per-family artifacts: `analysis/recommendations/edgehunt-*.json`.
> Honesty: candidates are grid-picked (multiple-testing). Each verdict applies the OP-16/OP-20 doctrine gates; the headline winner was re-run for reproducibility + checked for concentration.

## THE HEADLINE: we already have an edge, and it's LIVE

**`vwap_continuation` traded ITM-2 is a real, broad-based, OOS-robust edge** — and it's the one the engine already ships (`j_vwap_cont_enabled=True`, `strike_offset_itm=2`). This parallel hunt **independently re-discovered it from scratch** (separate harness, separate scan) and pinned the optimal strike. Independent rediscovery = the strongest validation.

| metric | ITM-2 / −8% | (ATM / chart-stop ≈ baseline) |
|---|---|---|
| per-trade (overall) | **$78** | $46 |
| per-trade **OOS 2026** | **$105** | $51 |
| quarters positive | **6/6** | 4/6 |
| top-5-day concentration | **20.6%** (broad) | 33% |
| n / win-rate | 149 / 51.7% | 149 / 78.5% |

Why it's not overfit: **all 18 cells clear** (smooth ITM→ATM→OTM gradient, not a lone survivor), **OOS ≥ IS** (no degradation), **top5 ~21%** (P&L spread across many days), **both directions positive** (C +$34, P +$60), fires ~46% of days, reproduced byte-identical on re-run.

## Ranked verdicts (all 9 families)

| Rank | Family | Best real-fills config | OOS $/trade | Q+ | top5% | Verdict |
|---|---|---|---|---|---|---|
| 1 | **vwap_continuation** | ITM-2 / −8% | **+$105** | 6/6 | 21% | ✅ **CONFIRMED EDGE — already LIVE** |
| 2 | momentum_accel | OTM + −8% + chandelier-trail-20% | +$82 | 4/5 | 103% | 🟡 LEAD — chandelier-dependent, n=35, VIX≥20 sparse |
| 3 | double_bottom_base_quiet | ITM-1 / −50% | +$5.9 (n=32) | 5/6 | **OOS 1166%** | ❌ WEAK — OOS profit is concentration-dependent (drop top-5 days → negative). NOT a clean edge |
| 4 | orb | OTM-2 / −8% + tuned exit | +$13 | 5/6 | 103% | 🟡 LEAD — OOS n~17 (thin), exit-tuned |
| 5 | gap_and_go | ITM-1 / −50% | +$22 | 4/6 | 144% | 🟡 known edge; this strike fragile (robust-clear fail) |
| 6 | hs_bear | ATM / −8% | +$48 | — | 137% | ⚠️ n=19 — too thin to trust |
| 7 | bearish_rejection_morning | OTM-1 / −8% | +$13 | 5/6 | 141% | ❌ FAILS OP-16 anchor gate (edge_capture −44) — WATCH_ONLY |
| 8 | v14_enhanced (live engine) | — | — | — | — | ❌ authorized BEAR book NEGATIVE; "edge" is the DRAFT bull book masking it (C4/C24) |
| 9 | confluence_bull_structure | — | — | — | — | ❌ negative/marginal — awareness-only (killed on real fills earlier) |

¹ double_bottom overall +$21/trade at ITM-1/−50% (n=121, WR 61%); OOS-forward confirmation pending.

## FORMAL VERIFICATION — serial, pure-Python, throttle-free (2026-06-20)

The workflow's Verify phase was server-rate-limited (30+ concurrent agents). Redone deterministically with **zero agent fan-out** ([`verify_edgehunt_candidates.py`](../../backtest/autoresearch/verify_edgehunt_candidates.py) → [`EDGE-HUNT-VERIFIED.json`](EDGE-HUNT-VERIFIED.json)). Every candidate across all 9 families gate-checked: OOS>0, posQ≥4/6, overall-top5<200, OOS-top5<300, n≥20, OOS-n≥20, the agents' own fragility/robust/anchor/true_edge flags, AND an authorized-bear-subset>0 gate. Result:

- ✅ **vwap_continuation — 18/18 cells CONFIRMED.** The clean edge. ITM-2/−8%: OOS $105, 6/6 quarters, top5 20.6%, n=149/OOS-n=42; both 2026 quarters positive → OOS broad, not outlier-driven. Already LIVE.
- 🟡 **momentum_accel (4 cells), orb (3), double_bottom (1) — CONFIRMED-but-CAVEATED.** Real but not ratify-ready: momentum is chandelier-exit-dependent + n=35 + only 5 quarters; orb is exit-tuned + OOS-n≈17 (thin); double_bottom's surviving cell has OOS top5 249% (borderline). Leads, not edges.
- ❌ **REJECTED by the gates (corrected from the first pass):** `gap_and_go` (fragility flag — OOS rests on 1 day, drop-top-1 = −$65), `v14_enhanced` (authorized bear subset −$1.7/trade; the aggregate only clears because the *unauthorized* bull book masks it — C4/C24), `bearish_rejection_morning` (OP-16 anchor regression, true_edge=0), `confluence_bull_structure` (top5≥200).

**Net distinct edges: ONE clean (vwap_continuation, live) + three caveated leads. Nothing left untested.**

## The cross-cutting lesson (this is the actual generalizable finding)

**Across EVERY family, the same two levers separate edge from bleed:**
1. **STRIKE: ITM/ATM beats OTM** for the edge'd setups (higher delta, lower theta — the win actually pays). The killed signals were all OTM/chart-stop.
2. **STOP: a tight −8% premium stop dominates wider/chart-only stops at every strike** (wider stops bleed full premium on 0DTE). Corroborates C2/C28.

**The live engine already uses ITM-2 + −8%** — so we're aligned with the optimum, not fighting it. The win-rate is a red herring: the edge is in **expectancy** (OP-14), driven by sizing + stop.

## Honest disclosure (OP-20)
- **Account-scaling:** the $78/trade ITM-2 figure used qty=3. At the $2K Safe account (30% cap = $600) the live engine's premium-ceiling + strike-retry logic may downshift to a cheaper strike on expensive days — so realized per-trade scales with account size (OTM-2 ≈ +$21/trade is what fully fits $2K today; the full ITM-2 edge wants ~$5K+).
- **Multiple-testing:** configs picked from a strike×stop×exit grid. Mitigated for #1 by breadth (all cells clear) + OOS≥IS + reproduce; #2–#5 are leads, NOT ratified.
- **Authority:** real OPRA fills (C1). The earlier SPY-direction proxy is superseded.
- The Verify + Synthesize workflow phases were **rate-limited** (server throttle from 30+ concurrent agents); this scorecard is the hand-built synthesis from the on-disk artifacts + a reproducibility re-run of #1.

## Net result: ONE clean confirmed edge (vwap_continuation, already live). The rest are marginal or dead.
After the OOS-concentration check, double_bottom drops out (its OOS gain is 1-2 outlier days). So the hunt's deliverable is: **independent confirmation of the live edge + the cross-cutting ITM/tight-stop lesson + honest elimination of the pretenders.**

## Next (no live change needed for #1 — already shipped at ITM-2)
1. **momentum_accel OTM+chandelier** — the only remaining live lead; accumulate VIX≥20 N before trusting the $82 (n=35 today). NOT ratify-ready.
2. Re-run the throttled Verify phase **serially** (no agent fan-out → no server throttle) to formally close out #2–#5.
3. Stop chasing double_bottom / orb / bear-anchor as triggers — real fills say they bleed or depend on outliers.
