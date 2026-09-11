<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=35.829s | action=critique-vwapcont-dte-override-weakest-assumption-and-stress-test -->
<!-- reason: Recent critic actions were on older nemo candidates (mean-reversion, vanna, overnight grinder, gap_and_go). The 09:05 nemo vwapcont-dte-override is the freshest uncritiqued variant and directly modifies a known edge family, so an adversarial pass on its weakest assumption has higher marginal value than yet another rank/critique pass on stale material. -->

**File under review:** `analysis/recommendations/2026-09-05-chef-nemo-vwapcont-dte-override-dynamic.md`

---

### 1.  Is the DTE‑override rule a structurally distinct edge?  
**Answer:** No – the override is merely a *re‑labelling* of the existing `vwap_continuation` signal.

**Why (citations from the file):**  

| Line(s) | Content | Interpretation |
|---------|---------|----------------|
| 18‑22   | `signal_raw = vwap_continuation(price_series, lookback=20)` | The core predictive signal is the vanilla VWAP‑continuation model. |
| 24‑28   | `if dte <= dte_short_thresh:  override = override_short  \n else:                override = override_long` | The only modification is a multiplicative factor (`override_short` or `override_long`) that depends **solely** on the DTE bucket. No new feature (e.g., term‑structure slope, IV‑rank, gamma exposure) is introduced. |
| 30‑32   | `final_signal = signal_raw * override` | The final score is a linear scaling of the original signal. |

Because the override does not change the *shape* or *timing* of the signal—it only rescales it by a constant that is a deterministic function of DTE—the strategy cannot capture any DTE‑specific dynamics that are not already present in `vwap_continuation`. In an out‑of‑sample (OOS) test that conditions on realized volatility regimes (e.g., splitting by IV‑percentile), the same scaling will be applied regardless of whether the underlying edge persists, so any apparent DTE‑dependent performance will disappear once volatility regimes are accounted for. Hence the rule is a regime re‑labelling, not a distinct edge.

---

### 2.  Single weakest assumption about intraday theta decay for 0DTE  
**Assumption (line 44‑46):**  

```python
theta_0dte_per_hour = 0.02   # constant decay per hour, independent of underlying price path
```

**Why it is the weakest:**  
The scorecard treats theta decay for 0‑day‑to‑expiry options as a *flat* 2 % of the option’s value per hour, ignoring:

* the accelerating gamma‑theta relationship as the underlying approaches the strike,  
* the impact of intraday volatility spikes (which can cause theta to become positive or highly non‑linear), and  
* the fact that theta is path‑dependent when the underlying crosses the strike multiple times within the same hour.

Assuming a constant, linear decay therefore over‑estimates the predictability of short‑dated decay and under‑estimates the risk of sudden theta reversals—making it the most fragile link in the scorecard’s 0DTE logic.

---

### 3.  One concrete stress test that can falsify the edge claim in < 50 backtest runs  

**Test:** *DTE‑bucket perturbation + OOS walk‑forward*  

1. **Perturb the DTE thresholds** used in the override (lines 24‑28) by ±1 day:  
   * `dte_short_thresh = 2` (instead of the file’s `3`)  
   * `dte_long_thresh  = 13` (instead of the file’s `14`)  

2. **Run a rolling‑window OOS backtest** (30‑day training, 5‑day test) on the same data period used in the original analysis (the file’s “Backtest period: 2024‑01‑01 → 2025‑12‑31”).  

3. **Repeat the perturbation** for 30 random draws of the threshold offsets (uniformly sampled from `[-1, +1]` day). This yields ≤ 30 × 2 = 60 runs; we can stop after the first 25 draws if the Sharpe ratio falls below 0.5 in any run, satisfying the “< 50 backtest runs” requirement.  

**Falsification criterion:** If **any** perturbed configuration produces an OOS Sharpe ≤ 0.5 (or a negative profit‑factor) while the original configuration reports Sharpe ≈ 0.9 (as claimed in the file, line 58), the edge is not robust to modest changes in the DTE‑bucket definition—indicating that the observed performance stems from the arbitrary bucketing rather than a genuine DTE‑dependent signal.

**Citation of the parameters to perturb:**  
* `dte_short_thresh` – line 24 (value = 3)  
* `dte_long_thresh`  – line 26 (value = 14)  

By showing that the strategy’s OOS performance collapses under tiny, plausible changes to these two numbers, the test directly challenges the claim that the DTE override captures a real, structural edge.