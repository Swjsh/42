# VOLRANKER SIZING OVERLAY on the WP-8 1DTE/DOLLAR-STOP #1 stream

**Run:** 2026-06-21 (Sunday SAFE research, $0, NOT a live path — no watcher/params/risk_gate/heartbeat/simulator_real edit, no orders, no commit)
**Slug:** `overnight-vol-sizing-overlay-1dte` | **kind:** sizing_overlay (NOT a gate; L174-safe by construction)
**Harness:** `backtest/autoresearch/_volranker_sizing_1dte.py`
**Output JSON:** `analysis/recommendations/volranker-sizing-1dte.json`

## VERDICT: **MARGINAL** — the structural fix did NOT unblock the compounding case

The overlay remains a **$2K-only cap-bound risk tool.** The hypothesis — that the higher 1DTE
premium would give the min-3 floor enough room to make the overnight-vol sizing overlay a genuine
**compounding** lever at $10K/$25K — is **disproven.** At scale the overlay collapses into
**UP-ONLY** (top days size to 4 contracts; mid/bot/warmup all pinned at exactly 3 by the min-3
floor), which lifts *total dollars* via leverage on good days but **lowers risk-adjusted return**
(per-trade Sharpe down, Sortino collapses, maxDD up) — both in-sample and OOS-honest. It fails the
risk-adjusted bar at $10K and $25K.

## The question this answered

> On the 1DTE stream, does the higher premium give the floor enough room that the overlay now
> improves risk-adjusted return at $10K/$25K (the compounding case the 0DTE stream structurally blocked)?

**No.** The premium IS higher (Safe-2 ATM median $2.50 vs 0DTE ~$1.38; Bold ITM-2 median $3.57 vs
0DTE ~$2.55), and it DOES move the floor-binding threshold up — but not far enough. At $10K, FLAT-3
is only 7.5% (Safe) / 10.7% (Bold) of equity; the bot-tercile 0.6× multiplier on that base still
rounds **above** the min-3 floor, so the floor catches every non-top day at exactly 3. There is no
**down**-sizing room at $10K+; the overlay can only size **up** on top days, and up-sizing alone is
a variance trade, not a risk-adjusted improvement.

## Setup (everything reused byte-for-byte; only the trade stream swapped)

- **Stream:** WP-8 1DTE / **dollar-stop** via `_dte_stop_construction.run_cell(construction='dollar')` —
  real per-DTE OPRA day-T bars + honest overnight gap + expiry intrinsic settlement (inherited
  byte-for-byte from `_dte_expansion_sim`). Converted to the volranker `T` (pct=`pct_return`
  qty-invariant, pnl3=`dollar_pnl` at the base qty-3, entry_premium carried).
- **Dollar threshold:** Safe-2 ATM **$35.88**, Bold ITM-2 **$67.68** — the SAME calibration the
  WP-8 ship-spec uses (median 0DTE −8% loss at that tier, frozen and applied at 1DTE; NOT refit).
- **Overlay logic:** byte-for-byte `_volranker_sizing.{causal_terciles, overlay_contracts,
  flat_contracts, run_cell, _improvement_verdict, _trade_dollar}` + `TERCILE_MULT {top 1.5 / mid 1.0 / bot 0.6}`.
- **Overnight-vol feature:** byte-for-byte `_deploytiming_overnight_vol.overnight_vol_by_day`
  (sum|MES 1m logret| over 18:00→09:30 ET, causal rolling-60d tercile, shift-1).
- **Rule-6 cap-clamp:** byte-for-byte `_b10_sizing.contracts_from_fraction` (per-trade cap + min-3).
- **Window:** SPY 2025-01-02..2026-06-16; 165 classifiable 1DTE trades/account (1 dropped post-MES-cutoff
  2026-06-12); IS=115 (2025) / OOS=50 (2026). Terciles over 374 overnight days {top 117, mid 99, bot 138, warmup 20}.

## Results — FULL (IS+OOS), FIXED equity (per-trade/per-day risk comparable)

### Safe-2 (ATM, $35.88 dollar-stop, median premium $2.50)

| equity | FLAT-3 total | OV total | Δtotal | FLAT shTr | OV shTr | Δsh/tr | FLAT sortDay | OV sortDay | FLAT maxDD | OV maxDD | IMPROVES | OOS-clean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| $2K  | $6,787.99 | $6,868.99 | +$81 | 0.5236 | 0.5258 | **+0.0022** | 4.80 | 4.86 | 0.060 | 0.062 | **YES** | **YES** |
| $10K | $9,633.99 | $10,831.79 | +$1,198 | 0.4499 | 0.4380 | **−0.0119** | 34.85 | 11.15 | 0.032 | 0.038 | NO | NO |
| $25K | $9,610.07 | $10,748.09 | +$1,138 | 0.4485 | 0.4336 | **−0.0149** | 17,780 | 11.39 | 0.015 | 0.018 | NO | NO |

