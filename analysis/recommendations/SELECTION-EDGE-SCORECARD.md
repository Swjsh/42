# Selection-Edge Campaign — Honest Ranked Scorecard

> **Run date:** 2026-06-20 · **Window:** 2025-01-01 .. 2026-05-15 (342 trading days)
> **Thesis under test:** *"SELECTION / CONFLUENCE is the edge"* — a selective detector (or stacked confirmations) converts the 0DTE coin-flip into a real per-trade option edge where ~32 mechanical-daily-signal strategies have died.
> **Fills authority:** real OPRA via `lib.simulator_real.simulate_trade_real` (C1) — not BS-sim. **Cost:** $0, no live orders.
> **Mandatory gate stack (OP-11 + fraud gates):** (1) n>=20, (2) OOS(2026)/tr > 0, (3) IS(2025)/tr > 0 [futures-trap / single-regime guard], (4) positive quarters >= 4/6, (5) top5-day concentration < 200%, (6) P&L after dropping top-5 days > 0, (7) beats 20-seed random-entry null, (8) no-truncation: sign does NOT invert at chart-stop-only (-0.99).
>
> **Two distinct things are tested in this campaign:** (A) does a *new selection rule* create edge (multi-signal-agreement, vwap+confluence, bearish-confluence, confluence-score-extreme)? and (B) can the *already-proven* vwap_continuation survivor be improved (regime-conditional sizing)? Ranked together below; the survivor itself is the anchor.

---

## Ranking

