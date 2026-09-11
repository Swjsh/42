<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=37.431s | action=critique_sweep_representative -->
<!-- reason: Sweep hit 8835 rows and looks mature; last entry is a flagged loser. Kill-confirmation on a representative recent reject turns raw sweep output into actionable triage. Rotates off yesterday's gap_and_go critique. -->

**1. Negative edge_capture vs. positive expectancy – sample‑size artifact?**  
- **edge_capture = ‑717.6** (the cumulative “edge” after the sweep’s cost model).  
- **expectancy = +9.07** (average profit‑per‑trade reported by the sweep).  
- With **n = 79** trades, the implied average edge from the cumulative figure is **‑717.6 / 79 ≈ ‑9.08** per trade – the exact opposite sign of the reported expectancy.  

If expectancy were truly +9.07, the cumulative edge after 79 trades would be **+9.07 × 79 ≈ +717.6**, not ‑717.6. The only way to reconcile the two numbers is that the sweep’s *expectancy* field is being calculated on a **different subset** (e.g., only winning trades, or after applying a separate scaling factor) while *edge_capture* reflects the full P&L including losers and transaction costs.  

With only **79 observations**, the standard error of the mean expectancy is roughly  

\[
SE \approx \frac{\sigma}{\sqrt{n}}.
\]

Even assuming a generous σ ≈ 30 (typical for a high‑volatility intraday system),  

\[
SE \approx \frac{30}{\sqrt{79}} \approx 3.4,
\]

so a 9‑point expectancy is only about **2.6 SE** away from zero – a marginal signal that can easily flip sign with a few outlier trades. In short, the discord between edge_capture and expectancy is **consistent with a small‑sample artifact**; the data do not give us confidence that the true expectancy is positive.

---

**2. Walk‑forward wf = ‑0.829 – does it confirm the J‑edge floor of 771 fails?**  
The walk‑forward metric (**wf**) measures the ratio of out‑of‑sample edge to in‑sample edge. A value **below 0** indicates that the strategy performed *worse* out‑of‑sample than it did in‑sample; the more negative, the larger the degradation.

- **wf = ‑0.829** means the out‑of‑sample edge is roughly **‑83 %** of the in‑sample edge (i.e., a loss of 183 % relative to the in‑sample gain).  
- The “J‑edge floor of 771” (the minimum cumulative edge the sweep requires to consider a combo viable) is far above the observed **edge_capture = ‑717.6**. Even if we ignored the sign, the absolute magnitude (‑717.6) is **below** the floor of +771.  

Thus, the negative wf **confirms** that the combo does **not** meet the J‑edge floor: the strategy’s edge collapses when tested on unseen data, and the cumulative edge is on the wrong side of the floor threshold.

---

**3. op16_reject = true – should the combo be auto‑killed regardless of expectancy?**  
`op16_reject` is a hard‑filter flag that the sweep applies after the OP‑16 statistical sanity test (which checks for things like excessive skew, kurtosis, or violation of the assumed return distribution). When the flag is **true**, the combo is **disqualified** from further consideration **irrespective** of any profitability metrics that may look attractive.

Given:
- **op16_reject = true**  
- **expectancy = +9.07** (positive but suspect, see #1)  

The correct operational rule is: **auto‑kill**. The positive expectancy cannot override a failed OP‑16 test because the test guards against spurious results driven by non‑stationarity, outliers, or distributional violations that would make the expectancy unreliable in live trading.

---

**4. If qty_frontier changed from null to a real qty value – would that rescue the combo?**  
`qty_frontier` is the position‑size frontier the sweep uses to enforce risk‑adjusted scaling (e.g., max contracts per trade based on volatility). A **null** value means the sweep fell back to its default sizing (often the minimum allowed), which can suppress both profit and loss.

Changing `qty_frontier` to a concrete number (say, 2 contracts instead of the default 1) would **scale both the edge_capture and the expectancy roughly linearly** with the quantity, assuming the strategy’s per‑trade edge remains unchanged:

- New edge_capture ≈ ‑717.6 × (Q_new / Q_default).  
- New expectancy ≈ +9.07 × (Q_new / Q_default).

Even if we doubled the qty (Q_new = 2 × Q_default), the numbers become:
- edge_capture ≈ ‑1 435.2  
- expectancy ≈ +18.14  

The **sign** of edge_capture stays negative, the **walk‑forward** wf would likely stay around ‑0.8 (scaling does not fix the out‑of‑sample degradation), and **op16_reject** would remain true because the OP‑16 test is independent of position size. The max drawdown would also scale (‑2664.49 × 2 ≈ ‑5 328.98), worsening risk.

Therefore, merely supplying a real qty_frontier **does not rescue** the combo; the fundamental flaws (negative cumulative edge, poor walk‑forward, OP‑16 failure) persist, and any size increase would amplify losses and drawdown rather than cure them.

---

### TL;DR
| Metric | Value | Interpretation |
|--------|-------|----------------|
| edge_capture | ‑717.6 | Negative cumulative edge – opposite sign of reported expectancy |
| expectancy | +9.07 | Likely a small‑sample artifact; with n=79 the SE ≈ 3–4, so the signal is weak |
| wr | 0.3291 | Low win‑rate (≈33 %) |
| max_