# Engine-Stress Swarm — Batch Report

**Generated:** 2026-06-28T23:52:30 ET
**Disclosure:** Perturbed/synthetic bars -> BS-sim option fills -> RANKING-ONLY, not a WR authority (CLAUDE.md C1).

## Grid
- Runs: 960 (960 ok / 0 errors)
- Seeds: 2026-06-11, 2026-06-05, 2026-06-09, 2026-06-23, 2026-05-27, 2026-05-19, 2026-06-01, 2026-06-16
- Perturbations: baseline, trend_flip, amplify, dampen, gap_open, vix_up, vix_down, add_noise
- Variants: base_v15, tp1_30_allout, tp1_30_split, tp1_50_split, tp1_75_split, risk_15pct, risk_50pct, exit_chandelier, exit_fixed_tight, bull_off, tp1_30_allout_risk50, runner_2x, runner_3x, stop_catastrophe_only, min_trig_bull_1
- Aggregate BS-sim P&L (ranking-only): $9280.8 over 456 trades

## Anomalies surfaced: 29
- **big_loss** seed=2026-06-11 pert=baseline variant=tp1_75_split pnl=-658.3
- **big_loss** seed=2026-06-09 pert=trend_flip variant=base_v15 pnl=-527.0
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_30_allout pnl=-527.0
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_30_split pnl=-527.0
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_50_split pnl=-527.0
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_75_split pnl=-527.0
- **big_loss** seed=2026-06-09 pert=trend_flip variant=risk_15pct pnl=-527.0
- **big_loss** seed=2026-06-09 pert=trend_flip variant=risk_50pct pnl=-527.0
- **sizing_fragile** seed=2026-06-11 pert=baseline variant=base_v15 pnl=1184.9
- **sizing_fragile** seed=2026-06-11 pert=vix_down variant=base_v15 pnl=846.3
- **sizing_fragile** seed=2026-06-05 pert=gap_open variant=tp1_30_split pnl=521.0
- **sizing_fragile** seed=2026-06-05 pert=vix_up variant=tp1_75_split pnl=541.4
- **sizing_fragile** seed=2026-06-09 pert=baseline variant=exit_chandelier pnl=420.8
- **sizing_fragile** seed=2026-06-09 pert=trend_flip variant=bull_off pnl=447.5
- **sizing_fragile** seed=2026-06-09 pert=dampen variant=tp1_30_allout pnl=672.6
- **sizing_fragile** seed=2026-06-09 pert=add_noise variant=tp1_75_split pnl=1423.1
- **missed_strong_move** seed=2026-06-11 pert=trend_flip variant=base_v15 pnl=0.0
- **missed_strong_move** seed=2026-06-11 pert=amplify variant=base_v15 pnl=0.0
- **missed_strong_move** seed=2026-06-05 pert=trend_flip variant=base_v15 pnl=0.0
- **missed_strong_move** seed=2026-06-09 pert=amplify variant=base_v15 pnl=0.0

## Swarm verdict (5-model free panel)
_models: cerebras:zai-glm-4.7, nvidia/nemotron-3-super-120b-a12b:free, openai/gpt-oss-120b:free, cerebras:gpt-oss-120b, openai/gpt-oss-20b:free (5/5 ok)_

**Consensus points**  
- The engine generated a net positive P&L (+$9,280.8) across 960 deterministic runs with zero errors, indicating the underlying entry/setup logic has some edge.  
- All perspectives agree that the reported P&L is **BS‑sim ranking‑only** and does not reflect realistic fills, slippage, bid‑ask spread, or execution latency.  
- The anomaly grid reveals **exit‑logic fragility** (identical catastrophic losses across all TP/risk/variant settings under the `trend_flip` perturbation) and **sizing fragility** (large P&L swings between variants on the same seed/perturbation).  
- Missing disclosures noted by every view: account size/position‑sizing basis, out‑of‑sample validation, real‑world fill assumptions, concentration risk, and failure‑mode analysis.  
- All agree that **further testing with realistic execution models and OOS data** is required before live deployment.

**Key disagreements**  
- **Nature of the anomaly:** Perspectives 1, 3, 4 argue the `trend_flip` losses expose a *real engine hole* (exit logic fails in regime‑shift scenarios). Perspective 2 treats them as a *signal needing validation* but does not yet label them a hole; Perspective 5 downplays them as artifacts of the synthetic grid.  
- **Sizing fragility:** Perspectives 1 & 3 highlight the wide P&L spread between `base_v15` and aggressive TP‑split variants as a genuine robustness issue; Perspective 2 acknowledges the spread but frames it as a sizing‑parameter sensitivity that needs realistic testing; Perspective 5 treats it as expected variant dispersion.  
- **Overall robustness claim:** Perspective 5 asserts the engine’s sizing/exit logic is robust; Perspective 1 & 3 claim fragility; Perspective 2 takes a middle ground—profitable in simulation but unproven in live conditions.  

**Most rigorous perspective:** Perspective 2 (nvidia/nemotron‑3‑super). It balances the positive simulation results with explicit, concrete shortcomings (BS‑sim fills, missing risk disclosures, lack of OOS validation) and proposes specific, actionable next steps (realistic fill Monte‑Carlo replay, OOS validation). It avoids over‑interpreting the anomaly patterns as proven holes while still flagging them for investigation, making its critique the most evidence‑grounded and action‑oriented.

**Synthesized recommendation**  
The engine shows a promising edge in a controlled, frictionless simulation, but its profitability cannot be trusted for live 0DTE SPY trading until we validate it with realistic execution models (slippage, bid‑ask spread, partial fills) and out‑of‑sample testing across multiple months. The exit‑logic failures observed under the `trend_flip` perturbation and the sizing‑sensitivity between variants must be stress‑tested under those realistic conditions; if the edge survives, we can then calibrate position‑sizing and exit parameters with confidence.

**Confidence in synthesis**  
8/10 – The five perspectives converge strongly on the need for realistic fills and OOS validation; the only divergence is the interpretation of the anomaly severity, which Perspective 2 resolves by treating them as testable hypotheses rather than proven flaws.

**Single most‑important next action**  
Run a Monte‑Carlo replay of the exact 960 deterministic scenarios using a realistic 0DTE fill model (e.g., historical SPY 0DTE bid‑ask spreads, latency‑adjusted order arrival, and partial‑fill probability based on observed depth) and compute the net P&L after slippage and commissions; compare the distribution to the BS‑sim baseline to determine whether the edge persists.

**Watch‑for signal**  
If the realistic‑fill replay shows the net P&L dropping below zero or the Sharpe ratio falling under 0.5 (or the max‑drawdown exceeding 20% of equity) across the same seed set, the synthesis is invalidated and the engine’s claimed edge is deemed an artifact of the simulation.