# Strategy candidate: UNBLOCK VIX_BULL_HARD_CAP (filter 9) — stale gate now suppresses winners

> DRAFT — Chef proposal 2026-06-26. J ratifies (REVOKE-only per OP-22).

## Hypothesis
`VIX_BULL_HARD_CAP` (filter 9, hard-coded `VIX_BULL_HARD_CAP=18.0` at `backtest/lib/filters.py:805`,
mirrored by `params.json#vix_entry_thresholds.bull_hard_cap=18.0`) blocks ALL call entries when
VIX ≥ 18.0. It was ratified 2026-06-17 on the **OLD engine** (OTM strikes + `-8%/-10%` premium-stop
bracket), where VIX-18-22 bull calls were net losers (IS n=4, OOS n=1, doc admits "evidence thin").

**Directional claim:** under the **CURRENT engine** (real OPRA fills + `-50%` catastrophe cap both
sides + chart-stop-primary + managed exits + per-tier strike + Safe $2K cap-admission), the same
VIX-18-22 band bull calls are now **winners**, so the block no longer earns its keep — it
*suppresses* P&L. Raise `vix_bull_max` 18.0 → 22.0 (restore the pre-2026-06-17 cap).

## Backtest evidence
Re-ran the A/B on the CURRENT engine via the params-driven path
(`autoresearch.runner.run_with_params` — the SAME path the chart-stops scorecard used), BASE =
current `params.json` (every live gate ON), CANDIDATE = BASE with `vix_bull_max` 18.0 → 22.0.
Script: `backtest/autoresearch/vix_bull_hardcap_revalidate.py`. Real OPRA fills, Safe-2 cap-admission.

- **Train/Full window:** 2025-01-01 → 2026-05-29 (real-OPRA coverage bound), n=52 (39 bear / 13 bull).
- **Test/OOS window:** 2026-03-01 → 2026-05-29, n=13.
- **UNBLOCK delta (full):** **+$471** (CAND $1,843 vs BASE $1,372). Block contributes **−$471**.
- **UNBLOCK delta (OOS):** **+$471** (CAND −$2,206 vs BASE −$2,677). Block contributes **−$471**.
- **Trades the gate blocks (both winners):** `2026-04-09` bull @ $2.73 → **+$205** (VIX 20.0–21.1);
  `2026-04-22` bull @ $2.42 → **+$266** (VIX 18.98–19.4). Both confirmed inside the 18–22 band.
- **edge_capture:** **UNCHANGED at −1379** under both BASE and CAND (delta=0). The block touches
  ZERO J source-of-truth days — every anchor delta = $0. (The −1379 is a *current-engine* property
  unrelated to this gate; this decision is EC-invariant.)
- **aggregate sharpe:** not the gating metric here — this is a single-knob gate-removal, not a new
  trade class. Aggregate P&L improves +$471 on identical bear book; per OP-16 EC is the floor and EC
  is invariant, so `final_score` is unaffected by this decision (tiebreaker only).
- **positive_quarters:** UNBLOCK is positive or flat in **4/4** IS sub-windows (W1/W2/W3 FLAT
  delta=$0, W4-Apr-May +$471). No sub-window where the block helps.
- **max_drawdown:** unchanged on the bear book (39 bear trades identical BASE vs CAND); the 2 added
  bull trades are net +$471, both winners (no new drawdown).
- **real_fills_validated:** **yes** (real OPRA fills via `simulate_trade_real`, C1 authority).

## Disclosures (per OP-20)
1. **Account-size assumption:** Safe-2 $2,000, cap-admitted (realizable book the live `risk_gate`
   permits). Both blocked trades ($2.73, $2.42 premium × qty 3 = ~$729–$819 notional) are
   borderline vs the 30% cap ($600) — see failure-mode #2; the A/B used per-trade cap-admission so
   the +$471 reflects the realizable book at $2K, NOT an unaffordable config.
