# Candidate — Support-Reclaim Long (VIX≥18)  [DRAFT]

**Status:** DRAFT research candidate. NOT live. Bull-side reclaim → OP-16 scope lock
(BULLISH_RECLAIM stays DRAFT until J has 3 live wins) + Rule 9 (no mid-build production
change). This file is the proposal; ratification is a separate after-hours step with an
A/B scorecard.

**Date:** 2026-06-20 · **Author:** Gamma · **Cost:** $0 (paper/sandbox research)

---

## Why this exists

The 2026-06-20 futures-vs-options control experiment
([analysis/futures-vs-options-control-2026-06-20.md](../../analysis/futures-vs-options-control-2026-06-20.md))
returned **NO-EDGE-IN-SIGNAL** for the engine *as a whole*: the same signals lose on a
linear instrument too (native MES fleet −$26,127 / 48% WR over 2,611 signals). The follow-up
question — *are there robust winning SUBSETS inside the losing whole?* — was answered by mining
the full 4,865-signal native fleet
([analysis/winning-signals-mine-2026-06-20.md](../../analysis/winning-signals-mine-2026-06-20.md)).

**One signal survived every discipline check:** `LEVEL_REJECT_LIVE | long` — and a VIX gate
cleanly separates its winning regime from its losing one.

## The signal (faithful to `shotgun_scalper_detector._detect_level_reject`, bullish path)

A **volume-confirmed support reclaim**:
1. A reversal bar's **low pokes a named support** from above (within tolerance).
2. The bar prints a **higher-low** vs the prior bar and **closes green**.
3. On **volume ≥ 1.5×** the trailing 20-bar average.
4. Price **reclaims that bar's body-midpoint** within 6 bars → enter long.
- Stop: reversal-bar low − buffer. Target: nearest resistance above.

**Regime gate (the key addition): only when VIX ≥ 18.**

## Evidence (native futures bars, no option tax; $/contract/trade)

| VIX band | MES | MNQ | verdict |
|---|---|---|---|
| < 15 | −$6.5 (56% WR) | +$3.0 (67%) | flat/neg |
| 15–18 | −$6.4 (54%) | −$11.2 (67%) | **loses both** |
| **18–22** | **+$59.7 (87%)** | **+$97.5 (75%)** | **strong both** |
| **> 22** | **+$46.9 (71%)** | **+$149.2 (78%)** | **strong both** |

Robustness checks that PASS (the discipline this project demands — C4/PBO/OOS):
- **Cross-instrument:** positive on BOTH MES and MNQ independently (the only setup×dir cell
  in the entire fleet that is). Robust (worse-of-both) avg **+$19.58/contract** all-VIX,
  **+$59.71/contract** in 18–22.
- **Time / OOS stability:** positive in **2025 (IS)** AND **2026 (OOS)** on both instruments —
  OOS *better* than IS (MES +$11→+$36, MNQ +$30→+$71). Only 2 mildly-negative quarters of 12,
  none in the gated (VIX≥18) regime.
- **Coherent thesis:** buying capitulation wicks at support with volume confirmation; elevated
  (not extreme) VIX is when intraday bounces are sharpest — not a data-mined coincidence.

## The actionable change

- The production engine currently **blocks** level-rejection *shorts* (`block_level_rejection:
  true` — correct; shorts lose −$5.9/−$16.1). It does **not** trade the *long* side at all.
- Proposal: a new **WATCH-ONLY** detector/heartbeat block for the long reclaim, gated VIX≥18,
  expressed on whichever instrument J chooses (0DTE call OR — given the control verdict — an
  MES/MNQ micro-future, which avoids the theta/spread tax that sank the option book).

## Deliverables shipped with this candidate

- **Pine indicator:** [`strategy/pine/gamma_support_reclaim_long.pine`](../pine/gamma_support_reclaim_long.pine)
  — v6, compiles clean in TradingView (saved in Pine editor 2026-06-20). Marks the setup live,
  shades the VIX≥18 regime, draws the stop, fires an alert. (Chart-display is plan-capped on the
  current TV tier — Volume + SMA + Saty Pivot Ribbon already fill the slots; adding it is an
  upgrade/swap decision for J.)
- **Mining harness:** `backtest/futures/mine_winning_signals.py` (reusable, cross-instrument).

## Gate to LIVE (NOT done yet — do not deploy)

1. Translate the signal through the **option real-fills** sim AND/OR a **futures paper** forward
   to confirm the per-contract edge survives real fills + spread (control already says futures
   is the right instrument).
2. File an **A/B scorecard** at `analysis/recommendations/support-reclaim-long-vix18.json`
   (OOS positive + WF ≥ 0.70 + sub-window stable + anchor no-regression — the OP-22 gate set).
3. **J ratification** (OP-16 bull-side DRAFT exception). J = REVOKE, not approve, per the
   "no blocker" directive — but bull-side scope expansion is the one place the scope lock still
   asks for an explicit nod.

## Second-place candidate (logged, not built)

`ERL_IRL_SWEEP_FVG | short` in VIX 18–22: robust **+$13.81/contract at 72% WR** (n=128) —
a regime-rescue (the setup loses −$9,841 overall but its elevated-VIX short side is positive on
both instruments). Weaker and more complex (ICT sweep+FVG) than the reclaim; build second if the
reclaim ratifies.

<!-- PROVENANCE-MISSING: analysis/recommendations/support-reclaim-long-vix18.json -->
