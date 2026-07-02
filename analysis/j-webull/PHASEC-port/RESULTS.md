# Phase C — J-EDGE bull-family PORT: results (2026-07-02)

> ## ✅ REAL OPRA FILLS — `run_backtest(use_real_fills=True)`, the only P&L authority (C1). Same harness family as chef-bull-scope-ab (2026-06-26). $0, one process, overnight.

**Question.** Phase B found 6 BH-FDR survivors on J's 2021-23 book — all ONE family: CALL entries + TP1 +30% sell 2/3 + breakeven runner + chandelier (arm +5%, trail 15% HWM), ATM/OTM1, catastrophe stop −20/−50, with NEGATIVE opposite-direction nulls. E6/E1 proved J's entry *selection* is not feature-recoverable, so Phase C asks the only portable question: **do the ENGINE'S OWN bull entries (BULLISH_RECLAIM path, production gates + per-direction block filters) carry that family on 2025-26 real fills?**

## VERDICT: **PORT_WEAK** — positive sign, right-signed nulls, but the family does NOT clear the bar. No scorecard filed, no conductor proposal, no params change.

The two nails (every one of the 12 pre-registered cells fails BOTH):

1. **BH-FDR significance:** best q = 0.257 across the 12 cells (pre-registered α = 0.10). Per-cell one-sided p ∈ [0.19, 0.26] at n = 29.
2. **drop-top3:** negative in ALL cells (−$137…−$180) — remove the 3 best trades and the ported family is a net loser.

