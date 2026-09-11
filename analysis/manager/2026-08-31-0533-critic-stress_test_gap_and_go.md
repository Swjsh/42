<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=19.284s | action=stress_test_gap_and_go -->
<!-- reason: Sweep is at 8835 rows; per 'next 4 actions' item #4 the gap_and_go critique is owed, and the most recent critic action was a contender-rank load — switching target to gap_and_go satisfies rotation + overseer's 'critique a SPECIFIC named candidate' guidance. -->

The weakest assumption is **data‑window representativeness** – the edge claim is built on 2020‑01‑01 → 2023‑12‑31, omitting the 2024‑2026 period of higher volatility, regime shifts, and altered liquidity.

**Stress‑test plan**

- **OOS slice to hold out:** 2024‑01‑01 → 2026‑06‑30 (inclusive). Based on the strategy’s historical trade frequency (~4.1 trades/day), we expect **≈3 000 OOS trades**.  
- **Parameter perturbation:** increase the slippage assumption by **+20 %** (from 0.05 % per trade to 0.06 % per trade) to reflect the worse execution conditions observed in the 2024‑2026 window.  
- **Kill criterion:** compute the profit‑factor (PF) and its 95 % confidence interval on the OOS results. If the **lower bound of the PF‑CI falls below 1.0** *or* the **edge‑capture (net profit per trade) drops by >30 %** relative to the in‑sample estimate, the claim is considered falsified.

No new variants are introduced; this test directly challenges the representativeness of the original data window.