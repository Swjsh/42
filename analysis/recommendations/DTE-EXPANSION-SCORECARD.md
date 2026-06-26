# DTE-EXPANSION SCORECARD

> ## HEADLINE — THE EXPIRY-DIMENSION VERDICT (2026-06-21, after the A/B follow-up)
>
> **The expiry dimension ESCAPES the 0DTE theta wall — but ON DOLLARS for the LIVE edge only, and at a variance cost that makes it J's product call, not an auto-ship.** Confirmed two ways:
>
> 1. **LIVE edge (`vwap_continuation`, ITM-2/-0.08): the theta wall lifts on dollars.** OOS exp **$36.34 → $59.02 → $66.13/tr** (0/1/2DTE), gross exp $51 → $67 → $72, OOS-drop-top5 STAYS positive and GROWS (broad-based, not concentration), and the lift is **PURE THETA** — held_overnight 0%, gap contribution $0 at 1DTE (same intraday trade, less theta drag). This is the breakthrough: the dimension that killed ~64 families is genuinely 0DTE-specific and 1DTE recovers real dollars on the money-maker. **BUT** risk-adjusted DEGRADES (exp/std 0.357 → 0.319 → 0.250; Sortino 0.90 → 0.78; maxDD ~2×) because lower gamma inflates per-trade dollar-variance two-sidedly → **`SHARPE_TRADEOFF_J_CALL` (L175), filed as WP-8.** Full decomposition: `DTE-LIVE-EDGE-RISKCHAR.md`.
> 2. **Dead directional LIBRARY: does NOT reopen.** 3 of 4 dead families flip 0DTE-dead → 1-2DTE OOS-positive but ALL stay L173-fragile (drop-5-best-OOS-days → negative; concentration, not theta-rescued alpha) → **0 shippable.** `gap_fade` (#4 below) is the canonical example — clears the candidate bar broadly, dies under L173. Full survey: `DTE-LIBRARY-SURVEY.md`. (vwap_pullback is a positive CONTROL, already shippable at 0DTE — not a resurrection.)
>
> **NET:** the 0DTE theta wall is REAL and 1DTE ESCAPES it on dollars for the live edge — so the expiry axis is an **OPEN J product decision on the money-maker (WP-8)**, while the dead-library expiry axis is **closed** (concentration, not theta, kills those families). The known 0DTE fix (ITM + wide-stop, C29/L149) stays correct for the auto-ship path; 1DTE is the dollars-maximizing alternative if J accepts the variance.
>
> ---

> Does the 0DTE theta wall (C3 / L58) lift at 1-2DTE? Run the SAME byte-for-byte detector
> at 0 / 1 / 2 DTE on real fills + honest overnight-gap accounting. Sim:
> `backtest/autoresearch/_dte_expansion_sim.py`. Output JSON:
> `analysis/recommendations/dte-expansion.json`. Pure Python, $0, no live orders.
>
> **CACHE BACKFILLED 2026-06-21 (supersedes the old n=8-10 caveat):** the 1/2DTE OPRA cache
> now holds **2796 (1DTE) / 2774 (2DTE)** contracts spanning the **full 2025-01 .. 2026-06**
> history. The 1/2DTE legs now fill at **n=165-166 (FULL history)**, not the old 8-10 sample.
> The prior "#1 NO_CHANGE on n=10 matched sample" verdict was a **small-n artifact and is
> REVERSED below**. 0DTE uses full history (`n~154-157`); the small-n matched-sample tables
> from the pre-backfill run are retained at the bottom for provenance but are NO LONGER the
> basis for the verdict.

---

## #1 vwap_continuation (the live marginal edge) — PRIMARY

Run: `backtest/.venv/Scripts/python.exe backtest/autoresearch/_dte_expansion_sim.py --family vwap_continuation`
Run date: 2026-06-21. Window: 2025-01-02 .. 2026-06-16. Signals: 166 (90C / 76P) on 166 days.
Validation: PASSED (ITM settlement = intrinsic at real expiry SPY close; OTM-worthless = -100%;
overnight gap applied at the real T+1 open; per-leg prices are real fetched OPRA bars).

### FULL-HISTORY RESULT (backfilled cache, 2026-06-21) — cells clearing the candidate bar

n is now FULL history at every DTE. Cells clearing the 4-gate candidate bar (n>=20, oos_exp>0,
posQ>=4/6, top5%<200):

| DTE | n (per cell) | cells clearing bar / 20 |
|---|---|---|
| **0DTE** | ~154-157 (full) | **15 / 20** |
| **1DTE** | **165-166 (full)** | **15 / 20** |
| **2DTE** | **165 (full)** | **16 / 20** |

On the backfilled cache **1DTE and 2DTE clear the bar on as many cells as 0DTE.** The old
"0/20 at 1-2DTE" was purely the n=8-10 small-sample block, now removed.

### LIVE TIER (ITM-2) — the apples-to-apples comparison that decides it

Identical detector / identical signal-days / ITM-2 strike. `riskadj = exp/std` (per-trade Sharpe).

| stop | DTE | n | exp/tr | OOS exp (n) | IS exp | posQ | top5% | WR | std | **riskadj** | held% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **-0.08** (live) | **0** | 157 | $51.27 | **$36.34** (50) | $58.25 | 5/6 | 21.2 | 45.9 | $143 | **0.357** | 0.0 |
|  | **1** | 166 | $67.25 | **$59.02** (51) | $70.89 | 5/6 | 22.3 | 42.8 | $211 | 0.319 | 0.0 |
|  | **2** | 165 | $71.57 | **$66.13** (50) | $73.94 | 4/6 | 29.5 | 42.4 | $286 | 0.250 | 1.2 |
| -0.50 | 0 | 157 | $73.87 | $22.90 | $97.69 | 6/6 | 23.0 | 77.7 | $300 | 0.247 | 0.6 |
|  | 1 | 166 | $109.66 | $12.72 | $152.66 | 5/6 | 39.2 | 69.9 | $480 | 0.229 | 4.8 |
|  | 2 | 165 | $104.29 | $59.59 | $123.73 | 5/6 | 75.2 | 63.6 | $751 | 0.139 | 12.1 |
| -0.99 (chart-only) | 0 | 157 | $85.04 | $36.50 | $107.72 | 5/6 | 20.0 | 80.9 | $321 | 0.265 | 3.2 |
|  | 1 | 166 | $108.95 | $11.52 | $152.16 | 5/6 | 39.4 | 70.5 | $489 | 0.223 | 5.4 |
|  | 2 | 165 | $104.36 | $60.40 | $123.48 | 5/6 | 75.1 | 63.6 | $750 | 0.139 | 12.1 |

**The decisive split:**
- **DTE LIFTS gross AND OOS dollar expectancy.** At the live -0.08 stop: exp $51 -> $67 -> $72;
  OOS exp $36 -> $59 -> $66. Higher DTE makes the same signal pay MORE in raw dollars.
- **DTE DEGRADES risk-adjusted return.** riskadj 0.357 (0DTE) -> 0.319 (1DTE) -> 0.250 (2DTE):
  std balloons $143 -> $211 -> $286 because lower gamma means more dollar-variance per unit of SPY
  move. The gentler theta pays in dollars but you carry proportionally more dispersion.

### 11-gate robustness at the live tier (ITM-2 / -0.08)

| gate | 0DTE | 1DTE | 2DTE |
|---|---|---|---|
| n >= 20 | 157 PASS | 166 PASS | 165 PASS |
| OOS exp > 0 | $36.34 PASS | $59.02 PASS | $66.13 PASS |
| posQ >= 4/6 | 5/6 PASS | 5/6 PASS | 4/6 PASS |
| drop-top5 exp > 0 | $41.73 PASS | $53.89 PASS | $52.04 PASS |
| OOS drop-top5 total > 0 (L173) | +$349 PASS | **+$894 PASS** | **+$968 PASS** |
| IS-half-1 exp > 0 | $60.25 PASS | $78.33 PASS | $114.65 PASS |
| IS-half-2 exp > 0 | $56.29 PASS | $63.58 PASS | **$33.93 PASS (weakest)** |
| top5% < 200 | 21.2 PASS | 22.3 PASS | 29.5 PASS |
| no-truncation (L171) | n/a intraday | held 0% | held 1.2% |

All three DTE pass every hard gate. The OOS-drop-top5 gate (L173) is STRONGER at 1/2DTE
(+$894/+$968 vs +$349) — the OOS lift is broad-based, NOT a concentration artifact. The only
soft weakness is 2DTE's IS time-stability ($115 -> $34 across halves).

### Overnight-gap contribution at the live stop (theta-driven, NOT gap-driven)

ITM-2 / -0.08, all fillable signals:

| DTE | n | held overnight | intraday-exit mean | held P&L | gap contribution to total |
|---|---|---|---|---|---|
| 0DTE | 157 | 0 (0.0%) | $51 | — | $0 of $8,050 |
| **1DTE** | 166 | **0 (0.0%)** | **$67** | — | **$0 of $11,163** |
| **2DTE** | 165 | **2 (1.2%)** | **$85** | -$986 mean (-$1,971 total) | **-$1,971 of $11,809** |

**This is the load-bearing mechanism.** At the live tight stop the position almost always exits
intraday on day T (held_overnight ~0% at 1DTE, 1.2% at 2DTE). So the gross lift is **purely the
extra extrinsic on a 1/2DTE contract paying more on the SAME-DAY exit before decay — it is NOT
financed by an overnight tail** (gap contribution = $0 at 1DTE). When the tail DOES fire (2 trades
at 2DTE) it is a pure -$1,971 drag, confirming overnight risk is real but rarely incurred under a
tight stop. At wider stops (-0.50/-0.99) held% rises to 5-12% and OOS riskadj collapses to ~0.14 —
the gap then DOES bite. The clean configuration is therefore tight-stop, where the lift is real
and gap-free but the dispersion penalty remains.

### VERDICT — vwap_continuation: **LIVE_EDGE_IMPROVED (gross/OOS, net of gap), NOT on risk-adjusted**

- **dte_helps = TRUE on dollar terms.** On the full backfilled cache the LIVE edge's gross AND OOS
  per-trade expectancy LIFT monotonically with DTE ($51->$67->$72 gross; $36->$59->$66 OOS),
  clears the 11-gate bar at every DTE (n>=20, OOS+, posQ>=4, drop-top5+, IS-half+, top5%<200), and
  at the live tight stop the lift is **theta-driven not gap-driven** (held 0%, gap contribution $0
  at 1DTE). This REVERSES the pre-backfill NO_CHANGE verdict, which was an n=8-10 artifact.
- **NOT on a risk-adjusted basis.** exp/std DEGRADES with DTE (0.357 -> 0.319 -> 0.250 at the live
  stop): lower gamma inflates dollar-variance faster than the gentler theta lifts the mean. A
  dollar-maximizer prefers 1-2DTE; a Sharpe/drawdown-sensitive sizer (which Gamma is — kill
  switches are %-of-equity) prefers 0DTE. **2DTE also has the weakest IS time-stability** ($115->$34).
- **NOT RESURRECTED_EDGE:** vwap_continuation was never 0DTE-dead — it is the LIVE edge; there is
  nothing to resurrect. RESURRECTED_EDGE applies only to the dead families (see #2/#3).
- **Posture (do NOT auto-ship a DTE change):** the standing auto-ship bar is OOS+ / WF>=0.70 /
  sub-window-stable / anchor-no-regression on a **risk-adjusted** basis. DTE-expansion fails the
  risk-adjusted leg (riskadj DOWN, 2DTE IS-half unstable), so it is **not** an auto-ship — it is a
  dollar-vs-Sharpe tradeoff that is J's product-design call, not a clean edge. Best single config
  if dollar-max is ever chosen: **1DTE ITM-2 / -0.08** (exp $67, OOS $59, riskadj 0.319, held 0%,
  gap $0 — captures most of the dollar lift with the least gap exposure).

### APPENDIX (provenance) — pre-backfill matched-sample tables (n=8-10, SUPERSEDED)

> Retained for audit trail. These drove the original NO_CHANGE verdict and are no longer the
> basis for the decision — the full-history numbers above supersede them.

Matched 10-day sample, ITM-2 stop -0.50: 0DTE +$52.26/tr (std $363) | 1DTE +$21.27/tr (std $640)
| 2DTE +$327.57/tr on n=9 with one +$4596 outlier (posQ 1/3, top5%>100 — concentration artifact).
On the tiny matched sample 1DTE looked strictly worse and 2DTE looked like a lottery; the
full-history backfill shows that was small-n noise — the real signal is a modest dollar lift with a
risk-adjusted penalty.

---

## #2 orb_continuation (the DEAD family — the REAL resurrection test) — PRIMARY

The task's actual target: a representative **0DTE-theta-killed long-directional family**
(opening-range-breakout continuation on elevated RVOL, Zarattini — `detect_orb_rvol`, imported
BYTE-FOR-BYTE from `infinite_ammo_discovery.py`, NO re-implementation). Long-biased = the canonical
"morning momentum / ORB-continuation" family the thesis says theta kills.

Run: `backtest/.venv/Scripts/python.exe backtest/autoresearch/_dte_expansion_sim.py --family orb_continuation`
Run date: 2026-06-21. Window: 2025-01-02 .. 2026-06-16. Signals: **123** (65C / 58P) on 123 days.
Validation: PASSED (same self-tests as #1).

### Is ORB actually DEAD at 0DTE? (full history, n~113) — MOSTLY, with two ITM survivors

| 0DTE cell | n | exp/tr | oos_exp | posQ | top5% | clears? |
|---|---|---|---|---|---|---|
| ITM2 / -8% (default-ish) | 113 | -$16.03 | -$21.92 | 1/6 | n/a | no |
| ATM / -8% | 112 | -$9.10 | -$12.66 | 2/6 | n/a | no |
| OTM2 / chart-only | 113 | -$47.90 | -$59.21 | 1/6 | n/a | no |
| **ITM2 / -50%** | 113 | +$16.37 | +$18.19 | 4/6 | 106.6 | **CLEARS** |
| **ITM1 / -50%** | 113 | +$10.42 | +$10.38 | 4/6 | 150.0 | **CLEARS** |

ORB is dead in the DEFAULT (tight-stop / OTM) configs — consistent with C3/L58 — but **already
has 2 surviving 0DTE cells** (ITM + the -50% wide premium stop). So this family is "mostly dead, not
fully dead" at 0DTE. The wide stop + ITM strike is the same lesson as vwap_continuation (C29/L149):
ITM + room-to-breathe is what survives 0DTE theta.

### The apparent 1/2DTE explosion — and why it is NOT resurrection

| Same cell ITM1 / -50% | n | exp/tr | oos_exp | WR | posQ | top5% | std | risk-adj | held o/n | clears? |
|---|---|---|---|---|---|---|---|---|---|---|
| **0DTE** | **113** | +$10.42 | +$10.38 | 69.9% | 4/6 | 150.0 | $267 | 0.039 | 0.0% | **CLEARS** |
| **1DTE** | **16** | +$148.57 | +$293.95 | 62.5% | 2/3 | 167.6 | $703 | 0.211 | 12.5% | no (n<20, posQ<4) |
| **2DTE** | **16** | +$325.31 | +$956.05 | 62.5% | 2/3 | 133.4 | $1184 | 0.275 | 18.8% | no (n<20, posQ<4) |

The 1/2DTE expectancy looks 10-30x bigger — but **it is a population artifact, not a flip.** The
1/2DTE OPRA cache only covers **20 of the 123 signal days** (entry-day range 2025-03-03..2026-06-15,
recent + bullish-skewed), so the 0DTE n=113 (mostly 2025) and the 1DTE n=16 (mostly recent) are
**different day populations.** The ONLY honest comparison is the matched same-day control:

### Matched same-day control (ITM1 / -50%, ONLY the 16 days the 1DTE cache can fill)

| DTE | n | exp/tr | oos_exp | WR | top5% |
|---|---|---|---|---|---|
| **0DTE (matched 16 days)** | 16 | **+$27.86** | +$39.80 | 62.5% | **307.9** |
| 1DTE | 16 | +$148.57 | +$293.95 | 62.5% | 167.6 |
| 2DTE | 16 | +$325.31 | +$956.05 | 62.5% | 133.4 |

**This is the kill shot for the resurrection thesis on this family:** on the comparable 16 days, the
signal was **already +$27.86/tr POSITIVE at 0DTE** — it was never dead there. There is no
"0DTE-negative -> 1DTE-positive" flip; there is only "already-positive-at-0DTE, gets bigger and
much noisier at longer DTE." Longer DTE here **lifts risk-adjusted return** (risk-adj 0.039 -> 0.21
-> 0.27) but does not RESURRECT anything.

### Overnight-gap contribution — the lift is gap-driven and concentration-flagged

- Exit mix shifts with DTE: 0DTE = 0% held overnight (all flat by close, exits = TP1 78 / premium-stop 33).
  1DTE = 12.5% held (2 of 16 ride to EXPIRY_SETTLEMENT). 2DTE = 18.8% held (3 of 16).
- Those **2-3 held-to-settlement trades carry the bulk of the P&L lift** — std blows out $267 -> $703
  -> $1184 and the 2DTE ITM2 cell reaches a headline oos_exp=$1009 on n=16 (top5_day_pct still 127%).
  This is the exact small-n / concentration pattern the posQ + top5% gates exist to reject (C4).
- Gap was favorable in points on this recent down-skewed sample (mean +6.1pt favor 1DTE / +5.8pt 2DTE,
  zero GAP_THROUGH_STOP events) — i.e. the sample's overnight gaps happened to help. On a fuller /
  two-sided sample the gap is a symmetric tail that would cut both ways (see #1 where held trades were
  net losers). **Net: the gap ADDS at least as much variance as the gentler theta saves**, and the
  favorable sign here is sample luck, not structure.

### VERDICT — orb_continuation: **NO_CHANGE (no resurrection); marginal risk-adj IMPROVEMENT is small-n-only**

- **NOT RESURRECTED_EDGE.** Requirement = a 0DTE-NEGATIVE signal clears the bar at 1-2DTE. Neither
  holds: (a) on the matched days the signal is already +$27.86/tr at 0DTE (not dead), and (b) **0 of
  20 1DTE cells and 0 of 20 2DTE cells clear the full bar** — every one fails n<20 and posQ<4 (only 3
  quarters exist in the 16-day sample). The bar is correctly NOT cleared.
- **Risk-adjusted return DOES rise with DTE** (0.039 -> 0.21 -> 0.27) but entirely on a 16-trade
  sample whose lift is concentrated in 2-3 held-to-settlement gap trades — uninvestable as shown.
- **Gap risk = HIGH and the favorable sign is sample luck** (recent down-skewed window, zero
  gap-through events — won't generalize).

**Bar applied (sample, small-n flagged): 0 of 40 1/2DTE orb cells clear. No full multi-window OPRA
fetch warranted** — the only signal-level lift is a population/concentration artifact, and the matched
control shows there was no 0DTE death to reverse. The honest read across BOTH families (#1 live-edge,
#2 dead-family): **the 0DTE theta wall is real, but the fix is ITM + wide-stop at 0DTE (already known,
C29), NOT moving out to 1-2DTE** — longer DTE swaps bounded theta for an unbounded overnight tail and,
on every matched comparison run so far, does not pay for it.

---

## #3 gap_fade (a 0DTE-DEAD REVERSAL / reclaim-ride) — second dead family, the cleanest test yet

> The brief's specific assignment: a SECOND dead directional family that is a **reclaim/reversal-ride**
> (the #2 orb/momentum families are CONTINUATION). gap_fade is the canonical mean-reversion reversal.

**Family:** `detect_gap_fade` reused **byte-for-byte** from `infinite_ammo_discovery` (one of the
~64-family library). Logic: fade an opening gap back toward prior close — gap-up 0.25-1.5% -> PUTS,
gap-down -> CALLS; entry on the first RTH bar close (fill next bar), stop = the opening-bar extreme.
A textbook **reversal-ride** (the reclaim/reversal counterpart to the continuation families in #2).

Run: `backtest/.venv/Scripts/python.exe backtest/autoresearch/_dte_expansion_sim.py --family gap_fade`
Run date: 2026-06-21. Window: 2025-01-02 .. 2026-06-16. Signals: **192 (82C / 110P) on 192 days**.
Validation: PASSED (same self-tests as #1/#2). Per-family JSON snapshot copied to
`analysis/recommendations/dte-expansion-gap_fade.json` (the shared `dte-expansion.json` is
overwritten by whichever family runs last — known collision; the per-family copy is the record).

### Cells clearing the bar (n>=20, oos_exp>0, posQ>=4/6, top5%<200) + OOS-positive tally

| DTE | n (per cell) | cells OOS-positive | cells clearing FULL bar | verdict |
|---|---|---|---|---|
| **0DTE** | ~177-178 (full) | **0 / 20** | **0 / 20** | **DEAD — cleanly 0DTE-dead** |
| **1DTE** | **16-18 (SAMPLE)** | **16 / 20** | **0 / 20** | flips positive; n<20 + posQ capped at /3 |
| **2DTE** | **16-17 (SAMPLE)** | **18 / 20** | **0 / 20** | flips positive; same small-n block |

**0DTE is unambiguously dead** — all 20 strike x stop cells are OOS-negative. Best 0DTE cell is
`ITM-1 / -0.08: n=177 exp=+$11.6 IS but oos_exp=-$0.88, posQ=4/6, top5%=80%` — still negative OOS.
This is a CLEAN dead 0DTE family (unlike vwap_continuation #1, which is already live, and unlike orb
#2, which was +$27.86/tr on its matched 0DTE control). gap_fade is the family the thesis actually targets.

**1/2DTE flip dramatically positive on the sample (broad, not a single-cell fluke):**
- `1DTE OTM-2 / -0.08: n=17 exp=+$86.22 oos_exp=+$114.76 is_exp=+$70.65 posQ=3/3 top5%=129.7 risk_adj=0.41`
- `2DTE ITM-1 / -0.20: n=16 exp=+$134.55 oos_exp=+$229.14 is_exp=+$91.55 posQ=3/3 top5%=127.2 risk_adj=0.40`
- vs the best 0DTE risk_adj of only **0.10**. Lift is broad: 16/20 (1DTE), 18/20 (2DTE) cells OOS-positive.

### Overnight-gap contribution — the honest tradeoff (and it differs from #1/#2)

| DTE | held_overnight% | gap_through_stop | expiry_settlement | exit mix |
|---|---|---|---|---|
| 0DTE | ~0% (2 settles in whole book) | 0 | 2 | PREMIUM_STOP / TP1 / LEVEL_STOP |
| **1DTE** | **0.0%** | **0** | **0** | all day-T PREMIUM_STOP / TP1 |
| **2DTE** | **0.0%** | **0** | **0** | all day-T PREMIUM_STOP / TP1 |

**Load-bearing caveat (it changes the MECHANISM):** gap_fade fires at the open with a tight
opening-extreme stop, so on this sample **every position exits intraday on day T before the
overnight** — `held_overnight ~ 0%`, `gap_through = 0`, `settlement = 0`. Consequences:
- **Overnight-gap contribution to 1/2DTE P&L variance ~ 0%** here — the gap risk the thesis warned
  about is **not being incurred** by this family. (Contrast #1, which held 20-22% overnight where the
  gap dominated variance, and #2, whose lift came from 2-3 held-to-settlement gap trades.)
- So the 1/2DTE lift is **NOT** "gentler theta on a held position." It is that a 1/2DTE contract
  carries **more extrinsic**, so the SAME day-T move pays more on the SAME-DAY exit (stop/TP fire on a
  less-decayed premium). A real effect, but a **different** one than the resurrection thesis — and one
  that is **not paid for with an overnight tail** (the favorable distinction from #1 and #2).

### VERDICT — gap_fade: **IMPROVEMENT (sample-level), NOT RESURRECTED_EDGE — bar NOT cleared**

- **dte_helps = TRUE on the sample:** a confirmed 0DTE-DEAD signal (0/20 OOS-positive) flips broadly
  positive at 1DTE (16/20) and 2DTE (18/20), risk_adj ~0.40 vs 0DTE ~0.10. Thesis direction corroborated.
- **NOT RESURRECTED_EDGE:** the gate (clear the full 11-gate bar at 1-2DTE) is **NOT met** — **0/40**
  1/2DTE cells clear. Every positive cell fails on **n=16-18 < 20** and **posQ capped at x/3** (the DTE
  cache spans only 3 quarters). Small-n structural blocks, not edge failures — but the bar is the bar
  (C4/C7, no survivor cherry-pick on tiny-n).
- **Gap risk on THIS family ~ ZERO** (held_overnight ~0%), so unlike #1/#2 the net-of-gap tradeoff is
  favorable — the lift is not financed by an overnight tail. That makes gap_fade the **strongest
  resurrection candidate across all three families tested.**

**Recommended next step (this one earns the spend):** gap_fade is the FIRST family to show a clean
0DTE-dead -> 1/2DTE-positive flip with NO offsetting gap penalty on the sample. A **full multi-window
1/2DTE OPRA backfill** (push n past 20, span >=4 quarters) is now warranted **specifically for
gap_fade** — if the flip holds at full n with posQ>=4 and top5%<200 it would clear the bar and become
a genuine RESURRECTED_EDGE. Until then: IMPROVEMENT-signal only, do NOT ship.

---

## #4 gap_fade @ FULL backfill — the spend was made; verdict RESOLVES to DEAD (concentration artifact)

> The #3 "earns the spend" recommendation has now been EXECUTED. The 1/2DTE OPRA cache is fully
> backfilled (2795 1DTE / 2771 2DTE contracts, full 2025-01..2026-06). gap_fade re-run at **full n**.
> This entry SUPERSEDES #3's "IMPROVEMENT-signal" reading: with the small-n block removed, the flip
> survives the candidate-edge bar but **fails the stricter L173 drop-top5-day-OOS robustness gate.**

Run: `backtest/.venv/Scripts/python.exe backtest/autoresearch/_dte_expansion_sim.py --family gap_fade`
Run date: 2026-06-21. Window: 2025-01-02 .. 2026-06-16. Signals: **192 (82C / 110P) on 192 days**.
Validation: PASSED (5/5 deterministic checks). Per-family JSON snapshot:
`analysis/recommendations/dte-expansion-gapfade.json`.

### Full-history result — cells clearing the candidate-edge bar (n>=20, oos_exp>0, posQ>=4/6, top5%<200)

| DTE | n (per cell) | OOS n | cells clearing candidate-edge bar | best cell OOS exp/tr |
|---|---|---|---|---|
| **0DTE** | 177 | 56 | **0 / 20** (every cell OOS-NEGATIVE) | ITM2/-0.08 = **-$15.61** |
| **1DTE** | 87-88 | 29 | **7 / 20** | ITM2/-0.08 = **+$46.01** |
| **2DTE** | 86-87 | 28 | **11 / 20** | ITM2/-0.08 = **+$57.79** |

At FULL n the headline flip is real and broad: 0DTE is cleanly dead (0/20, all OOS-negative,
ITM2/-0.08 WR 27.1% top5%=152.7% — a concentration mess), while 1DTE clears 7 cells and 2DTE clears
11, with **posQ 6/6** and **top5%<50%** on the headline ITM2/-0.08 cell. n is now healthy (86-88,
oos_n 28-29 — comfortably >20). On the candidate-edge bar alone this LOOKS like RESURRECTED_EDGE.

### The kill shot — L173 OOS-alone-drop-top5-day robustness (the 11-gate bar, not the candidate bar)

The candidate-edge bar is a SCREEN, not the ship bar. Applying L173 (strip the 5 best OOS *days*,
require the remainder still positive — the anti-2.10 concentration guard):

| DTE | OOS total | OOS total minus top-5 days | IS-half (h1 / h2) |
|---|---|---|---|
| 0DTE | -$874 | **-$2350 (NEG)** | +$26 / +$8 |
| **1DTE** | +$1334 | **-$870 (NEG)** | +$149 / +$69 |
| **2DTE** | +$1618 | **-$1193 (NEG)** | +$107 / +$67 |

**At every expiry the OOS edge collapses to NEGATIVE once the 5 best OOS days are removed.** With
only ~28 OOS trading days, ~5 days carry the entire OOS profit — textbook concentration (C7 / OP-2.10
/ L173). Swept across ALL strike x stop cells at 1DTE and 2DTE: **0 cells survive both the
candidate-edge bar AND drop-top5-day-OOS-positive.** Zero survivors.

### Overnight-gap contribution — confirmed ~ZERO on the winning cells (full n)

The headline clearing cells (the tight -0.08 stop) have `held_overnight%=0.0, gap_through=0,
expiry_settlement=0, mean_gap_favor=0.0pt` at BOTH 1DTE and 2DTE. The whole edge is day-T intraday
(more extrinsic -> same-day move pays more on the same-day exit), NOT a held-overnight gentler-theta
effect. The few cells that DO hold overnight (wider -0.5/-0.99 stops) carry only 1 gap_through + 2
settlements but inflate std to $568-585 (vs $257 at -0.08) — the overnight tail adds variance without
adding robust edge. So: **gap contribution to the winning-cell P&L = 0%; gap contribution to variance
on the wide-stop cells = large and unhelpful.**

### VERDICT — gap_fade @ full n: **DEAD (resurrection is a concentration artifact)**

- **dte_helps = TRUE in DIRECTION** (0DTE-negative -> 1/2DTE candidate-bar-positive, broad: 7 & 11
  cells, posQ 6/6, n>20) — the gentler-theta-on-same-day-move mechanism is real and the gap penalty
  is genuinely ~zero here. The thesis direction is corroborated one more time.
- **But it FAILS the 11-gate bar (L173):** every clearing cell's OOS profit lives in ~5 of ~28 OOS
  days; strip them and OOS goes negative at all three expiries. **0 / 40 cells survive the full bar.**
  This is the survivor trap the bar exists to catch — NOT a shippable edge.
- **Verdict = DEAD.** The candidate-bar "resurrection" does not clear the honest robustness gate. Do
  NOT ship. (Had it survived drop-top5-OOS it would have been RESURRECTED_EDGE — it does not.)

**Cross-family summary (all four tested at full n):** vwap_continuation = already-LIVE, best at
0DTE/1DTE, not a resurrection (#1). orb_continuation = MORE 0DTE cells (2) than 1/2DTE (1) — NO_CHANGE
(#2). momentum_morning = stays dead (0 -> 1 -> 0 cells, single fragile cell) — DEAD. gap_fade = the
only clean candidate-bar flip, but DEAD under L173 concentration robustness (#4). **Net doctrine: the
0DTE theta wall is real and longer DTE does lift gross/candidate-bar expectancy on reversal families,
but on every family tested the lift is either already-captured (vwap), population/concentration
artifact (orb, gap_fade), or noise (momentum). No dead 0DTE family RESURRECTS into a robustness-clean
1-2DTE edge. The known fix stays ITM + wide-stop AT 0DTE (C29/L149), not DTE expansion.**
