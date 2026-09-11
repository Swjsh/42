# Options-Market-Structure Metrics Catalog — Free Intraday Signals for SPY 0DTE

**Date:** 2026-07-09 | **Scope:** FREE data sources for 0DTE SPY directional trading | **Testability:** Backtest-battery ranking

---

## Ranked Metrics Table

| Rank | Metric | Signal Thesis (1-line) | Data Path / Source | Testability | Skeptic's Note |
|------|--------|------------------------|-------------------|-------------|-----------------|
| **1** | **Expected Move / Straddle Pricing** | ATM straddle cost predicts 1-σ range; range compression into close pins intraday targets. | **ZERO new data:** Computable from Alpaca option chain (ATM calls/puts real-time). Formula: `(call_price + put_price) × 0.85 = 1-σ EM`. | **HIGH** — backtest-ready; validates range-bound vs breakout regimes; sensitivity to theta-decay cadence. | Straddle overstates true EM by ~15% due to embedded premium; 0DTE EM shrinks nonlinearly (halves every 2h). Weighting OTM options (strangle method) tighter but harder to compute live. |
| **2** | **Put/Call Ratio (Volume/OI)** | Ratio < 0.7 = bullish sentiment; > 1.0 = bearish. Intraday swings flag exhaustion (overshoot risk). | **FREE, delayed:** Barchart.com (1-day download limit), Fintel.io (snapshot), OptionCharts (real-time web). CBOE histdata available end-of-day. | **MEDIUM-HIGH** — backward-looking (lags fills by 5-15m); works as regime filter, not trigger. | Put-call is market sentiment, not causation. High put/call doesn't guarantee downside; dealer hedging inverts naive read. Intraday lag (5-15m) kills precision; end-of-day rolls distort ratios artificially. |
| **3** | **Charm/Vanna Flow Windows** | Vanna peaks at open + macro events (IV flows). Charm dominates late-session (14:30-16:00 ET): dealers buy dips/sell rallies into close. | **Documentation-heavy, data sparse:** SpotGamma (paid), published research (FatTail, MenthorQ, FlashAlpha). No free real-time flow API; inference only from Greeks on Alpaca chain. | **MEDIUM** — strong conceptual foundation; hard to backtest without tick-by-tick Greeks. Simulation proxy: compute aggregate vanna/charm across all strikes hourly from Alpaca data. | Charm/vanna *flows* are inferred from gamma/vega/delta changes; no direct market read. "The 14:30-16:00 flow window" is folklore (true in placid days; breaks during news/shock). Dealer hedging is emergent behavior, not mechanical. |
| **4** | **Dealer Gamma Exposure (GEX)** | Positive GEX = dealers long gamma → stabilize (sell rallies, buy dips). Negative GEX = dealers short gamma → amplify (chase moves). Gamma flips are reversal signals. | **DELAYED, computable:** CBOE posts OI end-of-day (free). GEX formula: `Σ(gamma × OI × strike²) for calls − puts`. Barchart/SpotGamma free tiers show GEX snapshots; no live intraday. | **MEDIUM** — OI is snapshot (1x/day 4:15 PM ET); intraday GEX is inference only. Testable: daily grids or open-to-close regime. | GEX from backward-looking OI; actual dealer deltas move faster than reported OI. Gamma flip lag = 2-4h behind real dealer action. Naive gamma model ignores skew, put spreads, and index arbitrage. Low tradeable utility without tick-level data. |
| **5** | **VIX1D (1-Day Volatility Index)** | Measures 1-calendar-day SPX realized+implied vol. Spikes ahead of 0DTE selloffs; gaps fill intraday. | **FREE, daily:** Yahoo Finance (^VIX1D history), FRED (St. Louis Fed), CBOE Dashboard, MacroMicro. No true intraday—only opens/closes daily. Yfinance + Alpaca vol proxy workable. | **MEDIUM-LOW** — VIX1D = backward-looking 1-day vol (published end-of-day); too macro for 0DTE intraday triggers. Correlation to SPY 0DTE EM is ~0.6 (not tight). Better as regime confirmation. | VIX1D is SPX-only; SPY has different dealer dynamics (higher retail, wider spreads). Published once/day after close; intraday VIX1D is interpolation fantasy. Vol realized during a day ≠ vol implied at open. |
| **6** | **0DTE Share-of-Volume Stats** | 0DTE > 60% of total SPX volume = retail-dominated, wider spreads, pinning risk. < 40% = normal dealer flow. | **PUBLISHED QUARTERLY:** CBOE Insights (delayed), Traders Magazine, Option Clearing Corp reports. 2026 data: 62% SPX 0DTE in Feb/Mar; no daily refresh. | **LOW** — backward-looking regime classifier only. Testable: stratify backtest by 0DTE vol-share cohort (e.g., high vol = pinning edge larger). | Aggregate stat masks intraday flow shifts; a 60% share at 10am ≠ 60% at 3pm. SPY 0DTE share data sparse; extrapolating from SPX unreliable (SPY has more retail). |

