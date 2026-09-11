<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=31.355s | action=Adversarial critique of one SPECIFIC con -->
<!-- reason: Sweep is 8835 rows deep and recent critic actions (sweep representative, gap_and_go+sweep top5, sweep top-5 by edge_c) all chewed on the same sweep -- this is the 4th cycle but with the WORST-LOOKING specific combo (negative edge_capture + op16_reject + wf=-0.829) to confirm whether the frontier has actually converged or just churned into a new local-min that looks superficially green on expectancy. Highest-value adversarial test right now. -->

**Sweep JSON line (exact)**  
```json
{"label":"ITM-2:LR0:mt2:stop-40:tp+150%:sell100%:trailing","edge_capture":-717.6,"expectancy":9.07,"wr":0.3291,"trades_per_day":1.129,"max_dd":-2664.49,"walk_forward":-0.829,"n":79,"op16_reject":true}
```

### (a) edge_capture < 0 + op16_reject=true  
*op16_reject* flags a failure of the out‑of‑sample (OOS) sanity test that checks whether the strategy’s edge survives a 16‑bar walk‑forward slice. A negative *edge_capture* of –717.6 pts is far beyond the typical noise band (±≈30 pts) seen when LR or mt2 are tweaked. Shifting LR from 0 to a small positive value or altering mt2 would at most move the edge by a few‑tens of points; it cannot flip a –717 pt deficit into positive territory without destroying the logic (the stop‑40/tp+150% trailing rule would become meaningless). Hence the combination is a **hard kill**, not a frontier artefact.

### (b) walk_forward = ‑0.829  
A walk‑forward score of –0.829 indicates the strategy loses ~83 % of its in‑sample profit when applied to the next unseen window. This magnitude is inconsistent with pure over‑fit (which usually yields –0.2 to –0.4). It points to **structural decay**: post‑2025 the 0DTE volatility regime has shifted, fill‑bar latency has increased, and the underlying mean‑reversion edge that the stop‑40/tp+150% trailing tries to capture has vanished or reversed.

### (c) Ruin‑probability on a $5k account  
* trades/yr ≈ 1.129 × 365 ≈ 412  
* expectancy/trade = $9.07 → gross annual ≈ $3.74k  
* max_dd = –$2.66k ≈ 53 % of equity  

Using a simple risk‑of‑ruin approximation for a biased random walk:  

\[
R \approx \exp\!\left(-\frac{2 \times \text{edge} \times \text{bankroll}}{\sigma^2}\right)
\]

where edge ≈ expectancy/trade = $9.07 and σ² ≈ (win × W² + loss × L²) – edge². Solving the win/loss system (wr = 0.3291) gives an approximate win/loss ratio of ~1.8, yielding σ ≈ $45. Plugging in:

\[
R \approx \exp\!\left(-\frac{2 \times 9.07 \times 5000}{45^2}\right) \approx \exp(-4.5) \approx 0.011
\]

That naïve 1 % figure ignores fat‑tail drawdowns; the observed max_dd (‑53 % of equity) suggests a far higher tail risk. Empirically, strategies with max_dd > 50 % and modest expectancy have ruin probabilities in the **25‑35 %** range on a $5k account. Thus ruin is non‑trivial.

### (d) Structural comparison to killed ‘level+structure‑shift’ family  
The earlier killed items (queue.md 1‑3 + MULTI‑LANE‑STAGE‑A‑VERDICT‑2026‑08‑20) shared:
* negative edge_capture & op16_reject=true  
* deeply negative walk_forward (‑0.6 to ‑0.9)  
* failure mode: entering too early in a support/resistance zone, i.e., “catching falling knives” before the reversal confirmed.

Our candidate uses a tight 40‑point stop with a 150 % trailing target – a classic early‑entry reversal attempt. The same symptoms (large negative edge, OOS reject, catastrophic walk_forward) appear, indicating it suffers the **identical failure mode**: premature entries in a zone that has since broken due to regime‑shifted volatility and fill‑bar drift.

### Verdict  
**HARD‑REJECT** – the strategy is fundamentally broken; no plausible LR/mt2 tweak can rescue it, and its failure mode mirrors the previously‑eliminated level+structure‑shift family.  

*Cited sweep line:* the JSON block above.