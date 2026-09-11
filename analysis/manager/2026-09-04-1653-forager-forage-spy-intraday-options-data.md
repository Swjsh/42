<!-- gamma_manager (FREE) | role=forager lane=google_aistudio::gemini-flash-lite-latest elapsed=2.113s | action=forage-spy-intraday-options-data -->
<!-- reason: Recent candidates (vol-contract-breakout, OR vwap ribbon fade, vol-expansion continuation) all want richer intraday IV/chain data than we currently cache. Free data forage is bounded, cheap, and unblocks several pending candidates. Overseer flagged that generic EURUSD backtest-config JSON is hallucinated garbage -- this is a concrete web harvest of a specific known source, not a config write. Differs from last cycle's critic-on-exit-shape action. -->

CBOE blocks direct programmatic scraping of its historical data portal via standard tools like `wget` (returning 403 Forbidden/Cloudflare challenges). However, the public pricing structure and schema of CBOE’s historical intraday options data are well-documented:

1. **Free vs. Paid:** CBOE provides historical *daily summary* files for free, but **all historical intraday options chain data (minute-by-minute/tick data) is strictly paid**, requiring a commercial data subscription via DataShop. 
2. **Naming/Date Range:** N/A for free intraday data, as none exists. Paid intraday files use conventions like `YYYYMMDD_SPY_options.csv`.
3. **Inclusions:** Free CBOE datasets contain end-of-day (EOD) summaries or underlying OHLCV, but *not* free intraday options chains.
4. **Concrete URL:** None, due to CBOE's paywall. 

**Free Alternative:** 
To extend a SPY 0DTE intraday backtest dataset for free, use the **ThetaData Terminal Free Tier**. ThetaData provides historical intraday options trades and quotes for SPY via a local client API without upfront costs. Alternatively, for completely flat-file bulk downloads, researchers often pivot to end-of-day historical chains from free academic repositories or construct historical intraday bars using free underlying minute trades combined with third-party implied volatility models.