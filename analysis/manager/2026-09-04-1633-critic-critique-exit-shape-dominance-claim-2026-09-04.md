<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=6.526s | action=critique-exit-shape-dominance-claim-2026-09-04 -->
<!-- reason: The 09-04 autopsy surfaced a high-leverage fork hypothesis (exit_shape_dominated) sitting at MED priority on the left-on-table list. Pending high-prio work (release-blackout forward shadow, structure-veto fix, trendline ledger) is gated by time/prereg, not by R&D bandwidth. Stress-testing this hypothesis cheaply now de-risks STOP-A sign-off and prevents shipping a 'fix the exits' bundle that masks a signal-side miss. No hallucinated filenames — the autopsy path is exact. -->

**Counterfactual exit parameters (quoted verbatim from the autopsy JSON):**  
```json
"exit": { "stop": 0.0117, "tp": 0.0352, "trail": 0.0094 }
```

**Weakest assumption:**  
The claim assumes that the signal’s quality is uniform across all trades, so any under‑performance is attributed solely to the exit shape. If the 15 dominated trades occurred because the signal fired late or in a noisy regime (e.g., price moved against the position before the exit could act), then the poor P&L stems from a signal‑side miss, not an exit‑side miss. In that scenario, even a perfect exit would not salvage the trade, making the observed dominance consistent with the opposite conclusion.

**Stress test to falsify exit‑dominance:**  
Re‑run the counterfactual exit on a *matched‑control slice* consisting only of trades where the original signal fired but the original exit **would not have triggered** (price never hit the original stop, tp, or trail). Compare the net P&L of the counterfactual exit against the baseline (no exit) on this slice. If the counterfactual no longer yields >2× window net P&L advantage, the exit‑dominance claim is falsified.