Named third fragility (passed its pre-registered ≥2¢ bar, but barely): **spread-stress breakeven = 2.0–2.6¢/side** of *extra* half-spread (on top of the engine's baked-in 2¢/side) erases the whole edge. Real ATM SPY 0DTE half-spreads run 1–3¢. Economically thin even before significance.

## The headline that matters more than the verdict

**On the identical 27 entries, the engine's own exits made +$5,466.50; the ported Phase-B family made +$355–447.** The port is not just unproven — it is a ~13x management downgrade for this engine's bull entries:

| management | n | total | exp/tr | WR | TP1 fired | top-3 trades |
|---|---|---|---|---|---|---|
| **Production exits** (chart-TP1 + level/ribbon exits + BE + prod stops) | 27 | **+$5,466.50** | +$202.46 | 55.6% | 15/27 | +$3,343 / +$1,028 / +$768 |
| **Port family** (c2: premium-only TP1+30 ×2/3, chand 5/15, stop −50, ATM) | 29 | +$404.00 | +$13.93 | 51.7% | **1/29** | +$323 / +$132 / +$129 |

**Mechanism (the real Phase-C finding):** under the port, the +30% premium TP1 essentially never fires on engine entries (1/29) — the chandelier (arm +5%, trail 15% off HWM) cuts trades at small gains or breakeven long before +30% is reached. 28-29/29 exits are floor exits; the P&L distribution is a wall of $0 breakeven scratches plus $4-130 dribbles, max +$323. The engine's native exits (chart-level TP1, ribbon/level logic, wide catastrophe stop) are what let the +$3,343-class bull runners run. **J's 2021-23 entries reached +30% fast enough to beat the chandelier; the engine's 2025-26 entries do not.** The family's Phase-B P&L was carried by J's entry timing — consistent with E6/E1 (his selection is not recoverable) — not by transplantable management magic.

## Baseline anchor (reproduction gate)

| run | n (bull) | total | WR | note |
|---|---|---|---|---|
| chef-bull-scope-ab UNBLOCK bull subset (recorded 2026-06-26) | 25 | +$5,586.50 | 56.0% | params as of 06-26 |
| **This run, mixed (bear+bull), bull subset — today's params** | 27 | +$5,466.50 | 55.6% | drift = tp1_qty_fraction 0.667→0.8 (06-28) + gate evolutions |
| This run, bull-only isolation (min_triggers_bear=999) | 27 | +$5,466.50 | 55.6% | identical cohort ⇒ bear positions never blocked a bull entry |

Anchor judged REPRODUCED (Δtotal −2.1%, Δn +2, same shape); mixed full-book: n=98, +$6,042, WR 51.0%.

## The funnel (honest)

| stage | count |
|---|---|
| Pre-registered cells (6 Phase-B survivor cells × qty {1,3}) | 12 |
| Ran on real OPRA fills (bull-only engine runs + 2 entries recovered by fetching 10 uncached contracts; final cache misses = 0) | 12 |
| Sign-positive (total > 0) | 12 |
| OOS-2026 positive | 12 |
| Both halves positive | 12 |
| Null not dominant (opposite-direction PUT null negative) | 12 |
| Spread-stress ≥ 2¢/side | 12 |
| drop-top3 > 0 | **0** |
| BH-FDR q ≤ 0.10 | **0** |
| **SURVIVORS** | **0** |

## Cell table (qty3 rows; qty1 = exact /3 sibling by construction — same p/q/WR, totals ÷3)

Window 2025-01-02..2026-06-18 · IS = 2025 · OOS = 2026 · n=29 per cell (27 shared with baseline + 2 recovered) · oos_n=11.

| cell | total | exp/tr | WR | p (1-sided t) | **q (BH, m=12)** | IS total | OOS total | drop-top3 | halves | spread-BE ¢/side | null (PUT) total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c1 stop-50·otm1·tEOD | +$355.35 | +$12.25 | 51.7% | 0.238 | 0.257 | +$55.65 | +$299.70 | **−$145.80** | +171/+185 | 2.04 | −$370.80 |
| c2 stop-50·atm·tEOD | +$404.00 | +$13.93 | 51.7% | 0.257 | 0.257 | **−$108.00** | +$512.00 | **−$180.10** | +47/+358 | 2.32 | −$447.60 |
| c3 stop-50·otm1·t120 | +$355.35 | +$12.25 | 51.7% | 0.238 | 0.257 | +$55.65 | +$299.70 | **−$145.80** | +171/+185 | 2.04 | −$370.80 |
| c4 stop-50·atm·t120 | +$404.00 | +$13.93 | 51.7% | 0.257 | 0.257 | −$108.00 | +$512.00 | **−$180.10** | +47/+358 | 2.32 | −$447.60 |
| c5 stop-20·atm·t120 | +$446.90 | +$15.41 | 44.8% | 0.190 | 0.257 | +$96.30 | +$350.60 | **−$137.20** | +259/+188 | 2.57 | −$13.05 |
| c6 stop-50·otm1·t60 | +$355.35 | +$12.25 | 51.7% | 0.238 | 0.257 | +$55.65 | +$299.70 | **−$145.80** | +171/+185 | 2.04 | −$370.80 |

qty1 siblings (c*_q1): totals/exp ÷3 (e.g. c2_q1 = +$134.67 total, +$4.64/tr), identical q-values — BH with exact-duplicate p-values leaves q unchanged, so the qty axis adds no statistical claim (same disclosure Phase B made for fixed_3).

Confirmations that DID transfer: **the time-stop axis is inert** (t60 ≡ t120 ≡ tEOD — chandelier/TP1 always exits first; identical cell totals), exactly as Phase B's Interpretation §1 predicted. And **the opposite-direction nulls are negative in all 6 configs** (−$13…−$448): the engine's bullish read at these moments is real and directional — the failure is purely the *management* port.

Quarterly (c2): 2025Q1 −$291 (n=2) · Q2 $0 (n=1) · Q3 +$333 (n=10) · Q4 −$150 (n=5) · 2026Q1 +$478 (n=4) · Q2 +$34 (n=7) → 3/6 positive.

## What this closes

- **No ratification artifacts filed:** `analysis/recommendations/j-bull-family-port.json` NOT written; no `conductor-proposals.jsonl` row. The auto-ratify bar (OOS+ AND WF AND sub-window AND anchor) was never reached because the FDR + concentration gates failed first.
- **The J-history program (Phases A→C) closes with management-package-only as the salvage**, and even that package needs the precision: the surviving *shape* of J's edge (TP1-fraction + chandelier profit-lock at sane strikes) is already independently in production doctrine (v15.3); the Phase-B *parameterization* (premium-only TP1 +30 ×2/3 + chand 5/15) must NOT replace the engine's native bull exits — it would have cost ~$5.1K over this window.
- Programme residue worth keeping: (a) J's bullish directional read on 2021-23 was real (Phase-B negative nulls, reconfirmed here); (b) his entry selection is not feature-recoverable (E6/E1); (c) the engine's own bull path + native exits is the working vehicle (+$5,466 on 27 real-fill entries, chef-bull-scope-ab convergence).

## Caveats (all load-bearing)

1. **n=29 bull entries over 17.5 months is thin.** The 2025-26 engine bull cohort simply isn't big enough yet for a 12-cell FDR pass at these effect sizes (power, not just effect). The per-direction block filters were kept ON as production has them (block_elite_bull VIX 0-25, block_bull_1100_1200, min_triggers_bull=2, VIX bull caps) — each removes a validated losing cohort; unblocking them to inflate n would test a different (worse) book.
2. **The baseline itself is top-3 concentrated:** +$5,139 of +$5,466 (94%) sits in 3 trades; baseline drop-top3 = +$327.50 (positive but thin). The engine's bull edge remains an OP-16-caveated, few-big-winners book — this study neither strengthens nor weakens that; it only rejects the exit swap.
3. Params drift vs the 06-26 chef record (2 extra trades, −$120 total) is explained by documented post-06-26 changes; both numbers are quoted.
4. Fill conventions inherited from `simulator_real`: BUY at next-bar open +2¢, stop/TP1 limit fills at exact trigger price, exits at bar close −2¢. Stop-at-limit is optimistic in fast tape; the spread stress column is the honest sensitivity (2.0–2.6¢/side to zero).
5. qty1 rows are the fractional /3 siblings; a REAL 1-lot cannot sell 2/3 at TP1 (int truncation ⇒ pure-runner management). At the engine's actual min-3 (Rule 6), qty3 is the executable cell — it fails the same nails.
6. Window ends 2026-06-18 (freshest full SPY 5m master). Recency (post-06-18) is untested here; the live recency gate is currently RED anyway (pk-2026-07-01-001).
7. Baselines used the chef harness's params-path (`_params_to_kwargs`), which drops the v15 chandelier keys. **CORRECTION (2026-07-02 frame-audit): this drop is INTENTIONAL and L156-encoded — NOT a C14 dead-knob to "fix".** The chandelier is regime-conditional (net-negative on the volume-dominant trending windows), so mapping it into the baseline would permanently bias every candidate comparison negative (`test_profit_lock_not_in_baseline.py` REDs on any such mapping). The absence is also *symmetric* across A/B arms (baseline + candidate both traverse this mapper), so it does not corrupt relative verdicts — it only makes the *baseline's absolute* P&L conservative vs live production, which is the tradeoff L156 deliberately chose. Does not affect port cells (exits forced explicitly). The earlier "flagged for fix as a separate task" note was a misdiagnosis; the queue item PARAMS-TO-KWARGS-CHANDELIER-DEADKNOB is resolved WONT-FIX-BY-DESIGN.
8. Engine runs share the one-position-at-a-time + escalation-lock dynamics, so cell cohorts can drift ±2 entries vs baseline via hold-duration differences (observed: 27 shared + 2 recovered-by-fetch on all cells).

## Repro

- Harness: `backtest/autoresearch/_phasec_bull_family_port.py` (wrapper-monkeypatch around `orchestrator.simulate_trade_real`; production code untouched; pre-registered cells + gates in the docstring).
- Raw: `results.json` (battery + gates per cell), `trades.json` (per-trade rows for baseline/cells/nulls), `_stage1.json`, `_run.log` (26 engine runs incl. attempt-2 after fetching 10 uncached OPRA contracts; final misses = 0).
- Runtime: ~24 min single process, backtest/.venv.