---

## Top 3 Recommendation

1. **Expected Move / Straddle Pricing** — Computable in real-time from Alpaca chain (ZERO new data). Directly forecasts 1-σ intraday range; theta-decay cadence testable. Core lever for pinning/range-scalp setups.

2. **Put/Call Ratio (Volume)** — Free via Barchart intraday; lags 5-15m but works as market-sentiment regime filter. Flag extremes (< 0.5 / > 1.5) as exhaustion, not entry trigger.

3. **Charm/Vanna Flow Windows** — Documented (14:30-16:00 charm dominance verified); compute aggregate vanna/charm hourly from Alpaca Greeks. Testable as late-session breakout suppressor or pinning accelerant.

---

## Zero-New-Data Metrics (Computable from Project Assets)

**ZERO new data required (build from existing Alpaca chain + banked CBOE OI):**
- **Expected Move / Straddle:** ATM call + put prices → straddle cost → 1-σ range. Real-time every tick.
- **Dealer Gamma Exposure (GEX):** End-of-day CBOE OI (free download) + gamma formula. Once/day 4:15 PM ET.
- **Charm/Vanna Flows:** Aggregate gamma/vega/delta across all strikes hourly from Alpaca chain. Proxy for dealer flow direction.

**Require external free refresh:**
- **VIX1D:** Yfinance / FRED daily (open API, no auth).
- **Put/Call Ratio:** Barchart / OptionCharts snapshot (web scrape or API, 5-15m lag).
- **0DTE Share-of-Volume:** CBOE Insights (quarterly, historical only).

---

## Integration Roadmap

**Phase 1 (This Week):** Wire Expected Move (straddle formula) into engine as range-bound regime flag; backtest pinning scalp vs breakout splits.

**Phase 2:** Add Put/Call ratio thresholds (< 0.6 = skip bearish, > 1.2 = skip bullish) as kill-gate filter; validate lag tolerance.

**Phase 3:** Compute vanna/charm hourly from Alpaca Greeks; test late-day (14:30-16:00 ET) flow window as edge-multiplier or exit-trigger.

**Defer:** VIX1D (macro regime, not tactical) and 0DTE vol-share stats (quarterly, coarse).

---

**Sources:**
- [CBOE Volatility Index Dashboard (VIX1D)](https://www.cboe.com/us/indices/dashboard/vix1d/)
- [Yahoo Finance VIX1D History](https://finance.yahoo.com/quote/%5EVIX1D/history/)
- [SpotGamma GEX Explained](https://spotgamma.com/gamma-exposure-gex/)
- [CBOE 0DTE Market Impact Analysis](https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options/)
- [Barchart SPY Put/Call Ratio](https://www.barchart.com/etfs-funds/quotes/SPY/put-call-ratios)
- [Volatility Box: Expected Move Calculator](https://volatilitybox.com/research/expected-move-options/)
- [MenthorQ: Straddle Price to Expected Move](https://menthorq.com/guide/from-straddle-price-to-expected-move/)
- [SpotGamma: Vanna & Charm Explained](https://spotgamma.com/vanna-and-charm-explained/)
- [Fintel: SPY Put/Call Ratio](https://fintel.io/sopt/us/spy)
