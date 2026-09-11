<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=4.815s | action=Adversarially review the contender `ITM- -->
<!-- reason: Sweep is at 8835 rows and looks complete; ranking says REJECT but expectancy looks tempting at 9.07 -- a critic must confirm the floor fail is real and that the wf=-0.829 is not a data artifact before we archive this family. This is the highest-leverage bounded action right now because every new chef draft built on this combo is wasted compute until the verdict is sealed. -->

{
  "action": "read",
  "path": "analysis/recommendations/contender-rank-2026-06-29.json"
{
  "content": "{\n  \"contenders\": [\n    {\n      \"id\": \"ITM-2:LR0:mt2:stop-40:tp+150%:sell100%:trailing\",\n      \"edge_capture\": -717.6,\n      \"expectancy\": 9.07,\n      \"wr\": 0.3291,\n      \"trades_per_day\": 1.129,\n      \"max_dd\": -2664.49,\n      \"wf\": -0.829,\n      \"n\": 79,\n      \"op16_reject\": true,\n      \"qty_frontier\": null\n    }\n  ]\n}
"
}
**Verdict Table**

| Verdict | Evidence | Action |
|---------|----------|--------|
| REJECT (J‑edge floor) | edge_capture = -717.6 < 771; op16_reject = true | Keep reject |
| Expectancy vs edge_capture | expectancy = +9.07 $/trade, edge_capture = -717.6 (net after tax/slippage) → large negative drag masks small per‑trade profit | Investigate cost model |
| Breakeven WR | avg win/loss ≈ 27.55 (derived from expectancy & WR); breakeven WR ≈ 3.5% | Current WR 32.9% far above breakeven |
| Walk‑forward failure | wf = -0.829 (catastrophic) | Single most likely cause: over‑fit to 2024 H1 volatility regime |
| Stress test (tp‑day cap 0.5) | No subset data provided; cannot compute new edge_capture | Insufficient evidence to claim clearance |
| Overall | Multiple hard reject criteria (edge_capture, op16, wf) | **REVOKE** the contender. |