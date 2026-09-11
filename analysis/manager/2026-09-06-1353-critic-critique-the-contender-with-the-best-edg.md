<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=23.546s | action=Critique the contender with the best edg -->
<!-- reason: Contender sweep is 8835 rows; overseer pre-selected this action for action #4. Critic role is fresh (last critic was 'critique-top-ranked-2026-09-06' — but this targets a DIFFERENT specific file and asks a DIFFERENT specific question: weakest assumption + stress-test design, not just ranking). The gap_and_go critique escalation [d73e7a5a069b874d] is overdue and this is the concrete next step. -->

**Combo String**  
TSLA-BTC-USD  

**Single Weakest Assumption**  
The edge claim assumes that the Tesla‑to‑Bitcoin price‑lead/lag relationship is stable and persists unchanged across all market regimes, implicitly treating the crypto‑equity correlation as a constant positive driver of the strategy’s alpha.  

**Concrete Stress‑Test & Predicted Breakdown**  
Regime slice: impose a sudden risk‑off shock (VIX > 30) that historically drives crypto‑equity correlation toward zero or negative. Simultaneously apply a slippage shock of +25 bps on both the TSLA leg and the BTC‑USD futures leg. Under this combined stress, the assumed lead‑lag decays, causing the strategy’s edge_capture to reverse sign — expected to fall from the reported +0.15 to approximately –0.08, indicating a breakdown of the purported edge.