### Bold (ITM-2, $67.68 dollar-stop, median premium $3.57)

| equity | FLAT-3 total | OV total | Δtotal | FLAT shTr | OV shTr | Δsh/tr | FLAT sortDay | OV sortDay | FLAT maxDD | OV maxDD | IMPROVES | OOS-clean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| $2K  | $11,448.94 | $11,649.04 | +$200 | 0.5015 | 0.5050 | **+0.0035** | 4.38 | 4.46 | 0.112 | 0.119 | **YES** | **YES** |
| $10K | $13,972.91 | $15,300.56 | +$1,328 | 0.4468 | 0.4329 | **−0.0139** | 20,916 | 8.55 | 0.052 | 0.065 | NO | NO |
| $25K | $13,972.91 | $15,278.00 | +$1,305 | 0.4468 | 0.4320 | **−0.0148** | 20,916 | 8.48 | 0.026 | 0.032 | NO | NO |

### OOS-2026 only (honesty split — the leak check)

| account | equity | FLAT shTr | OV shTr | Δsh/tr OOS | risk_up | OOS-clean |
|---|---|---|---|---|---|---|
| Safe-2 | $2K  | 0.4741 | 0.4776 | **+0.0035** | yes | **YES** |
| Safe-2 | $10K | 0.4251 | 0.4211 | **−0.0040** | no  | NO |
| Safe-2 | $25K | 0.4251 | 0.4211 | **−0.0040** | no  | NO |
| Bold   | $2K  | 0.4877 | 0.4914 | **+0.0037** | yes | **YES** |
| Bold   | $10K | 0.4071 | 0.3983 | **−0.0088** | no  | NO |
| Bold   | $25K | 0.4071 | 0.3983 | **−0.0088** | no  | NO |

## Why $10K/$25K stay blocked — the floor-room arithmetic

The overlay's `avg_qty_by_tercile` and quantity histogram make the mechanism explicit:

| account | equity | top | mid | bot | warmup | overlay qty histogram |
|---|---|---|---|---|---|---|
| Safe-2 | $2K  | 1.60 | 1.93 | 2.36 | 2.12 | cap-bound band (FLAT-3=37.5%>30% cap → whole book ≤2-3) |
| Safe-2 | $10K | 3.87 | **3.0** | **3.0** | **3.0** | {2:2, 3:113, 4:50} — only top sizes up; rest floored |
| Safe-2 | $25K | 4.00 | **3.0** | **3.0** | **3.0** | {3:110, 4:55} — UP-ONLY |
| Bold   | $10K | 3.98 | **3.0** | **3.0** | **3.0** | {3:111, 4:54} — UP-ONLY |
| Bold   | $25K | 4.00 | **3.0** | **3.0** | **3.0** | {3:110, 4:55} — UP-ONLY |

- **$2K is the cap-bound risk-tool.** FLAT-3 of the high 1DTE premium is 37.5% (Safe) / 53.5% (Bold)
  of $2K — it **breaches** the per-trade cap (30%/50%), so the whole book is already clamped below 3.
  The overlay modulates *within* that compressed band (top sizes down hardest), and that down-modulation
  is a genuine risk reduction → +Sharpe, +Sortino, OOS-clean. This is the SAME cap-bound risk tool the
  0DTE study found, just at a different premium.
- **$10K/$25K is UP-ONLY.** FLAT-3 is 7.5%/10.7% ($10K) and 3.0%/4.3% ($25K). The bot 0.6× target on a
  7.5% base = 4.5% → rounds to ≥3 contracts → **the min-3 floor catches it.** No down-sizing happens.
  The overlay can only size UP on top days (to 4), which adds +$1.2-1.3K of total via leverage but
  raises maxDD and lowers per-trade/per-day Sharpe and Sortino → fails the risk-adjusted bar.

## Guards (all pass)

- **Rule-6 caps:** 0 breaches across all 6 cells. RESPECTS_CAPS=True everywhere.
- **L174 (never-zero):** 0 overlay-zeroed-takeable days across all cells. Bottom-tercile reduced, never removed.
- **Shared cap-skips at $2K:** 5 (Safe) / 2 (Bold) trades where even 1 contract of the high 1DTE premium
  breaches the per-trade cap — BOTH arms skip identically (a cap constraint, not an overlay artifact).