| Rank | Hypothesis | n | per-trade | IS / OOS | pos Q | drop-top5 | beats null | trunc-safe | Gates | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| **1** | **vwap_continuation** (the survivor / anchor) | 149 | **+$68.78** | +$58.55 / +$94.84 | 6/6 | +$54.44 | YES (+$72.06 vs null max +$17.21) | YES (chart-stop +$97.93) | **8/8 PASS** | **SELECTION_EDGE — CONFIRMED. SHIP (already live).** |
| **2** | **regime_conditional_vwap_sizing** (sizing overlay on #1) | 103 | +$215.88 (OOS) | +$137.51 / +$215.88 | 6/6 | +$11,530 | YES (100th pctile) | YES (chart-stop +$17,714) | **8/8 PASS** *(verified)* | **CONFIRMED edge — but NOT a Safe-account drop-in (see caveat). Ship size-DOWN leg only.** |
| 3 | confluence_score_extreme | 790 | +$5.58 (OOS-ish) | +$3.87 / +$9.99 | 4/6 | +$1,643 | YES | **NO** | 7/8 FAIL (G7) | **FAIL / KILL — truncation artifact (sign inverts to -$32.19 at chart-stop).** |
| 4 | multi_signal_agreement (>=2) | 279 | +$2.13 | -$0.24 / +$7.92 | 4/6 | -$6.52 | **NO** (null +$10.06 > +$7.92) | **NO** (-$38.36) | 4/8 FAIL | **FAIL / KILL — single-regime + top5=399% + loses to random timing.** |
| 5 | bearish_rejection_strict_confluence | 107 | -$12.68 | -$12.16 / -$14.22 | 1/6 | -$26.06 | **NO** | YES* | 2/8 FAIL | **FAIL / KILL — loses in BOTH regimes; J-anchor edge_capture = $0.** |
| 6 | vwap_plus_confluence | 8 | -$10.14 | -$4.66 / -$19.28 | 1/4 | -$130.32 | **NO** | **NO** | 0/8 FAIL | **FAIL / INCONCLUSIVE-BY-N — confluence over-constrains 158 → 8 signals; destroys the survivor.** |

\* bearish-confluence is "truncation-safe" only trivially — it is negative at BOTH the -8% stop and chart-stop-only, so there is no sign to invert.

---

## Detail — by rank

### 1. vwap_continuation — THE SURVIVOR. CONFIRMED. (the only standalone selection that works)

- **Config (exact):** detector = byte-for-byte `vwap_continuation_watcher` port (first 3 RTH closes same-side of as-of VWAP = day side; first in-trend continuation = one causal entry/day, next-bar-open fill, no look-ahead). Structure = **strike_offset = -2 (ITM-2), premium_stop_pct = -0.08, qty 3, v15 exits.**
- **Numbers:** n=149 (158 signals, 94.3% fill), per-trade **+$68.78**, IS(2025) **+$58.55**, OOS(2026) **+$94.84**, **6/6 positive quarters** (min 2026Q2 +$17.94), top5-day 23.5%, drop-top5 **+$54.44/tr**, WR 48.3%. Both sides positive (C +$84 n=82, P +$71 n=67 — *from the sizing run*).
- **Fraud gates:** no-truncation **PASS** (chart-stop-only +$97.93 holds the sign vs chosen +$64.45); random-null **PASS** (chosen +$64.45/tr beats null **max** +$17.21; null mean -$7.61; edge-over-null +$72.06). **8/8 PASS.**
- **OP-11 bar:** CLEARED — OOS positive AND IS positive (not the futures-trap artifact) AND sub-window stable (6/6 quarters) AND beats random null AND survives chart-stop (signal alpha, not a premium-stop truncation trick). A/B-grade evidence is in `sel-vwap-continuation.json`.
- **SHIP STATUS:** **ALREADY LIVE** — `j_vwap_cont_enabled=true` was shipped 2026-06-?? (see CHANGELOG "SHIP VWAP-continuation LIVE"). This campaign **re-confirms** the live edge under the full fraud-gate stack — it is the first and only candidate to clear ALL 8 gates including both fraud gates. Under the standing "ship profitable-validated → flip + report for REVOKE" authorization, no further action is needed beyond this REVOKE-note: **the edge is real and remains in production.**

### 2. regime_conditional_vwap_sizing — CONFIRMED edge, conditional ship

- **Config (best dynamic):** `2x_below_skip_top_tercile` — on the vwap_continuation survivor, size **6** when entry VIX <= causal expanding-window median, **SKIP** the top VIX tercile, base **3** otherwise (warmup 8 trades, no look-ahead).
- **Numbers (best dynamic):** n=103, OOS/tr **+$215.88**, IS/tr **+$137.51**, **6/6 positive quarters**, top5-day 27.8%, drop-top5 **+$11,530**, beats null (100th pctile), chart-stop total **+$17,714** (sign holds). **8/8 PASS — independently re-implemented and reproduced to the cent** (`sel-regime_conditional_vwap_sizing.VERIFY.json`).
- **OP-11 bar:** the *gate stack* is cleared and verified. **BUT the honest caveats block a clean Safe-account ship:**
  1. `best_beats_flat_clean = FALSE` — every size-UP (2x) schedule lifts return by **deepening dollar drawdown** (2x_below_skip_top maxDD -$784 vs FLAT -$612, ~+$172 deeper; 2x_below_median -$950). The gain is *concentration of capital into good regimes*, not a free lunch.
  2. **Account cap breach:** 2x ITM-2 sizing breaches the $2K Safe **30%-per-trade cap** (maxDD already 39-47% of $2K notional). The size-UP variants are a **larger-account / Bold** concept.
  3. The **only clause-compliant ("without increasing ruin") leg** is **`skip_top_tercile_only`** (size DOWN / skip worst regime, NEVER up): RAISES OOS/tr to **+$142.54**, SHRINKS maxDD to **-$424** and worst trade to -$85, at the cost of lower absolute dollars (+$9,541 total, fewer contracts deployed). This leg also clears all gates.
- **SHIP STATUS / how:** **Ship the `skip_top_tercile_only` leg** as a Safe-account-appropriate regime filter — it strictly reduces ruin while raising OOS per-trade, so it is *unambiguously profitable-validated* and ships under the standing authorization. Mechanism: add a causal-VIX-tercile abstention gate to the vwap_continuation arm (skip entries when entry-time VIX is in the expanding-window top tercile). **The 2x size-UP leg is a Bold/larger-account overlay — file as a Treasurer/Rule-9 after-hours item, paired with the existing post-loss-throttle design from `SIZING-STUDY-2026-06-19.md`, NOT a Safe-2 drop-in.** Report both for REVOKE.

### 3. confluence_score_extreme — FAIL (truncation artifact)

- Top-decile conviction (data-driven 76.7/100) AND >=4 confluence factors agreeing. **Not actually rare** — fired ~856 bars / 790 trades (~5% of 18,443 reads), so N is large.
- Superficially passes 7/8: OOS +$9.99, IS +$3.87, 4/6 quarters, top5 62.7%, drop-top5 +$1,643, beats null.
- **G7 KILLS it:** re-run on chart-stop-only the per-trade **inverts to -$32.19 overall / -$17.41 OOS** — textbook stop-misfire / theta-trap (C3 / L58 / L100). WR only ~24-28% → the "edge" is pure asymmetric -8%-stop mechanics on ITM-2, not directional or hit-rate edge. Matches the confluence engine's own CALIBRATION_TAG verdict: *awareness, not alpha.* **Do NOT ship.**

### 4. multi_signal_agreement — FAIL (mirage)

- >=2 distinct independent watchers same direction within 15min, 45min cooldown. n=279, OOS looks +$7.92 — but it's a mirage: **IS half NEGATIVE (-$0.24)** (single-regime / futures-trap), **top5-day 399%** with **drop-top5 NEGATIVE (-$1,775)**, **loses to random null** (random same-day timing scored HIGHER, +$10.06 > +$7.92 → the agreement timing added nothing), and **sign inverts at chart-stop** (+$7.92 → -$38.36). Tightening to >=3 made it strictly worse (negative everywhere, 2/6 quarters). **Independent-detector confluence is awareness only, NOT a trigger** (C4 / L154).

### 5. bearish_rejection_strict_confluence — FAIL (loses everywhere; misses J's winners)

- STRICT >=2-of-4 confluence (named-level rejection / ribbon-flip-bear / multi-day trendline / sequence-rejection), 09:35-11:00 ET, puts only, survivor structure. n=107, WR 28%, per-trade **-$12.68**, IS **-$12.16**, OOS **-$14.22** (negative in BOTH regimes → loses everywhere), 1/6 quarters, total -$1,357. Beaten by random null (chosen -$16.44 vs null max +$4.21).
- **Decisive J-anchor finding:** `edge_capture = $0` — the strict gate **never reaches 2 components on ANY of J's 3 winner days** (4/29, 5/01, 5/04 each fire only ONE structural component). Strict confluence selected MORE trades, not BETTER ones, and **did not co-locate with J's real winners** (C24: anchor trades are one-off exceptional setups; the general same-pattern population are losers; structural substitutes don't reproduce J's hand-drawn levels/trendlines). **Do NOT ship.**

### 6. vwap_plus_confluence — FAIL / inconclusive-by-N (over-constrains the survivor)

- Take vwap_continuation but keep ONLY (named-level within $0.30 AND ribbon-aligned AND vol>=1.3x). Collapses 158 → **8** signals (below n>=20). Subset is **worse**: -$10.14/tr (OOS -$19.28) vs vwap-alone +$56.01 (OOS +$63.73) over the identical structure. 0/8 gates.
- **Root cause:** the rarest confirmation is named-level-within-$0.30 (only 33/158) — *structurally contradictory* with a vwap-CONTINUATION entry, which by definition extends AWAY from levels. **More confirmations did NOT sharpen — they over-constrained the proven survivor into noise.** Unfiltered survivor stays production.

---

## The verdict, stated plainly

**Selection is NOT a generic edge.** Stacking more independent confirmations (#3 confluence-score, #4 multi-signal-agreement, #5 bearish-confluence, #6 vwap+confluence) DID NOT convert the coin-flip into an option edge — in every case it either narrowed nothing (still a theta-trap that dies at chart-stop), selected MORE trades not BETTER ones, or over-constrained the one survivor into noise. This is consistent with C4/L154: a cross-sectional / agreement signal != a per-trade option edge.

**The edge is the *specific structural selectivity* of the vwap_continuation setup + compounding.** vwap_continuation works because it is selective in a STRUCTURAL way (morning VWAP-side trend continuation, one causal entry/day) — not because it stacks confirmations. The campaign therefore VALIDATES the survivor and INVALIDATES the "generic confluence" generalization. The one genuinely additive finding is **regime selection (skip the worst VIX tercile)** — which is itself a *subtractive* selectivity (skip bad regimes), not an additive (require more confirmations) one. That direction is the live research vein.

**Per the Implement phase: the next-best lever is the sizing/compounding doctrine** (`markdown/research/SIZING-COMPOUNDING.md`, `sel-vwap-sizing.json`): Kelly never binds — Rule 6's 30% cap / 6% ceiling / min-3 floor is the active governor; true ruin ~0% (the -8% stop caps loss); the real small-account threat is **STRANDING** ($5K min-3 ITM-2 throttled by the 6% ceiling strands 46.7% of paths). Cheapest fix surfaced: fund Safe-2 to >=$2.5K to unlock full ITM-2 edge (+$78/tr vs OTM-2 +$21/tr).

---

## NEXT-ITERATION RECOMMENDATION (keep testing until profitable — do NOT stop)

The directive is to keep iterating. Three concrete next tests, in priority order:

1. **[HIGHEST — ship-adjacent] Wire + validate the `skip_top_tercile_only` VIX-abstention gate onto the live vwap_continuation arm.** It is already gate-clean and ruin-reducing (OOS +$142.54, maxDD -$424). Next iteration = re-run it through `verify_edgehunt_candidates.py` GATE_FRAUD on Safe-2's exact OTM-2 structure (NOT just ITM-2 — C29: knobs don't transfer across strike tiers) to confirm it survives on the account that will actually trade it, then flip the flag.

2. **[the real research vein — subtractive selection] Sweep the regime/abstention axis, not the confirmation-count axis.** Since *requiring more* failed but *skipping bad regimes* worked, test other causal "skip-when" filters on the survivor: skip on (a) gap-day open beyond N-ATR, (b) first-15min range > prior-day-range tercile, (c) VIX *character* (rising vs falling 5-day slope, per C5/L40 — character > level). Same 8-gate stack, same survivor structure. Hypothesis: the edge concentrates in calm/trending mornings; skipping the chaotic tail lifts per-trade without adding trades.

3. **[extend the survivor structurally, not by confluence] Test a SECOND structural one-entry/day detector of the same family** — e.g. an **opening-range-reclaim continuation** or **VWAP-reclaim-after-failed-break** (structural, causal, one entry/day) through the identical 8-gate + fraud stack. The lesson from this campaign is that the winning shape is "selective structural continuation, one causal entry/day" — so the next survivor candidate should mimic that *shape*, not stack confirmations on top of it.

**Do NOT pursue further additive-confluence variants** — that axis is now triple-killed (confluence-score, multi-signal-agreement, vwap+confluence all died the same way).
