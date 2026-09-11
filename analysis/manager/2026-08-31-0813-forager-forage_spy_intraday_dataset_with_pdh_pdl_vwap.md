<!-- gamma_manager (FREE) | role=forager lane=google_aistudio::gemini-flash-lite-latest elapsed=4.473s | action=forage_spy_intraday_dataset_with_pdh_pdl_vwap -->
<!-- reason: Overseer feedback flagged that backtest-config JSON actions hallucinate off-instrument placeholders. Real SPY intraday data with PDH/PDL + VWAP co-located in one file is the gating dependency for any credible NLWB / level-rejection / structure-shift variant — including the two pending-queue items demanding a level-rejection pullback that beats the structure-shift null. Free-model foragers can actually do this lookup (it's web/search work, not config fabrication). Varies verb from recent critic/strategist runs. -->

Based on a search of public market data sources, **no single static free download** (such as a Kaggle dataset or static mirror) spans January 2024 through August 2026 while pre-packaging session VWAP resets, rolling PDH/PDL, and 09:30–10:00 Opening Range boundaries. 

Instead, the optimal approach is to pull **raw 1-minute OHLCV data** from an API provider that offers a free tier (or a developer trial) and compute the required indicators programmatically. 

The best candidate source, retrieval method, and schema requirements are detailed below.

---

### Best Candidate Source: Polygon.io (Free Tier / Developer API)
* **Source URL:** `https://api.polygon.io/v2/aggs/ticker/SPY/range/1/minute/{from}/{to}`
* **Format:** JSON (easily parsed to CSV/Parquet locally)
* **Resolution:** 1-minute bars (RTH and Extended Hours)
* **License Terms:** Free tier permits personal, non-commercial use, local backtesting, and data storage for internal research. (Redistribution is prohibited).
* **Approx File Size:** ~150 MB to 200 MB uncompressed JSON for the full 2024-01-01 to 2026-08-31 window (~550 trading days $\times$ 390 bars/day).
* **Sample Schema (Raw API Output):**
  ```json
  {"v": 12500, "vw": 560.12, "o": 560.05, "c": 560.20, "h": 560.25, "l": 559.95, "t": 1725019800000, "n": 145}
  ```

---

### Exact Retrieval Command (`curl` / `wget`)
Polygon splits large date ranges into pagination requests or requires looping by month/year on the free tier (which limits requests to 5 per minute). Below is a Python-ready `curl` snippet for a single day's 1-minute bars to verify connectivity:

```bash
curl -X GET "https://api.polygon.io/v2/aggs/ticker/SPY/range/1/minute/2024-01-02/2024-01-02?adjusted=true&sort=asc&limit=50000&apiKey=YOUR_POLYGON_API_KEY" \
-H "Accept: application/json"
```

---

### Required Merge & Computation Step (For VWAP, PDH/PDL, & OR)
Because raw data does not come pre-baked with session-reset VWAP, rolling daily high/lows, or opening ranges, you must apply the following transformations in your local backtest environment (e.g., using `pandas` or `polars`):

1. **Session Partitioning:** Filter timestamps to Regular Trading Hours (RTH: 09:30 – 16:00 ET) and assign a `trade_date` group key.
2. **Prior-Day High/Low (PDH/PDL):** 
   * Calculate daily max($H$) and min($L$) per `trade_date`.
   * Shift the resulting series down by 1 row to align yesterday's high/low with today's intraday bars.
3. **Session VWAP Reset:** 
   * Compute Typical Price: $TP = \frac{\text{High} + \text{Low} + \text{Close}}{3}$
   * Compute Dollar Volume: $PV = TP \times \text{Volume}$
   * Group by `trade_date` and calculate cumulative sums: $\text{VWAP} = \frac{\sum PV}{\sum \text{Volume}}$, resetting every day at 09:30 ET.
4. **Opening Range (09:30 – 10:00 ET):**
   * Filter bars where time is $\ge 09:30$ and $< 10:00$.
   * Calculate the max high (`OR_High`) and min low (`OR_Low`) for that 30-minute window, then broadcast those values across all subsequent bars for that specific session.