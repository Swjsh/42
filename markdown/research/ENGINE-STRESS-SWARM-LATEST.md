# Engine-Stress Swarm — Batch Report

**Generated:** 2026-07-14T08:00:29 ET
**Disclosure:** Perturbed/synthetic bars -> BS-sim option fills -> RANKING-ONLY, not a WR authority (CLAUDE.md C1).

## Grid
- Runs: 960 (960 ok / 0 errors)
- Seeds: 2026-06-11, 2026-06-05, 2026-06-09, 2026-06-23, 2026-05-27, 2026-05-19, 2026-06-04, 2026-06-26
- Perturbations: baseline, trend_flip, amplify, dampen, gap_open, vix_up, vix_down, add_noise
- Variants: base_v15, tp1_30_allout, tp1_30_split, tp1_50_split, tp1_75_split, risk_15pct, risk_50pct, exit_chandelier, exit_fixed_tight, bull_off, tp1_30_allout_risk50, runner_2x, runner_3x, stop_catastrophe_only, min_trig_bull_1
- Aggregate BS-sim P&L (ranking-only): $-3009.9 over 827 trades

## Anomalies surfaced: 25
- **big_loss** seed=2026-06-09 pert=trend_flip variant=base_v15 pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_30_allout pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_30_split pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_50_split pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=tp1_75_split pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=risk_15pct pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=risk_50pct pnl=-1008.6
- **big_loss** seed=2026-06-09 pert=trend_flip variant=exit_chandelier pnl=-1008.6
- **sizing_fragile** seed=2026-06-11 pert=baseline variant=base_v15 pnl=1184.9
- **sizing_fragile** seed=2026-06-11 pert=vix_down variant=base_v15 pnl=846.3
- **sizing_fragile** seed=2026-06-05 pert=vix_up variant=tp1_75_split pnl=541.4
- **sizing_fragile** seed=2026-06-09 pert=baseline variant=exit_chandelier pnl=420.8
- **sizing_fragile** seed=2026-06-09 pert=trend_flip variant=bull_off pnl=447.6
- **sizing_fragile** seed=2026-06-09 pert=amplify variant=tp1_75_split pnl=792.9
- **sizing_fragile** seed=2026-06-09 pert=dampen variant=tp1_30_allout pnl=672.6
- **sizing_fragile** seed=2026-06-09 pert=gap_open variant=exit_chandelier pnl=524.4
- **sizing_fragile** seed=2026-06-09 pert=vix_up variant=bull_off pnl=621.3
- **sizing_fragile** seed=2026-06-09 pert=add_noise variant=runner_2x pnl=1210.4
- **sizing_fragile** seed=2026-05-27 pert=add_noise variant=min_trig_bull_1 pnl=838.4
- **missed_strong_move** seed=2026-06-11 pert=trend_flip variant=base_v15 pnl=0.0

## Swarm verdict (5-model free panel)
_models: cerebras:zai-glm-4.7, nvidia/nemotron-3-super-120b-a12b:free, cerebras:gpt-oss-120b, openai/gpt-oss-20b:free, nvidia/nemotron-3-ultra-550b-a55b:free (5/5 ok)_

**1. Consensus points**  
- The “big_loss” anomalies are concentrated on a single seed/perturbation (2026‑06‑09 + trend_flip) and show identical P&L across all sizing/exit variants, indicating the loss occurs before variant‑specific logic can act.  
- The current evidence is insufficient to claim robustness; out‑of‑sample (OOS) testing, realistic fill modeling, and broader perturbation coverage are required.  
- The engine’s exit rule (`EXIT_ALL_PREMIUM_STOP`) appears to be a single point of failure that turns adverse moves into total‑premium losses.  
- Position‑sizing variants (`risk_15pct`, `risk_50pct`) do not differentiate outcomes in these loss cases, revealing a sizing‑logic gap when the stop is absolute.  
- Entry/gate logic lacks a short‑term trend or volatility filter, allowing trades to be taken immediately before a reversal that wipes premium.  

**2. Key disagreements**  
- **Sizing‑fragile robustness:** Perspective 3 explicitly names `risk_15pct` as the robust choice (limits exposure per trade). Perspective 1 notes the missing `sizing_fragile` rows but observes that `risk_15pct` and `risk_50pct` behave identically in the shown losses, implying the sizing logic is non‑functional in this failure mode. Perspectives 2, 4, 5 do not address the question.  
  *Most rigorous take:* Perspective 3’s answer is concrete and actionable; the agreement that sizing variants fail to diverge under the observed catastrophic stop supports the idea that a lower‑risk cap (e.g., 15 %) is the only defensible sizing choice until the exit logic is fixed.  

- **Defensibility of engine decisions:** Perspective 3 and 5 argue the entry decision is not defensible because it omits a trend‑confirmation gate. Perspective 1 treats the loss as a potential real hole but does not explicitly rule out defensibility. Perspectives 2 and 4 focus on evidence gaps rather than decision logic.  
  *Most rigorous take:* Perspectives 3 & 5 provide a clear, testable hypothesis (missing trend filter) that aligns with the identical early exits; this is more specific than the generic “hole” claim.  

**3. Synthesized recommendation**  
The engine’s catastrophic losses stem from an exit rule that triggers total‑premium loss before any sizing or exit variant can modulate risk, compounded by an entry gate that admits trades without confirming short‑term trend or volatility conditions. To harden the system, replace the absolute “all‑premium‑stop” with a volatility‑scaled trailing stop (e.g., 1.5 × ATR), add a trend‑confirmation filter (e.g., require a 5‑minute directional bias or ADX > X before accepting level‑rejection/reclaim signals), and implement volatility‑adjusted position sizing that caps dollar risk per trade (e.g., 15 % of equity scaled by recent 5‑min realized vol). These changes are concrete, directly address the observed failure mode, and can be validated with OOS walk‑forward testing.  

**4. Confidence in synthesis**  
8 / 10 – All five perspectives converge on the need for more evidence and identify the same structural weaknesses (exit stop, entry gate, sizing irrelevance). The only notable divergence is the explicit sizing‑fragile recommendation, which is supported by the shared observation that sizing variants do not alter outcomes in the loss cases.  

**5. Single most‑important next action**  
Execute a walk‑forward OOS back‑test on at least 250 calendar days (including the eight seed dates and all eight perturbations) using realistic fill assumptions (slippage, bid‑ask spread, latency). Compare three configurations: (a) current baseline, (b) baseline + volatility‑scaled trailing stop, (c) baseline + trailing stop + trend‑confirmation filter + volatility‑adjusted 15 % risk sizing. Measure max‑drawdown, tail‑loss (5 % VaR), and win‑rate.  

**6. Watch‑for signal**  
If the OOS test shows that the proposed volatility‑scaled trailing stop (or any exit modification) does **not** reduce the frequency or magnitude of > ‑800 PNL losses relative to baseline, or if the trend‑confirmation filter fails to improve the win‑rate on the same perturbation set, then the synthesized hypothesis (exit‑stop + gate + sizing) is invalid and the engine’s core logic must be re‑examined.