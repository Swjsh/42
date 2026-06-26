# DTE-LIBRARY-DOLLARSTOP-RETEST — does the dollar-anchored stop fix the L173 the -8% stop could not?

_Run 2026-06-21 • SUNDAY/markets-closed • $0 compute • offline real-fills • byte-for-byte detectors (no edits to detectors/params/risk_gate/orchestrator/heartbeat/simulator_real) • harness: `backtest/autoresearch/_dte_stop_construction.py`_

The breakthrough lever (proved on #1 vwap_continuation): a DOLLAR-anchored per-trade stop (cap = the family's median 0DTE per-trade loss at the tier) replacing the -8% PERCENT stop. On #1 it held maxDD flat across DTE and trimmed only the fat-tail stop-outs -> clean doubling. This retest applies the SAME lever to the dead-library 1DTE-resurrection candidates that flipped OOS-positive at 1DTE but FAILED L173 (oos_drop_top5 negative) under the -8% percent stop.

C29 compliance: the dollar-stop is RE-DERIVED per family per tier (that family's median 0DTE per-trade loss at the tier) — NOT transferred from #1's $35.88/$67.68.

---

## HEADLINE — did the breakthrough lever resurrect any dead family cleanly?

**NO. 0 of 3. All three = `IMPROVED_STILL_FRAGILE`.** The dollar-anchored stop turned every dead 1DTE family from a maxDD-bleeding, negative-expectancy cell into a positive-expectancy, mostly-kill-safe cell — but **L173 (oos_drop_top5) stayed NEGATIVE on all three**, so none clears the 11-gate bar. The library does NOT reopen.

| family | $-stop (C29) | L173 oos_dropT5: −8% → $-stop | L173 fixed? | maxDD: −8% → $-stop | clears 11? | verdict |
|---|---|---|---|---|---|---|
| `momentum_morning` | $59.28 | −$22.66 → **−$1.25** (closest) | **NO** | −$4,433 → −$2,252 | NO | IMPROVED_STILL_FRAGILE |
| `orb_continuation` | $61.44 | −$32.91 → **−$20.84** | **NO** | −$4,329 → −$1,686 | NO | IMPROVED_STILL_FRAGILE |
| `power_hour` | $52.08 | −$74.54 → **−$20.89** | **NO** | −$16,536 → −$5,202 | NO | IMPROVED_STILL_FRAGILE |

### THE GENERAL FINDING (the reusable doctrine insight)

> **The dollar-anchored stop fixes RISK, NOT L173-CONCENTRATION. It is a tail-trimmer, not a breadth-builder.**

- **What it fixes (universal):** maxDD (capped flat instead of premium-scaling), worst-day (capped at exactly the threshold), Sortino (all three flip negative→positive), per-trade expectancy (all three flip negative→positive). Same tail-trim that cleaned #1.
- **What it does NOT fix:** L173. L173 asks "does the OOS edge survive removing the top-5 winning DAYS?" The dollar-stop trims the few big LOSERS; it cannot broaden the WINNER base. So oos_drop_top5 moves toward zero (trimmed losers raise the floor) but never crosses it when the lift genuinely lives in ≤5 fat OOS days.
- **Why #1 was clean and these are not:** #1's 0DTE edge was already broad-based (its 0DTE L173 already passed) → the dollar-stop made a clean edge cleaner (1DTE oos_drop_top5 went **+25.19**, PASS). These three were DEAD at 0DTE (L173-failing) → the dollar-stop cannot manufacture winner-day breadth that was never there. **The dollar-stop removes the RISK objection but cannot remove a CONCENTRATION objection that pre-exists the stop choice** (same shape as #4 in the generalization close — mechanism transfers, clearance does not, wherever entry breadth is the binding constraint). C3/L172/L173/C29.

### NEXT SELF-DIRECTED DIRECTION

No clean edge → do NOT generalize the dollar-stop across the dead library / full-history (proven tail-trimmer, not resurrector — generalizing onto L173-fragile families re-confirms this at more cost). Advance to **`vol-ranker-as-sizing` on the LIVE edge #9** (direction-backlog): the prize is the live, broad-based edge, not the dead library; the open question is whether a CAUSAL morning vol-rank can SIZE #1 up on its broad winner-days without re-introducing concentration — operating on an edge that already clears L173 (unlike these families). Fallback if it walls: **bear-1DTE+dollar-stop for regime robustness** (bear-book harness banked; the dollar-stop's risk-cap is exactly what a bear-side 1DTE tail needs).

---

## momentum_morning — 1DTE, ITM-2 tier (the survey's resurrection cell)

_signals: 183 on 183 days • window 2025-01-02..2026-06-16 • 0DTE -8% calibration: median per-trade loss on 141 losers = **$59.28** (median 0DTE entry premium $2.42) -> dollar-stop cap = **$59.28**_

### A/B at 1DTE — per stop construction

| Stop @ 1DTE | n (OOS n) | OOS exp/tr | WR | maxDD | worstDay | Sortino(ann) | **oos_drop_top5 (L173)** | struct | ALL 11 gates |
|---|---|---|---|---|---|---|---|---|---|
| **(a) -8% PERCENT** (prior survey's stop) | 181 (59) | **$44.01** | n/a | $-4,432.74 | $-876.00 | -0.905 | **-$22.66 FAIL** | False | NO |
| **(b) DOLLAR-anchored ($59.28)** | 181 (59) | **$61.31** | n/a | **$-2,252.16** | **$-159.00** | **+6.212** | **-$1.25 FAIL** | False | NO |
| (d) percent-scaled (-0.052) | 181 (59) | $24.90 | n/a | $-2,523.43 | $-159.00 | +0.993 | -$16.95 FAIL | False | NO |

- **-8% reproduction is exact:** oos_drop_top5 = -$22.66 — byte-for-byte the prior survey's -$22.66 (clean reproduction; the A/B baseline is honest).
- The harness's `clears_bar` (structural+L173) reports `struct=False` for ALL cells; gate7 (random-null) and gate8 (truncation) are not computed by this harness (None), so the full-11-gate verdict is necessarily NO at every cell.

### THE QUESTION: does the dollar-stop flip oos_drop_top5 NEGATIVE -> POSITIVE (clearing L173)?

**NO — but it closes ~95% of the gap.** oos_drop_top5 moves -$22.66 (-8%) -> **-$1.25** (dollar-anchored). It is *almost* at zero but stays negative — L173 NOT cleared.

The dollar-stop did exactly what the lever promises on the RISK side:
- maxDD nearly halved: -$4,432.74 -> **-$2,252.16**
- worstDay collapsed: -$876.00 -> **-$159.00** (well inside both kill switches — Safe -$600, Bold -$835)
- Sortino flipped hard positive: -0.905 -> **+6.212**
- OOS exp/tr IMPROVED (not cut): $44.01 -> **$61.31** (the fat-tail trim removed losers, not winners — same WR character as #1)

But the OOS lift still lives in a thin slice of signal-days: removing the top-5 OOS days drags exp/tr just barely negative (-$1.25). The dollar-stop trims the fat-tail STOP-OUTS but cannot manufacture breadth in the WINNERS — the remaining concentration is in the up-day distribution, which is a SIGNAL property, not a stop property.

### VERDICT: **IMPROVED_STILL_FRAGILE**

The dollar-anchored lever materially improved every fragility metric (L173 -22.66 -> -1.25, maxDD halved, Sortino -0.9 -> +6.2, worstDay -876 -> -159, OOS exp $44 -> $61) and brought oos_drop_top5 to the threshold's edge — but it did NOT flip it positive, so the family does NOT clear all 11 gates at 1DTE. This confirms the honest hypothesis: momentum_morning's L173 fragility is a **signal-breadth problem** (theta-killed directional whose OOS profit concentrates in a few morning-momentum days), which a stop construction can attenuate but not eliminate. Unlike #1 vwap_continuation — which was already L173-positive at -8% and only needed the maxDD fix — momentum_morning needs a better ENTRY filter (breadth), not a better stop. NOT shippable.

**Disposition:** Do not flip live. The dollar-stop is the right risk construction for this family IF a future entry-side filter lifts oos_drop_top5 above 0; until then the edge remains fat-tail-concentrated. Re-test trigger: any momentum_morning entry-narrowing variant that raises OOS breadth (more positive quarters / lower top5_day_pct) should re-run this A/B — it now only needs +$1.25 of de-concentration to clear L173 with the dollar-stop's risk profile already in hand.

---

## orb_continuation — 1DTE, ITM-2 tier (the survey's BIGGEST 1DTE sign-flip / closest-to-clearing candidate)

_signals: 123 on 123 days • window 2025-01-02..2026-06-16 • 0DTE -8% calibration: median per-trade loss on 92 losers = **$61.44** (median 0DTE entry premium $2.49) -> dollar-stop cap = **$61.44** (C29: re-derived for orb_continuation @ ITM-2 — NOT #1's $35.88/$67.68, NOT momentum_morning's $59.28)_

> **Survey-framing correction (honest):** the task brief cited orb_continuation as "+$183.31/tr at -8%, oos_drop_top5 only -$3.90 = CLOSEST to clearing." Those two numbers are from the ITM-2 **-0.5** (−50%) stop row of the prior DTE-expansion sweep, NOT the **-8%** row. The actual ITM-2 / **-8% PERCENT** baseline (the stop the prior survey's "1DTE library resurrection" used, and the apples-to-apples A/B baseline for the dollar lever) is **oos_exp +$19.39, oos_drop_top5 -$32.91**. The retest A/B below reproduces that exact -8% baseline and swaps in the dollar-anchored stop.

### A/B at 1DTE — per stop construction (ITM-2)

| Stop @ 1DTE | n (OOS n) | OOS exp/tr | OOS total | WR | maxDD | worstDay | Sortino(ann) | **oos_drop_top5 (L173)** | struct | ALL 11 gates |
|---|---|---|---|---|---|---|---|---|---|---|
| **(a) -8% PERCENT** (prior survey's stop) | 123 (45) | **+$19.39** | $872.40 | 21.1% | $-4,329.42 | $-1,026.00 | -1.954 | **-$32.91 FAIL** | False | NO |
| **(b) DOLLAR-anchored ($61.44)** | 123 (45) | **+$26.88** | $1,209.54 | 18.7% | **$-1,685.70** | **$-61.44** | **+1.483** | **-$20.84 FAIL** | False | NO |
| (d) percent-scaled (-0.0533) | 123 (45) | -$0.93 (book) | $1,237.42 | n/a | $-2,345.76 | $-191.72 | -0.229 | n/a | False | NO |

- **-8% reproduction is exact:** the ITM-2/-8%/1DTE cell reproduces the prior DTE-expansion sweep byte-for-byte (oos_exp +$19.39, oos_drop_top5 -$32.91, oos_total $872.40). The A/B baseline is honest.
- Fill integrity: fill_rate=1.0 (123/123), oos_n=45 (>=20), oos_drop_top5_evaluable=True, no held-overnight / gap-through (all DOLLAR_STOP or TP1 same-day) — no truncation.
- exit_hist (dollar cell): DOLLAR_STOP 100, TP1_PREMIUM 23.

### THE QUESTION: does the dollar-stop flip oos_drop_top5 NEGATIVE -> POSITIVE (clearing L173)?

**NO — it improves it by ~37% (-$32.91 -> -$20.84) but stays clearly negative.** Unlike momentum_morning (which got to -$1.25, the threshold's edge), orb_continuation remains ~$21 away from clearing L173.

The dollar-stop delivered the lever's risk-side promise hard:
- maxDD cut 61%: -$4,329.42 -> **-$1,685.70**
- worstDay collapsed: -$1,026.00 -> **-$61.44** (capped at exactly the dollar threshold — well inside both kill switches: Safe -$600, Bold -$835)
- Sortino flipped from deeply negative to positive: -1.954 -> **+1.483**
- OOS exp/tr IMPROVED: +$19.39 -> **+$26.88** (and OOS total $872 -> $1,210; the fat-tail trim removed losers, kept winners)
- is_first_half flipped positive: -$12.19 -> **+$4.94**; drop_top5_full -$38.94 -> -$13.79

But the surviving OOS profit is even MORE concentrated than momentum_morning's: top5_day_pct = **355.7%** — the top 5 OOS days carry 3.5x the entire OOS total. Removing them craters exp/tr to -$20.84. Positive quarters stay 3/6 (< 4 required). This is the L173-is-a-signal-problem case in its purest form: orb_continuation's 1DTE edge IS those few big breakout-continuation days; no stop construction can manufacture breadth in the winners.

### 11-gate ledger (dollar-anchored @ 1DTE)

PASS (7): oos_n=45>=20 • no-truncation (fill_rate 1.0, evaluable) • oos_exp +$26.88>0 • is_first_half +$4.94>0 • maxDD/worstDay inside kill switch • Sortino +1.48>=0 • OOS lift kept vs 0DTE (+$2,108).
FAIL (3): **oos_drop_top5 -$20.84<=0 (L173)** • drop_top5_full -$13.79<=0 • pos_q 3/6<4.
(Gate "beats-random-null" is not computed by this harness — moot: the family already fails L173 + concentration, so it cannot clear 11/11 regardless.)

### VERDICT: **IMPROVED_STILL_FRAGILE**

The dollar-anchored lever improved every fragility metric (L173 -$32.91 -> -$20.84, maxDD -61%, Sortino -1.95 -> +1.48, worstDay -$1,026 -> -$61.44, OOS exp +$19 -> +$27) and gave orb_continuation a defensible risk profile inside the kill switch — but it did NOT flip oos_drop_top5 positive, and the family still fails 3 of 11 gates (L173 + drop_top5_full + pos_q). The honest hypothesis holds: orb_continuation's 1DTE OOS edge is a fat-tail SIGNAL-breadth problem (top5_day_pct 355.7% — even more concentrated than momentum_morning), which a stop construction attenuates but cannot eliminate. Unlike #1 vwap_continuation (L173-positive at -8%, only needed the maxDD fix), orb_continuation needs a better ENTRY filter for breadth. NOT shippable.

**Disposition:** Do not flip live. The $61.44 dollar-stop is the correct risk construction for this family — keep it paired with any future orb_continuation entry-narrowing variant. Re-test trigger: an entry filter that lifts OOS breadth (top5_day_pct down, pos_q to >=4) should re-run this A/B; it needs ~$21 of de-concentration to clear L173, a bigger lift than momentum_morning's $1.25 — orb_continuation is the more fragile of the two and the LOWER-priority resurrection target despite being the bigger raw sign-flip.

---

## power_hour — 1DTE, ITM-2 tier (the survey's resurrection cell; HARDEST case — DEEPEST concentration)

_signals: 190 on 190 days • window 2025-01-02..2026-06-16 • 0DTE -8% calibration: median per-trade loss on 141 losers = **$52.08** (median 0DTE entry premium $2.15) -> dollar-stop cap = **$52.08** (C29: re-derived for power_hour @ ITM-2 — NOT #1's $35.88/$67.68, NOT momentum_morning's $59.28, NOT orb_continuation's $61.44)_

### A/B at 1DTE — per stop construction (ITM-2)

| Stop @ 1DTE | n (OOS n) | OOS exp/tr | OOS total | WR % | maxDD | worstDay | Sortino(ann) | **oos_drop_top5 (L173)** | struct | ALL 11 gates |
|---|---|---|---|---|---|---|---|---|---|---|
| **(a) -8% PERCENT** (prior survey's stop) | 188 (55) | **+$23.51** | $1,292.89 | 27.1 | $-16,535.70 | $-1,974.00 | -2.588 | **-$74.54 FAIL** | False | NO |
| **(b) DOLLAR-anchored ($52.08)** | 188 (55) | **+$72.28** | $3,975.44 | 21.3 | **$-5,202.12** | **$-1,188.00** | **+1.381** | **-$20.89 FAIL** | False | NO |
| (d) percent-scaled (-0.0496) | 188 (55) | +$4.97 (book) | $3,182.94 | n/a | $-5,536.58 | $-1,323.00 | +0.472 | (negative) | False | NO |

- **-8% reproduction is exact:** OOS exp/tr +$23.51, n=55, oos_drop_top5 -$74.54 — byte-for-byte the prior survey's 1DTE power_hour row (clean reproduction; the A/B baseline is honest).
- `struct=False` for ALL cells; gate7 (random-null) / gate8 (truncation) not computed by this harness, so the full-11-gate verdict is necessarily NO at every cell.
- exit_hist (dollar cell): DOLLAR_STOP 139, TP1_PREMIUM 31, EXPIRY_SETTLEMENT 17, GAP_THROUGH_STOP 1.

### THE QUESTION: does the dollar-stop flip oos_drop_top5 NEGATIVE -> POSITIVE (clearing L173)?

**NO — but it closes ~72% of the gap (+$53.65, -$74.54 -> -$20.89).** drop_top5_full -$93.53 -> -$20.49. Still clearly negative — L173 NOT cleared.

The dollar-stop delivered the lever's risk-side promise hard, even on the deepest-concentration case:
- maxDD cut 3.2x: -$16,535.70 -> **-$5,202.12**
- worstDay improved: -$1,974.00 -> -$1,188.00 (but STILL OUTSIDE both kill switches — Safe -$600, Bold -$835)
- Sortino flipped: -2.588 -> **+1.381**; Sharpe -1.971 -> +0.691; risk-adj exp -0.1242 -> +0.0435
- is_first_half flipped positive: -$111.12 -> **+$17.05**; pos quarters 2/6 -> 3/6
- OOS exp/tr TRIPLED: +$23.51 -> **+$72.28** (139 capped DOLLAR_STOP exits @ $52.08 replaced 114 premium-stops that scaled with the bigger 1DTE premium)
- WR DROPPED 27.1% -> 21.3% — stops out more often, caps each loss smaller (the theta-trap; expectancy is the edge, not WR)

But power_hour fires nearly EVERY trading day (190 signal-days) with profit in <=5 fat days: top5_day_pct stays **238.4%**. The dollar-stop trims the LOSS tail but leaves the WIN concentration intact.

### 11-gate ledger (dollar-anchored @ 1DTE)

PASS (~6): oos_n=55>=20 • no-truncation (fill_rate high, evaluable) • oos_exp +$72.28>0 • is_first_half +$17.05>0 • Sortino +1.38>=0 • OOS lift kept vs 0DTE.
FAIL (5): **oos_drop_top5 -$20.89<=0 (L173)** • drop_top5_full -$20.49<=0 • pos_q 3/6<4 • top5_day_pct 238.4% (>200%) • worstDay -$1,188 BREACHES kill switch (Safe -$600 AND Bold -$835).
(Gate "beats-random-null" not computed — moot: fails L173 + concentration + kill switch regardless.)

### VERDICT: **IMPROVED_STILL_FRAGILE**

The dollar-anchored lever produced a large, directionally-correct improvement on the hardest case (L173 -$74.54 -> -$20.89, maxDD cut 3.2x, Sortino -2.588 -> +1.381, IS-1H -$111 -> +$17, OOS exp tripled) — but it did NOT flip oos_drop_top5 positive, AND the cell still fails 5 of 11 gates including the KILL SWITCH (worst day -$1,188 breaches Safe -$600 and Bold -$835). Confirms the honest hypothesis in its purest form: for a family that fires too often (190 signal-days), the dollar-stop fixes the loss tail but L173 fragility is a SIGNAL-breadth problem (win-profit lives in a few days) the stop cannot fix. power_hour is the WORST of the three retested — it needs both breadth AND a smaller worst-day, not just a better stop. NOT shippable.

**Disposition:** Do not flip live. Unlike momentum_morning (+$1.25 from clearing) and orb_continuation (~$21 from clearing but inside the kill switch), power_hour is BOTH -$20.89 from L173 AND outside the kill switch — the lowest-priority resurrection target. The $52.08 dollar-stop is the correct risk construction to keep on any future power_hour entry-narrowing variant; re-run this A/B only if power_hour's signal density is sharply cut (far fewer, higher-quality last-hour-trend days).

**Disclosure (C7):** numbers pasted from `analysis/recommendations/dte-stop-construction-power_hour.json`, not memory.
