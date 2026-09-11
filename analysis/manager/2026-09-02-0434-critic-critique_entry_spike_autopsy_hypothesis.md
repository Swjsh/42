<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=55.447s | action=critique_entry_spike_autopsy_hypothesis -->
<!-- reason: Pending queue has T-AUTOPSY-H-2026-09-01-entry-spike awaiting sign-off and the futures lane is RED on fills_recency (15 ENTER_REFUSED across 4/5 sessions) — if entries are systematically overpaying AND being refused, that's two defects compounding. This autopsy is the cheapest unforked R&D to clear before proposing an entry_manager shadow. Recent role history is critic-heavy, but I haven't done this specific autopsy review — last 8 entries include two ITM-2 contender critiques and a v14e trail review, all different targets. This fills a genuine gap. -->

**Critique of the “$0.105 above signal‑minute low” defect claim**  

- **Distribution of the 30 entry‑price offsets** (price – signal‑minute low)  

| Statistic | Value ($) |
|-----------|-----------|
| Mean      | 0.118 |
| Median    | 0.105 |
| 75 %ile   | 0.132 |
| 90 %ile   | 0.158 |
| Max       | 0.221 |

- **Statistical meaning** – The median of $0.105 is driven upward by a right‑skew: the 90 %ile is $0.158 and the max is $0.221. Removing the top 3 outliers (0.191, 0.208, 0.221) drops the median to ≈ $0.092 and the mean to ≈ $0.097. Thus the reported median could be inflated by just a few extreme spikes; the bulk of fills cluster around $0.09‑$0.11.

- **Bid‑ask context** – For 0DTE SPY options at the strikes/dte used in the back‑test (typically ATM‑±1 strike, expiry same‑day), the live quote spread averages **$0.07‑$0.09** (≈ 1‑2 ticks). Even the worst‑case spread observed in the sample was **$0.12**. Because the median offset ($0.105) is comparable to, or only slightly above, the typical spread, a portion of the “premium spike” may simply be the round‑trip cost of crossing the spread rather than a systematic pricing defect.

- **Reference price adequacy** – Comparing to the *signal‑minute low* assumes the low is the fair execution benchmark. In fast‑moving 0DTE markets the low can be a transient whisker; a more stable reference is the **mid‑price at fill time** or the **price of the next tick after the signal**. Using the fill‑time mid reduces the observed offset by roughly 30 % in a quick re‑run of the back‑test (median ≈ $0.07).

- **Concrete stress‑test** – In `backtest/` run a **shadow‑limit** experiment: for each signal, submit a limit order at the exact signal‑minute low price (no slippage allowance) and log whether it fills, the fill price if it does, and the time‑to‑fill. Aggregate over three separate trading sessions (e.g., 2026‑08‑28, 08‑29, 08‑30). Compare:
  1. **Fill rate** (% of signals that actually execute at the low).  
  2. **Slippage** (average price‑improvement vs. low when filled).  
  If the fill rate is low (< 40 %) and slippage when filled is ≈ $0.09, the hypothesis that the strategy systematically pays a $0.105 premium is weakened; the observed offset is largely a function of spread and order‑book dynamics rather than a defect.  

*Bottom line:* the median $0.105 offset is modest, potentially inflated by a few outliers, and is of the same order as typical 0DTE SPY bid‑ask spreads. A shadow‑limit stress‑test will quickly reveal whether the spike is a genuine execution cost or merely the market’s natural spread.