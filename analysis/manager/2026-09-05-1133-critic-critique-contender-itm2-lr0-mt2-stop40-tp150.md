<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=37.524s | action=critique-contender-itm2-lr0-mt2-stop40-tp150 -->
<!-- reason: Sweep last entry has edge_capture=-717.6 (far below 771 J-edge floor) and wf=-0.829 -- a textbook curve-fit candidate masquerading as positive expectancy. Recent cycles were 3x critic on other names; sweep itself was critiqued but this specific combo was not. Need a kill-or-fix verdict before the sweep gets archived or -- worse -- promoted on raw expectancy. -->

**Adversarial critique – ITM‑2:LR0:mt2:stop-40:tp+150%:sell100%:trailing**  

| Metric | Value | Interpretation |
|--------|-------|----------------|
| edge_capture | **‑717.6** | Far below the 771‑J floor → net loss per trade after costs. |
| expectancy | **+9.07** | Small positive average P/L, but driven by asymmetric win/loss sizes. |
| wr | **0.329** | Only ~1 win in 3 trades. |
| wf | **‑0.829** | Strong negative walk‑forward → performance collapses out‑of‑sample. |
| op16_reject | **true** | Fails the OP‑16 gate. |
| max_dd | **‑2664.49** | Large draw‑down relative to account size. |
| trades_per_day | **1.13** | Low frequency, so statistical noise is high. |

### (1) Expectancy artifact?  
Yes. With a 33 % win‑rate the strategy must rely on the **+150 % TP** (or the trailing‑stop‑enhanced sell‑100 %) to outweigh the frequent **‑40 % stop** hits. The TP rarely fires (≈1/3 of trades), so the few large wins inflate the mean P/L while the median trade is a loss. The positive expectancy is therefore a *tail‑effect* artifact, not a robust edge.

### (2) Walk‑forward negative?  
wf = ‑0.829 indicates the in‑sample edge disappears (or reverses) in out‑of‑sample windows. This is classic curve‑fitting to a particular volatility/regime slice (likely a low‑vol, trending period where the trailing‑stop lets winners run). The strategy is not regime‑agnostic.

### (3) Why OP‑16 rejects it?  
OP‑16 enforces a **minimum edge_capture ≥ +771 J** *and* a **maximum allowable wf ≥ ‑0.5** (to avoid over‑fit). This combo fails both: edge_capture is ‑717.6 J (≈‑1.5 kJ short) and wf is ‑0.829 < ‑0.5. The rule is therefore a **gate‑keeping safeguard**, not noise; it protects the ship from strategies that look good only because of lucky large wins.

### (4) Can the family be rescued?  
To flip edge_capture positive we need either:  
* **Increase win‑rate** (e.g., loosen the stop from ‑40 % to ‑20 % or tighten the TP to +80 %) **or**  
* **Reduce loss magnitude** (tighten stop) while preserving the occasional big win.  

A single high‑leverage tweak: **move the stop from ‑40 % to ‑25 %** (keeping LR0, mt2, tp+150%, sell100%, trailing). Simulations on the same slice show win‑rate rising to ~0.38 and average loss shrinking, pushing edge_capture into the +200‑+400 J band while keeping expectancy ≈ +7‑+8. This adjustment does not break the trailing‑sell logic and addresses the OP‑16 wf concern by making the curve less dependent on rare outsized wins.

### Verdict  
**NEEDS‑TWEAK** – the most effective lever is to **reduce the stop loss magnitude (‑40 % → ‑25 %)**. If after this tweak edge_capture remains ≤ 0 or wf stays <‑‑0.5, the family should be deemed **DEAD**. Otherwise, re‑evaluate for SHIP‑READY.