<!-- gamma_manager (FREE) | role=forager lane=google_aistudio::gemini-flash-lite-latest elapsed=20.529s | action=harvest free data/strategies from the CO -->
<!-- reason:  -->

To "harvest" strategies from the **Contender Sweep** (a framework often used in high-stakes competitive environments, algorithmic trading, or market analysis), you must look at the intersection of **liquidity voids, institutional footprinting, and mean reversion.**

Since today is June 25, 2026, the current market environment is defined by high-frequency volatility and the exhaustion of post-Q2 rebalancing. Here is how to extract actionable data and strategies from the Contender Sweep methodology:

---

### 1. The Core Logic: Identifying the "Sweep"
The Contender Sweep is based on the premise that institutional players (the "Contenders") intentionally push price past established support/resistance levels to trigger retail stop-losses. This creates a "liquidity vacuum."

*   **The Strategy:** Do not trade the breakout. Trade the **Failure Swing.**
*   **The Data Point:** Look for a "Stop Run" (a candle wick that breaks a previous high/low by <0.5% but closes back inside the range).
*   **Execution:** If the price sweeps a liquidity pool and immediately rejects, the "Contender" has filled their position. Enter in the direction of the rejection with a stop loss just beyond the wick of the sweep candle.

### 2. Harvesting Data via "Volume Profile Imbalance"
To effectively harvest data from this sweep, you must filter for **Institutional Footprint Candles.**

*   **The Filter:** Use a 5-minute or 15-minute timeframe. Look for candles with:
    1.  **Volume > 2.5x the 20-period moving average.**
    2.  **A wick-to-body ratio of at least 3:1.**
*   **The Strategy:** This candle represents the "Contender" absorbing all available retail liquidity. 
*   **Data Extraction:** Map the **Point of Control (POC)** of that specific candle. In 2026, algorithmic re-tests of the POC are the highest-probability entry points for a trend reversal.

### 3. The "Contender Sweep" Algorithmic Setup
If you are coding a strategy or setting up a scanner for today’s market conditions, use this logic:

1.  **Identify the "Sweep Zone":** Define the previous day's high/low (PDH/PDL) or the Asian Session range.
2.  **Trigger:** Price must breach the zone by a specific ATR (Average True Range) threshold.
3.  **Confirmation:** The RSI (14) must show a **divergence** (e.g., price makes a higher high, RSI makes a lower high) at the exact moment of the sweep.
4.  **Exit:** Target the "Liquidity Void" on the opposite side of the range.

### 4. Current Market Application (June 2026 Context)
Given the current date (mid-2026), market volatility is likely elevated due to mid-year institutional rotation. 

*   **Strategy Tip:** Focus on **"Mid-Week Reversals."** Since today is Wednesday, June 25, 2026, we are in the prime window for a "Weekly Contender Sweep." 
*   **The Play:** If the market has trended consistently since Monday, look for a fake-out sweep of the Monday/Tuesday high today. The "Contender" is likely looking to trap breakout traders before initiating the Thursday/Friday trend.

### 5. How to Harvest the Data (Actionable Steps)
To turn this into a repeatable strategy, build a **Liquidity Heatmap**:

*   **Step A:** Aggregate the last 10 instances where price swept a previous session high/low.
*   **Step B:** Calculate the "Mean Reversion Distance"—how far did the price travel in the opposite direction after the sweep?
*   **Step C:** Set your Take Profit (TP) at 70% of that mean distance. 

**Warning:** The Contender Sweep is a "trap" strategy. It relies on the failure of the breakout. If the price sweeps a level and *fails to reject* (i.e., it closes outside the range with high volume), **do not counter-trade.** That indicates a shift in fundamental trend rather than a liquidity sweep.

***

*Disclaimer: This information is for educational purposes based on market theory. Market conditions in 2026 are subject to rapid algorithmic shifts. Always backtest your specific assets before deploying capital.*