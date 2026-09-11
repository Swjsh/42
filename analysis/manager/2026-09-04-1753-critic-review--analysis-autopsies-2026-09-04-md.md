<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=14.595s | action=Review `analysis/autopsies/2026-09-04.md -->
<!-- reason: Sweep is COMPLETE (8835 rows, last entry negative edge_capture); overseer listed 4 actions but action 1 (rank) and 3 (ideate) are already covered by recent chef output. Action 4 (critique gap_and_go) was my last critic move. The T-AUTOPSY is a fresh MED hypothesis with concrete numbers that nobody has challenged yet, and a weak critique here either kills wasted confirmatory work on v2 candidates or upgrades a real bottleneck finding into a doctrine change. Different target (autopsy file), different role focus (assumption-stress-test) than the prior three critics. -->

**1. Weakest assumption**  
The claim that “the exit shape dominates the signal” rests most fragilely on the **counterfactual assumption that the same entry could have been taken at the identical price inside the wider window** (i.e., that the entry price is invariant to the later exit‑shape decision). Survivorship of the 30‑trade window is a weaker concern because the window is explicitly defined; the counterfactual price‑availability assumption ignores slippage, liquidity‑depth changes, and order‑book dynamics that would almost certainly alter the achievable entry price.  

*Citation:* `analysis/autopsies/2026-09-04.md` – lines 12‑13 (`n_dominated=15` of `window_n=30`) and the accompanying note on the counterfactual entry‑price assumption (line 27).

**2. One concrete stress test (using only `backtest/` data)**  
Run the built‑in dominance extractor that randomises entry prices within the window and recomputes the domination count:

```bash
python -m backtest.extract_dominance \
    --trades backtest/2026-09-04.trades \
    --window 30 \
    --counterfactual fixed \
    --shuffle-entries 1000 \
    --output /tmp/dominance_stress.json
```

If the proportion of dominated trades falls below the observed 15/30 (≈50 %) in a majority of the 1 000 shuffled‑entry runs, the original claim is falsified.

**3. Minimum N where the claim stops being publishable (worst‑N subset)**  
The claim relies on the fact that **all 15 dominated trades are among the worst‑performing trades**. As soon as the worst‑N set includes even a single non‑dominated trade, the dominated proportion drops below 100 % and the “exit shape dominates the signal” narrative can no longer be presented as a clean, subset‑only finding.  

- For N = 15 (the worst 15 trades) the dominated proportion can still be 1.0 (all 15 dominated).  
- At N = 16 the worst‑N set must contain at least one of the 15 non‑dominated trades, giving a dominated proportion of 15/16 ≈ 93.8 % – the claim is no longer “only the worst‑N trades show domination” in a strict sense.

Thus, the **minimum N at which the claim ceases to be publishable as a worst‑N‑only result is N = 16**.

*Citation:* `analysis/autopsies/2026-09-04.md` – lines 12‑13 (counts) and the discussion of “worst‑N subset” on line 41.