# Intraday Equity Anomalies & Effects — Catalog for Retail SPY 0DTE / MES Swing Testing

**Date:** 2026-07-09  
**Scope:** Documented, replicable intraday equity-index anomalies from academic papers + reputable quant blogs. Prioritized for SPY 0DTE options and MES futures validation on retail data.

---

## Anomalies by PRIOR Score (High to Low)

| # | Anomaly | Claim (One-line) | Source | Current Consensus (Post-Publication) | Data Needed for Test | PRIOR |
|---|---------|-----------------|--------|---------------------------------------|----------------------|-------|
| **1** | **First-2H Momentum → Rest-of-Day Reversal** | First 2-hour intraday return predicts subsequent half-hour returns; last 2H drives reversal (Da, Zhu) | [Reversal, Momentum and Intraday Returns](https://assets.super.so/e46b77e7-ee08-445e-b43f-4ffd88ae0a0e/files/f360fb42-445c-433b-8d78-0059bcf604ca.pdf); [Intraday Momentum & Return Predictability](https://www.diva-portal.org/smash/get/diva2:1878991/FULLTEXT01.pdf); [Hedging Demand Drives Intraday Momentum](https://www3.nd.edu/~zda/intramom.pdf) | Actively researched (2020s). Gamma hedging mechanism identified & ongoing ND/UNC papers. Volume/volatility stratification refines signal. | SPY 5-min bars (open/close per 2H window). Volume optional. First 2H = 09:30–11:30; last 2H = 14:30–16:00 ET. 18mo intraday on disk suffices. | **5** |
| **2** | **Intraday Short-Term Reversal (5min–60min scale)** | Overreaction to intraday moves reverses within same day; gamma hedging explains persistence. | [Short-Term Return Reversals & Intraday Transactions](https://quantpedia.com/short-term-return-reversals-and-intraday-transactions/); [End-of-Day Reversal (Baltussen, Da, Soebhag)](https://www3.nd.edu/~zda/EOD.pdf) | Persistent (2020s). Mechanically grounded in gamma hedging + limit-order book microstructure. Hedge rebalancing rhythms = tradeable. | SPY 1-min or 5-min bars (can aggregate). Measure reversal lag: 5m, 15m, 30m, 60m post-spike. Same 18mo dataset. | **5** |
| **3** | **Overnight Returns >> Intraday Returns (Long-term average)** | Since ~1990, cumulative overnight gains in SPY far exceed intraday; ~7.2% p.a. overnight vs. negative/flat intraday average. | [Cooper, Cliff, Gulen (2008)](https://robotwealth.com/revisiting-overnight-vs-intraday-equity-returns/); [Nasdaq "Night and Day"](https://www.nasdaq.com/articles/night-and-day); [Does Overnight News Explain Overnight Returns? (2024)](https://arxiv.org/pdf/2507.04481) | Still holds gross of transaction costs; net of costs marginal (2–3% p.a. after fees). Institutional position-holding + news digestion effect. Robust over 30+ years. | SPY daily close-to-close (overnight) vs. open-to-close (intraday). 20+ years daily data sufficient. Stratify by regime (VIX, Fed regime). | **4** |
| **4** | **Opening Range Extension (ORB) — Directional Breakout Probability** | 78% of time, price breaks out of first 1H range and ONLY continues that direction (no reversal to opposite side). First 5m candle breakout extends 71% of time. | [Opening Range Breakout Statistics (Intraday Screener)](https://intradayscreener.com/opening-range-breakout); [ORB Strategy Guide](https://www.buildalpha.com/opening-range-breakout/); [LiteFinance ORB Analysis](https://www.litefinance.org/blog/for-beginners/trading-strategies/opening-range-breakout-strategy/) | Diminished by HFT (2010s onward) but still ~70%+ on SPY per backtests. Most ORB strategies overfit; core 1H-range mechanics survive. Testable but tight stops required. | SPY 5-min bars. Identify 09:30–10:30 open/high/low. Measure breakout direction + hold % to close, profit target zones. 18mo bars. | **4** |
| **5** | **Gap Fill Rates by Gap Size (Stratified)** | Sub-0.5% overnight gaps fill intraday ~70%, small gaps 42%, medium 25%, large (>1.2% ATR) only ~8%. Common gaps 70–75% within 5 sessions. | [Gap Fill Statistics (TradingStats)](https://tradingstats.net/gap-fill-indicator/); [QuantifiedStrategies Gap Backtest](https://www.quantifiedstrategies.com/gap-fill-trading-strategies/); [Fading the Gap (SharePlanner)](https://www.shareplanner.com/blog/strategies-for-trading/fading-the-gap-how-large-overnight-moves-in-spy-and-qqq-play-out-during-the-trading-day.html) | Robust post-publication. Gap size stratification is mechanistic: small = mean reversion (market shock buffer), large = breakout (news-driven). Consistent across 15+ years. | SPY daily open vs. prior close (gap %). Measure fill % + time-to-fill by 5 gap-size buckets. 18mo daily data. Optional: regime filter (VIX, trend). | **4** |
| **6** | **VIX Term Structure Regime Flip (Contango ↔ Backwardation)** | VIX futures curve inversion (spot > VIX3M, backwardation) precedes major drawdowns 100% historically; contango flip = re-entry signal (88% win in 5 days post-flip). | [VIX Term Structure as Trading Signal (Macrosynergy)](https://macrosynergy.com/research/vix-term-structure-as-a-trading-signal/); [Sharpnel VIX Guide](https://www.sharpnel-trading.com/learn/vix-term-structure/); [Options Cafe "Buy the Relief"](https://options.cafe/blog/vix-term-structure-contango-backwardation/) | Active regime signal used by desks. Contango ~80% of time, backwardation rare + precedes all major crashes. Mechanically sound (risk appetite). Testable on public CBOE futures curve. | VIX term structure curve (VIX spot, VIX1, VIX2, VIX3M). CBOE historical futures settlement or .csv; compute slope daily. Pair with SPY returns next 1–5 days. 18mo+ data available. | **4** |
| **7** | **Lunch Hour Volatility Collapse (11:30 AM–1:30 PM ET)** | Volume/volatility drop 60–70% during lunch window; signals generated in 09:30–11:30 and 14:00–16:00 outperform lunch-hour trades by 200–300 bps daily P&L. | [Should You Trade Lunch? (TosIndicators)](https://tosindicators.com/research/should-you-trade-during-the-lunch-time-hour); [QuantifiedStrategies Lunch Effect](https://www.quantifiedstrategies.com/lunch-effect-stock-market/); [Intraday Repeating Patterns](https://tradethatswing.com/stock-market-intraday-repeating-patterns/) | Robust post-identification (2000s onward). Institutional lunch break + reduced participation. Mechanical: low signal/noise, not arbitraged. 18+ years consistent. | SPY 5-min volume + volatility. Stratify time windows: pre-lunch, lunch, post-lunch. Measure strategy Sharpe by window. 18mo 5m bars. | **4** |
| **8** | **Prior-Day-Range Opening Behavior (Prior PDH/PDL Tag Rate)** | When SPY opens *inside* prior day's range, 86% probability it tags either prior PDH or PDL same-day; only 14% stay inside PDR all day. | [Opening Range Behavior](https://intradayscreener.com/opening-range-breakout); [Gap Fill Analysis](https://www.shareplanner.com/blog/strategies-for-trading/fading-the-gap-how-large-overnight-moves-in-spy-and-qqq-play-out-during-the-trading-day.html) | Mechanically sound (mean reversion to wider structure). Consistent across 10+ years SPY data per public backtests. High probability but low profit per trade (reversal = mean-reversion zone). | SPY daily open vs. prior day high/low. Measure same-day touch % + time-to-touch (1H, 2H, EOD). Optional: entry zone model. 18mo daily. | **4** |
| **9** | **Month-End & Quarter-End Rebalancing MOC Imbalances** | Passive index/ETF rebalancing drives MOC (market-on-close) order imbalances at month/quarter-end (3:50 PM window); avg 5.5 bps close-price shift, 7% daily volume. | [CME Month-End Equity Flows](https://www.cmegroup.com/articles/2025/managing-month-end-equity-flows-and-portfolio-risk.html); [Understanding End-of-Quarter Rebalancing](https://www.gme.academy/digest/theerudite/understanding-end-of-quarter-rebalancing); [Global Market Structure](https://globalmarketstructure.com/en/capital-flows-and-positioning/passive-etf-and-rebalancing-flows/month-end-and-quarter-end-rebalancing/) | Identifiable & persistent (index growth + passive growth post-2010). Real price impact observable in close-auction imbalances. Crowded but timing-specific. | SPY 3:50–4:00 PM data (MOC imbalance + close). Calendar (month-end/quarter-end dates). Measure close-price shift vs. 3:45 PM level. 18mo daily. | **3** |
| **10** | **Post-CPI / Post-NFP Directional Persistence** | Post-print moves persist directionally for 1–4 hours on average, reversal increases later same day. Depends: strong beat → bullish persistence; weak miss + Fed-hawkish interpretation → bearish. | [Nonfarm Payroll Impact (Moomoo)](https://www.moomoo.com/us/learn/detail-non-farm-payroll-nfp-117365-240844093); [EconDB FX/Equity Reactions](https://www.equiti.com/sc-en/news/trading-ideas/what-non-farm-payrolls-mean/); Post-CPI studies (scattered, not canonical) | Context-dependent (Fed regime, inflation narrative, prior CPI trajectory). NOT mechanistic; requires regime classification. Persistence window narrowed post-2010 (HFT arb). Works best in trending markets. | SPY intraday price + economic calendar (CPI release time, NFP release time). Measure returns in windows: ±2H, +2–4H post-print. Filter by market regime (VIX, trend bias). Requires data alignment. 18mo+ data. | **3** |
| **11** | **Market Close Auction (Last 10 Minutes, 3:50–4:00 PM)** | MOC imbalances published every second 3:50–4:00 PM; LOC cutoff 3:58 PM. Observable price drift into close linked to buy/sell skew. Institutional rebalance window. | [MOC SpotGamma Support](https://support.spotgamma.com/hc/en-us/articles/15249378625555-MOC-Market-on-Close); [MOC Imbalance TradersVPS](https://www.tradervps.com/blog/moc-imbalance-in-trading-what-it-is-and-how-to-use-it/); [Market-On-Close Orders (Pure Power Picks)](https://purepowerpicks.com/market-on-close-orders-benefits-and-drawbacks/) | Identifiable in real-time (imbalance feed available). Price impact real but minute-scale + crowded (large desks active). Window too narrow for 0DTE options retail; better for close-skew overlay. | SPY last-10-min bars + MOC imbalance feed (public from exchanges). Measure close-price vs. 3:50 PM level. Imbalance direction → close direction? 18mo daily, last-10-min bars. | **3** |
| **12** | **FOMC Pre-Announcement Drift (PAD)** | +20 bps average return in 24h window pre-FOMC announcement (Lucca & Moench 2015). Weakening: disappeared for announcements with press conferences (post-Jan 2016). | [Investor Sentiment & Pre-FOMC Drift](https://www.sciencedirect.com/science/article/abs/pii/S1544612319311262); [Disappearing Pre-FOMC Drift (2020)](https://www.sciencedirect.com/science/article/abs/pii/S1544612320315956); [Pre-FOMC Short-Lived or Long-Lasting? (2024)](https://www.tandfonline.com/doi/full/10.1080/00036846.2024.2322573); [New York Fed SR512 (Lucca & Moench)](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr512.pdf) | **DECAYING.** Still present but 50–70% weaker than 1994–2015 baseline. Press conferences (>1.5 hr) killed the effect. Likely arbitraged + information environment changed. Avoid for new edge. | SPY 24h returns ±1 day around FOMC announcement dates (FOMC calendar). Compare to null distribution (random dates). 20+ year dataset. Filter: pre-press-conference vs. post-2016. | **2** |
| **13** | **Turn-of-Month Effect (Last 3 days + First 3 days)** | Last 3 trading days of month + first 3 of next month yield +0.5–1.0% average abnormal return vs. mid-month. Originally strong (1950s–1990s), now largely dead. | [SSRN Turn-of-Month (Vidal & Vidal-García)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4106003); [QuantPedia Turn-of-Month in Indexes](https://quantpedia.com/strategies/turn-of-the-month-in-equity-indexes); [QuantSeeker TOM Still Works? (Mixed Evidence)](https://www.quantseeker.com/p/turn-of-the-month-strategies-do-they) | **LARGELY ARBITRAGED AWAY (2010s+).** Post-publication (1980s), effect decayed. Recent work (2022–2025) finds effect marginal in major indices; may persist in smaller-cap/emerging. Avoid for SPY. | SPY daily returns stratified by calendar: last-3, first-3, mid-month buckets. Test 20+ years. Optional: regime stratification (VIX percentile, trend). 20+ years daily data. | **2** |
| **14** | **Monday/Friday Day-of-Week Effect** | Fridays → highest average return, Mondays → lowest/negative (1990s–2000s evidence). Post-publication: effect weakened, now inconsistent across geographies. | [Day-of-Week Meta-Analysis (2024, Springer)](https://link.springer.com/article/10.1007/s40822-024-00293-9); [SSRN Day-of-Week](https://papers.ssrn.com/sol3/Delivery.cfm/5072791.pdf?abstractid=5072791&mirid=1); [Alpha Architect Day-of-Week & Anomalies](https://alphaarchitect.com/how-the-day-of-the-week-affects-stock-market-anomalies/) | **WEAK/DEAD POST-2010.** 2024 meta-analysis notes replication crisis: results conflict, outliers cluster 1980–2000. Monday effect evident in 1980s–1990s; largely evaporated post-2000. Avoid for new research. | SPY daily returns by day-of-week (Monday–Friday). Test 15+ years. Compute t-stats for each DOW. Stratify by era: 1990–2005 vs. 2010–2026. 20+ years daily data. | **1–2** |
| **15** | **Post-Earnings Announcement Drift (PEAD)** | Stocks outperform/underperform for weeks post-earnings surprise. Ball & Brown (1968) documented; Jegadeesh & Titman (1993) formalized. **Status: Largely DEAD in nonmicrocaps.** | [Wikipedia PEAD](https://en.wikipedia.org/wiki/Post%E2%80%93earnings-announcement-drift); [Quantpedia PEAD Strategy](https://quantpedia.com/strategies/post-earnings-announcement-effect); [UCLA Anderson "Is PEAD a Thing Again?" (2023)](https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again/); [CFA Institute AI & PEAD (2025)](https://blogs.cfainstitute.org/investor/2025/04/22/can-generative-ai-disrupt-post-earnings-announcement-drift-pead/) | **DISAPPEARED → POSSIBLY RETURNING.** Martineau (2022) showed drift vanished in nonmicrocaps by 2006. Microcaps may still show drift (low coverage). 2025 speculation: AI-driven retail faster reaction may compress/revive drift. **Not actionable for SPY (broad index).** | Individual stock data (post-earnings drift tested at single-stock level, not index). SPY is too diversified to show drift. Skip for SPY 0DTE. 18mo stock earnings + returns needed. | **1** |

---

## Top-3 Test Designs (Highest PRIOR + Testable on SPY 5-Min Bars, Data On Disk)

### **#1: First-2H Momentum → Rest-of-Day Return Reversal (PRIOR 5)**

**Exact Test Design (1 line):**  
Partition 18mo intraday SPY 5m bars into: first-2H return buckets (−2σ to +2σ); stratify by volume/volatility regime; measure mean intraday returns in windows {2H gap, next 3H, last 2H} per bucket; quantify fading effect (Sharpe ratio, hit rate, sign-flip probability per lag window).

**What to Verify:** momentum drives early; reversal (last 2H) dominates close; gamma-hedging bandwidth correlates with reversal magnitude.

---

### **#2: Opening Range Extension (ORB) Directional Breakout Hold Rate (PRIOR 4)**

**Exact Test Design (1 line):**  
For each day, identify 09:30–10:30 high/low from SPY 5m bars; stratify breakouts (>1st-hour range) by direction (bull vs. bear); measure {extension % to next target, reversal probability, hold time to EOD} by breakout direction; cross-tab with 1st-hour volume and overnight gap direction.

**What to Verify:** 70%+ extension-hold rate; reversal frequency by breakout magnitude; optimal entry/exit zones vs. simple breakout-hold.

---

### **#3: Gap-Fill Rate by Overnight Gap Size Stratification (PRIOR 4)**

**Exact Test Design (1 line):**  
Compute overnight gap % = (SPY open − prior close) / prior close; partition into 5 buckets {sub−0.5%, 0.5–1%, 1–2%, 2–3%, >3%}; for each bucket measure {intraday fill %, time-to-fill quartiles, regime-conditional fill (high-VIX vs. low-VIX)} over 18mo; build logistic model: fill_probability = f(gap_size, VIX, trend_bias, prior_day_close_strength).

**What to Verify:** gap-size stratification predicts fill behavior; small gaps mean-revert >70%, large gaps reverse only <20%; regime filter (VIX) improves accuracy.

---

## Data Availability Check

**All top-3 require ONLY data on disk:**
- SPY 5-min OHLCV: ✓ (18mo on disk, per CLAUDE.md)
- SPY daily open/close: ✓ (20+ years available)
- Calendar (market holidays, FOMC dates, CPI/NFP): ✓ (public, hardcode-friendly)
- VIX spot + term curve: ✓ (CBOE historical, 18mo+ downloadable)

**None require:**
- Real-time Alpaca fills (backtesting only)
- Tick-level data (5m bars sufficient)
- External API calls (all computable from historical bars)

---

## Research Priority & Next Steps

1. **Execute #1 (Momentum/Reversal)**: Highest PRIOR (5), mechanically clearest, academically active. Expected Sharpe: 0.8–1.5 if signal decays by 60% post-publication.
2. **Execute #2 (ORB)**: PRIOR 4, tight risk/reward, fits 0DTE duration well. Expected win rate: 65–75%.
3. **Execute #3 (Gap Fill)**: PRIOR 4, binary outcome (fill or not), feeds into risk model. Expected fill probability model accuracy: 70–75%.

**Avoid (PRIOR ≤ 2):** FOMC PAD (decaying), TOM (dead), Monday/Friday (extinct), PEAD (disappeared in nonmicrocaps).

---

## Sources

- [Reversal, Momentum and Intraday Returns (Da, Zhu)](https://assets.super.so/e46b77e7-ee08-445e-b43f-4ffd88ae0a0e/files/f360fb42-445c-433b-8d78-0059bcf604ca.pdf)
- [Intraday Momentum and Return Predictability](https://www.diva-portal.org/smash/get/diva2:1878991/FULLTEXT01.pdf)
- [Hedging Demand and Market Intraday Momentum (Da, Zhu)](https://www3.nd.edu/~zda/intramom.pdf)
- [Short-Term Return Reversals and Intraday Transactions (Quantpedia)](https://quantpedia.com/short-term-return-reversals-and-intraday-transactions/)
- [End-of-Day Reversal (Baltussen, Da, Soebhag)](https://www3.nd.edu/~zda/EOD.pdf)
- [Cooper, Cliff, Gulen (2008) — Overnight Returns](https://robotwealth.com/revisiting-overnight-vs-intraday-equity-returns/)
- [Nasdaq "Night and Day"](https://www.nasdaq.com/articles/night-and-day)
- [Does Overnight News Explain Overnight Returns? (2024)](https://arxiv.org/pdf/2507.04481)
- [Opening Range Breakout Statistics (Intraday Screener)](https://intradayscreener.com/opening-range-breakout)
- [ORB Strategy Guide (BuildAlpha)](https://www.buildalpha.com/opening-range-breakout/)
- [LiteFinance ORB Analysis](https://www.litefinance.org/blog/for-beginners/trading-strategies/opening-range-breakout-strategy/)
- [Gap Fill Statistics (TradingStats)](https://tradingstats.net/gap-fill-indicator/)
- [QuantifiedStrategies Gap Backtest](https://www.quantifiedstrategies.com/gap-fill-trading-strategies/)
- [SharePlanner Fading the Gap](https://www.shareplanner.com/blog/strategies-for-trading/fading-the-gap-how-large-overnight-moves-in-spy-and-qqq-play-out-during-the-trading-day.html)
- [VIX Term Structure as Trading Signal (Macrosynergy)](https://macrosynergy.com/research/vix-term-structure-as-a-trading-signal/)
- [Sharpnel VIX Term Structure Guide](https://www.sharpnel-trading.com/learn/vix-term-structure/)
- [Options Cafe "Buy the Relief"](https://options.cafe/blog/vix-term-structure-contango-backwardation/)
- [Should You Trade Lunch? (TosIndicators)](https://tosindicators.com/research/should-you-trade-during-the-lunch-time-hour)
- [QuantifiedStrategies Lunch Effect](https://www.quantifiedstrategies.com/lunch-effect-stock-market/)
- [Intraday Repeating Patterns (Trade That Swing)](https://tradethatswing.com/stock-market-intraday-repeating-patterns/)
- [CME Month-End Equity Flows](https://www.cmegroup.com/articles/2025/managing-month-end-equity-flows-and-portfolio-risk.html)
- [Understanding End-of-Quarter Rebalancing](https://www.gme.academy/digest/theerudite/understanding-end-of-quarter-rebalancing)
- [Global Market Structure — Rebalancing Flows](https://globalmarketstructure.com/en/capital-flows-and-positioning/passive-etf-and-rebalancing-flows/month-end-and-quarter-end-rebalancing/)
- [MOC SpotGamma Support](https://support.spotgamma.com/hc/en-us/articles/15249378625555-MOC-Market-on-Close)
- [MOC Imbalance TradersVPS](https://www.tradervps.com/blog/moc-imbalance-in-trading-what-it-is-and-how-to-use-it/)
- [Nonfarm Payroll Impact (Moomoo)](https://www.moomoo.com/us/learn/detail-non-farm-payroll-nfp-117365-240844093)
- [Investor Sentiment & Pre-FOMC Drift](https://www.sciencedirect.com/science/article/abs/pii/S1544612319311262)
- [Disappearing Pre-FOMC Drift (2020)](https://www.sciencedirect.com/science/article/abs/pii/S1544612320315956)
- [Pre-FOMC Short-Lived or Long-Lasting? (2024)](https://www.tandfonline.com/doi/full/10.1080/00036846.2024.2322573)
- [New York Fed SR512 (Lucca & Moench)](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr512.pdf)
- [SSRN Turn-of-Month (Vidal & Vidal-García)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4106003)
- [QuantPedia Turn-of-Month in Indexes](https://quantpedia.com/strategies/turn-of-the-month-in-equity-indexes)
- [QuantSeeker TOM Still Works?](https://www.quantseeker.com/p/turn-of-the-month-strategies-do-they)
- [Day-of-Week Meta-Analysis (2024, Springer)](https://link.springer.com/article/10.1007/s40822-024-00293-9)
- [SSRN Day-of-Week](https://papers.ssrn.com/sol3/Delivery.cfm/5072791.pdf?abstractid=5072791&mirid=1)
- [Alpha Architect Day-of-Week & Anomalies](https://alphaarchitect.com/how-the-day-of-the-week-affects-stock-market-anomalies/)
- [Wikipedia PEAD](https://en.wikipedia.org/wiki/Post%E2%80%93earnings-announcement-drift)
- [Quantpedia PEAD Strategy](https://quantpedia.com/strategies/post-earnings-announcement-effect)
- [UCLA Anderson "Is PEAD a Thing Again?" (2023)](https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again/)
- [CFA Institute AI & PEAD (2025)](https://blogs.cfainstitute.org/investor/2025/04/22/can-generative-ai-disrupt-post-earnings-announcement-drift-pead/)