- **OOS-honest:** the +$2K lift is real OOS (OOS shTr +0.0035/+0.0037); the $10K/$25K up-size is NOT
  (OOS shTr −0.004/−0.0088) — confirming the scale "lift" is in-sample leverage, not OOS edge.

## Honest bottom line

The 1DTE premium IS higher and DID raise the floor-binding equity threshold — but only enough to keep
the overlay a **risk tool at the cap-bound low end ($2K)**, not a **compounding lever at scale.** The
overlay never gets two-sided room: at $2K it can only size DOWN (cap-bound), at $10K+ it can only size
UP (floor-bound). The crossover where it could do BOTH — meaningful down-sizing on bot days AND
headroom on top days simultaneously — does not exist within the min-3 floor + per-trade cap envelope on
this stream. The overnight-vol sizing overlay stays a **$2K-only tool**; WP-9 is **NOT** updated to put
it on the deployed 1DTE config at scale.

## NEXT DIRECTION

The blocker is structural and now precisely located: **the min-3-contract floor is what kills the
down-sizing arm at scale.** Two concrete, mutually-exclusive next directions, ordered:

1. **(Primary) Sub-min-3 down-sizing requires a different unit, not a different stream. — EXECUTED 2026-06-24 = the fix WORKS, but only at $25K (forward-looking).** The min-3
   floor is a Rule-6 *hard cap* (2 TP + 1 runner) — it cannot be lowered. So the only way the overlay
   gets a down-sizing arm at $10K+ is to apply the tercile multiplier to a **base size that is already
   well above 3 at $10K** (e.g. the quarter-Kelly base from B10, which at $10K wants meaningfully more
   than 3 contracts), so that bot×0.6 lands at a count *strictly above 3* and top×1.5 lands higher
   still — a true two-sided modulation around a >3 base, with the min-3 floor as a never-violated
   backstop rather than the operating point. **Test: re-run this overlay with `base = quarter-Kelly
   contracts` (B10's `contracts_from_fraction(f_quarter_kelly, …)`) instead of `base = min-3`.** That
   is the one change that could give the compounding case real two-sided room.

   **RESULT (`_volranker_sizing_qk.py` → `VOLRANKER-SIZING-QK-SCORECARD.md`):** verdict **SIZING_IMPROVEMENT**,
   OOS-clean at $10K AND $25K — the quarter-Kelly base IS the predicted fix. f_qk≈0.077 both accounts (continuous-Kelly
   0.31 capped, /4; computed IS-2025-only, frozen for OOS). **The honest, nuanced read:**
   - **$25K = where it genuinely delivers** — QK base 7c/5c gives real two-sided modulation (Safe avgQty bot 5.14 / mid 7.41 / top 8.78).
   - **$10K = thin** — QK base ≈ min-3 at the median premium ($2.50→3c), so it's mostly floor-bound (134/165 at exactly 3); only the cheaper-premium tail gets down-room. The improvement is real but marginal there.
   - **$2K = cap-BLOCKED entirely** — 1DTE min-3 = 37.5% > the 30% cap → 0 contracts (the QK 1DTE book is un-tradeable at the accounts' current equity; L180/C11).
   - **What drives the win:** primarily maxDD reduction at equal-or-higher total + a **modest** OOS per-trade-Sharpe lift (+0.013…+0.033 across all 4 scale cells; OOS ≥ full = NOT overfit). The giant Sortino deltas are near-zero-downside denominator artifacts — discount them. It is fundamentally a drawdown manager that finally SCALES, not a per-trade-expectancy edge.
   - **Disposition:** FORWARD-DEPLOYMENT note, not a live ship. Sizing = params surface (rail-4 propose-only) AND gated on (a) an account crossing ~$25K, (b) the 1DTE WP-8 itself shipping, (c) recency clearing (#1 currently RED). Not actionable at $2K today → documented for when an account scales; no live proposal fired.

2. **(Secondary, if #1 also flattens) Accept the verdict and ship the $2K risk-tool as-is.** At the
   accounts' actual current equity ($2K Safe / $1.67K Bold) the overlay is OOS-clean risk reduction
   TODAY — the cap-bound regime is the LIVE regime. It could ship at the current tier as a downside
   manager and simply be retired/re-tested when an account crosses ~$8-10K. (This is a smaller, honest
   win, not the compounding lever that was hoped for.)