2. **Sample-bias disclosure:** the gate blocks only **2 trades** over 17 months of real-OPRA history
   (the 18-22 VIX band is rare on the bull side). Small n — but the OLD ratification was *also* thin
   (n_oos_blocked=1, doc-admitted), and the sign **flipped** from "block helps" (old engine) to
   "block hurts" (current engine). This is a directional re-validation, not a fresh discovery.
3. **Out-of-sample test result:** OOS (2026-03..05) UNBLOCK delta = **+$471** (POSITIVE) — both
   blocked winners fall in the OOS window. Sign-stable with full history.
4. **Real-fills check:** yes — `simulate_trade_real` real OPRA fills throughout; no BS-sim.
5. **Failure-mode enumeration:**
   (a) *n=2.* The unblock rests on 2 trades. If both were marginal the call would be weak — but both
   are clear winners (+$205, +$266) and the block produces a NEGATIVE delta with no offsetting losers.
   (b) *Cap affordability.* At $2.73 premium × qty 3 = $819 notional > $600 (30% cap) the live gate
   would REDUCE/skip; the A/B's cap-admission already accounts for this (the trades survive admission
   in the run). If a future equity/premium combo breaches the cap, the trade simply isn't placed —
   removing the BLOCK does not force an unaffordable order.
   (c) *Regime.* VIX 18-22 is an elevated-fear band; on the OLD engine its bull calls bled via the
   tight premium stop. The fix is structural (the −50% cap rides them), not regime-luck.
6. **Concentration:** top5_pct N/A (gate-removal on a 2-trade delta, not a P&L-stacking strategy).
   The +$471 is split across 2 trades on 2 distinct dates in 2 distinct months — not concentrated.

## Knob changes proposed
NEVER edited by Chef. Proposed for J to ratify (REVOKE-only per OP-22):
- `automation/state/params.json` → `vix_entry_thresholds.bull_hard_cap`: **18.0 → 22.0**
- `backtest/lib/filters.py:805` → `VIX_BULL_HARD_CAP = 18.0` → **22.0** (the hard-coded constant —
  it does NOT appear in a params audit; both must move together or they drift).
- `automation/prompts/heartbeat.md` filter 9 → `VIX<18 (HARD)` → `VIX<22 (HARD)` + VIX cache
  refresh threshold `18.00 → 22.00` (gamma-sync, A5-style).
- Update `params.json#_vix_bull_hard_cap_doc` to record the UNBLOCK + this re-validation.

## Anchor no-regression (OP-16)
**PASS.** Every J source-of-truth day (4/29, 5/01, 5/04 winners; 5/05, 5/06, 5/07 losers) shows
delta = $0 between BASE and CAND. `edge_capture` is invariant (−1379 both). The gate fires only on
the bull side in the 18-22 VIX band; J's anchors are bear/put days with VIX below the cap, so
unblocking cannot touch them. Bearish source-of-truth is NOT regressed.

## Pre-merge gate
`python crypto/validators/runner.py` → **passed=97/98, overall_pass=True** (1 KNOWN_FLAKY_LIVE_SOURCE
excluded). GREEN before AND after this work — the candidate adds only a new standalone A/B script
in `backtest/autoresearch/`, no production-code change.

## My confidence (1-10) and why
**8/10.** The evidence is clean and decisive: the block contributes a NEGATIVE delta in BOTH
full-history (−$471) AND OOS (−$471), it suppresses 2 confirmed winners, anchor/EC are invariant,
and the gym is green. The sign **flipped** exactly as the task hypothesized — a gate that correctly
blocked a losing OTM+wide-stop config now blocks a winner under ITM+managed exits. The −2 from 10 is
purely n=2: the statistical base is thin (as was the original ratification). But OP-22 says block ONLY
if blocking *still* beats not-blocking — and it demonstrably does not. The honest read: this gate's
evidence went stale when the engine changed under it, and it now costs ~$471 to keep.
