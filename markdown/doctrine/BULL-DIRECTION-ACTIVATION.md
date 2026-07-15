# Bull Direction Activation — Detail Log

> Relocated from CLAUDE.md OP-16 on 2026-06-29 (context-leanness trim). Rule summary stays in CLAUDE.md.

## Activation event

J's direct order 2026-06-28: "we need bull strats wired in." Both directions UNLOCKED.

## Validated setup

`BULLISH_RECLAIM_RIDE_THE_RIBBON` — active. Direction is NOT a scope; *validation* is the scope.

`enable_bullish=True` by default (orchestrator v12 + heartbeat_core). ENTER_BULL executes the identical path as ENTER_BEAR.

## A/B validation results (chef-bull-scope-ab, 2026-06-26)

- Top-level A/B (KEEP_bear_only vs UNBLOCK_bull_and_bear, n=25): **+$5,586 / 56% WR / Sharpe 0.046→0.156**.
  Evidence class corrected 2026-07-11 (CLAUDE.md OP-16): this is a **real-OPRA-priced SIM, not broker fills** —
  live paper bull fills to date are n=80 WR 1.2% −$1,573; re-eval at n≥20 under SS-B + ATM.
- The ribbon_flip cohort split (winner: NON-ribbon_flip reclaim n24 WR 29%; loser: ribbon_flip reclaim n21 WR 10%
  −$2,222) is **NOT in the chef-bull-scope-ab file** — those numbers trace to LESSONS-LEARNED.md **L126**
  (2026-06-17 IS analysis), whose verdict REJECTED blocking the cohort. See "Rejected / never armed" below.

## Active per-block filters (A/B-validated, individually)

| Block | Reason |
|---|---|
| `block_elite_bull` | confluence+level_reclaim combo [0,25) blocks elite-bull entries |
| VIX<17.2 bull block | Low-VIX bull entries underperform |
| elite-bull VIX 15-18 | Specific VIX range gate for elite-bull |
| `block_bull_1100_1200` | Late-morning filter |

Filters stay ON — they remove *losing cohorts*, not the direction.

## Rejected / never armed — do NOT mistake for active filters

| Gate | Status | Provenance |
|---|---|---|
| `block_bull_ribbon_flip` | **DEFINITIVELY REJECTED** as a production gate. Research parameter only (`gates.py`, default=False), key absent from both `params.json` files, zero live fires ever. | **L126** (LESSONS-LEARNED.md, 2026-06-17; CHANGELOG context-15): WF=−23.984 (bar ≥0.70), SW_hurt=3/5, OOS delta −$3,123 — regime-conditional (ribbon_flip quality inverts between range-bound and trending markets). Verdict: "never set True in production." |

> Correction 2026-07-15: earlier revisions listed `block_bull_ribbon_flip` in the Active table citing
> chef-bull-scope-ab — a **false citation** (that file contains only the top-level enable_bullish A/B, no
> ribbon_flip split). Flagged by GATE-PROVENANCE-AUDIT-2026-07-02 (G4) and GATE-PROVENANCE-SWEEP-2026-07-10
> §1.4; fixed per DIRECTIONAL-GATE-DEEP-RESEARCH-2026-07-15 §4.

## Regression guards

- `test_enable_bullish_live_true` — RED on any disable of bull direction
- `test_enter_bull_in_placement_path` — RED if ENTER_BULL drops out of placement path

## Arming note

Live-money arming of EITHER direction still requires J (OP-0 #1). Paper/shadow execution does not.
